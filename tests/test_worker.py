import asyncio
import base64
import hashlib
import hmac
from unittest.mock import AsyncMock

from app import worker

def test_feishu_sign_uses_real_newline():
    stamp, secret = "1700000000", "key"
    expected = base64.b64encode(hmac.new((stamp + "\n" + secret).encode(), digestmod=hashlib.sha256).digest()).decode()
    wrong = base64.b64encode(hmac.new((stamp + "\\n" + secret).encode(), digestmod=hashlib.sha256).digest()).decode()
    assert worker.feishu_sign(stamp, secret) == expected
    assert expected != wrong

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
