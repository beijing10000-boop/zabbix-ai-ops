"""Feishu tenant app message and interactive card operations."""
import json
import logging
import httpx
from redis import Redis
from .main import REDIS_URL
from .main import read_setting
from .text_safety import md_safe
log = logging.getLogger(__name__)
ROOT = "https://open.feishu.cn/open-apis"
TOKEN_KEY = "zabbix-ai:feishu:tenant_token"
_EXPIRED = {99991663, 99991661}

def token_redis():
    return Redis.from_url(REDIS_URL)

def make_card(title, text, template="blue"):
    return {"config":{"wide_screen_mode":True,"update_multi":True},
            "header":{"title":{"tag":"plain_text","content":title},"template":template},
            "elements":[{"tag":"div","text":{"tag":"lark_md","content":md_safe(text,11000)}}]}

async def request(client, method, url, token=None, **kwargs):
    async def _once(current_token):
        headers = {"Authorization": "Bearer "+current_token} if current_token else {}
        response = await client.request(method,url,headers=headers,**kwargs)
        response.raise_for_status()
        return response.json()
    data = await _once(token)
    if token and data.get("code") in _EXPIRED:
        token_redis().delete(TOKEN_KEY)
        token = await get_token(client)
        data = await _once(token)
    if data.get("code",0) != 0:
        raise RuntimeError("Feishu API error code=%s message=%s" %
            (data.get("code"),str(data.get("msg",""))[:120]))
    return data

async def get_token(client):
    redis = token_redis()
    cached = redis.get(TOKEN_KEY)
    if cached:
        return cached.decode()
    data = await request(client,"POST",ROOT+"/auth/v3/tenant_access_token/internal",
                         json={"app_id":read_setting("lark_app_id"),"app_secret":read_setting("lark_app_secret")})
    token = data["tenant_access_token"]
    ttl = max(1,int(data.get("expire",7200))-300)
    redis.set(TOKEN_KEY,token,ex=ttl)
    return token

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
