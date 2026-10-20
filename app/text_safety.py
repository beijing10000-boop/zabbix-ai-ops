"""Minimal safe text for Feishu lark_md cards."""
import re

_AT_TAG = re.compile(r"<at\b[^>]*>(?:.*?)</at\s*>|<at\b[^>]*/?>",re.IGNORECASE | re.DOTALL)

def md_safe(text, limit):
    value=_AT_TAG.sub("",str(text or ""))
    return value.replace("<","＜").replace(">","＞")[:limit]
