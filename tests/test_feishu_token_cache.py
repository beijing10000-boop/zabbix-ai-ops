import asyncio
from app import feishu_client as fc

class FakeRedis:
    def __init__(self): self.data={}
    def get(self,key): return self.data.get(key)
    def set(self,key,val,ex=None): self.data[key]=val.encode() if isinstance(val,str) else val; self.ttl=ex
    def delete(self,key): self.data.pop(key,None)

class Response:
    def __init__(self,payload): self.payload=payload
    def raise_for_status(self): pass
    def json(self): return self.payload

def test_token_cache_and_expiration(monkeypatch):
    redis=FakeRedis()
    monkeypatch.setattr(fc,"token_cache",lambda:redis)
    monkeypatch.setattr(fc,"read_setting",lambda key:"demo")
    class Client:
        calls=0
        async def request(self,*args,**kwargs):
            self.calls+=1
            return Response({"code":0,"tenant_access_token":"token-1","expire":1000})
    client=Client()
    assert asyncio.run(fc.get_token(client))=="token-1"
    assert redis.ttl==700
    assert asyncio.run(fc.get_token(client))=="token-1"
    assert client.calls==1

def test_token_invalid_refresh_once(monkeypatch):
    redis=FakeRedis();redis.set(fc.TOKEN_KEY,"old")
    monkeypatch.setattr(fc,"token_cache",lambda:redis)
    monkeypatch.setattr(fc,"read_setting",lambda key:"demo")
    class Client:
        calls=0
        async def request(self,method,url,**kwargs):
            self.calls+=1
            if self.calls==1:return Response({"code":99991663,"msg":"expired"})
            if self.calls==2:return Response({"code":0,"tenant_access_token":"new","expire":800})
            return Response({"code":0,"data":{"ok":True}})
    client=Client()
    result=asyncio.run(fc.request(client,"GET","https://example.invalid/v1",token="old"))
    assert result["code"]==0 and client.calls==3
    assert redis.get(fc.TOKEN_KEY)==b"new"
