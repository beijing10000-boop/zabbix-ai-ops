"""Feishu Q&A, referenced alert analysis, administrator approval dry-run."""
import asyncio
import logging
import os
from .main import read_setting
from redis import Redis
from rq import Worker, Queue
from .ai_agent import ask
from .alert_context import resolve_replied_event
from .change_approval import request_change, consume_decision
from .feishu_client import send_card, update_card, send_text

log = logging.getLogger(__name__)

async def execute(chat_id, question, message_id, sender_open_id=None, parent_id=None):
    # Approval is a deterministic server-side command, not an LLM tool call.
    # No credentials or arbitrary MCP write tool are available to this path.
    action = consume_decision(question, sender_open_id, chat_id)
    if action is None:
        action = request_change(question, sender_open_id, chat_id)
    if action is not None:
        await send_card(chat_id, "Zabbix 变更审批" if read_setting("write_enabled") == "true" else "Zabbix 变更审批（模拟）", action, "orange")
        log.info("FEISHU_APPROVAL_HANDLED message_id=%s", message_id)
        return

    progress_id = None
    try:
        progress_id = await send_card(chat_id, "AI 分析中",
             "**问题：** " + question[:180] + "\n\n⏳ 正在查询 Zabbix MCP 并进行分析……")
        log.info("FEISHU_PROGRESS_SENT message_id=%s", message_id)
    except Exception:
        log.exception("FEISHU_PROGRESS_FAILED message_id=%s", message_id)

    try:
        context = ""
        if parent_id:
            try:
                event_id = await resolve_replied_event(parent_id, chat_id)
                if event_id:
                    context = "用户正在回复 Zabbix 告警，引用的事件 ID 为 " + event_id + "。请使用 MCP 重新核验最新状态。"
                    log.info("FEISHU_REPLIED_ALERT message_id=%s event_id=%s", message_id, event_id)
            except Exception:
                log.exception("FEISHU_REPLY_LOOKUP_FAILED message_id=%s", message_id)
        result = await ask(question, context)
        if progress_id:
            try:
                await update_card(progress_id, "AI 分析完成", result)
                log.info("FEISHU_CARD_UPDATED message_id=%s", message_id)
                return
            except Exception:
                log.exception("FEISHU_CARD_UPDATE_FAILED message_id=%s", message_id)
        await send_text(chat_id, result)
    except Exception:
        log.exception("FEISHU_QA_FAILED message_id=%s", message_id)
        if progress_id:
            try:
                await update_card(progress_id, "AI 分析失败",
                                  "分析失败，请稍后重试或联系管理员。", "red")
                return
            except Exception:
                log.exception("FEISHU_ERROR_UPDATE_FAILED message_id=%s", message_id)
        await send_text(chat_id, "AI 分析失败，请稍后再试。")

def process_question(chat_id, question, message_id, sender_open_id=None, parent_id=None):
    return asyncio.run(execute(chat_id, question, message_id, sender_open_id, parent_id))

if __name__ == "__main__":
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    Worker([Queue("ai-questions", connection=redis)], connection=redis).work()
