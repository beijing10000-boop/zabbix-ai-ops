from app.text_safety import md_safe
from app.worker import make_card

def test_md_safe_removes_mentions_and_replaces_angles():
    assert md_safe('<at user_id="ou_1">person</at><script>x</script>',100)=='＜script＞x＜/script＞'
    assert md_safe('<at id="x"/>hello',3)=='hel'
    assert md_safe('a<b>c',99)=='a＜b＞c'

def test_card_escapes_host_and_times():
    event={"event_id":"100123","event_value":"1","severity":"2",
           "host_name":"host<at id=\"x\">u</at><test>",
           "host_ip":"192.0.2.1","event_name":"CPU <100",
           "event_date":"2026.10.20<bad>","event_time":"11:00:00"}
    card=make_card(event)
    raw=card["elements"][0]["text"]["content"]
    assert "<at" not in raw and "<test>" not in raw and "＜bad＞" in raw
