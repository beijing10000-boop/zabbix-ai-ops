"""Privileged change worker; only handles a single allowlisted Zabbix operation.

Use a dedicated MCP deployment with restricted Zabbix API permissions.
Do not grant write credentials to the chat or alert workers.
"""
import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from redis import Redis
from rq import Worker, Queue
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from .main import read_setting, REDIS_URL

log = logging.getLogger(__name__)
PREFIX = "zabbix-ai:approval:"
ALLOWED = {"event_acknowledge"}

async def run_mcp_change(task):
    if task.get("kind") != "event_acknowledge" or not str(task.get("event_id", "")).isdigit():
        raise ValueError("unsupported or invalid change request")
    endpoint = read_setting("write_mcp_url")
    token = read_setting("write_mcp_token")
    if not endpoint or not token:
        raise RuntimeError("write MCP service not configured")
    headers = {"Authorization": "Bearer " + token}
    async with AsyncExitStack() as stack:
        read, write, _ = await stack.enter_async_context(
            streamablehttp_client(endpoint, headers=headers, timeout=20))
        session = await stack.enter_async_context(ClientSession(read,write))
        await session.initialize()
        tools = await session.list_tools()
        if "event_acknowledge" not in {t.name for t in tools.tools}:
            raise RuntimeError("dedicated write MCP has no event_acknowledge tool")
        # Deliberately fixed action=2 (acknowledge only), not arbitrary parameters.
        result = await session.call_tool("event_acknowledge",
                  {"eventids":[task["event_id"]], "action":2})
        if result.isError:
            raise RuntimeError("MCP write returned an error")
        return {"ok":True,"event_id":task["event_id"]}

def execute(approval_id):
    client=Redis.from_url(REDIS_URL,decode_responses=True)
    key=PREFIX+approval_id
    raw=client.get(key)
    if not raw:
        return {"status":"expired"}
    task=json.loads(raw)
    if task.get("status") != "approved" or task.get("kind") not in ALLOWED:
        return {"status":"rejected"}
    if read_setting("write_enabled") != "true":
        return {"status":"write_disabled"}
    # Exactly-once attempt claim. MCP may apply a change even if the response
    # is lost: never automatically retry the write.
    script="""local x=redis.call('GET',KEYS[1])
    if not x then return 0 end
    local t=cjson.decode(x)
    if t.status ~= 'approved' then return 0 end
    t.status='executing'
    redis.call('SET',KEYS[1],cjson.encode(t),'KEEPTTL')
    return 1"""
    if client.eval(script,1,key) != 1:
        return {"status":"already_processed"}
    try:
        if read_setting("write_enabled") != "true":
            task["status"] = "disabled"
            client.set(key,json.dumps(task),ex=86400)
            return {"status":"write_disabled"}
        result=asyncio.run(run_mcp_change(task))
        task["status"]="success"
        client.set(key,json.dumps(task),ex=86400)
        log.warning("CHANGE_SUCCEEDED approval=%s event_id=%s",approval_id,task["event_id"])
        return result
    except Exception:
        task["status"]="uncertain"
        client.set(key,json.dumps(task),ex=86400)
        log.exception("CHANGE_UNCERTAIN approval=%s; manual review required",approval_id)
        raise

if __name__ == "__main__":
    redis=Redis.from_url(REDIS_URL)
    Worker([Queue("ai-changes",connection=redis)],connection=redis).work()
