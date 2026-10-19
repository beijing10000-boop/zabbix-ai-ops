"""Two-stage restricted Zabbix action requests.

Phase 1 remains a dry run by default. NEVER execute arbitrary MCP tool names
or model-generated arguments.
"""
import json
import os
import re
import secrets
import time
import logging
from redis import Redis
from .main import read_setting, REDIS_URL

log=logging.getLogger(__name__)
PREFIX="zabbix-ai:approval:"
TTL=300
# Approval is requested only by a specifically allowlisted admin. One permitted
# action in preview: acknowledge a Zabbix event with a fixed action code.
CHANGE_RE=re.compile(r"^(?:确认告警|确认事件)\s+(\d{3,20})$",re.I)
CONFIRM_RE=re.compile(r"^确认执行\s+([0-9a-f]{12})$")
CANCEL_RE=re.compile(r"^取消执行\s+([0-9a-f]{12})$")

def redis_client():
    return Redis.from_url(REDIS_URL,decode_responses=True)

def admin_ids():
    return {v.strip() for v in read_setting("ai_approver_open_ids").split(",") if v.strip()}

def request_change(text, open_id, chat_id):
    match=CHANGE_RE.fullmatch(text.strip())
    if not match:return None
    if not open_id or open_id not in admin_ids():
        return "无权限：只有 Web 配置中指定的飞书管理员可以申请修改。"
    aid=secrets.token_hex(6)
    record={"kind":"event_acknowledge","event_id":match.group(1),
            "requester":open_id,"chat_id":chat_id,"status":"pending","created":int(time.time())}
    if not redis_client().set(PREFIX+aid,json.dumps(record),ex=TTL,nx=True):
        return "创建审批失败，请重试。"
    return ("**Zabbix 修改待二次确认**\n"
            f"操作：确认告警，事件 ID：{record['event_id']}\n"
            f"仅管理员本人可以在 5 分钟内回复：\n"
            f"`确认执行 {aid}`\n"
            f"或 `取消执行 {aid}`\n"
            "**当前默认模拟模式，不实际修改 Zabbix。**")

def consume_decision(text, open_id, chat_id):
    text=text.strip()
    yes=CONFIRM_RE.fullmatch(text)
    no=CANCEL_RE.fullmatch(text)
    if not yes and not no:return None
    aid=(yes or no).group(1)
    client=redis_client()
    key=PREFIX+aid
    raw=client.get(key)
    if not raw:return "审批单不存在或已过期，不会执行修改。"
    task=json.loads(raw)
    if not open_id or open_id not in admin_ids() or task["requester"] != open_id or task["chat_id"] != chat_id:
        return "身份验证失败：仅申请该变更的指定管理员可批准。"
    # Redis atomic pending -> executing/cancelled. Works across workers.
    script="""local v=redis.call('GET',KEYS[1])
    if not v then return 0 end
    local t=cjson.decode(v)
    if t.status ~= 'pending' then return -1 end
    t.status=ARGV[1]
    redis.call('SET',KEYS[1],cjson.encode(t),'KEEPTTL')
    return 1"""
    result=client.eval(script,1,key,"approved" if yes else "cancelled")
    if result != 1:return "审批已处理或过期，不能重复执行。"
    if no:return "已取消变更，未执行任何修改。"
    # Do not submit arbitrary write calls to MCP here. A separate authorized
    # execution worker must validate snapshot and run restricted tools.
    client.hset("zabbix-ai:approved-review",aid,json.dumps(task))
    return (f"已完成管理员二次验证，审批单 {aid}。\n"
            f"当前为安全模拟模式：拟确认事件 {task['event_id']}，**未执行 Zabbix 修改**。")
