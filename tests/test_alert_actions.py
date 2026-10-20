import json
from app.alert_mute import action_signature
from app.alert_actions import handle_choose_mute, handle_analyze_action
from app.main import connection

def test_choose_mute_requires_admin_and_offers_five_durations(monkeypatch):
    monkeypatch.setenv("FEISHU_ADMIN_OPEN_IDS", "ou_admin")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "unit-test-secret")
    event = {"event_id": "884422", "trigger_id": "202", "host_id": "101",
             "event_value": "1", "severity": "2", "event_name": "CPU high"}
    with connection() as db:
        db.execute("""INSERT OR REPLACE INTO alert_events
            (event_id,event_value,event_name,host_name,severity,event_json)
            VALUES (?, '1', 'CPU high', 'server', 2, ?)""",
            (event["event_id"], json.dumps(event)))
    value = {"op": "choose_mute", "event_id": "884422", "trigger_id": "202",
             "sig": action_signature("884422", "202", 0)}
    assert handle_choose_mute(value, "ou_other")[0] is False
    ok, message, card = handle_choose_mute(value, "ou_admin")
    assert ok and "时长" in message
    assert card["config"]["update_multi"] is False
    buttons = card["elements"][-1]["actions"]
    assert len(buttons) == 5
    assert {a["value"]["hours"] for a in buttons} == {1,4,24,72,168}
    assert all(a["value"]["op"] == "mute_alert" for a in buttons)
    with connection() as db:
        assert db.execute("SELECT * FROM alert_mutes WHERE host_id='101' AND trigger_id='202'").fetchone() is None
    assert handle_choose_mute({**value, "trigger_id": "999"}, "ou_admin")[0] is False

def test_analyze_requires_admin_and_valid_event(monkeypatch):
    monkeypatch.setenv("FEISHU_ADMIN_OPEN_IDS", "ou_admin")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "unit-test-secret")
    value = {"op":"analyze_alert","event_id":"884422","trigger_id":"202",
             "sig": action_signature("884422","202",0)}
    assert handle_analyze_action(value,"ou_other")[0] is False
    assert handle_analyze_action({**value, "sig":"wrong"},"ou_admin")[0] is False
