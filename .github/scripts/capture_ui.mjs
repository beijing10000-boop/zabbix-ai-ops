import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync } from 'node:fs';
const base='http://127.0.0.1:8765';
const browser=await chromium.launch({headless:true});
mkdirSync('screenshots',{recursive:true});
const sampleAlerts=[
 {event_id:'6100570',host_name:'DESKTOP-5Q36VUJ',event_name:'Windows: High CPU utilization',severity:3,notify_status:'sent',ai_status:'success',received_at:'2026-10-20 11:48:26'}
];
function response(url){
  const path=new URL(url).pathname;
  if(path==='/api/v1/auth/me')return {name:'Ops Admin',open_id:'ou_test',csrf:'csrf-test'};
  if(path==='/api/v1/status')return {database:'ok',redis:'ok',queues:{'ai-alerts':0,'ai-questions':0},version:'0.2.0'};
  if(path==='/api/v1/alert-stats')return {problems:187,recoveries:12,ai_analyses:12};
  if(path==='/api/v1/qa-stats')return {total:26,success:25,failed:1,pending:0,running:0};
  if(path==='/api/v1/alert-events')return sampleAlerts;
  if(path==='/api/v1/qa-events')return [{question:'查询核心交换机 CPU 使用率',source:'feishu',status:'success',created_at:'2026-10-20 11:40:00'}];
  if(path==='/api/v1/alert-mutes')return [{host_id:'10234',trigger_id:'84021',expires_at:1792522800,created_at:'2026-10-20 11:44:00'}];
  if(path==='/api/v1/settings')return {web_protocol:'https',web_public_host:'aiops.example.internal',openai_model:'gpt-6.1-sol',openai_base_url:'https://example.openai.azure.com/openai/v1/',feishu_enabled:'true',ai_min_severity:'4',lark_app_id:'cli_abc',openai_api_key:'********',mcp_token:'********'};
  if(path==='/api/v1/logs')return {audit:[],failed_jobs:[],queues:{}};
  return {};
}
let failed=false;
for(const mode of ['light','dark']){
 for(const width of [1440,375]){
  const page=await browser.newPage({viewport:{width,height:width===1440?900:812},colorScheme:mode,deviceScaleFactor:1});
  const exceptions=[];page.on('pageerror',e=>exceptions.push(e.message));
  await page.route('**/api/v1/**',async route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(response(route.request().url()))}));
  await page.goto(base+'/',{waitUntil:'networkidle'});
  await page.waitForSelector('.metric-card',{timeout:15000});
  await page.screenshot({path:'screenshots/'+mode+'-'+width+'.png',fullPage:true});
  const dims=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
  if(dims.scroll>dims.viewport){console.error('Horizontal overflow',mode,width,dims);failed=true}
  if(exceptions.length){console.error('JS errors',mode,width,exceptions);failed=true}
  const accessibility=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  const issues=accessibility.violations.filter(v=>['serious','critical'].includes(v.impact));
  if(issues.length){console.error('A11y issues',mode,width,JSON.stringify(issues.map(v=>({id:v.id,nodes:v.nodes.length,impact:v.impact}))));failed=true}
  console.log(mode,width,'rendered',dims,issues.length);
  await page.close();
 }
}
await browser.close();
if(failed)process.exitCode=1;
