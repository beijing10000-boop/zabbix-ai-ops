"""Sanitize untrusted plain text before embedding in Feishu markdown."""
import re
_AT = re.compile(r"<at\b[^>]*>.*?</at\s*>|<at\b[^>]*/>", re.I | re.S)
def md_safe(text, limit):
    cleaned=_AT.sub("",str(text or ""))
    return cleaned.replace("<","＜").replace(">","＞")[:limit]
