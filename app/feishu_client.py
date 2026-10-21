"""Feishu tenant app message and interactive card operations."""
import json
import logging
import httpx
from .main import read_setting
log = logging.getLogger(__name__)
ROOT = "https://open.feishu.cn/open-apis"

def make_card(title, text, template="blue"):
    """Consistent, compact Feishu Q&A card; do not embed actions in columns."""
    body = str(text)[:11000]
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": body}}]
    if "分析中" in title:
        footer = "◷ 正在处理 · 请稍候，完成后将在此卡片更新结果"
    elif "失败" in title:
        footer = "● 处理未完成 · 请检查问题或稍后重试"
    elif "完成" in title:
        footer = "✓ 分析已完成 · 结果仅供运维诊断参考"
    else:
        footer = ""
    if footer:
        elements.extend([
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": footer}},
        ])
    return {"config": {"wide_screen_mode": True, "update_multi": True},
            "header": {"title": {"tag": "plain_text", "content": title},
                       "template": template},
            "elements": elements}

async def request(client, method, url, token=None, **kwargs):
    headers = {"Authorization": "Bearer "+token} if token else {}
    response = await client.request(method,url,headers=headers,**kwargs)
    response.raise_for_status()
    data = response.json()
    if data.get("code",0) != 0:
        raise RuntimeError("Feishu API error code=%s message=%s" % (data.get("code"),str(data.get("msg",""))[:120]))
    return data

async def get_token(client):
    data = await request(client,"POST",ROOT+"/auth/v3/tenant_access_token/internal",
                         json={"app_id":read_setting("lark_app_id"),"app_secret":read_setting("lark_app_secret")})
    return data["tenant_access_token"]

async def send_card(chat_id,title,text,template="blue"):
    async with httpx.AsyncClient(timeout=30) as client:
        token = await get_token(client)
        result = await request(client,"POST",ROOT+"/im/v1/messages",token,
            params={"receive_id_type":"chat_id"},
            json={"receive_id":chat_id,"msg_type":"interactive",
                  "content":json.dumps(make_card(title,text,template),ensure_ascii=False)})
        return result.get("data",{}).get("message_id")

async def reply_card(message_id, title, text, template="blue"):
    """Reply to the original Feishu message; return the reply message ID.

    The reply stays associated with the user's message. Later progress updates
    PATCH this reply rather than posting additional group messages.
    """
    if not message_id:
        raise ValueError("original message ID is required for a reply")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await get_token(client)
        result = await request(client, "POST",
            ROOT + "/im/v1/messages/" + message_id + "/reply", token,
            json={"msg_type": "interactive",
                  "content": json.dumps(make_card(title, text, template), ensure_ascii=False),
                  "reply_in_thread": False})
        reply_id = (result.get("data") or {}).get("message_id")
        if not reply_id:
            raise RuntimeError("飞书回复成功但未返回消息 ID")
        return reply_id


async def update_card(message_id,title,text,template="green"):
    async with httpx.AsyncClient(timeout=30) as client:
        token = await get_token(client)
        return await request(client,"PATCH",ROOT+"/im/v1/messages/"+message_id,token,
            json={"content":json.dumps(make_card(title,text,template),ensure_ascii=False)})

async def send_text(chat_id,text):
    async with httpx.AsyncClient(timeout=30) as client:
        token = await get_token(client)
        return await request(client,"POST",ROOT+"/im/v1/messages",token,
            params={"receive_id_type":"chat_id"},
            json={"receive_id":chat_id,"msg_type":"text",
                  "content":json.dumps({"text":text},ensure_ascii=False)})
