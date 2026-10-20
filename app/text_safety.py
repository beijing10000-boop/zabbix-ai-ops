"""Sanitize untrusted text before putting it into Feishu lark_md cards."""
import re

_AT_TAG = re.compile(r"<\s*/?\s*at\b[^>]*>", re.IGNORECASE)

def md_safe(text, limit):
    value = _AT_TAG.sub("", str(text or ""))
    return value.replace("<", "＜").replace(">", "＞")[:limit]
