import os
from cryptography.fernet import Fernet
os.environ["APP_ENCRYPTION_KEY"]=Fernet.generate_key().decode()
os.environ["ADMIN_API_TOKEN"]="test-admin"
os.environ["DATA_DIR"]="/tmp/zabbix-ai-ops-pytest"
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
