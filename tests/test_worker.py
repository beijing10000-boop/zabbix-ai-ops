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
        assert len(sent) == 2  # low-priority card + original severe card
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

def test_feishu_reply_card_uses_original_message(monkeypatch):
    from app import feishu_client
    import json
    sent = []
    async def fake_token(client):
        return "test-token"
    async def fake_request(client, method, url, token=None, **kwargs):
        sent.append((method, url, kwargs["json"]))
        return {"data":{"message_id":"om_reply"}}
    monkeypatch.setattr(feishu_client,"get_token",fake_token)
    monkeypatch.setattr(feishu_client,"request",fake_request)
    result=asyncio.run(feishu_client.reply_card("om_source","AI 分析中","正在分析"))
    assert result=="om_reply"
    assert sent[0][0]=="POST"
    assert sent[0][1].endswith("/im/v1/messages/om_source/reply")
    assert sent[0][2]["reply_in_thread"] is False
    assert json.loads(sent[0][2]["content"])["header"]["title"]["content"]=="AI 分析中"

def test_compact_alert_card_and_recovery():
    event={"event_id":"6056231","severity":"2","event_value":"1",
           "host_name":"DESKTOP","host_ip":"172.20.108.2","host_groups":"Office"}
    card=worker.make_card(event)
    body=str(card)
    assert "Office" in body and "172.20.200.93 转发" in body
    assert "故障原因" not in body and "处理建议" not in body
    assert "AI 分析" not in body and "需人工核验" not in body
    recovered=worker.make_card({**event,"event_value":"0"})
    assert recovered["header"]["template"]=="green"
    assert "告警已恢复" in recovered["header"]["title"]["content"]

def test_severe_analysis_has_detail():
    event={"event_id":"6056232","severity":"4","event_value":"1"}
    details={"cause":"CPU 排队","action":"核对进程","analysis":"指标趋势"}
    initial=worker.make_card(event,details)
    analyzed=worker.make_card(event,details,analysis=True)
    assert "故障原因" not in str(initial)
    assert "故障原因" in str(analyzed)

def test_alert_card_newlines_are_real():
    card = worker.make_card({"event_id":"12345","severity":"3","event_value":"1",
        "host_name":"C15-HX-M","host_ip":"172.20.202.1","event_name":"Link down"})
    body = card["elements"][0]["text"]["content"]
    assert "\n" in body
    assert "\\n" not in body
    assert body.splitlines()[0] == "**主机名称：** C15-HX-M"
