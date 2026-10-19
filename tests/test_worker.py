import asyncio
from unittest.mock import AsyncMock

from app import worker

def test_alert_prompt_keeps_required_json_contract():
    value = worker.alert_instructions("请重点分析网络性能")
    assert "host_groups,cause,action,analysis,human_required" in value
    assert "重点分析网络性能" in value

def test_ai_failure_still_notifies(monkeypatch):
    async def broken(_):
        raise RuntimeError("model offline")
    sent = []
    async def notify(card):
        sent.append(card)
    monkeypatch.setattr(worker, "analyze", broken)
    monkeypatch.setattr(worker, "notify", notify)
    result = asyncio.run(worker.handle_alert({"event_id":"12345","severity":"4"}))
    assert result == {"event_id":"12345","diagnosed":False,"ai_failed":True}
    assert len(sent) == 1
    assert "AI 分析失败" in str(sent[0])

def test_enterprise_app_alert_notifier(monkeypatch):
    from app import feishu_client
    sent = []
    monkeypatch.setattr(worker, "cfg", lambda k: {
        "feishu_enabled": "true",
        "feishu_alert_chat_ids": "oc_test_1,oc_test_2",
        "allowed_chat_ids": "",
    }.get(k, ""))
    async def token(_client):
        return "mock-token"
    async def request(_client, method, url, auth, **kwargs):
        sent.append(kwargs["json"]["receive_id"])
        return {"code": 0}
    monkeypatch.setattr(feishu_client, "get_token", token)
    monkeypatch.setattr(feishu_client, "request", request)
    asyncio.run(worker.notify({"header": {"title": {"content": "test"}}}))
    assert sent == ["oc_test_1", "oc_test_2"]
