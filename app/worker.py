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

def valid_macro(value):
    """Suppress unresolved Zabbix macros, empty values and display placeholders."""
    value = str(value or "").strip()
    return value if value and "{" not in value and value not in ("待查询", "未查到", "未提供", "UNKNOWN") else ""


def event_duration(event):
    """Use Zabbix duration macro; derive it from event times only if absent."""
    value = valid_macro(event.get("event_duration"))
    if value:
        return value[:80]
    try:
        from datetime import datetime
        began = datetime.strptime(event["event_date"] + " " + event["event_time"], "%Y.%m.%d %H:%M:%S")
        ended = datetime.strptime(event["recovery_date"] + " " + event["recovery_time"], "%Y.%m.%d %H:%M:%S")
        seconds = int((ended - began).total_seconds())
        if seconds < 0:
            return ""
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        return (f"{days}天 " if days else "") + f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except (KeyError, ValueError, TypeError):
        return ""


def zabbix_event_link(event):
    """Link only to a validated event/trigger pair; never accept arbitrary URLs."""
    event_id = str(event.get("event_id") or "")
    trigger_id = str(event.get("trigger_id") or "")
    if not (event_id.isdigit() and trigger_id.isdigit()):
        return ""
    # Internal Zabbix 7.4 frontend currently runs on port 8080.
    from urllib.parse import urlencode
    base = os.getenv("ZABBIX_FRONTEND_URL", "http://172.20.200.90:8080").rstrip("/")
    return base + "/tr_events.php?" + urlencode({"triggerid": trigger_id, "eventid": event_id})


def make_card(event, info=None, *, analysis=False, mute_info=None):
    """Mobile-friendly, compact ops event; separate rich severe AI analysis."""
    info = info or {}
    sev = str(event.get("severity", "0"))
    recovery = str(event.get("event_value", "1")) == "0"
    title = "告警恢复" if recovery else LEVELS.get(sev, "未知")
    if analysis and not recovery:
        title = LEVELS.get(sev, "未知") + "｜AI 分析结果"
    groups = valid_macro(event.get("host_groups")) or valid_macro(info.get("host_groups"))
    event_name = valid_macro(event.get("event_name")) or "未知事件"
    lines = [
        "**主机名称**  " + safe(event.get("host_name"), 80),
        "**主机 IP**  " + safe(event.get("host_ip"), 50),
    ]
    if groups:
        lines.append("**所属分组**  " + safe(groups, 180))
    if recovery:
        started = valid_macro(event.get("event_date")) and valid_macro(event.get("event_time"))
        if started:
            lines.append("**告警时间**  " + event["event_date"] + " " + event["event_time"])
        recovery_date = valid_macro(event.get("recovery_date"))
        recovery_time = valid_macro(event.get("recovery_time"))
        if recovery_date and recovery_time:
            lines.append("**恢复时间**  " + recovery_date + " " + recovery_time)
        duration = event_duration(event)
        if duration:
            lines.append("**持续时间**  " + duration)
    else:
        occurred_date = valid_macro(event.get("event_date"))
        occurred_time = valid_macro(event.get("event_time"))
        if occurred_date and occurred_time:
            lines.append("**发生时间**  " + occurred_date + " " + occurred_time)
    lines.extend([
        "**事件名称**  " + safe(event_name, 250),
        "**事件 ID**  " + safe(event.get("event_id"), 40),
    ])
    link = zabbix_event_link(event)
    if link:
        lines.append("**事件来源**  [查看 Zabbix 告警 ↗](" + link + ")")
    else:
        lines.append("**事件来源**  Zabbix")
    elements = [
        {"tag":"div", "text":{"tag":"lark_md", "content":"\n".join(lines)}}
    ]
    if not recovery and not analysis:
        host_id = str(event.get("host_id") or "")
        trigger_id = str(event.get("trigger_id") or "")
        event_id = str(event.get("event_id") or "")
        if host_id.isdigit() and trigger_id.isdigit() and event_id.isdigit():
            from .alert_mute import action_signature
            elements.append({"tag": "hr"})
            elements.append({"tag": "div", "text": {"tag": "lark_md",
                "content": "**告警操作**"}})
            elements.append({"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "🔕 暂时屏蔽"},
                 "type": "default", "value": {"op": "choose_mute", "event_id": event_id,
                     "trigger_id": trigger_id,
                     "sig": action_signature(event_id, trigger_id, 0)}},
                {"tag": "button", "text": {"tag": "plain_text", "content": "🤖 AI分析"},
                 "type": "primary", "value": {"op": "analyze_alert", "event_id": event_id,
                     "trigger_id": trigger_id, "sig": action_signature(event_id, trigger_id, 0)}}
            ]})
    if mute_info and not recovery:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": "**屏蔽信息**\n**操作人**  " + safe(mute_info.get("operator"), 100)
            + "\n**屏蔽时长**  " + safe(mute_info.get("duration"), 30)
            + "\n**操作时间**  " + safe(mute_info.get("time"), 40)
            + "\n**到期时间**  " + safe(mute_info.get("expires"), 40)}})
    if analysis and not recovery:
        for label, field, size in (("故障原因","cause",120),("处理建议","action",160),("AI 分析","analysis",500)):
            detail = valid_macro(info.get(field))
            if detail:
                elements.append({"tag":"hr"})
                elements.append({"tag":"div","text":{"tag":"lark_md",
                    "content": "**"+label+"**\n"+safe(detail,size)}})
    return {
        "config":{"wide_screen_mode":True},
        "header":{"title":{"tag":"plain_text","content":title},
                  "template":"green" if recovery else COLORS.get(sev,"grey")},
        "elements":elements
    }

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


def update_event(event, **states):
    from .main import connection
    allowed = {"notify_status", "ai_status"}
    changes = {key:value for key,value in states.items() if key in allowed}
    if not changes:
        return
    with connection() as db:
        db.execute("UPDATE alert_events SET " + ", ".join(key + "=?" for key in changes)
                   + " WHERE event_id=? AND event_value=?",
                   (*changes.values(), str(event["event_id"]), str(event.get("event_value","1"))))


async def handle_alert(event):
    # Delivery and AI diagnostics are separate: do not wait for the model
    # before sending the initial alert.
    severity = int(event.get("severity", "0"))
    recovery = str(event.get("event_value", "1")) == "0"
    info = initial_info(event)
    if recovery:
        # A recovery is only useful in Feishu if its original problem was
        # actually delivered. Muted/failed/disabled/unknown problems are silent.
        from .main import connection
        with connection() as db:
            previous = db.execute(
                "SELECT notify_status FROM alert_events WHERE event_id=? AND event_value='1'",
                (str(event.get("event_id","")),)
            ).fetchone()
        if not previous or previous[0] != "sent":
            update_event(event, notify_status="suppressed_unpaired", ai_status="not_required")
            log.info("FEISHU_RECOVERY_SUPPRESSED_UNPAIRED event_id=%s previous_status=%s",
                     event.get("event_id"), previous[0] if previous else "missing")
            return {"event_id":event["event_id"],"notified":False,
                    "recovery_suppressed":True,"ai_skipped":True}
    if not recovery:
        from .main import connection
        import time
        host_id=str(event.get("host_id") or "")
        trigger_id=str(event.get("trigger_id") or "")
        if host_id.isdigit() and trigger_id.isdigit():
            with connection() as db:
                muted=db.execute("SELECT 1 FROM alert_mutes WHERE host_id=? AND trigger_id=? AND expires_at>?",
                    (host_id,trigger_id,int(time.time()))).fetchone()
            if muted:
                update_event(event,notify_status="muted",ai_status="not_required")
                log.info("FEISHU_ALERT_MUTED event_id=%s",event.get("event_id"))
                return {"event_id":event["event_id"],"notified":False,"muted":True}
    try:
        await notify(make_card(event, info))
        update_event(event, notify_status="sent" if cfg("feishu_enabled").lower()=="true" else "disabled")
    except Exception:
        update_event(event, notify_status="failed")
        log.exception("INITIAL_ALERT_DELIVERY_FAILED event_id=%s", event.get("event_id"))
        raise
    threshold = int(cfg("ai_min_severity") or "4")
    if recovery or severity < threshold:
        return {"event_id":event["event_id"], "notified":True, "diagnosed":False, "ai_skipped":True}
    update_event(event, ai_status="running")
    try:
        analysis = await analyze(event)
    except Exception as exc:
        update_event(event, ai_status="failed")
        log.warning("ALERT_ANALYZE_FAILED event_id=%s error=%s", event.get("event_id"), type(exc).__name__)
        # Initial notification already arrived. Avoid flooding the same group
        # with another card when the model is unavailable.
        return {"event_id":event["event_id"],"notified":True,"diagnosed":False,"ai_failed":True}
    try:
        await notify(make_card(event,analysis,analysis=True))
        update_event(event, ai_status="success")
    except Exception:
        update_event(event, ai_status="failed")
        log.exception("AI_ANALYSIS_DELIVERY_FAILED event_id=%s",event.get("event_id"))
        raise
    return {"event_id":event["event_id"],"notified":True,"diagnosed":True}



def process_alert(event):
    return asyncio.run(handle_alert(event))

if __name__ == "__main__":
    redis = Redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"))
    Worker([Queue("ai-alerts", connection=redis)], connection=redis).work()

async def analyze_on_demand(event, message_id):
    """Analyze a saved alert on explicit Feishu request using the existing read-only pipeline."""
    update_event(event, ai_status="running")
    try:
        result = await analyze(event)
        from .feishu_client import reply_card
        if not message_id or not message_id.startswith("om_"):
            raise ValueError("missing original Feishu message id")
        detail = "\n".join("**" + label + "**\n" + safe(result.get(field), size)
                           for label, field, size in (("故障原因","cause",120),
                                                      ("处理建议","action",160),
                                                      ("AI 分析","analysis",500)))
        await reply_card(message_id, "AI 分析结果", detail)
        update_event(event, ai_status="success")
        return {"diagnosed": True, "event_id": event["event_id"]}
    except Exception:
        update_event(event, ai_status="failed")
        log.exception("MANUAL_AI_ANALYSIS_FAILED event_id=%s", event.get("event_id"))
        raise


def process_manual_analysis(event, message_id):
    return asyncio.run(analyze_on_demand(event, message_id))
