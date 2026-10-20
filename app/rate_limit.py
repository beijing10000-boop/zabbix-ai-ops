"""Atomic Redis fixed-window limits; independent counters for user and group."""
import hashlib
import time
from redis import Redis
from .main import REDIS_URL

def allow(key, ceiling, duration):
    redis=Redis.from_url(REDIS_URL)
    suffix=hashlib.sha256(str(key).encode()).hexdigest()
    bucket=int(time.time()//duration)
    redis_key=f"zabbix-ai:rate:{duration}:{suffix}:{bucket}"
    count=redis.incr(redis_key)
    if count==1:
        redis.expire(redis_key,duration*2)
    return count<=ceiling
