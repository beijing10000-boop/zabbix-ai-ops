"""Contract tests for second-round backend safeguards."""
import asyncio
import hashlib
import hmac
import os
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from app.main import Alert, beijing_time
from app.text_safety import md_safe
from app.alert_mute import action_signature
from app.rate_limit import allow_request

def test_text_safety_removes_mentions_and_angles():
    text=md_safe('CPU <at user_id="ou_test">Alice</at> <90%>',100)
    assert '<at' not in text and 'Alice' not in text
    assert '＜90%＞' in text

@pytest.mark.parametrize("key,value",[
    ("event_id","bad"),("event_id","1"*21),("host_id","host"),
    ("trigger_id","-4"),("recovery_id","x"),("severity","6")])
def test_alert_rejects_invalid_identifiers(key,value):
    with pytest.raises(ValidationError):
        Alert.model_validate({"event_id":"123",key:value})

def test_mute_signature_is_domain_separated(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY","security-test-secret")
    actual=action_signature("11","22",24)
    previous=hmac.new(b"security-test-secret",b"mute_alert:11:22:24",hashlib.sha256).hexdigest()
    assert actual!=previous

class Counter:
    def __init__(self):
        self.vals={}
    def incr(self,key):
        self.vals[key]=self.vals.get(key,0)+1
        return self.vals[key]
    def expire(self,key,sec):
        assert sec>0

def test_atomic_qa_rate_limit():
    redis=Counter()
    assert all(allow_request(redis,"user","ou_1",60,5) for _ in range(5))
    assert not allow_request(redis,"user","ou_1",60,5)
    assert allow_request(redis,"user","ou_2",60,5)
    assert all(allow_request(redis,"group","oc_1",86400,300) for _ in range(300))
    assert not allow_request(redis,"group","oc_1",86400,300)

def test_timezone_utc_conversion():
    assert beijing_time("2026-10-20 00:01:00")=="2026-10-20 08:01:00"
