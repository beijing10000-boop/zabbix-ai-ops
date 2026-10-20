"""Escape untrusted user/Zabbix content before rendering Feishu markdown."""
import re

AT_TAG = re.compile(r"<at\b[^>]*>.*?</at\s*>|<at\b[^>]*/\s*>", re.IGNORECASE | re.DOTALL)

def md_safe(text, limit):
    value = AT_TAG.sub("", str(text if text is not None else ""))
    return value.replace("<", "＜").replace(">", "＞")[:max(0,int(limit))]
