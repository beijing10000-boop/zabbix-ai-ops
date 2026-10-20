"""Atomic fixed-window Redis request limits."""
import hashlib
import time

def allow_request(redis, namespace, identifier, window_seconds, limit):
    identity=hashlib.sha256(str(identifier).encode()).hexdigest()
    bucket=int(time.time()//window_seconds)
    key=f"zabbix-ai:limit:{namespace}:{identity}:{bucket}"
    value=redis.incr(key)
    if value==1:
        redis.expire(key,window_seconds+2)
    return value<=limit
