"""Read-only AI diagnostics worker. Never executes Zabbix mutations."""
import asyncio
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
    """Send alert cards solely through the configured Feishu enterprise app."""
    if cfg("feishu_enabled").lower() != "true":
        log.warning("FEISHU_APP_ALERT_DISABLED")
        return
    from .feishu_client import get_token, request, ROOT
    ids = cfg("feishu_alert_chat_ids") or cfg("allowed_chat_ids")
    chats = list(dict.fromkeys(x.strip() for x in ids.split(",") if x.strip()))
    if not chats:
        raise RuntimeError("未配置飞书企业应用告警群 Chat ID")
    errors = []
    async with httpx.AsyncClient(timeout=30) as client:
        token = await get_token(client)
        for chat_id in chats:
            try:
                await request(client, "POST", ROOT + "/im/v1/messages", token,
                    params={"receive_id_type": "chat_id"},
                    json={"receive_id": chat_id, "msg_type": "interactive",
                          "content": json.dumps(card, ensure_ascii=False)})
                log.info("FEISHU_APP_ALERT_SENT chat_id_prefix=%s", chat_id[:5])
            except Exception as exc:
                log.error("FEISHU_APP_ALERT_FAILED chat_id_prefix=%s error=%s",
                          chat_id[:5], type(exc).__name__)
                errors.append(chat_id[:5])
    if errors:
        raise RuntimeError("企业应用告警有群发送失败，数量：" + str(len(errors)))


def initial_info(event):
    recovery = str(event.get("event_value", "1")) == "0"
    return {
        "host_groups": "待查询",
        "cause": "Zabbix 告警恢复" if recovery else "Zabbix 监控触发告警",
        "action": "可查看 Zabbix 事件详情" if recovery else "请检查告警主机及监控项",
        "analysis": "恢复通知，无需 AI 分析" if recovery else "原始事件通知；达到 AI 分析门槛后另发分析结果",
        "human_required": not recovery,
    }


async def handle_alert(event):
    # Delivery and AI diagnostics are separate: do not wait for the model
    # before sending the initial alert.
    severity = int(event.get("severity", "0"))
    recovery = str(event.get("event_value", "1")) == "0"
    info = initial_info(event)
    try:
        await notify(make_card(event, info))
    except Exception:
        log.exception("INITIAL_ALERT_DELIVERY_FAILED event_id=%s", event.get("event_id"))
        raise
    threshold = int(cfg("ai_min_severity") or "4")
    if recovery or severity < threshold:
        return {"event_id":event["event_id"], "notified":True, "diagnosed":False, "ai_skipped":True}
    try:
        analysis = await analyze(event)
    except Exception as exc:
        log.warning("ALERT_ANALYZE_FAILED event_id=%s error=%s", event.get("event_id"), type(exc).__name__)
        # Initial notification already arrived. Avoid flooding the same group
        # with another card when the model is unavailable.
        return {"event_id":event["event_id"],"notified":True,"diagnosed":False,"ai_failed":True}
    try:
        await notify(make_card(event,analysis))
    except Exception:
        log.exception("AI_ANALYSIS_DELIVERY_FAILED event_id=%s",event.get("event_id"))
        raise
    return {"event_id":event["event_id"],"notified":True,"diagnosed":True}



def process_alert(event):
    return asyncio.run(handle_alert(event))

if __name__ == "__main__":
    redis = Redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"))
    Worker([Queue("ai-alerts", connection=redis)], connection=redis).work()
