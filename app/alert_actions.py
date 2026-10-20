"""Signed Feishu alert actions and personalized duration selector."""
import hmac
import json
import logging
from redis import Redis
from rq import Queue
from .alert_mute import action_signature
from .main import connection, REDIS_URL

log = logging.getLogger(__name__)

def _event(value):
    event_id = str(value.get("event_id") or "")
    trigger_id = str(value.get("trigger_id") or "")
    if not (event_id.isdigit() and trigger_id.isdigit()):
        return None
    expected = action_signature(event_id, trigger_id, 0)
    if not hmac.compare_digest(str(value.get("sig") or ""), expected):
        return None
    with connection() as db:
        row = db.execute("SELECT event_json FROM alert_events WHERE event_id=? AND event_value='1'",
                         (event_id,)).fetchone()
    if not row or not row[0]:
        return None
    try:
        event = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    if str(event.get("trigger_id")) != trigger_id or str(event.get("event_id")) != event_id:
        return None
    return event

def _authorized(operator_open_id):
    import os
    admins = {s.strip() for s in os.getenv("FEISHU_ADMIN_OPEN_IDS", "").split(",") if s.strip()}
    return operator_open_id in admins if operator_open_id else False

def handle_choose_mute(value, operator_open_id):
    """Return a replacement card visible only to clicking user (update_multi=False)."""
    if not _authorized(operator_open_id):
        return False, "仅飞书管理员可以暂停告警通知", None
    event = _event(value)
    if event is None:
        return False, "告警已过期或卡片签名无效", None
    from .worker import make_card
    card = make_card(event)
    host = str(event["host_id"])
    trigger = str(event["trigger_id"])
    buttons = []
    for hours, label in ((1, "1小时"), (4, "4小时"), (24, "24小时"),
                         (72, "3天"), (168, "7天")):
        buttons.append({"tag": "button", "text": {"tag": "plain_text", "content": label},
            "type": "primary" if hours == 1 else "default",
            "value": {"op": "mute_alert", "host_id": host, "trigger_id": trigger,
                      "hours": hours, "sig": action_signature(host, trigger, hours)}})
    card["config"]["update_multi"] = False
    card["elements"][-2:] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": "**选择暂时屏蔽时长**（仅屏蔽后续飞书通知）"}},
        {"tag": "action", "actions": buttons}]
    return True, "请选择屏蔽时长", card

def handle_analyze_action(value, operator_open_id):
    if not _authorized(operator_open_id):
        return False, "仅飞书管理员可以触发 AI 分析"
    event = _event(value)
    if event is None:
        return False, "告警已过期或卡片签名无效"
    redis = Redis.from_url(REDIS_URL)
    key = "zabbix-ai:manual-analysis:" + event["event_id"]
    if not redis.set(key, "queued", ex=300, nx=True):
        return True, "此告警的 AI 分析已提交，请勿重复点击"
    try:
        Queue("ai-alerts", connection=redis).enqueue(
            "app.worker.process_manual_analysis", event, job_timeout=360)
    except Exception:
        redis.delete(key)
        log.exception("MANUAL_ANALYSIS_ENQUEUE_FAILED")
        return False, "AI 分析任务提交失败"
    return True, "已提交 AI 分析，结果将发送到告警群"
