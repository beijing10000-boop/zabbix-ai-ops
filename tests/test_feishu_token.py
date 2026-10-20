"""Feishu tenant token cache and expiry recovery without external services."""
import asyncio
from app import feishu_client

class FakeStore:
    def __init__(self):
        self.cache = {}
        self.ttls = []
        self.deleted = []
    def get(self, key):
        value=self.cache.get(key)
        return value.encode() if value else None
    def set(self,key,value,ex=None):
        self.cache[key]=value
        self.ttls.append(ex)
    def delete(self,key):
        self.deleted.append(key)
        self.cache.pop(key,None)

class Response:
    def __init__(self,data):self.data=data
    def raise_for_status(self):pass
    def json(self):return self.data

class FakeClient:
    def __init__(self):
        self.calls=[]
        self.old_token_invalid=False
    async def request(self, method, url, headers=None, **kwargs):
        self.calls.append((method,url,headers))
        if url.endswith('/auth/v3/tenant_access_token/internal'):
            return Response({'code':0,'tenant_access_token':'new-token','expire':7200})
        if self.old_token_invalid and headers.get('Authorization')=='Bearer old-token':
            return Response({'code':99991663,'msg':'expired'})
        return Response({'code':0,'data':{'message_id':'ok'}})

def test_token_redis_cache_uses_expire_minus_300(monkeypatch):
    store=FakeStore();client=FakeClient()
    monkeypatch.setattr(feishu_client,'token_store',lambda:store)
    monkeypatch.setattr(feishu_client,'read_setting',lambda key:'credential')
    async def run():
        assert await feishu_client.get_token(client)=='new-token'
        assert await feishu_client.get_token(client)=='new-token'
    asyncio.run(run())
    assert store.ttls==[6900]
    assert sum('/tenant_access_token/internal' in url for _,url,_ in client.calls)==1

def test_expired_token_is_evicted_and_retried_once(monkeypatch):
    store=FakeStore();store.cache[feishu_client.TOKEN_KEY]='old-token'
    client=FakeClient();client.old_token_invalid=True
    monkeypatch.setattr(feishu_client,'token_store',lambda:store)
    monkeypatch.setattr(feishu_client,'read_setting',lambda key:'credential')
    result=asyncio.run(feishu_client.request(client,'POST',feishu_client.ROOT+'/im/v1/messages',
                                           'old-token',json={'msg_type':'text'}))
    assert result['code']==0
    assert store.deleted==[feishu_client.TOKEN_KEY]
    assert store.cache[feishu_client.TOKEN_KEY]=='new-token'
    assert [c[2].get('Authorization') for c in client.calls if '/im/v1/messages' in c[1]] == ['Bearer old-token','Bearer new-token']

def test_card_text_is_safe():
    card=feishu_client.make_card('测试','<at user_id="ou_1">X</at><b>危险</b>')
    content=card['elements'][0]['text']['content']
    assert content=='X＜b＞危险＜/b＞'
