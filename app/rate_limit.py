"""Redis-backed fixed-window quotas shared across processes."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from redis import Redis

def permit(key, maximum, seconds):
    redis=Redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"))
    count=redis.incr("zabbix-ai:quota:"+key)
    if count==1:
        redis.expire("zabbix-ai:quota:"+key,seconds)
    return count<=maximum

def daily_key(chat_id):
    day=datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    return "feishu:chat:"+chat_id+":"+day
