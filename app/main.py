"""Zabbix AI Ops management API and webhook ingress (development baseline)."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException
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
SENSITIVE = {"openai_api_key", "mcp_token", "lark_app_secret", "feishu_webhook_url", "feishu_sign_secret", "zabbix_webhook_secret"}
ALLOWED = SENSITIVE | {"openai_base_url", "openai_model", "mcp_url", "lark_app_id", "allowed_chat_ids", "min_severity", "ai_prompt", "feishu_enabled"}
DEFAULTS = {"min_severity": "3", "feishu_enabled": "false"}

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

def require_admin(authorization: str | None = Header(default=None)):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="admin token not configured")
    if not authorization or not hmac.compare_digest(authorization, "Bearer " + ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")

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
    with connection() as db:
        for key, val in body.values.items():
            if key in SENSITIVE and val == "********":
                continue
            stored = cipher().encrypt(val.encode()).decode() if key in SENSITIVE else val
            db.execute("INSERT INTO settings(key,value,secret) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, secret=excluded.secret",
                       (key, stored, int(key in SENSITIVE)))
            db.execute("INSERT INTO audit(action,key) VALUES(?,?)", ("settings_update", key))
    return {"ok": True}

@app.get("/api/v1/audit", dependencies=[Depends(require_admin)])
def audit():
    with connection() as db:
        rows = db.execute("SELECT id,action,key,created_at FROM audit ORDER BY id DESC LIMIT 100").fetchall()
    return [{"id": r[0], "action": r[1], "key": r[2], "time": r[3]} for r in rows]

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
