"""Capture four Apple-style UI states and smoke-test browser behavior."""
import json
import threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"artifacts"/"ui"
OUTPUT.mkdir(parents=True,exist_ok=True)
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT/"web"),**kwargs)
    def end_headers(self):
        self.send_header("Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'")
        super().end_headers()

def mock(url):
    p=urlsplit(url).path
    if p.endswith("/auth/me"): return {"open_id":"ou_test","name":"运维管理员","csrf":"test"}
    if p.endswith("/status"): return {"database":"ok","redis":"ok","queues":{"ai-alerts":0,"ai-questions":0},"version":"0.2.0"}
    if p.endswith("/alert-stats"): return {"problems":187,"recoveries":12,"ai_analyses":12}
    if p.endswith("/qa-stats"): return {"total":37,"success":35,"failed":2,"pending":0,"running":0}
    if p.endswith("/settings"): return {"web_protocol":"https","web_public_host":"aiops.example.internal",
        "openai_base_url":"https://model.example.internal/v1","openai_model":"example-model",
        "openai_api_key":"********","ai_alert_prompt":"只读分析","ai_qa_prompt":"资深运维工程师",
        "mcp_url":"https://zabbix.example.internal/mcp","mcp_token":"********",
        "lark_app_id":"cli_example","lark_app_secret":"********",
        "allowed_chat_ids":"oc_example","feishu_enabled":"true",
        "feishu_alert_chat_ids":"oc_example","zabbix_webhook_secret":"********","ai_min_severity":"4"}
    if p.endswith("/alert-mutes"): return [{"host_id":"10012","trigger_id":"20021","expires_at":1890000000}]
    if p.endswith("/logs"): return {"audit":[{"action":"settings_update","key":"ai_min_severity","time":"2026-10-20 10:01:00"}],"failed_jobs":[]}
    if p.endswith("/ask"): return {"ok":True,"answer":"CPU 采集正常。"}
    if p.endswith("/qa-events"): return [{"source":"feishu","question":"查询 CPU","status":"success","created_at":"2026-10-20 10:00:00"}]
    if p.endswith("/alert-events"): return [{"host_name":"测试主机","event_name":"CPU 告警","event_id":"123",
        "severity":2,"received_at":"2026-10-20 10:00:00","notify_status":"sent","ai_status":"success"}]
    return {"ok":True,"tools":["host_get"]}

def run():
    server=ThreadingHTTPServer(("127.0.0.1",8765),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    failures=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            for width in (1440,375):
                for theme in ("light","dark"):
                    ctx=browser.new_context(viewport={"width":width,"height":900},color_scheme=theme)
                    page=ctx.new_page()
                    page.on("pageerror",lambda e: failures.append(str(e)))
                    page.on("console",lambda e: failures.append(e.text) if e.type=="error" else None)
                    page.route("**/api/v1/**",lambda route: route.fulfill(
                        status=200,content_type="application/json",
                        body=json.dumps(mock(route.request.url),ensure_ascii=False)))
                    page.goto("http://127.0.0.1:8765",wait_until="networkidle")
                    page.locator("#metrics-grid .metric-card").first.wait_for()
                    page.screenshot(path=str(OUTPUT/("overview-"+str(width)+"-"+theme+".png")),full_page=True)
                    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), ("overflow",width,theme)
                    small=page.locator("button:visible, a.button:visible").evaluate_all(
                        "nodes=>nodes.filter(e=>{let r=e.getBoundingClientRect();return r.width<44||r.height<44}).map(e=>e.outerHTML.slice(0,150))")
                    assert not small, ("small click targets",small)
                    nav="#navigation" if width>900 else "#bottom-nav"
                    page.locator(nav+' [data-page="config"]').click()
                    page.locator("#settings-groups .group-section").first.wait_for()
                    page.locator(nav+' [data-page="mutes"]').click()
                    page.locator("#mute-list .group-row").first.wait_for()
                    page.locator(nav+' [data-page="assistant"]').click()
                    page.locator("#ask-input").fill("查询 CPU")
                    page.locator("#ask-form button").click()
                    page.get_by_text("CPU 采集正常。").wait_for()
                    page.locator(nav+' [data-page="logs"]').click()
                    page.locator("#log-list .group-row").first.wait_for()
                    page.keyboard.press("Tab")
                    assert page.evaluate("document.activeElement.tagName") in ("BUTTON","A","INPUT","TEXTAREA")
                    ctx.close()
            browser.close()
        assert not failures,failures
        print("PASS: four screenshots, CSP, mobile width, touch sizes, navigation and chat")
    finally:
        server.shutdown()

if __name__=="__main__": run()
