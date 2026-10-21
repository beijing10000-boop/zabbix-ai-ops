"""Unified native MCP agent shared by alert analysis and Feishu Q&A.

Native tools/schemas are discovered from MCP; authorization is enforced by the
MCP server, NOT by any local tool allowlist. Deploy with a server-side read-only
credential and disable server-side mutation and sensitive-data tools.
"""
import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import AsyncOpenAI
from .main import read_setting

log = logging.getLogger(__name__)
MAX_ROUNDS = 6
MAX_CALLS = 16
MAX_PER_ROUND = 8
MAX_SECONDS = 110
MAX_OUTPUT_CHARS = 14000


def native_tools(remote_tools):
    """Expose the exact native function names and input schemas from MCP."""
    return [{"type": "function", "name": tool.name,
             "description": (tool.description or tool.name)[:600],
             "parameters": tool.inputSchema or {"type": "object", "properties": {}},
             "strict": False} for tool in remote_tools]


async def run(prompt, question, *, client=None, model=None, context=""):
    """Conduct a bounded multi-round native-MCP investigation."""
    endpoint = read_setting("mcp_url")
    if not endpoint:
        raise RuntimeError("MCP 未配置")
    key = read_setting("openai_api_key")
    model = model or read_setting("openai_model")
    base_url = read_setting("openai_base_url")
    if not model or (client is None and not (key and base_url)):
        raise RuntimeError("AI 模型未配置")
    token = read_setting("mcp_token")
    headers = {"Authorization": "Bearer " + token} if token else {}
    async with AsyncExitStack() as stack:
        read, write, _ = await stack.enter_async_context(
            streamablehttp_client(endpoint, headers=headers, timeout=20))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()
        definitions = native_tools(result.tools)
        available = {tool["name"] for tool in definitions}
        if not available:
            raise RuntimeError("MCP 未返回任何工具")
        if client is None:
            client = await stack.enter_async_context(
                AsyncOpenAI(api_key=key, base_url=base_url, timeout=150))
        conversation = [{"role": "user", "content": question[:16000] +
                         ("\n上下文：" + context[:12000] if context else "")}]
        deadline = time.monotonic() + MAX_SECONDS
        executed = 0
        for round_number in range(MAX_ROUNDS):
            if time.monotonic() >= deadline - 8:
                break
            response = await client.responses.create(
                model=model, instructions=prompt, input=conversation,
                tools=definitions, timeout=min(45, max(8, int(deadline-time.monotonic()))))
            output = list(response.output or [])
            conversation.extend(item.model_dump(exclude_none=True) for item in output)
            calls = [item for item in output if item.type == "function_call"]
            if not calls:
                log.info("MCP_AGENT_DONE rounds=%s calls=%s", round_number+1, executed)
                return (response.output_text or "").strip()
            for i, call in enumerate(calls):
                if call.name not in available:
                    outcome = {"error": "tool absent from MCP discovery"}
                elif executed >= MAX_CALLS or i >= MAX_PER_ROUND or time.monotonic() > deadline - 5:
                    outcome = {"error": "MCP call budget exhausted"}
                else:
                    try:
                        args = json.loads(call.arguments or "{}")
                        if not isinstance(args, dict):
                            raise ValueError("arguments must be an object")
                        executed += 1
                        mcp_result = await asyncio.wait_for(session.call_tool(call.name, args), timeout=18)
                        outcome = {"is_error": bool(getattr(mcp_result, "isError", False)),
                                   "data": [str(getattr(part, "text", ""))[:9000]
                                            for part in mcp_result.content[:2]]}
                        log.info("MCP_AGENT_TOOL tool=%s error=%s call=%s",
                                 call.name, outcome["is_error"], executed)
                    except Exception as exc:
                        log.warning("MCP_AGENT_TOOL_FAILED tool=%s type=%s",
                                    call.name, type(exc).__name__)
                        outcome = {"error": type(exc).__name__}
                conversation.append({"type": "function_call_output", "call_id": call.call_id,
                                     "output": json.dumps(outcome, ensure_ascii=False)[:MAX_OUTPUT_CHARS]})
        response = await client.responses.create(
            model=model, instructions=prompt + "\n工具预算已结束，请立即根据已有证据给出最终回答，不要编造事实。",
            input=conversation, tool_choice="none", timeout=35)
        log.info("MCP_AGENT_BUDGET_END calls=%s", executed)
        return (response.output_text or "").strip()
