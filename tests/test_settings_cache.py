"""A2 regression: one schema connection and one cache fetch for burst reads."""
from app import main

def test_read_setting_100_times_uses_at_most_two_connects(monkeypatch):
    main.init_db()
    main.invalidate_settings_cache()
    original = main.sqlite3.connect
    calls = []
    def tracked(*args,**kwargs):
        calls.append(1)
        return original(*args,**kwargs)
    monkeypatch.setattr(main.sqlite3,"connect",tracked)
    for _ in range(100):
        assert isinstance(main.read_setting("feishu_enabled"), str)
    assert len(calls) <= 2

def test_settings_cache_invalidated_after_update():
    main.read_all_settings()
    main.invalidate_settings_cache()
    assert main._settings_cache_until == 0.0
