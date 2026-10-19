from app.alert_context import extract_event_id
from app.change_approval import request_change, consume_decision

def test_reference_extracts_event_id_from_text():
    assert extract_event_id("事件 ID：5843564") == "5843564"

def test_reference_extracts_event_id_from_card():
    card={"header":{"title":{"content":"严重｜需要人工介入"}},
          "elements":[{"tag":"div","text":{"content":"事件 ID：5843564"}}]}
    assert extract_event_id(card) == "5843564"

def test_reference_does_not_invent_event_id():
    assert extract_event_id("没有事件编号") is None

def test_change_commands_require_exact_forms(monkeypatch):
    monkeypatch.setattr("app.change_approval.admin_ids",lambda:{"ou_test"})
    assert request_change("确认告警 删除全部", "ou_test", "oc_test") is None
    assert request_change("删除主机 12345", "ou_test", "oc_test") is None
    assert request_change("确认告警 12345", "ou_other", "oc_test").startswith("无权限")
    assert consume_decision("确认执行 invalid","ou_test","oc_test") is None
