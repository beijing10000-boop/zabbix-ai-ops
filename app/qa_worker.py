"""Feishu Q&A, referenced alert analysis, administrator approval dry-run."""
import asyncio
import logging
import os
from .main import read_setting, record_ai_question
from redis import Redis
from rq import Worker, Queue
from .ai_agent import ask
from .alert_context import resolve_replied_event
from .conversation_context import remember, recall, format_context
from .feishu_client import reply_card, send_card, update_card, send_text

log = logging.getLogger(__name__)

async def execute(chat_id, question, message_id, sender_open_id=None, parent_id=None, root_id=None):
    record_ai_question("feishu", message_id, question, "running")
    progress_id = None
    try:
        progress_id = await reply_card(message_id, "AI 分析中",
             "**问题：** " + question[:180] + "\n\n⏳ 正在查询 Zabbix MCP 并进行分析……")
        log.info("FEISHU_PROGRESS_SENT message_id=%s", message_id)
    except Exception:
        log.exception("FEISHU_PROGRESS_FAILED message_id=%s", message_id)

    try:
        stored = recall(chat_id, parent_id) or (recall(chat_id, root_id) if root_id and root_id != parent_id else None)
        log.info("FEISHU_CONTEXT_RESOLVED message_id=%s found=%s parent=%s root=%s", message_id, bool(stored), bool(parent_id), bool(root_id))
        context = format_context(stored)
        if parent_id and not stored:
            try:
                event_id = await resolve_replied_event(parent_id, chat_id)
                if event_id:
                    context = "用户正在回复 Zabbix 告警，引用的事件 ID 为 " + event_id + "。请使用 MCP 重新核验最新状态。"
                    log.info("FEISHU_REPLIED_ALERT message_id=%s event_id=%s", message_id, event_id)
            except Exception:
                log.exception("FEISHU_REPLY_LOOKUP_FAILED message_id=%s", message_id)
        from .mcp_runtime import format_usage
        result, usage = await ask(question, context, return_usage=True)
        display_result = result + "\n\n---\n" + format_usage(usage)
        record_ai_question("feishu", message_id, question, "success", token_usage=usage)
        remember(chat_id, message_id, progress_id, question, result, stored)
        if progress_id:
            try:
                await update_card(progress_id, "AI 分析完成", display_result)
                log.info("FEISHU_CARD_UPDATED message_id=%s", message_id)
                return
            except Exception:
                log.exception("FEISHU_CARD_UPDATE_FAILED message_id=%s", message_id)
        await reply_card(message_id, "AI 分析完成", display_result)
    except Exception as exc:
        record_ai_question("feishu", message_id, question, "failed", type(exc).__name__)
        log.exception("FEISHU_QA_FAILED message_id=%s", message_id)
        if progress_id:
            try:
                await update_card(progress_id, "AI 分析失败",
                                  "分析失败，请稍后重试或联系管理员。", "red")
                return
            except Exception:
                log.exception("FEISHU_ERROR_UPDATE_FAILED message_id=%s", message_id)
        await reply_card(message_id, "AI 分析失败", "分析失败，请稍后重试或联系管理员。", "red")

def process_question(chat_id, question, message_id, sender_open_id=None, parent_id=None, root_id=None):
    return asyncio.run(execute(chat_id, question, message_id, sender_open_id, parent_id, root_id))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    Worker([Queue("ai-questions", connection=redis)], connection=redis).work()
