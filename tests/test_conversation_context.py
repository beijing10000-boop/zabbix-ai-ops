import json
from app import conversation_context as ctx

class FakeRedis:
    def __init__(self):
        self.items = {}
    def set(self, key, value, ex=None):
        self.items[key] = value
    def get(self, key):
        return self.items.get(key)

def test_reply_context_is_scoped_by_chat_and_message(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(ctx, "_client", lambda: fake)
    ctx.remember("oc_group1", "om_q1", "om_a1", "host.example.internal有什么告警", "Swap使用率过高，事件6042005")
    stored = ctx.recall("oc_group1", "om_a1")
    assert len(stored["turns"]) == 1
    assert "Swap使用率" in ctx.format_context(stored)
    assert ctx.recall("oc_group2", "om_a1") is None
    assert ctx.recall("oc_group1", "om_unknown") is None
    ctx.remember("oc_group1", "om_q2", "om_a2", "更深入分析", "请核实Swap趋势", stored)
    followup = ctx.recall("oc_group1", "om_a2")
    assert len(followup["turns"]) == 2
    assert "host.example.internal" in ctx.format_context(followup)

def test_context_limited_to_ten_turns(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(ctx, "_client", lambda: fake)
    data = None
    for i in range(13):
        ctx.remember("oc_test", "om_q" + str(i), "om_a" + str(i), "question" + str(i), "answer" + str(i), data)
        data = ctx.recall("oc_test", "om_a" + str(i))
    assert len(data["turns"]) == 10
    assert data["turns"][-1]["question"] == "question12"
