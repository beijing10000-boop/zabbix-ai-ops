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
MAX_OUTPUT_CHARS = 14000  # legacy compatibility
PROFILES = {
    "quick": {"rounds": 2, "calls": 4, "per_round": 3, "result_chars": 2000, "seconds": 65},
    "standard": {"rounds": 4, "calls": 8, "per_round": 4, "result_chars": 4000, "seconds": 110},
    "deep": {"rounds": 6, "calls": 16, "per_round": 8, "result_chars": 6000, "seconds": 150},
}
def compact_result(value, max_chars):
    """Bound each result while preserving the start and end (often summary/status)."""
    text = str(value)
    if len(text) <= max_chars:
        return text
    head = int(max_chars * .75)
    return text[:head] + "\\n...[truncated %d chars]...\\n" % (len(text)-max_chars) + text[-(max_chars-head):]



def usage_counts(response):
    """Token usage reported by the model provider; never estimate from text."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    def count(name):
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        try:
            return max(0, int(value)) if value is not None else None
        except (ValueError, TypeError):
            return None
    return {"input": count("input_tokens"), "output": count("output_tokens"),
            "total": count("total_tokens")}


def format_usage(usage):
    if not usage or usage.get("available") is not True:
        return "本轮 Token 消耗：模型未返回用量"
    return ("本轮 Token 消耗：{:,}（输入 {:,} / 输出 {:,}）".format(
        usage["total"], usage["input"], usage["output"]))


def native_tools(remote_tools):
    """Expose the exact native function names and input schemas from MCP."""
    return [{"type": "function", "name": tool.name,
             "description": (tool.description or tool.name)[:600],
             "parameters": tool.inputSchema or {"type": "object", "properties": {}},
             "strict": False} for tool in remote_tools]


async def run(prompt, question, *, client=None, model=None, context="", return_usage=False):
    """Conduct a bounded multi-round native-MCP investigation."""
    endpoint = read_setting("mcp_url")
    if not endpoint:
        raise RuntimeError("MCP 未配置")
    key = read_setting("openai_api_key")
    model = model or read_setting("openai_model")
    base_url = read_setting("openai_base_url")
    if not model or (client is None and not (key and base_url)):
        raise RuntimeError("AI 模型未配置")
    profile_name = read_setting("ai_analysis_profile") or "standard"
    profile = PROFILES.get(profile_name, PROFILES["standard"])
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
        conversation = [{"role": "user", "content": question[:4000] +
                         ("\n上下文：" + context[:6000] if context else "")}]
        deadline = time.monotonic() + profile["seconds"]
        executed = 0
        usage_totals = {"input": 0, "output": 0, "total": 0}
        usage_complete = True
        telemetry = []
        def track(response):
            nonlocal usage_complete
            counts = usage_counts(response)
            if not counts or counts["input"] is None or counts["output"] is None:
                usage_complete = False
                return
            for key in ("input", "output"):
                usage_totals[key] += counts[key]
            usage_totals["total"] += counts["total"] if counts["total"] is not None else counts["input"] + counts["output"]
        def finish(text):
            # Telemetry contains only metadata, not prompts or MCP result contents.
            try:
                from .main import connection
                source = "alert" if question.lstrip().startswith('{"alert":') else "qa"
                with connection() as db:
                    db.execute("""INSERT INTO ai_cost_runs
                        (source,model,profile,token_input,token_output,token_total,rounds,tools,result_chars,details)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (source,str(model)[:120],profile_name,
                         usage_totals["input"] if usage_complete else None,
                         usage_totals["output"] if usage_complete else None,
                         usage_totals["total"] if usage_complete else None,
                         sum(1 for d in telemetry if d.get("kind")=="round"),
                         executed,sum(d.get("chars",0) for d in telemetry if d.get("kind")=="tool"),
                         json.dumps(telemetry,ensure_ascii=False)))
            except Exception:
                log.exception("AI_COST_TELEMETRY_SAVE_FAILED")
            result_usage = {**usage_totals, "available": usage_complete}
            return (text, result_usage) if return_usage else text
        for round_number in range(profile["rounds"]):
            # Diagnostics are demand-driven: stop once the model has enough evidence.
            # All discovered native MCP tools remain available in every model round.
            if time.monotonic() >= deadline - 8:
                break
            response = await client.responses.create(
                model=model, instructions=prompt, input=conversation,
                tools=definitions, timeout=min(45, max(8, int(deadline-time.monotonic()))))
            track(response)
            round_counts = usage_counts(response)
            log.info("MCP_AGENT_ROUND profile=%s round=%s input=%s output=%s total=%s calls_so_far=%s",
                     profile_name, round_number + 1,
                     (round_counts or {}).get("input"), (round_counts or {}).get("output"),
                     (round_counts or {}).get("total"), executed)
            telemetry.append({"kind":"round","round":round_number+1,
                "input":(round_counts or {}).get("input"),
                "output":(round_counts or {}).get("output"),
                "total":(round_counts or {}).get("total"),
                "tools_before":executed})
            output = list(response.output or [])
            conversation.extend(item.model_dump(exclude_none=True) for item in output)
            calls = [item for item in output if item.type == "function_call"]
            if not calls:
                log.info("MCP_AGENT_DONE rounds=%s calls=%s", round_number+1, executed)
                return finish((response.output_text or "").strip())
            for i, call in enumerate(calls):
                began = time.monotonic()
                raw_chars = 0
                if call.name not in available:
                    outcome = {"error": "tool absent from MCP discovery"}
                elif executed >= profile["calls"] or i >= profile["per_round"] or time.monotonic() > deadline - 5:
                    outcome = {"error": "MCP call budget exhausted"}
                else:
                    try:
                        args = json.loads(call.arguments or "{}")
                        if not isinstance(args, dict):
                            raise ValueError("arguments must be an object")
                        executed += 1
                        mcp_result = await asyncio.wait_for(session.call_tool(call.name, args), timeout=18)
                        contents = [str(getattr(part, "text", "")) for part in mcp_result.content[:2]]
                        raw_chars = sum(len(part) for part in contents)
                        # Per-call budget: prevents one verbose item from dominating later rounds.
                        budget = profile["result_chars"]
                        outcome = {"is_error": bool(getattr(mcp_result, "isError", False)),
                                   "data": [compact_result(part, budget // max(1, len(contents))) for part in contents]}
                        log.info("MCP_AGENT_TOOL tool=%s error=%s call=%s",
                                 call.name, outcome["is_error"], executed)
                    except Exception as exc:
                        log.warning("MCP_AGENT_TOOL_FAILED tool=%s type=%s",
                                    call.name, type(exc).__name__)
                        outcome = {"error": type(exc).__name__}
                result_body = json.dumps(outcome, ensure_ascii=False)[:profile["result_chars"] + 250]
                telemetry.append({"kind":"tool","round":round_number+1,
                    "name":call.name[:100],"chars":len(result_body),
                    "raw_chars":raw_chars,"ms":round((time.monotonic()-began)*1000),
                    "error":bool(outcome.get("error") or outcome.get("is_error"))})
                conversation.append({"type": "function_call_output", "call_id": call.call_id,
                                     "output": result_body})
        response = await client.responses.create(
            model=model, instructions=prompt + "\n工具预算已结束，请立即根据已有证据给出最终回答，不要编造事实。",
            input=conversation, tool_choice="none", timeout=35)
        track(response)
        counts = usage_counts(response)
        log.info("MCP_AGENT_ROUND profile=%s round=final input=%s output=%s total=%s calls_so_far=%s",
                 profile_name, (counts or {}).get("input"), (counts or {}).get("output"),
                 (counts or {}).get("total"), executed)
        telemetry.append({"kind":"round","round":"final","input":(counts or {}).get("input"),
                          "output":(counts or {}).get("output"),"total":(counts or {}).get("total"),
                          "tools_before":executed})
        log.info("MCP_AGENT_BUDGET_END calls=%s", executed)
        return finish((response.output_text or "").strip())
