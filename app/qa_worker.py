"""Feishu Q&A worker sends progress and updates the same interactive card."""
import asyncio
import logging
import os
from redis import Redis
from rq import Worker,Queue
from .ai_agent import ask
from .feishu_client import send_card,update_card,send_text

log = logging.getLogger(__name__)

async def execute(chat_id,question,message_id):
    progress_id = None
    try:
        progress_id = await send_card(chat_id,"AI 分析中",
               "**问题：** "+question[:180]+"\n\n⏳ 已收到，正在查询 Zabbix MCP 并分析，请稍候。")
        log.info("FEISHU_PROGRESS_SENT message_id=%s",message_id)
    except Exception:
        log.exception("FEISHU_PROGRESS_FAILED message_id=%s",message_id)
    try:
        result = await ask(question)
        if progress_id:
            try:
                await update_card(progress_id,"AI 分析完成",result)
                log.info("FEISHU_CARD_UPDATED message_id=%s",message_id)
                return
            except Exception:
                log.exception("FEISHU_CARD_UPDATE_FAILED message_id=%s",message_id)
        await send_text(chat_id,result)
    except Exception:
        log.exception("FEISHU_QA_FAILED message_id=%s",message_id)
        if progress_id:
            try:
                await update_card(progress_id,"AI 分析失败","分析失败，请稍后重试或联系管理员。","red")
                return
            except Exception:
                log.exception("FEISHU_ERROR_UPDATE_FAILED message_id=%s",message_id)
        await send_text(chat_id,"AI 分析失败，请稍后再试。")

def process_question(chat_id,question,message_id):
    return asyncio.run(execute(chat_id,question,message_id))

if __name__ == "__main__":
    redis=Redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"))
    Worker([Queue("ai-questions",connection=redis)],connection=redis).work()
