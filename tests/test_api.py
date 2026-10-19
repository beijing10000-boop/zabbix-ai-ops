from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)

def test_health():
    assert client.get("/healthz").json()["ok"] is True

def test_no_admin_access():
    assert client.get("/api/v1/settings").status_code == 401

def test_secret_masking():
    h={"Authorization":"Bearer test-admin"}
    assert client.put("/api/v1/settings",headers=h,json={"values":{"openai_api_key":"test-secret"}}).status_code == 200
    assert client.get("/api/v1/settings",headers=h).json()["openai_api_key"] == "********"

def test_webhook_unauthorized():
    payload={"event_id":"123"}
    assert client.post("/zabbix",json=payload).status_code == 401

def test_runtime_status_requires_admin():
    assert client.get("/api/v1/status").status_code == 401
    result = client.get("/api/v1/status", headers={"Authorization": "Bearer test-admin"})
    assert result.status_code == 200
    assert "queues" in result.json()

def test_mcp_test_requires_admin():
    assert client.post("/api/v1/test/mcp").status_code == 401

def test_ai_and_ask_require_admin():
    assert client.post("/api/v1/test/ai").status_code == 401
    assert client.post("/api/v1/ask", json={"question":"测试"}).status_code == 401

def test_ask_validation():
    h={"Authorization":"Bearer test-admin"}
    assert client.post("/api/v1/ask", headers=h, json={"question":""}).status_code == 422
    assert client.post("/api/v1/ask", headers=h, json={"question":"x"*3001}).status_code == 422

def test_web_ask_calls_read_only_agent(monkeypatch):
    from app import ai_agent
    async def fake_ask(question):
        assert question == "查询严重告警"
        return "已从 MCP 查询"
    monkeypatch.setattr(ai_agent, "ask", fake_ask)
    response=client.post("/api/v1/ask",
        headers={"Authorization":"Bearer test-admin"},
        json={"question":"查询严重告警"})
    assert response.status_code == 200
    assert response.json() == {"ok":True,"answer":"已从 MCP 查询"}

def test_ai_model_requires_configuration(monkeypatch):
    from app import main
    monkeypatch.setattr(main, "read_setting", lambda key: "")
    response=client.post("/api/v1/test/ai",
        headers={"Authorization":"Bearer test-admin"})
    assert response.status_code == 422

def test_write_settings_are_secret_and_default_off():
    h={"Authorization":"Bearer test-admin"}
    response=client.get("/api/v1/settings",headers=h)
    assert response.status_code == 200
    assert response.json()["write_enabled"] == "false"
    assert client.put("/api/v1/settings",headers=h,json={"values":{"write_mcp_url":"http://example.invalid/mcp","write_mcp_token":"secret-write"}}).status_code == 200
    response=client.get("/api/v1/settings",headers=h).json()
    assert response["write_mcp_url"] == "http://example.invalid/mcp"
    assert response["write_mcp_token"] == "********"

def test_restricted_write_auth_and_enable_guards(monkeypatch):
    h={"Authorization":"Bearer test-admin"}
    assert client.post("/api/v1/write/enable").status_code == 401
    assert client.post("/api/v1/write/disable").status_code == 401
    assert client.put("/api/v1/settings",headers=h,json={"values":{"write_enabled":"true"}}).status_code == 422
    assert client.post("/api/v1/write/disable",headers=h).status_code == 200
    from app import main
    monkeypatch.setattr(main,"read_setting",lambda k:"" if k.startswith("write_") else "different")
    assert client.post("/api/v1/write/enable",headers=h).status_code == 422
