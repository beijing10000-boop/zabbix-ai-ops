import asyncio
from unittest.mock import AsyncMock

from app import worker

def test_alert_prompt_keeps_required_json_contract():
    value = worker.alert_instructions("请重点分析网络性能")
    assert "host_groups,cause,action,analysis,human_required" in value
    assert "重点分析网络性能" in value

def test_all_alerts_notified_before_ai_and_severity_gate(monkeypatch):
    sent=[]
    async def notify(card):
        sent.append(card)
    async def analyze(event):
        assert len(sent) == 1  # original alert must already be delivered
        return {"host_groups":"test","cause":"原因","action":"处理","analysis":"AI诊断","human_required":False}
    monkeypatch.setattr(worker, "notify", notify)
    monkeypatch.setattr(worker, "analyze", analyze)
    monkeypatch.setattr(worker, "cfg",lambda key: "4" if key=="ai_min_severity" else "")
    low=asyncio.run(worker.handle_alert({"event_id":"low","severity":"2","event_value":"1"}))
    assert low["ai_skipped"] is True
    assert len(sent)==1
    high=asyncio.run(worker.handle_alert({"event_id":"high","severity":"4","event_value":"1"}))
    assert high["diagnosed"] is True
    assert len(sent)==3
    recovered=asyncio.run(worker.handle_alert({"event_id":"recovered","severity":"5","event_value":"0"}))
    assert recovered["ai_skipped"] is True
    assert len(sent)==4


def test_ai_failure_does_not_block_initial_alert(monkeypatch):
    async def broken(_):
        raise RuntimeError("model offline")
    sent=[]
    async def notify(card):
        sent.append(card)
    monkeypatch.setattr(worker, "cfg",lambda key:"4" if key=="ai_min_severity" else "")
    monkeypatch.setattr(worker, "analyze", broken)
    monkeypatch.setattr(worker, "notify", notify)
    result=asyncio.run(worker.handle_alert({"event_id":"12345","severity":"4","event_value":"1"}))
    assert result["ai_failed"] is True and result["notified"] is True
    assert len(sent)==1


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
