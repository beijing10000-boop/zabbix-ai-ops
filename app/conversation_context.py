"""Short-lived per-message Feishu AI context. Never stores credentials or tool results."""
import json
from redis import Redis
from .main import REDIS_URL

TTL = 1800
MAX_DEPTH = 10
PREFIX = "feishu-ai:context:"
THREAD_PREFIX = "feishu-ai:thread:"

def _client():
    return Redis.from_url(REDIS_URL, decode_responses=True)

def remember(chat_id, source_id, reply_id, question, answer, parent_context=None, root_id=None):
    if not chat_id or not source_id:
        return
    previous = (parent_context or {}).get("turns", [])[-(MAX_DEPTH - 1):]
    turn = {"question": str(question)[:1200], "answer": str(answer)[:2500]}
    payload = {"chat_id": chat_id, "turns": previous + [turn]}
    client = _client()
    encoded = json.dumps(payload, ensure_ascii=False)
    for message_id in (source_id, reply_id):
        if message_id:
            client.set(PREFIX + message_id, encoded, ex=TTL)
    if root_id:
        client.set(THREAD_PREFIX + chat_id + ":" + root_id, encoded, ex=TTL)

def recall(chat_id, parent_id):
    if not parent_id:
        return None
    data = _client().get(PREFIX + parent_id)
    if not data:
        return None
    try:
        payload = json.loads(data)
        if payload.get("chat_id") != chat_id:
            return None
        if not isinstance(payload.get("turns"), list):
            return None
        return payload
    except (ValueError, TypeError):
        return None

def recall_thread(chat_id, root_id):
    """Recover latest context in a Feishu reply thread, scoped to one chat."""
    if not chat_id or not root_id:
        return None
    data = _client().get(THREAD_PREFIX + chat_id + ":" + root_id)
    if not data:
        return None
    try:
        payload = json.loads(data)
        if payload.get("chat_id") != chat_id or not isinstance(payload.get("turns"), list):
            return None
        return payload
    except (ValueError, TypeError):
        return None

def format_context(payload):
    if not payload:
        return ""
    turns = payload.get("turns", [])[-MAX_DEPTH:]
    lines = ["以下是用户回复的上文问答，仅供确定指代；请用只读 MCP 重新核验实时数据，不能将历史回答当作最新证据："]
    for index, turn in enumerate(turns, 1):
        lines.append(f"第{index}轮 用户：{str(turn.get('question',''))[:1200]}")
        lines.append(f"第{index}轮 AI：{str(turn.get('answer',''))[:2500]}")
    return "\n".join(lines)[-11500:]
