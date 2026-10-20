"""Structural guardrails: frontend assets remain external and served by FastAPI."""
import re
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

ROOT = Path(__file__).resolve().parents[1]

def test_external_static_assets_load():
    html=(ROOT/"web/index.html").read_text(encoding="utf-8")
    assert '<style' not in html and '<script>' not in html
    assert not re.search(r'\s(?:onclick|onkeydown|style)=', html)
    assert 'href="/assets/app.css"' in html
    assert 'src="/assets/app.js"' in html
    client=TestClient(app)
    assert client.get("/assets/app.css").status_code==200
    assert client.get("/assets/app.js").status_code==200
    assert client.get("/").status_code==200

def test_all_delegated_actions_have_handlers():
    html=(ROOT/"web/index.html").read_text(encoding="utf-8")
    js=(ROOT/"web/assets/app.js").read_text(encoding="utf-8")
    for action in set(re.findall(r'data-delegated-action="([^"]+)"',html)):
        assert f'"{action}":' in js

def test_tokens_exist_without_replacing_legacy_styles():
    css=(ROOT/"web/assets/app.css").read_text(encoding="utf-8")
    assert css.startswith(":root{--font:")
    assert "--sidebar:rgba(246,246,248,.72)" in css
    assert ".side{" in css
