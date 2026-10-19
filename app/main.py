"""Zabbix AI Ops management API and webhook ingress (development baseline)."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet, InvalidToken
from redis import Redis
from rq import Queue

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB = DATA_DIR / "app.sqlite3"
MASTER_KEY = os.getenv("APP_ENCRYPTION_KEY", "")
ADMIN_TOKEN = os.getenv("ADMIN_API_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = FastAPI(title="Zabbix AI Ops", version="0.1.0")
SENSITIVE = {"openai_api_key", "mcp_token", "lark_app_secret", "feishu_webhook_url", "feishu_sign_secret", "zabbix_webhook_secret", "write_mcp_token"}
ALLOWED = SENSITIVE | {"openai_base_url", "openai_model", "mcp_url", "lark_app_id", "allowed_chat_ids", "min_severity", "ai_prompt", "ai_alert_prompt", "ai_qa_prompt", "feishu_enabled", "ai_approver_open_ids", "web_protocol", "web_public_host", "write_mcp_url", "write_enabled"}
DEFAULTS = {"min_severity": "3", "feishu_enabled": "false", "web_protocol": "http", "write_enabled": "false"}

def cipher():
    if not MASTER_KEY:
        raise RuntimeError("APP_ENCRYPTION_KEY must be configured")
    return Fernet(MASTER_KEY.encode())

@contextmanager
def connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=20)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, secret INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, key TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        db.commit()
        yield db
        db.commit()
    finally:
        db.close()

def read_setting(key):
    with connection() as db:
        row = db.execute("SELECT value, secret FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return DEFAULTS.get(key, "")
    return cipher().decrypt(row[0].encode()).decode() if row[1] else row[0]

def require_admin(request: Request):
    from .feishu_auth import authenticate
    return authenticate(request)

class SettingsUpdate(BaseModel):
    values: dict[str, str]

class Alert(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    event_value: str = "1"
    event_source: str = "0"
    event_name: str = ""
    severity: str = "0"
    host_name: str = ""
    host_id: str = ""
    host_ip: str = ""
    trigger_id: str = ""
    subject: str = ""
    message: str = ""

@app.get("/")
def home():
    return FileResponse(Path(__file__).parent.parent / "web" / "index.html")

@app.get("/healthz")
def health():
    with connection() as db:
        db.execute("SELECT 1").fetchone()
    return {"ok": True}

@app.get("/api/v1/settings", dependencies=[Depends(require_admin)])
def get_settings():
    return {k: ("********" if k in SENSITIVE and read_setting(k) else read_setting(k)) for k in sorted(ALLOWED)}

@app.put("/api/v1/settings", dependencies=[Depends(require_admin)])
def update_settings(body: SettingsUpdate):
    invalid = set(body.values) - ALLOWED
    if invalid:
        raise HTTPException(status_code=422, detail=f"invalid settings: {sorted(invalid)}")
    if any(not isinstance(v, str) or len(v) > 12000 for v in body.values.values()):
        raise HTTPException(status_code=422, detail="invalid value")
    if "write_enabled" in body.values:
        raise HTTPException(422, "请通过写入权限开关专用接口进行启用或关闭")
    if "write_mcp_url" in body.values or "write_mcp_token" in body.values:
        # Any change to write endpoint or credentials revokes prior capability approval.
        # Admin must explicitly revalidate the target before another write.
        with connection() as db:
            db.execute("INSERT INTO settings(key,value,secret) VALUES ('write_enabled','false',0) ON CONFLICT(key) DO UPDATE SET value='false',secret=0")
            db.execute("INSERT INTO audit(action,key) VALUES ('write_disabled','write_mcp_config_changed')")
    with connection() as db:
        for key, val in body.values.items():
            if key in SENSITIVE and val == "********":
                continue
            stored = cipher().encrypt(val.encode()).decode() if key in SENSITIVE else val
            db.execute("INSERT INTO settings(key,value,secret) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, secret=excluded.secret",
                       (key, stored, int(key in SENSITIVE)))
            db.execute("INSERT INTO audit(action,key) VALUES(?,?)", ("settings_update", key))
    return {"ok": True}

@app.post("/api/v1/write/disable", dependencies=[Depends(require_admin)])
def disable_write():
    with connection() as db:
        db.execute("INSERT INTO settings(key,value,secret) VALUES ('write_enabled','false',0) ON CONFLICT(key) DO UPDATE SET value='false',secret=0")
        db.execute("INSERT INTO audit(action,key) VALUES ('write_disabled','event_acknowledge')")
    return {"enabled": False}

@app.post("/api/v1/write/enable", dependencies=[Depends(require_admin)])
async def enable_write():
    """Validate independent write MCP tools before enabling acknowledgement."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    url, token = read_setting("write_mcp_url"), read_setting("write_mcp_token")
    if not url or not token:
        raise HTTPException(422, "请先保存独立的写入 MCP URL 和 Token")
    if url == read_setting("mcp_url") and token == read_setting("mcp_token"):
        raise HTTPException(409, "写入 MCP 与只读 MCP 不允许使用相同的地址及令牌组合")
    try:
        async with streamablehttp_client(url, headers={"Authorization": "Bearer " + token}, timeout=10) as (rd, wr, _):
            async with ClientSession(rd, wr) as session:
                await session.initialize()
                listed = await session.list_tools()
        tool = next((t for t in listed.tools if t.name == "event_acknowledge"), None)
        if not tool or not {"eventids","action"}.issubset((tool.inputSchema or {}).get("properties",{})):
            raise HTTPException(409, "写入 MCP 未提供兼容的 event_acknowledge 工具")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "写入 MCP 工具检测失败：" + type(exc).__name__) from None
    with connection() as db:
        db.execute("INSERT INTO settings(key,value,secret) VALUES ('write_enabled','true',0) ON CONFLICT(key) DO UPDATE SET value='true',secret=0")
        db.execute("INSERT INTO audit(action,key) VALUES ('write_enabled','event_acknowledge')")
    return {"enabled": True, "allowed_action": "event_acknowledge"}

@app.get("/api/v1/audit", dependencies=[Depends(require_admin)])
def audit():
    with connection() as db:
        rows = db.execute("SELECT id,action,key,created_at FROM audit ORDER BY id DESC LIMIT 100").fetchall()
    return [{"id": r[0], "action": r[1], "key": r[2], "time": r[3]} for r in rows]

@app.get("/api/v1/logs", dependencies=[Depends(require_admin)])
def logs_overview():
    """Sanitized operational log overview; never return raw exception traces."""
    from rq.registry import FailedJobRegistry
    result={"failed_jobs":[], "queues":{}, "note":"详细容器日志请使用 docker compose logs 查看"}
    try:
        redis=Redis.from_url(REDIS_URL,socket_connect_timeout=3,socket_timeout=5)
        for name in ("ai-alerts","ai-questions","ai-changes"):
            queue=Queue(name,connection=redis)
            result["queues"][name]={"queued":len(queue),
                                     "failed":len(FailedJobRegistry(name,connection=redis))}
            ids=FailedJobRegistry(name,connection=redis).get_job_ids()[:20]
            for jid in ids:
                result["failed_jobs"].append({"queue":name,"id":jid})
    except Exception:
        result["error"]="队列日志暂不可用，请查看 Redis 状态"
    with connection() as db:
        rows=db.execute("SELECT id,action,key,created_at FROM audit ORDER BY id DESC LIMIT 100").fetchall()
    result["audit"]=[{"id":r[0],"action":r[1],"key":r[2],"time":r[3]} for r in rows]
    return result

@app.get("/api/v1/status", dependencies=[Depends(require_admin)])
def runtime_status():
    result = {"database": "ok", "redis": "unknown", "queues": {}, "version": app.version}
    try:
        client = Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=3)
        result["redis"] = "ok" if client.ping() else "unavailable"
        for q in ("ai-alerts", "ai-questions"):
            result["queues"][q] = len(Queue(q, connection=client))
    except Exception:
        result["redis"] = "unavailable"
    return result

@app.post("/api/v1/test/mcp", dependencies=[Depends(require_admin)])
async def test_mcp():
    """Read-only tool discovery. Never execute MCP write operations."""
    endpoint = read_setting("mcp_url")
    if not endpoint:
        raise HTTPException(status_code=422, detail="please configure MCP URL first")
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from .ai_agent import ALLOWED_TOOLS
    token = read_setting("mcp_token")
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        async with streamablehttp_client(endpoint, headers=headers, timeout=10) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                allowed = sorted(t.name for t in tools.tools if t.name in ALLOWED_TOOLS)
                return {"ok": True, "read_only_tools": allowed, "count": len(allowed)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP connection failed: " + type(exc).__name__)

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=3000)

@app.post("/api/v1/test/ai", dependencies=[Depends(require_admin)])
async def test_ai_model():
    """Test model availability without tools; report Azure errors without leaking credentials."""
    import asyncio
    import logging
    import time
    from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError, RateLimitError
    key = read_setting("openai_api_key")
    model = read_setting("openai_model")
    base_url = read_setting("openai_base_url")
    if not all((key, model, base_url)):
        raise HTTPException(status_code=422, detail="请先保存 AI Base URL、模型及 API Key")
    started = time.monotonic()
    try:
        # Disable SDK retries here: a 429 is diagnostic, not an invitation to retry.
        async with AsyncOpenAI(api_key=key, base_url=base_url, timeout=90, max_retries=0) as client:
            response = await asyncio.wait_for(
                client.responses.create(
                    model=model,
                    instructions="你是模型连通性检查服务。请只回复：AI连接成功",
                    input="测试连接",
                    max_output_tokens=80,
                ), timeout=95)
        return {"ok": True, "model": model,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "reply": (response.output_text or "")[:500]}
    except RateLimitError:
        msg = "Azure OpenAI 返回 429：模型部署触发限流或当前区域容量不足。请稍后重试，检查 Azure 部署容量与配额。"
        status = 429
    except APIStatusError as exc:
        status = 502
        if exc.status_code in (401, 403):
            msg = f"Azure OpenAI 返回 {exc.status_code}：请检查 API Key、账号权限及网络访问策略。"
        elif exc.status_code == 404:
            msg = "Azure OpenAI 返回 404：请核实 Base URL、模型部署名与 API 版本。"
        elif exc.status_code >= 500:
            msg = f"Azure OpenAI 返回 {exc.status_code}：上游服务暂时不可用。"
        else:
            msg = f"Azure OpenAI 返回 {exc.status_code}：请求参数或部署配置可能不兼容。"
    except (APITimeoutError, asyncio.TimeoutError):
        status, msg = 504, "调用超过 90 秒：Azure 模型响应超时，请检查部署容量或稍后重试。"
    except APIConnectionError:
        status, msg = 502, "无法连接 Azure OpenAI：请检查容器网络、DNS、TLS 与 API 地址。"
    except Exception as exc:
        status, msg = 502, "AI 模型测试失败（" + type(exc).__name__ + "），请查看服务器日志。"
    elapsed = round(time.monotonic() - started, 2)
    logging.getLogger(__name__).warning(
        "AI_MODEL_TEST_FAILED status=%s elapsed=%.2f", status, elapsed)
    raise HTTPException(status_code=status, detail=f"{msg} 耗时 {elapsed} 秒") from None


@app.post("/api/v1/ask", dependencies=[Depends(require_admin)])
async def ask_web(body: AskRequest):
    """Use the same read-only MCP agent as Feishu; never expose write tools."""
    from .ai_agent import ask
    try:
        import asyncio
        answer = await asyncio.wait_for(ask(body.question), timeout=180)
        return {"ok": True, "answer": answer}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "WEB_QA_FAILED error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="问答失败（" + type(exc).__name__ + "），请检查模型与 MCP 服务"
        ) from None

@app.post("/zabbix", status_code=202)
def ingest(alert: Alert, authorization: str | None = Header(default=None)):
    secret = read_setting("zabbix_webhook_secret")
    if not secret or not authorization or not hmac.compare_digest(authorization, "Bearer " + secret):
        raise HTTPException(status_code=401, detail="unauthorized")
    if alert.event_source != "0" or alert.event_value != "1":
        return {"status": "skipped", "reason": "not problem trigger"}
    try:
        severity = int(alert.severity)
        threshold = int(read_setting("min_severity") or "3")
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid severity setting")
    if severity < threshold:
        return {"status": "skipped", "reason": "below threshold"}
    redis = Redis.from_url(REDIS_URL)
    key = "zabbix-ai:processed:" + alert.event_id
    if not redis.set(key, "queued", nx=True, ex=86400):
        return {"status": "duplicate"}
    try:
        job = Queue("ai-alerts", connection=redis).enqueue("app.worker.process_alert", alert.model_dump(), job_timeout=360)
    except Exception:
        redis.delete(key)
        raise
    return {"status": "queued", "job_id": job.id}

# Register OAuth endpoints after defining app and persistence helpers.
from . import feishu_auth  # noqa: E402,F401
