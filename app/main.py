"""Zabbix AI Ops management API and webhook ingress (development baseline)."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from functools import lru_cache
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
SHANGHAI = ZoneInfo('Asia/Shanghai')
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
app = FastAPI(title="Zabbix AI Ops", version="0.2.0")
SENSITIVE = {"openai_api_key", "mcp_token", "lark_app_secret", "zabbix_webhook_secret"}
ALLOWED = SENSITIVE | {"openai_base_url", "openai_model", "mcp_url", "lark_app_id", "allowed_chat_ids", "min_severity", "ai_min_severity", "ai_prompt", "ai_alert_prompt", "ai_qa_prompt", "feishu_enabled", "web_protocol", "web_public_host", "feishu_alert_chat_ids"}
DEFAULTS = {"min_severity": "3", "ai_min_severity": "4", "feishu_enabled": "false", "web_protocol": "http"}

@lru_cache(maxsize=1)
def cipher():
    if not MASTER_KEY:
        raise RuntimeError("APP_ENCRYPTION_KEY must be configured")
    return Fernet(MASTER_KEY.encode())

_db_initialized = False
_db_lock = threading.Lock()
_settings_cache = None
_settings_cache_deadline = 0.0
_settings_lock = threading.RLock()

def init_db():
    global _db_initialized
    if _db_initialized:
        return
    with _db_lock:
        if _db_initialized:
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(DB,timeout=20)
        try:
            db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, secret INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, key TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        db.execute("""CREATE TABLE IF NOT EXISTS alert_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL, event_value TEXT NOT NULL, event_name TEXT, host_name TEXT, severity INTEGER, received_at TEXT DEFAULT CURRENT_TIMESTAMP, notify_status TEXT DEFAULT 'queued', ai_status TEXT DEFAULT 'not_required', UNIQUE(event_id,event_value))""")
        db.execute("""CREATE TABLE IF NOT EXISTS ai_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            request_id TEXT NOT NULL,
            question TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            error_type TEXT,
            UNIQUE(source,request_id)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS ix_ai_questions_created ON ai_questions(id DESC)")
        db.execute("CREATE TABLE IF NOT EXISTS alert_mutes (host_id TEXT NOT NULL,trigger_id TEXT NOT NULL,expires_at INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(host_id,trigger_id))")

            db.execute("CREATE TABLE IF NOT EXISTS oauth_states (state_hash TEXT PRIMARY KEY,expires INTEGER NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS admin_sessions (
                token_hash TEXT PRIMARY KEY,open_id TEXT NOT NULL,name TEXT NOT NULL,
                csrf TEXT NOT NULL,expires INTEGER NOT NULL)""")
            db.execute("DELETE FROM settings WHERE key IN ('write_enabled','write_mcp_url','write_mcp_token','ai_approver_open_ids')")
            db.commit()
            _db_initialized=True
        finally:
            db.close()

@contextmanager
def connection():
    init_db()
    db=sqlite3.connect(DB,timeout=20)
    try:
        yield db
        db.commit()
    finally:
        db.close()

def read_all_settings():
    global _settings_cache,_settings_cache_deadline
    now=time.monotonic()
    with _settings_lock:
        if _settings_cache is None or now >= _settings_cache_deadline:
            with connection() as db:
                rows=db.execute("SELECT key,value,secret FROM settings").fetchall()
            _settings_cache={key:(cipher().decrypt(value.encode()).decode() if secret else value)
                             for key,value,secret in rows}
            _settings_cache_deadline=time.monotonic()+15
        return dict(_settings_cache)

def invalidate_settings_cache():
    global _settings_cache,_settings_cache_deadline
    with _settings_lock:
        _settings_cache=None
        _settings_cache_deadline=0

def read_setting(key):
    return read_all_settings().get(key,DEFAULTS.get(key,""))

def beijing_time(value):
    """Convert SQLite UTC CURRENT_TIMESTAMP fields for API presentation."""
    if not value:
        return value
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return value


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
    host_groups: str = ""
    event_date: str = ""
    event_time: str = ""
    recovery_date: str = ""
    recovery_time: str = ""
    recovery_value: str = ""
    event_duration: str = ""
    recovery_id: str = ""
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
    return {"ok": True, "version": app.version}

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
    with connection() as db:
        for key, val in body.values.items():
            if key in SENSITIVE and val == "********":
                continue
            stored = cipher().encrypt(val.encode()).decode() if key in SENSITIVE else val
            db.execute("INSERT INTO settings(key,value,secret) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, secret=excluded.secret",
                       (key, stored, int(key in SENSITIVE)))
            db.execute("INSERT INTO audit(action,key) VALUES(?,?)", ("settings_update", key))
    invalidate_settings_cache()
    return {"ok": True}

def record_ai_question(source, request_id, question, status="pending", error_type=None):
    if source not in ("feishu", "web") or status not in ("pending", "running", "success", "failed"):
        raise ValueError("invalid question metrics")
    with connection() as db:
        db.execute("""INSERT INTO ai_questions (source,request_id,question,status,error_type,completed_at)
            VALUES (?,?,?,?,?,CASE WHEN ? IN ('success','failed') THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON CONFLICT(source,request_id) DO UPDATE SET
            status=excluded.status, error_type=excluded.error_type,
            completed_at=excluded.completed_at""",
            (source,str(request_id)[:120],str(question)[:500],status,error_type,status))


@app.get("/api/v1/qa-stats", dependencies=[Depends(require_admin)])
def qa_stats():
    with connection() as db:
        rows=db.execute("SELECT status, COUNT(*) FROM ai_questions GROUP BY status").fetchall()
    d=dict(rows)
    return {"total":sum(d.values()),"pending":d.get("pending",0),
            "running":d.get("running",0),"success":d.get("success",0),"failed":d.get("failed",0)}


@app.get("/api/v1/qa-events", dependencies=[Depends(require_admin)])
def qa_events(limit:int=100,offset:int=0):
    with connection() as db:
        rows=db.execute("""SELECT source,request_id,question,status,created_at,completed_at,error_type
            FROM ai_questions ORDER BY id DESC LIMIT ? OFFSET ?""",
            (min(max(limit,1),200),max(offset,0))).fetchall()
    return [{"source":r[0],"request_id":r[1],"question":r[2],"status":r[3],
             "created_at":beijing_time(r[4]),"completed_at":beijing_time(r[5]),
             "error_type":r[6]} for r in rows]


class MuteRequest(BaseModel):
    host_id: str = Field(pattern=r"^[0-9]{1,20}$")
    trigger_id: str = Field(pattern=r"^[0-9]{1,20}$")
    hours: int = Field(ge=1,le=168)

@app.post("/api/v1/alert-mutes", dependencies=[Depends(require_admin)])
def create_mute(body: MuteRequest):
    import time
    expires=int(time.time())+body.hours*3600
    with connection() as db:
        db.execute("INSERT INTO alert_mutes(host_id,trigger_id,expires_at) VALUES(?,?,?) ON CONFLICT(host_id,trigger_id) DO UPDATE SET expires_at=excluded.expires_at,created_at=CURRENT_TIMESTAMP",(body.host_id,body.trigger_id,expires))
        db.execute("INSERT INTO audit(action,key) VALUES (?,?)",("alert_mute",body.host_id+":"+body.trigger_id))
    return {"ok":True,"expires_at":expires}

@app.get("/api/v1/alert-mutes", dependencies=[Depends(require_admin)])
def list_mutes():
    import time
    with connection() as db:
        rows=db.execute("SELECT host_id,trigger_id,created_at,expires_at FROM alert_mutes WHERE expires_at>? ORDER BY expires_at",(int(time.time()),)).fetchall()
    return [{"host_id":r[0],"trigger_id":r[1],"created_at":beijing_time(r[2]),"expires_at":r[3]} for r in rows]

@app.delete("/api/v1/alert-mutes/{host_id}/{trigger_id}", dependencies=[Depends(require_admin)])
def remove_mute(host_id: str, trigger_id: str):
    if not host_id.isdigit() or not trigger_id.isdigit():
        raise HTTPException(422, "invalid mute identity")
    with connection() as db:
        db.execute("DELETE FROM alert_mutes WHERE host_id=? AND trigger_id=?",(host_id,trigger_id))
        db.execute("INSERT INTO audit(action,key) VALUES(?,?)",
                   ("alert_unmute",host_id+":"+trigger_id))
    return {"ok": True}


@app.get("/api/v1/alert-stats", dependencies=[Depends(require_admin)])
def alert_stats():
    with connection() as db:
        rows = db.execute("""SELECT event_value, COUNT(*) FROM alert_events GROUP BY event_value""").fetchall()
        ai = db.execute("SELECT COUNT(*) FROM alert_events WHERE ai_status IN ('pending','running','success','failed')").fetchone()[0]
    counts = dict(rows)
    return {"problems": counts.get("1",0), "recoveries": counts.get("0",0), "ai_analyses": ai}


@app.get("/api/v1/alert-events", dependencies=[Depends(require_admin)])
def alert_events(kind: str = "problems", limit: int = 100, offset: int = 0):
    if kind not in ("problems", "recoveries", "ai"):
        raise HTTPException(422, "invalid event kind")
    limit = min(max(limit,1),200)
    offset = max(offset,0)
    clause = "event_value='1'" if kind == "problems" else "event_value='0'" if kind == "recoveries" else "ai_status IN ('pending','running','success','failed')"
    with connection() as db:
        rows = db.execute(f"""SELECT event_id,event_value,event_name,host_name,severity,received_at,notify_status,ai_status FROM alert_events WHERE {clause} ORDER BY id DESC LIMIT ? OFFSET ?""",(limit,offset)).fetchall()
    return [{"event_id":r[0],"event_value":r[1],"event_name":r[2],"host_name":r[3],"severity":r[4],"received_at":beijing_time(r[5]),"notify_status":r[6],"ai_status":r[7]} for r in rows]


@app.get("/api/v1/audit", dependencies=[Depends(require_admin)])
def audit():
    with connection() as db:
        rows = db.execute("SELECT id,action,key,created_at FROM audit ORDER BY id DESC LIMIT 100").fetchall()
    return [{"id": r[0], "action": r[1], "key": r[2], "time": beijing_time(r[3])} for r in rows]

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
    result["audit"]=[{"id":r[0],"action":r[1],"key":r[2],"time":beijing_time(r[3])} for r in rows]
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
    import uuid
    request_id = uuid.uuid4().hex
    record_ai_question("web", request_id, body.question, "running")
    try:
        import asyncio
        answer = await asyncio.wait_for(ask(body.question), timeout=180)
        record_ai_question("web", request_id, body.question, "success")
        return {"ok": True, "answer": answer}
    except Exception as exc:
        record_ai_question("web", request_id, body.question, "failed", type(exc).__name__)
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
    # Zabbix recovery operations retain original {EVENT.VALUE}=1.
    # Prefer the dedicated recovery macro when present and resolved.
    resolved_recovery = alert.recovery_value == "0" or (
        alert.recovery_id.isdigit() and bool(alert.recovery_id)
    )
    if resolved_recovery:
        alert.event_value = "0"
    if alert.event_source != "0" or alert.event_value not in ("0", "1"):
        return {"status": "skipped", "reason": "unsupported event type"}
    try:
        severity = int(alert.severity)
        if not 0 <= severity <= 5:
            raise ValueError("invalid severity")
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid severity")
    redis = Redis.from_url(REDIS_URL)
    key = "zabbix-ai:processed:" + alert.event_id + ":" + alert.event_value
    if not redis.set(key, "queued", nx=True, ex=86400):
        return {"status": "duplicate"}
    try:
        ai_pending = alert.event_value == "1" and severity >= int(read_setting("ai_min_severity") or "4")
        with connection() as db:
            db.execute("""INSERT OR IGNORE INTO alert_events(event_id,event_value,event_name,host_name,severity,ai_status) VALUES(?,?,?,?,?,?)""",
                       (alert.event_id,alert.event_value,alert.event_name,alert.host_name,severity,"pending" if ai_pending else "not_required"))
        job = Queue("ai-alerts", connection=redis).enqueue("app.worker.process_alert", alert.model_dump(), job_timeout=360)
    except Exception:
        redis.delete(key)
        raise
    return {"status": "queued", "job_id": job.id}

# Register OAuth endpoints after defining app and persistence helpers.
from . import feishu_auth  # noqa: E402,F401
