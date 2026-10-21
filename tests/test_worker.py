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
    assert len(sent)==3
    assert recovered["recovery_suppressed"] is True


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
    assert "Office" in body and "事件来源" in body
    assert "故障原因" not in body and "处理建议" not in body
    assert "AI 分析" not in body and "需人工核验" not in body
    recovered=worker.make_card({**event,"event_value":"0"})
    assert recovered["header"]["template"]=="green"
    assert "告警恢复" in recovered["header"]["title"]["content"]

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
    assert body.splitlines()[0] == "**主机名称**  C15-HX-M"

def test_zabbix_alarm_and_recovery_event_times():
    event={"event_id":"600001","severity":"2","event_value":"1",
           "event_date":"2026.10.19","event_time":"19:53:20",
           "recovery_date":"2026.10.19","recovery_time":"20:01:21"}
    problem=str(worker.make_card(event))
    assert "发生时间" in problem and "19:53:20" in problem
    recovered=str(worker.make_card({**event,"event_value":"0"}))
    assert "恢复时间" in recovered and "20:01:21" in recovered
    unresolved=str(worker.make_card({**event,"event_date":"{EVENT.DATE}"}))
    assert "发生时间" not in unresolved

def test_recovery_duration_and_group_are_rendered():
    event = {"event_id":"123456","event_value":"0","severity":"4",
        "host_name":"C15-HX-M","host_groups":"Core/Switch",
        "event_date":"2026.10.20","event_time":"10:00:00",
        "recovery_date":"2026.10.20","recovery_time":"10:18:02",
        "event_duration":"18m 02s"}
    card=worker.make_card(event)
    body=card["elements"][0]["text"]["content"]
    assert card["header"]["template"]=="green"
    assert "所属分组" in body and "Core/Switch" in body
    assert "持续时间" in body and "18m 02s" in body
    assert "恢复时间" in body and "10:18:02" in body
    assert "故障原因" not in body

def test_duration_calculated_when_macro_unresolved():
    from app.worker import event_duration
    assert event_duration({"event_date":"2026.10.20","event_time":"10:00:00",
        "recovery_date":"2026.10.20","recovery_time":"10:03:27",
        "event_duration":"{EVENT.DURATION}"})=="00:03:27"

def test_zabbix_event_deep_link():
    event={"event_id":"6057922","trigger_id":"102345","severity":"3",
        "event_value":"1","event_name":"Link down"}
    card=worker.make_card(event)
    body=card["elements"][0]["text"]["content"]
    assert "[查看 Zabbix 告警 ↗](http://172.20.200.90:8080/tr_events.php?triggerid=102345&eventid=6057922)" in body
    assert "172.20.200.93 转发" not in body
    recovery=worker.make_card({**event,"event_value":"0"})
    assert "eventid=6057922" in recovery["elements"][0]["text"]["content"]
    no_id=worker.make_card({**event,"trigger_id":"{TRIGGER.ID}"})
    assert "tr_events.php" not in str(no_id)

def test_alert_mute_button_targets_host_and_trigger():
    event={"event_id":"777001","host_id":"101","trigger_id":"202",
           "severity":"2","event_value":"1","event_name":"Load high"}
    card=worker.make_card(event)
    buttons=[a for el in card["elements"] if el["tag"]=="column_set" for col in el["columns"] for item in col["elements"] if item["tag"]=="action" for a in item["actions"]]
    assert len(buttons)==2
    assert {b["value"]["op"] for b in buttons}=={"choose_mute","analyze_alert"}
    assert all(b["value"]["trigger_id"]=="202" and b["value"]["event_id"]=="777001" for b in buttons)
    assert all("url" not in b for b in buttons)
    recovery=worker.make_card({**event,"event_value":"0"})
    assert not any(el["tag"]=="column_set" for el in recovery["elements"])

def test_alert_mute_requires_matching_identity():
    event={"event_id":"777002","host_id":"{HOST.ID}","trigger_id":"202",
           "severity":"2","event_value":"1"}
    card=worker.make_card(event)
    assert not any(el["tag"]=="column_set" for el in card["elements"])

def test_recovery_sent_only_for_original_feishu_sent_problem(monkeypatch):
    from app.main import connection
    sent=[]
    async def notify(card):
        sent.append(card)
    monkeypatch.setattr(worker,"notify",notify)
    monkeypatch.setattr(worker,"cfg",lambda key:"true" if key=="feishu_enabled" else "4")
    for eid,state in [("paired001","sent"),("muted001","muted"),
                      ("failed001","failed"),("disabled001","disabled")]:
        with connection() as db:
            db.execute("""INSERT OR REPLACE INTO alert_events
                (event_id,event_value,event_name,host_name,severity,notify_status)
                VALUES (?, '1', 'test', 'host', 2, ?)""",(eid,state))
    for eid in ("muted001","failed001","disabled001","missing001"):
        result=asyncio.run(worker.handle_alert({"event_id":eid,"event_value":"0","severity":"2"}))
        assert result["recovery_suppressed"] is True
    assert sent==[]
    result=asyncio.run(worker.handle_alert({"event_id":"paired001","event_value":"0","severity":"2"}))
    assert result["notified"] is True
    assert len(sent)==1

def test_mute_summary_follows_action_buttons():
    event={"event_id":"773310","host_id":"101","trigger_id":"202","severity":"2",
           "event_value":"1","event_name":"CPU high"}
    card=worker.make_card(event,mute_info={"operator":"ou_admin","duration":"4 小时",
        "time":"2026-10-21 10:00:00","expires":"2026-10-21 14:00:00"})
    assert card["config"]["update_multi"] is True
    assert "临时屏蔽仅影响后续飞书通知" not in str(card)
    assert any(el["tag"]=="column_set" for el in card["elements"])
    assert "ou_admin" in str(card["elements"][-2])
    assert "4 小时" in str(card["elements"][-2])
    assert card["elements"][-1]["actions"][0]["value"]["op"]=="unmute_alert"

def test_manual_analysis_replies_to_original_card(monkeypatch):
    from app import feishu_client
    sent=[]
    async def analyze(event):
        return {"cause":"负载较高","action":"检查进程","analysis":"CPU趋势连续上升"}
    async def reply(message_id,title,detail):
        sent.append((message_id,title,detail))
    monkeypatch.setattr(worker,"analyze",analyze)
    monkeypatch.setattr(feishu_client,"reply_card",reply)
    result=asyncio.run(worker.analyze_on_demand(
        {"event_id":"773311","severity":"2","event_value":"1"},"om_original"))
    assert result["diagnosed"]
    assert len(sent)==1
    assert sent[0][0]=="om_original"
    assert "CPU趋势连续上升" in sent[0][2]
