from app import rate_limit as rl

class FakeRedis:
    def __init__(self): self.values={};self.expires={}
    def incr(self,key): self.values[key]=self.values.get(key,0)+1;return self.values[key]
    def expire(self,key,ttl): self.expires[key]=ttl

def test_per_user_and_chat_quotas(monkeypatch):
    store=FakeRedis()
    monkeypatch.setattr(rl.Redis,"from_url",lambda _:store)
    assert [rl.permit("feishu:user:ou_test",5,60) for _ in range(6)]==[True]*5+[False]
    assert store.expires["zabbix-ai:quota:feishu:user:ou_test"]==60
    assert [rl.permit("web:user:ou_test",5,60) for _ in range(6)]==[True]*5+[False]
    key=rl.daily_key("oc_test")
    assert [rl.permit(key,300,90000) for _ in range(301)][-1] is False
    assert key.startswith("feishu:chat:oc_test:")
