"""Deterministic read-only lookup for natural-language event acknowledgement.

Never executes a write. Only a unique, active matching problem can be passed to
the existing administrator approval flow.
"""
import json
import re
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from .main import read_setting

ACK_PHRASE = re.compile(r"^(?:请|帮我|把|给我)?\s*(?:确认|签收)(?:一下|这条|这个|该)?\s*(.+?)(?:的)?(?:告警|事件)\s*$")
HOST_PATTERN = re.compile(r"(?i)(?:[a-z0-9]+(?:[-_.][a-z0-9]+)+|(?:\d{1,3}\.){3}\d{1,3})")

def parse_ack_request(message, parent_context=None):
    match = ACK_PHRASE.fullmatch(message.strip())
    if not match:
        return None
    target = match.group(1).strip()
    host = HOST_PATTERN.search(target)
    if not host and parent_context:
        for turn in reversed(parent_context.get("turns", [])):
            found = HOST_PATTERN.search(str(turn.get("question", "")))
            if found:
                host = found
                break
    if not host:
        return {"error": "无法确定主机。请写明主机名称，例如：确认 DESKTOP-5Q36VUJ 的重启告警。"}
    host_name = host.group(0)
    # Keyword must be explicit; do not auto-select among all open problems.
    remainder = target.replace(host_name, "").strip(" 的这条该")
    keyword = remainder.strip()
    if not keyword:
        return {"error": "请说明具体告警，例如：确认 DESKTOP-5Q36VUJ 的重启告警。"}
    return {"host": host_name, "keyword": keyword}


def unpack(result):
    if getattr(result, "isError", False):
        raise RuntimeError("MCP 查询返回错误")
    values = []
    for c in result.content:
        text = getattr(c, "text", "")
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        # Supported MCP wrappers vary by deployment.
        for _ in range(3):
            if isinstance(data, dict):
                if isinstance(data.get("result"), (list,dict)):
                    data = data["result"]
                elif isinstance(data.get("data"), (list,dict)):
                    data = data["data"]
                elif isinstance(data.get("events"), list):
                    data = data["events"]
                elif isinstance(data.get("hosts"), list):
                    data = data["hosts"]
                else:
                    break
        if isinstance(data, list):
            values.extend(x for x in data if isinstance(x,dict))
        elif isinstance(data, dict):
            values.append(data)
    return values


async def lookup_candidates(host, keyword):
    url = read_setting("mcp_url")
    token = read_setting("mcp_token")
    if not url:
        raise RuntimeError("只读 MCP 未配置")
    headers = {"Authorization":"Bearer " + token} if token else {}
    async with AsyncExitStack() as stack:
        rd, wr, _ = await stack.enter_async_context(
            streamablehttp_client(url,headers=headers,timeout=20))
        session = await stack.enter_async_context(ClientSession(rd,wr))
        await session.initialize()
        tools = {tool.name for tool in (await session.list_tools()).tools}
        if not {"host_get","event_get"}.issubset(tools):
            raise RuntimeError("只读 MCP 缺少 host_get 或 event_get")
        hosts = unpack(await session.call_tool("host_get",
            {"output":["hostid","host","name"],"search":{"name":host},"searchByAny":True}))
        exact = [h for h in hosts if host.casefold() in
                 (str(h.get("name","")).casefold(),str(h.get("host","")).casefold())]
        if len(exact) != 1:
            return [], "未找到唯一匹配的 Zabbix 主机，请提供准确主机名称"
        host_id = str(exact[0].get("hostid",""))
        if not host_id.isdigit():
            raise RuntimeError("MCP 未返回有效 hostid")
        events = unpack(await session.call_tool("event_get",{
            "output":"extend", "hostids":[host_id], "source":0,"object":0,
            "value":1,"sortfield":"eventid","sortorder":"DESC","limit":100,
            "selectRelatedObject":"extend"}))
    matches = []
    for event in events:
        event_id = str(event.get("eventid",""))
        name = str(event.get("name") or event.get("object_name") or
                  (event.get("relatedObject") or {}).get("description") or "")
        if not event_id.isdigit() or not name:
            continue
        if event.get("r_eventid") not in (None,"",0,"0"):
            continue  # recovered already
        if str(event.get("value","1")) != "1":
            continue
        if keyword.casefold() not in name.casefold():
            # Chinese shorthand for English trigger names
            aliases = {"重启":("restart","reboot","uptime"),"CPU":("cpu",),"内存":("memory","ram"),
                       "磁盘":("disk",),"网络":("network","interface","link")}
            if not any(alias in name.casefold() for k, a in aliases.items()
                       if k.casefold() in keyword.casefold() for alias in a):
                continue
        matches.append({"event_id":event_id,"host":host,"name":name})
    return matches, None


async def resolve_change(message, parent_context=None):
    parsed = parse_ack_request(message,parent_context)
    if parsed is None or "error" in parsed:
        return parsed
    try:
        matches, problem = await lookup_candidates(parsed["host"],parsed["keyword"])
    except Exception as exc:
        return {"error":"只读 MCP 核验失败（"+type(exc).__name__+"），没有发起写入。"}
    if problem:
        return {"error":problem}
    if len(matches) != 1:
        if not matches:
            return {"error":"未找到与主机及告警描述唯一匹配的未恢复事件，没有发起写入。"}
        return {"error":"匹配到多条未恢复告警，请提供具体事件 ID：\n" +
                        "\n".join(e["event_id"]+"｜"+e["name"][:110] for e in matches[:8])}
    return matches[0]
