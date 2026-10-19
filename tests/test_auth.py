import os
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)

def test_feishu_login_requires_admin_allowlist(monkeypatch):
    monkeypatch.delenv("FEISHU_ADMIN_OPEN_IDS",raising=False)
    result=client.get("/api/v1/auth/login",follow_redirects=False)
    assert result.status_code == 503

def test_me_requires_auth_without_legacy(monkeypatch):
    monkeypatch.setenv("ALLOW_LEGACY_ADMIN_TOKEN","false")
    assert client.get("/api/v1/auth/me").status_code == 401

def test_csrf_and_session_cookie_security(monkeypatch):
    from app import feishu_auth
    monkeypatch.setenv("ALLOW_LEGACY_ADMIN_TOKEN","false")
    monkeypatch.setenv("FEISHU_ADMIN_OPEN_IDS","ou_test")
    class R:
        cookies={"zabbix_ai_session":"session-secret"}
        headers={}
        method="POST"
    from app.main import connection
    import time
    with connection() as db:
        feishu_auth._tables(db)
        db.execute("INSERT OR REPLACE INTO admin_sessions VALUES (?,?,?,?,?)",
                   (feishu_auth._hash("session-secret"),"ou_test","Admin","csrf123",int(time.time())+3600))
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as err:
        feishu_auth.authenticate(R())
    assert err.value.status_code == 403
    R.headers={"x-csrf-token":"csrf123"}
    assert feishu_auth.authenticate(R())["open_id"] == "ou_test"
