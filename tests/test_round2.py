"""Round-two hardening regressions, no external Redis/Zabbix required."""
from unittest.mock import patch
import sqlite3
from pydantic import ValidationError
import pytest
from app import main
from app.text_safety import md_safe

def test_settings_cache_avoids_reconnecting_one_hundred_reads(monkeypatch):
    main.invalidate_settings_cache()
    real_connect = sqlite3.connect
    calls = []
    def counted_connect(*args, **kwargs):
        calls.append(1)
        return real_connect(*args, **kwargs)
    monkeypatch.setattr(main.sqlite3, "connect", counted_connect)
    for _ in range(100):
        assert isinstance(main.read_setting("ai_min_severity"), str)
    assert len(calls) <= 2

def test_settings_update_invalidates_cache(monkeypatch):
    with main.connection() as db:
        db.execute("INSERT OR REPLACE INTO settings(key,value,secret) VALUES ('min_severity','3',0)")
    main.invalidate_settings_cache()
    assert main.read_setting("min_severity") == "3"
    # Direct DB modification requires explicit invalidation (normal writes call it).
    with main.connection() as db:
        db.execute("UPDATE settings SET value='4' WHERE key='min_severity'")
    assert main.read_setting("min_severity") == "3"
    main.invalidate_settings_cache()
    assert main.read_setting("min_severity") == "4"

@pytest.mark.parametrize("payload", [
    {"event_id": "123a"},
    {"event_id": "0"*21},
    {"event_id": "1", "host_id": "x"},
    {"event_id": "1", "trigger_id": "x"},
    {"event_id": "1", "recovery_id": "a"},
    {"event_id": "1", "severity": "6"},
    {"event_id": "1", "severity": "-1"},
])
def test_alert_rejects_bad_numeric_fields(payload):
    with pytest.raises(ValidationError):
        main.Alert(**payload)

def test_alert_accepts_numeric_bounds():
    obj=main.Alert(event_id="9"*20,host_id="1"*20,trigger_id="",recovery_id="",severity="5")
    assert obj.severity=="5"

def test_safe_markdown_removes_mentions_and_angle_brackets():
    assert md_safe('hi <at user_id="ou_abc">Ada</at> <script>alert(1)</script>', 500) == 'hi Ada ＜script＞alert(1)＜/script＞'
    assert md_safe("<at>user</at>abcdef", 3) == "use"

def test_timezone_conversion_has_shanghai_module_constant():
    assert main.beijing_time("2026-10-19 10:42:16")=="2026-10-19 18:42:16"
    assert main.SHANGHAI is not None
