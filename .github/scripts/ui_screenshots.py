"""Deterministic UI previews against the real frontend with mocked read-only APIs."""
from pathlib import Path
import json
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8088"
OUT = Path("ui-screenshots")
OUT.mkdir(exist_ok=True)
for _ in range(60):
    try:
        with urlopen(BASE + "/healthz", timeout=2) as r:
            if r.status == 200:
                break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("Preview server did not become available")

MOCKS = {
    "/api/v1/auth/me": {"open_id": "ou_preview", "name": "预览管理员", "csrf": "preview"},
    "/api/v1/status": {"database": "ok", "redis": "ok", "queues": {"ai-alerts": 2, "ai-questions": 1}, "version": "0.2.0"},
    "/api/v1/alert-stats": {"problems": 68, "recoveries": 54, "ai_analyses": 32},
    "/api/v1/qa-stats": {"total": 128, "success": 123, "failed": 2, "pending": 2, "running": 1},
    "/api/v1/settings": {},
    "/api/v1/logs": {"audit":[],"failed_jobs":[],"queues":{}},
    "/api/v1/ask": {"ok":True,"answer":"模拟模型返回"},
    "/api/v1/qa-events": [],
    "/api/v1/alert-events": [],
    "/api/v1/alert-mutes": [],
}

def mock_api(route):
    path = route.request.url.split("127.0.0.1:8088",1)[-1].split("?",1)[0]
    data = MOCKS.get(path, {"ok": True})
    route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    findings = []
    for width, height in ((1440, 900), (375, 812)):
        for theme in ("light", "dark"):
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1, color_scheme=theme)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.route("**/api/v1/**", mock_api)
            page.goto(BASE, wait_until="networkidle")
            page.locator("#app").wait_for(state="visible", timeout=20000)
            page.screenshot(path=str(OUT / f"dashboard-{width}-{theme}.png"), full_page=False)
            dimensions = page.evaluate("({width:document.documentElement.scrollWidth,view:innerWidth})")
            assert page.locator("button[data-page='mutes']").count() == 1
            assert "script-src 'self'" in page.goto(BASE).headers.get("content-security-policy", "")
            if width == 375:
                bottom = page.locator(".side").bounding_box()
                assert bottom is not None
                assert abs(bottom["y"] + bottom["height"] - height) <= 2, "Mobile tab bar must be bottom fixed"
            page.locator("button[data-page='config']").click()
            toggle_box = page.locator("button[role=switch]").bounding_box()
            assert toggle_box and toggle_box["height"] >= 44 and toggle_box["width"] >= 44

            page.locator("#field-feishu_enabled").wait_for(state="attached")
            assert page.locator("button[role=switch]").count() == 1
            page.locator("button[data-page='mutes']").click()
            assert page.locator("#mute-host").count() == 1
            page.locator("button[data-page='ask']").click()
            page.locator("#ask-question").fill("查询目前的严重告警")
            page.locator("#ask-question").press("Enter")
            page.locator(".chat-message.user").wait_for()
            page.locator("button[data-page='logs']").click()
            assert page.locator("#log-body").count() == 1
            findings.append({"width":width, "theme":theme, "dimensions":dimensions, "errors":errors})
            assert dimensions["width"] <= width + 1, f"Horizontal overflow: {dimensions}"
            assert not errors, f"Browser errors: {errors}"
            page.close()
    (OUT / "smoke-results.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2))
    browser.close()
