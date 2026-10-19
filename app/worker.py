"""Read-only AI diagnostics worker. Never executes Zabbix mutations."""
import asyncio
import base64
import hashlib
import hmac
import time
import json
import logging
import os
import re
import httpx
from openai import AsyncOpenAI
from redis import Redis
from rq import Worker, Queue
from .main import read_setting

log = logging.getLogger(__name__)
BASE_PROMPT = ("你是资深 Zabbix 运维分析师。只允许只读查询。严禁修改系统。"
               "只输出JSON对象，字段host_groups,cause,action,analysis,human_required。"
               "故障原因100字内，建议150字内，分析500字内。无证据时不要猜测。")
COLORS = {"0":"grey","1":"blue","2":"yellow","3":"orange","4":"red","5":"carmine"}
LEVELS = {"0":"未分类","1":"信息","2":"警告","3":"一般严重","4":"严重","5":"灾难"}

def feishu_sign(timestamp: str, secret: str) -> str:
    key = (timestamp + "\n" + secret).encode("utf-8")
    return base64.b64encode(hmac.new(key, digestmod=hashlib.sha256).digest()).decode()

def alert_instructions(custom: str) -> str:
    return BASE_PROMPT + ("\n补充要求：" + custom if custom else "")

def cfg(key):
    return read_setting(key)

async def analyze(event):
    key = cfg("openai_api_key")
    model = cfg("openai_model")
    url = cfg("openai_base_url")
    if not key or not model or not url:
        raise RuntimeError("AI model configuration missing")
    # Tool calls are integrated in a separate MCP adapter; never assert MCP
    # evidence unless it has been fetched by that adapter.
    from .mcp_client import gather_evidence
    evidence = await gather_evidence(event)
    prompt = alert_instructions(cfg("ai_alert_prompt"))
    async with AsyncOpenAI(api_key=key, base_url=url, timeout=120) as client:
        result = await client.responses.create(model=model, instructions=prompt,
                        input=json.dumps({"event":event,"mcp_evidence":evidence},ensure_ascii=False))
    raw = result.output_text.strip()
    try:
        data = json.loads(re.sub(r"^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$", "", raw))
        if not isinstance(data, dict):
            raise ValueError("not object")
    except (ValueError, TypeError):
        data = {"cause": "分析结果需要人工复核", "action": "请检查告警相关指标及服务日志",
                "analysis": raw[:500], "human_required": True, "host_groups": "未查到"}
    return data

def safe(value,n):
    return str(value or "未提供").replace("\n"," ")[:n]

def make_card(event, info):
    sev = str(event.get("severity","0"))
    human = info.get("human_required", True) is not False
    content = (f'**主机名称：** {safe(event.get("host_name"),80)}\n'
               f'**主机 IP：** {safe(event.get("host_ip"),50)}\n'
               f'**所属分组：** {safe(info.get("host_groups"),140)}\n'
               f'**事件：** {safe(event.get("event_name"),200)}\n'
               f'**事件 ID：** {safe(event.get("event_id"),40)}')
    return {"config":{"wide_screen_mode":True},
      "header":{"title":{"tag":"plain_text","content":LEVELS.get(sev,"未知")+"｜"+("需人工核验" if human else "AI分析完成")},
                "template":COLORS.get(sev,"grey")},
      "elements":[{"tag":"div","text":{"tag":"lark_md","content":content}},
                  {"tag":"hr"},
                  *[{"tag":"div","text":{"tag":"lark_md","content":"**"+title+"**\n"+safe(info.get(key),maximum)}}
                    for title,key,maximum in [("故障原因","cause",100),("处理建议","action",150),("AI 分析","analysis",500)]]]}
    
async def notify(card):
    if cfg("feishu_enabled").lower() != "true":
        log.warning("Feishu alert sending disabled")
        return
    mode = cfg("feishu_alert_mode") or "app"
    if mode == "app":
        from .feishu_client import get_token, request, ROOT
        ids = cfg("feishu_alert_chat_ids") or cfg("allowed_chat_ids")
        chats = list(dict.fromkeys(x.strip() for x in ids.split(",") if x.strip()))
        if not chats:
            raise RuntimeError("飞书企业应用告警群未配置：feishu_alert_chat_ids")
        errors = []
        async with httpx.AsyncClient(timeout=30) as client:
            token = await get_token(client)
            for chat_id in chats:
                try:
                    await request(client, "POST", ROOT + "/im/v1/messages", token,
                        params={"receive_id_type":"chat_id"},
                        json={"receive_id":chat_id, "msg_type":"interactive",
                              "content":json.dumps(card,ensure_ascii=False)})
                except Exception as exc:
                    log.error("FEISHU_APP_ALERT_FAILED chat_id=%s error=%s",
                              chat_id[:5],type(exc).__name__)
                    errors.append(chat_id[:5])
        if errors:
            raise RuntimeError("飞书企业应用部分群发送失败，数量：" + str(len(errors)))
        return
    if mode != "webhook":
        raise RuntimeError("不支持的飞书告警发送方式")
    webhook = cfg("feishu_webhook_url")
    if not webhook:
        raise RuntimeError("飞书 Webhook 未配置")
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"msg_type":"interactive","card":card}
        sign_secret = cfg("feishu_sign_secret")
        if sign_secret:
            timestamp = str(int(time.time()))
            payload.update({"timestamp":timestamp, "sign":feishu_sign(timestamp, sign_secret)})
        for attempt in range(3):
            try:
                response = await client.post(webhook, json=payload)
                response.raise_for_status()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                retryable = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code >= 500
                )
                if not retryable or attempt == 2:
                    raise
                await asyncio.sleep((1, 3)[attempt])
                continue
            try:
                data = response.json()
            except ValueError as exc:
                snippet = response.text[:200]
                # Never log secret-bearing payloads or HTML returned by unknown proxies.
                log.error("FEISHU_INVALID_JSON status=%s body_length=%s", response.status_code, len(snippet))
                raise RuntimeError("飞书返回非 JSON 响应（前 200 字符已省略以保护敏感信息）") from exc
            if data.get("code", data.get("StatusCode", 0)) != 0:
                raise RuntimeError("Feishu rejected card: code=" + str(data.get("code", data.get("StatusCode"))))
            return

async def handle_alert(event):
    ai_failed = False
    try:
        info = await analyze(event)
    except Exception as exc:
        ai_failed = True
        log.exception("ALERT_ANALYZE_FAILED event_id=%s", event.get("event_id"))
        info = {"cause":"AI 分析失败，请人工处理", "action":"请直接查看 Zabbix 告警详情",
                "analysis":"AI 服务异常：" + type(exc).__name__,
                "human_required":True, "host_groups":"未查到"}
    await notify(make_card(event, info))
    return {"event_id":event["event_id"], "diagnosed":not ai_failed, "ai_failed":ai_failed}

def process_alert(event):
    return asyncio.run(handle_alert(event))

if __name__ == "__main__":
    redis = Redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"))
    Worker([Queue("ai-alerts", connection=redis)], connection=redis).work()
