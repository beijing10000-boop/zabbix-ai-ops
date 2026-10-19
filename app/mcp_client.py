"""Read-only MCP evidence collection over Streamable HTTP."""
import json
import logging
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from .main import read_setting

log = logging.getLogger(__name__)
# Deliberately allowlisted: no write tools can execute through this module.
READ_TOOLS = ("event_get", "trigger_get", "host_get", "hostgroup_get", "item_get", "history_get")

async def gather_evidence(event):
    endpoint = read_setting("mcp_url")
    if not endpoint:
        return {"status":"not_configured", "warning":"未配置 MCP，不能声称已核验监控数据"}
    headers = {}
    token = read_setting("mcp_token")
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        async with AsyncExitStack() as stack:
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(endpoint, headers=headers, timeout=20))
            session = await stack.enter_async_context(ClientSession(read,write))
            await session.initialize()
            listed = await session.list_tools()
            available = {x.name for x in listed.tools}
            evidence = {}
            queries = []
            if str(event.get("event_id", "")).isdigit():
                queries.append(("event_get", {"eventids":[event["event_id"]],"output":"extend"}))
            if str(event.get("host_id", "")).isdigit():
                queries.append(("host_get", {"hostids":[event["host_id"]],"output":"extend","selectGroups":"extend"}))
            for name, arguments in queries:
                if name not in READ_TOOLS or name not in available:
                    continue
                try:
                    response = await session.call_tool(name, arguments)
                    evidence[name] = [getattr(c,"text","")[:12000] for c in response.content][:2]
                except Exception as exc:
                    evidence[name] = {"error": type(exc).__name__}
            return {"status":"queried","tools":evidence}
    except Exception:
        log.exception("MCP evidence collection failed")
        return {"status":"failed","warning":"MCP 查询失败，不能据此确认根因"}
