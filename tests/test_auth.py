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
    from app.main import connection, invalidate_settings_cache
    import time
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO admin_sessions VALUES (?,?,?,?,?)",
                   (feishu_auth._hash("session-secret"),"ou_test","Admin","csrf123",int(time.time())+3600))
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as err:
        feishu_auth.authenticate(R())
    assert err.value.status_code == 403
    R.headers={"x-csrf-token":"csrf123"}
    assert feishu_auth.authenticate(R())["open_id"] == "ou_test"

def test_http_callback_is_default_and_url_is_validated(monkeypatch):
    from app.feishu_auth import _redirect_uri, _secure_cookie
    from fastapi import HTTPException
    import pytest
    from app.main import connection
    with connection() as db:
        db.execute("DELETE FROM settings WHERE key IN ('web_protocol','web_public_host')")
    from app.main import invalidate_settings_cache
    invalidate_settings_cache()
    monkeypatch.setenv("FEISHU_LOGIN_REDIRECT_URI","http://zabbix.example.internal:8088/api/v1/auth/callback")
    assert _redirect_uri()=="http://zabbix.example.internal:8088/api/v1/auth/callback"
    assert _secure_cookie() is False
    monkeypatch.setenv("FEISHU_LOGIN_REDIRECT_URI","http://example.invalid/evil")
    with pytest.raises(HTTPException): _redirect_uri()
    monkeypatch.setenv("FEISHU_LOGIN_REDIRECT_URI","https://aiops.example.com/api/v1/auth/callback")
    assert _secure_cookie() is True


def test_default_http_and_ui_https_switch(monkeypatch):
    from app import feishu_auth
    from app.main import connection, invalidate_settings_cache
    monkeypatch.setenv("FEISHU_LOGIN_REDIRECT_URI","http://zabbix.example.internal:8088/api/v1/auth/callback")
    with connection() as db:
        db.execute("DELETE FROM settings WHERE key IN ('web_protocol','web_public_host')")
    invalidate_settings_cache()
    assert feishu_auth._secure_cookie() is False
    from cryptography.fernet import Fernet
    with connection() as db:
        db.execute("INSERT INTO settings(key,value,secret) VALUES ('web_protocol','https',0)")
        db.execute("INSERT INTO settings(key,value,secret) VALUES ('web_public_host','aiops.example.com',0)")
    invalidate_settings_cache()
    assert feishu_auth._redirect_uri()=="https://aiops.example.com/api/v1/auth/callback"
    assert feishu_auth._secure_cookie() is True
    with connection() as db:
        db.execute("DELETE FROM settings WHERE key IN ('web_protocol','web_public_host')")
    invalidate_settings_cache()
