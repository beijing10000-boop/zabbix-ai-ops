"""Feishu lark_md content sanitization (not an HTML sanitizer)."""
import re

_AT_TAG = re.compile(r"</?at(?:\s+[^<>]*?)?\s*/?>", re.IGNORECASE)

def md_safe(text, limit):
    """Remove Feishu mention tags, neutralize angle brackets, then truncate."""
    if limit < 0:
        raise ValueError("limit must not be negative")
    cleaned = _AT_TAG.sub("", str(text if text is not None else ""))
    return cleaned.replace("<", "＜").replace(">", "＞")[:limit]
