import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const base='http://127.0.0.1:8099';
mkdirSync('artifacts/ui',{recursive:true});
let errors=[];
const status={database:'ok',redis:'ok',queues:{'ai-alerts':2,'ai-questions':1},version:'0.2.0'};
const settings={web_protocol:'https',web_public_host:'aiops.example.internal',
  openai_base_url:'https://example.invalid/openai/v1/',openai_model:'gpt-6',
  openai_api_key:'********',mcp_url:'https://zabbix.example.internal/mcp',mcp_token:'********',
  lark_app_id:'cli_demo',lark_app_secret:'********',allowed_chat_ids:'oc_demo',
  feishu_enabled:'true',feishu_alert_chat_ids:'oc_demo',zabbix_webhook_secret:'********',
  ai_min_severity:'4',ai_alert_prompt:'只读告警分析',ai_qa_prompt:'只读问答'};
const mock=(url)=>{
 const p=new URL(url).pathname;
 if(p==='/api/v1/auth/me')return {open_id:'ou_visual',name:'Operations',csrf:'visualcsrf'};
 if(p==='/api/v1/status')return status;
 if(p==='/api/v1/alert-stats')return {problems:187,recoveries:12,ai_analyses:12};
 if(p==='/api/v1/qa-stats')return {total:38,pending:0,running:1,success:36,failed:1};
 if(p==='/api/v1/settings')return settings;
 if(p==='/api/v1/alert-mutes')return [{host_id:'10001',trigger_id:'20002',expires_at:Math.floor(Date.now()/1000)+3600*3}];
 if(p==='/api/v1/alert-events')return [{event_id:'6100570',host_name:'DESKTOP-TEST',event_name:'CPU load is high',notify_status:'sent',ai_status:'success',severity:4,received_at:'2026-10-20 09:20:10'}];
 if(p==='/api/v1/qa-events')return [{created_at:'2026-10-20 10:12:22',question:'最近 24 小时 CPU 使用率',source:'feishu',status:'success',completed_at:'2026-10-20 10:12:50'}];
 if(p==='/api/v1/logs')return {audit:[],failed_jobs:[]};
 if(p==='/api/v1/ask')return {answer:'CPU 使用率为 15.93%。'};
 if(p==='/api/v1/test/mcp')return {ok:true,tool_count:15};
 if(p==='/api/v1/test/ai')return {ok:true,model:'gpt-6'};
 return {ok:true};
};
for(const [theme,width,height] of [['light',1440,900],['dark',1440,900],['light',375,812],['dark',375,812]]){
 const page=await browser.newPage({viewport:{width,height},colorScheme:theme});
 page.on('pageerror',err=>errors.push(err.message));
 page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text())});
 await page.route('**/api/v1/**',async route=>{
   const data=mock(route.request().url());
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
 });
 await page.goto(base,{waitUntil:'networkidle'});
 await page.waitForSelector('.stat-card');
 await page.screenshot({path:'artifacts/ui/dashboard-'+theme+'-'+width+'.png',fullPage:true});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
 assert.equal(overflow,false,theme+' '+width+' horizontal overflow');
 assert.equal(await page.locator('[onclick],[onkeydown],[style]').count(),0,'inline handlers/styles forbidden');
 assert.equal(await page.locator('h1').first().innerText(),'总览仪表盘');
 const csp=(await page.request.get(base)).headers()['content-security-policy'];
 assert.equal(csp,"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'");
 if(width===1440){
   await page.getByRole('button',{name:/接收告警.*查看明细/}).click();
   assert.equal(await page.locator('.drawer.open').count(),1);
 }
 await page.close();
}
assert.deepEqual(errors,[],'Browser console errors');
await browser.close();
console.log('UI visual screenshots and smoke tests passed');
