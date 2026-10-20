import pytest
from app.natural_change import parse_ack_request, resolve_change

def test_explicit_host_and_problem():
    parsed = parse_ack_request("确认 DESKTOP-5Q36VUJ 的重启告警")
    assert parsed["host"] == "DESKTOP-5Q36VUJ"
    assert "重启" in parsed["keyword"]

def test_missing_host_stays_read_only():
    result = parse_ack_request("确认这台机器的重启告警")
    assert "error" in result

def test_host_from_prior_conversation():
    result = parse_ack_request("确认这台机器的重启告警",
        {"turns":[{"question":"查询 DESKTOP-5Q36VUJ 有没有告警","answer":"有"}]})
    assert result["host"] == "DESKTOP-5Q36VUJ"

@pytest.mark.asyncio
async def test_ambiguous_or_missing_match_requires_explicit_id(monkeypatch):
    async def many(host, keyword):
        return [{"event_id":"111","name":"restart","host":host},{"event_id":"222","name":"restart","host":host}], None
    monkeypatch.setattr("app.natural_change.lookup_candidates",many)
    result=await resolve_change("确认 DESKTOP-5Q36VUJ 的重启告警")
    assert "多条" in result["error"] and "111" in result["error"]
