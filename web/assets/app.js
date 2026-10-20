/* UI primitives — vanilla JS, no external framework or remote fonts. */
const UI=(()=>{
  const svgPaths={
    grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    settings:'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/>',
    bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9z"/><path d="M10 21h4"/>',
    chat:'<path d="M20 11.5a8.5 8.5 0 1 1-4.5-7.5"/><path d="M12 3h9v7l-3-2h-6z"/>',
    terminal:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3m6 0h4"/>',
    logs:'<path d="M6 4h12M6 9h12M6 14h12M6 19h8"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',close:'<path d="M6 6l12 12M18 6 6 18"/>',
    arrow:'<path d="m9 18 6-6-6-6"/>',check:'<path d="m5 12 4 4L19 6"/>',
    user:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    shield:'<path d="m12 2 8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/>',
    activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',refresh:'<path d="M20 11a8 8 0 1 0-2 6m2-3v-5h-5"/>',
    send:'<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    database:'<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 4 18 4 18 0V5M3 12c0 4 18 4 18 0"/>',
    cpu:'<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9zM9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4"/>'
  };
  function node(tag,cls='',text=null){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==null)e.textContent=String(text);return e}
  function icon(name){const e=document.createElementNS('http://www.w3.org/2000/svg','svg');e.setAttribute('viewBox','0 0 24 24');e.setAttribute('aria-hidden','true');e.innerHTML=svgPaths[name]||svgPaths.activity;return e}
  function Button(label,fn,variant='primary',iconName=null){const b=node('button','btn '+(variant==='primary'?'':variant));b.type='button';if(iconName)b.append(icon(iconName));b.append(document.createTextNode(label));if(fn)b.addEventListener('click',fn);return b}
  function Card(children=[],extra=''){const c=node('section','card '+extra);for(const child of children)c.append(typeof child==='string'?document.createTextNode(child):child);return c}
  function StatusDot(text,state='gray'){return node('span','status-dot '+state,text)}
  function Segmented(items,value,change){const wrap=node('div','segmented');wrap.setAttribute('role','tablist');const update=()=>{for(const child of wrap.children){child.setAttribute('aria-selected',String(child.dataset.value===String(value)))}};for(const item of items){const b=node('button','',item.label);b.type='button';b.dataset.value=item.value;b.setAttribute('role','tab');b.addEventListener('click',()=>{value=item.value;update();change(value)});wrap.append(b)}update();return wrap}
  function Toggle(value,change){const b=node('button','toggle');b.type='button';b.setAttribute('role','switch');b.setAttribute('aria-label','切换开关');const update=()=>b.setAttribute('aria-checked',String(value));b.addEventListener('click',()=>{value=!value;update();change(value)});update();return b}
  function GroupedList(rows){const list=node('div','grouped');for(const row of rows){const r=node('div','group-row'),l=node('div','leading');const texts=node('div');texts.append(node('div','row-title',row.label));if(row.help)texts.append(node('div','row-help',row.help));if(row.icon)l.append(icon(row.icon));l.append(texts);r.append(l);if(row.control)r.append(row.control);else if(row.value!==undefined)r.append(node('span','row-value',row.value));list.append(r)}return list}
  let toastTimer;
  function Toast(text,kind='success'){let bar=document.getElementById('toast');if(!bar){bar=node('div','toast');bar.id='toast';bar.setAttribute('role','status');bar.setAttribute('aria-live','polite');document.body.append(bar)}bar.replaceChildren(icon(kind==='error'?'close':'check'),document.createTextNode(text));bar.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>bar.classList.remove('show'),2500)}
  let activeSheet;
  function Sheet({title,description='',content,action='确认',danger=false,onConfirm}){if(activeSheet)activeSheet.remove();const overlay=node('div','overlay');const dialog=node('div','sheet');dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-label',title);dialog.append(node('h2','',title));if(description)dialog.append(node('p','footnote',description));if(content)dialog.append(content);const actions=node('div','sheet-actions');const close=()=>{overlay.remove();activeSheet=null};const cancel=Button('取消',close,'secondary');const ok=Button(action,async()=>{try{const result=await onConfirm?.();if(result!==false)close()}catch(e){Toast(e.message,'error')}},danger?'danger':'primary');actions.append(cancel,ok);dialog.append(actions);overlay.append(dialog);document.body.append(overlay);activeSheet=overlay;overlay.addEventListener('click',e=>{if(e.target===overlay)close()});const key=e=>{if(e.key==='Escape'){close();document.removeEventListener('keydown',key)}};document.addEventListener('keydown',key);cancel.focus();return {close,dialog}}
  function Drawer(title,content){const old=document.getElementById('ui-drawer');if(old)old.remove();document.getElementById('ui-drawer-mask')?.remove();const mask=node('div','drawer-mask');mask.id='ui-drawer-mask';const d=node('aside','drawer');d.id='ui-drawer';d.setAttribute('role','dialog');d.setAttribute('aria-modal','true');d.setAttribute('aria-label',title);const top=node('div','drawer-top');top.append(node('h2','',title),Button('关闭',()=>{d.classList.remove('open');setTimeout(()=>{d.remove();mask.remove()},250)},'secondary','close'));d.append(top,content);document.body.append(mask,d);mask.addEventListener('click',()=>top.lastChild.click());requestAnimationFrame(()=>d.classList.add('open'));top.lastChild.focus();return d}
  function LargeTitle(text,subtitle){const wrap=node('div','page-head');wrap.append(node('h1','',text));if(subtitle)wrap.append(node('p','footnote',subtitle));return wrap}
  function Sidebar(items,selected,fn){const nav=node('nav');for(const item of items){const b=node('button','nav-item');b.type='button';b.dataset.page=item.id;if(item.id===selected)b.setAttribute('aria-current','page');b.append(icon(item.icon),document.createTextNode(item.label));b.addEventListener('click',()=>fn(item.id));nav.append(b)}return nav}
  return {node,icon,Button,Card,StatusDot,Segmented,Toggle,GroupedList,Toast,Sheet,Drawer,LargeTitle,Sidebar}
})();


/* Console application: delegated events and native API integration. */
const PAGES=[
 {id:'dashboard',label:'总览',title:'总览仪表盘',icon:'grid'},
 {id:'config',label:'配置',title:'系统配置',icon:'settings'},
 {id:'mutes',label:'屏蔽',title:'告警屏蔽',icon:'bell'},
 {id:'debug',label:'调试',title:'连接调试',icon:'terminal'},
 {id:'ask',label:'AI 助手',title:'AI 诊断助手',icon:'chat'},
 {id:'logs',label:'日志',title:'运行日志',icon:'logs'}
];
const CONFIG_GROUPS=[
 {name:'访问',keys:['web_protocol','web_public_host']},
 {name:'AI 模型',keys:['openai_base_url','openai_model','openai_api_key']},
 {name:'提示词',keys:['ai_alert_prompt','ai_qa_prompt']},
 {name:'Zabbix MCP',keys:['mcp_url','mcp_token']},
 {name:'飞书',keys:['lark_app_id','lark_app_secret','allowed_chat_ids','feishu_enabled','feishu_alert_chat_ids']},
 {name:'告警策略',keys:['ai_min_severity','zabbix_webhook_secret']}
];
const LABELS={
 web_protocol:'Web 访问协议',web_public_host:'外部访问主机',
 openai_base_url:'API Base URL',openai_model:'AI 模型',openai_api_key:'AI API Key',
 ai_alert_prompt:'告警分析提示词',ai_qa_prompt:'AI 问答提示词',
 mcp_url:'只读 MCP URL',mcp_token:'只读 MCP Token',
 lark_app_id:'飞书 App ID',lark_app_secret:'飞书 App Secret',
 allowed_chat_ids:'允许问答的群 ID',feishu_enabled:'启用飞书通知',
 feishu_alert_chat_ids:'告警通知群 ID',
 ai_min_severity:'自动分析级别',zabbix_webhook_secret:'Zabbix Webhook 密钥'
};
const HELP={
 web_protocol:'生产推荐 HTTPS 反向代理',web_public_host:'例如 aiops.example.internal',
 openai_base_url:'支持 Azure OpenAI Responses API',openai_model:'填写已部署的模型名称',
 openai_api_key:'来自 Azure / 模型服务平台',mcp_url:'仅连接只读 Zabbix MCP 服务',
 mcp_token:'从只读 MCP 服务中获取',lark_app_id:'飞书开放平台 → 企业自建应用',
 lark_app_secret:'飞书应用凭据',allowed_chat_ids:'多个群用逗号分隔',
 feishu_alert_chat_ids:'留空则沿用问答允许群 ID',
 zabbix_webhook_secret:'与 Zabbix 媒介类型 secret 一致'
};
const SECRETS=new Set(['openai_api_key','mcp_token','lark_app_secret','zabbix_webhook_secret']);
const PROMPTS=new Set(['ai_alert_prompt','ai_qa_prompt']);
const SEVERITIES=['未分类','信息','警告','一般严重','严重','灾难'];
const appState={user:null,csrf:'',page:'dashboard',settings:{},pending:{},dirty:false,chat:[],logMode:'audit',health:null};
const $=id=>document.getElementById(id);
const n=UI.node;
const formatDuration=seconds=>{
 const n=Math.max(0,Math.floor(seconds));
 if(n>=86400)return Math.floor(n/86400)+'天 '+Math.floor(n%86400/3600)+'小时';
 if(n>=3600)return Math.floor(n/3600)+'小时 '+Math.floor(n%3600/60)+'分';
 if(n>=60)return Math.floor(n/60)+'分';
 return n+'秒';
};
async function api(path,options={}){
 const headers={'Accept':'application/json'};
 if(options.body!==undefined)headers['Content-Type']='application/json';
 if(appState.csrf)headers['X-CSRF-Token']=appState.csrf;
 const response=await fetch(path,{credentials:'same-origin',cache:'no-store',...options,headers:{...headers,...options.headers}});
 const raw=await response.text();
 let data;try{data=raw?JSON.parse(raw):{}}catch{throw Error('服务器响应不是有效 JSON')}
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'请求失败（HTTP '+response.status+'）');
 return data;
}
function setVisibleLoggedIn(yes){$('login-view').hidden=yes;$('app-shell').hidden=!yes}
function showLogin(){
 setVisibleLoggedIn(false);
 $('login-action').addEventListener('click',()=>location.assign('/api/v1/auth/login'),{once:true});
}
function clear(el){el.replaceChildren()}
function currentTitle(){return PAGES.find(x=>x.id===appState.page)?.title||'Zabbix AI Ops'}
function heading(parent,title,extra=null){
 const h=n('div','section-heading');h.append(n('h2','',title));if(extra)h.append(extra);parent.append(h);return h;
}
function showFailure(e){UI.Toast(e.message||String(e),'error')}
function setPage(id){
 if(!PAGES.some(x=>x.id===id))id='dashboard';
 appState.page=id;
 $('page-title').textContent=currentTitle();$('frosted-title').textContent=currentTitle();
 $('page-subtitle').textContent=({
  dashboard:'告警态势 · 服务运行状态',config:'应用服务与连接设置',
  mutes:'只停止飞书重复通知，不修改 Zabbix',
  debug:'检查 Redis、只读 MCP 与模型可用性',
  ask:'基于只读 Zabbix MCP 的实时问答',
  logs:'审计记录与失败任务'
 })[id]||'';
 renderNavigation();
 clear($('page-content'));
 const renderers={dashboard:renderDashboard,config:renderConfig,mutes:renderMutes,debug:renderDebug,ask:renderAsk,logs:renderLogs};
 renderers[id]();
 window.scrollTo({top:0,behavior:'instant'});
}
function renderNavigation(){
 const host=$('desktop-navigation');clear(host);
 host.append(UI.Sidebar(PAGES,appState.page,setPage));
 const mobile=$('mobile-navigation');clear(mobile);
 for(const item of PAGES.slice(0,5)){
  const b=n('button','tab');b.type='button';b.dataset.page=item.id;
  if(item.id===appState.page)b.setAttribute('aria-current','page');
  b.append(UI.icon(item.icon),n('span','',item.label));b.addEventListener('click',()=>setPage(item.id));mobile.append(b);
 }
}
function statCard(label,value,iconName,detail){
 const top=n('div','stat-top');top.append(n('span','',label),UI.icon(iconName));
 const number=n('strong','stat-num nums',value);
 const card=UI.Card([top,number],'stat-card'+(detail?' actionable':''));
 if(detail){card.setAttribute('aria-label',label+'：查看明细');const btn=n('button','stat-card actionable');
  btn.type='button';btn.append(...card.childNodes);btn.addEventListener('click',detail);return btn;}
 return card;
}
async function renderDashboard(){
 const page=$('page-content'),a=n('div','cards-4'),b=n('div','cards-4');page.append(a);
 for(const label of ['数据库','Redis','告警队列','问答队列'])a.append(statCard(label,'—','activity'));
 heading(page,'事件统计');
 page.append(b);
 for(const label of ['接收告警','接收恢复','自动 AI 分析','AI 问答'])b.append(statCard(label,'—','activity'));
 heading(page,'服务健康');
 const healthHost=n('div','grouped');page.append(healthHost);
 const details=n('details','code-details');const summary=n('summary','','显示详细信息');const pre=n('pre','mono','加载中…');
 details.append(summary,pre);page.append(details);
 try{
  const [status,alerts,qa]=await Promise.all([api('/api/v1/status'),api('/api/v1/alert-stats'),api('/api/v1/qa-stats')]);
  if(appState.page!=='dashboard')return;
  appState.health=status;clear(a);clear(b);
  const vals=[
   ['数据库',status.database==='ok'?'正常':'异常','database'],
   ['Redis',status.redis==='ok'?'正常':'异常','activity'],
   ['告警队列',status.queues?.['ai-alerts']??0,'bell'],
   ['问答队列',status.queues?.['ai-questions']??0,'chat']
  ];
  vals.forEach(([name,value,ico])=>a.append(statCard(name,value,ico)));
  b.append(
   statCard('接收告警',alerts.problems??0,'bell',()=>openMetric('problems')),
   statCard('接收恢复',alerts.recoveries??0,'check',()=>openMetric('recoveries')),
   statCard('自动 AI 分析',alerts.ai_analyses??0,'cpu',()=>openMetric('ai')),
   statCard('AI 问答',qa.total??0,'chat',()=>openMetric('qa'))
  );
  clear(healthHost);
  healthHost.append(UI.GroupedList([
   {label:'数据库',control:UI.StatusDot(status.database==='ok'?'正常':'异常',status.database==='ok'?'green':'red'),icon:'database'},
   {label:'Redis',control:UI.StatusDot(status.redis==='ok'?'正常':'异常',status.redis==='ok'?'green':'red'),icon:'activity'},
   {label:'后端版本',value:'v'+(status.version||'未知'),icon:'cpu'}
  ]));
  pre.textContent=JSON.stringify(status,null,2);
  $('backend-version').textContent='版本 v'+(status.version||'未知');
 }catch(e){UI.Toast('状态加载失败：'+e.message,'error')}
}
async function openMetric(kind){
 const title={problems:'接收告警',recoveries:'接收恢复',ai:'自动 AI 分析',qa:'AI 问答'}[kind];
 const container=n('div','detail-list');container.append(n('p','footnote','正在读取最近 100 条记录…'));
 UI.Drawer(title+'明细',container);
 try{
  const rows=await api(kind==='qa'?'/api/v1/qa-events?limit=100':'/api/v1/alert-events?kind='+kind+'&limit=100');
  clear(container);
  if(!rows.length){container.append(n('p','footnote','暂无记录'));return}
  for(const item of rows){
   const cell=n('div','detail-entry');
   const hd=n('div','entry-head');hd.append(n('span','',item.received_at||item.created_at||'—'),
                n('span','',kind==='qa'?(item.status||'—'):(item.notify_status||'—')));
   cell.append(hd);
   cell.append(n('p','',kind==='qa'?item.question:(item.host_name||'未知主机')+' · '+(item.event_name||'未知告警')));
   cell.append(n('p','footnote',kind==='qa'?'来源：'+(item.source==='feishu'?'飞书':'Web')+' · 完成：'+(item.completed_at||'—'):
     '事件 '+item.event_id+' · 级别 '+SEVERITIES[Number(item.severity)]+' · AI '+item.ai_status));
   container.append(cell);
  }
 }catch(e){container.replaceChildren(n('p','footnote',e.message))}
}
function markSetting(key,value){
 if(appState.settings[key]===value){delete appState.pending[key]}else appState.pending[key]=value;
 appState.dirty=Object.keys(appState.pending).length>0;
 renderSaveActions();
}
function renderSaveActions(){
 $('save-actions').hidden=!appState.dirty;
}
function configControl(key){
 const value=Object.hasOwn(appState.pending,key)?appState.pending[key]:appState.settings[key];
 if(key==='feishu_enabled')return UI.Toggle(value==='true',v=>markSetting(key,v?'true':'false'));
 if(key==='web_protocol')return UI.Segmented([{label:'HTTP',value:'http'},{label:'HTTPS',value:'https'}],value,v=>markSetting(key,v));
 if(key==='ai_min_severity')return UI.Segmented(SEVERITIES.map((x,i)=>({label:x,value:String(i)})),String(value??'4'),v=>markSetting(key,v));
 const button=UI.Button(SECRETS.has(key)?((value&&value!=='')?'已设置 · 修改':'未设置 · 修改'):
   (PROMPTS.has(key)?'编辑 ›':(String(value||'').slice(0,26)||'设置')+' ›'),
   ()=>openConfigSheet(key,value),'text');
 return button;
}
function openConfigSheet(key,value){
 const wrap=n('div','form-stack'),label=n('label','form-label',LABELS[key]||key);
 const control=PROMPTS.has(key)?n('textarea','field'):n('input','field');
 if(!PROMPTS.has(key))control.type=SECRETS.has(key)?'password':'text';
 control.id='sheet-setting-input';
 control.value=SECRETS.has(key)?'':String(value||'');
 control.placeholder=SECRETS.has(key)?'留空不会覆盖现有密钥':'请输入配置值';
 label.htmlFor=control.id;wrap.append(label,control);
 UI.Sheet({title:LABELS[key]||key,description:HELP[key]||'',content:wrap,action:'应用修改',onConfirm:()=>{
  const text=control.value;
  if(SECRETS.has(key)&&!text)return true;
  markSetting(key,text);
  renderConfig();
  return true;
 }});
}
async function renderConfig(){
 const page=$('page-content');clear(page);
 if(!Object.keys(appState.settings).length){
  page.append(n('p','footnote','正在加载配置…'));
  try{appState.settings=await api('/api/v1/settings')}catch(e){showFailure(e);return}
  if(appState.page!=='config')return;clear(page);
 }
 for(const group of CONFIG_GROUPS){
  const name=n('div','group-title',group.name);page.append(name);
  page.append(UI.GroupedList(group.keys.map(key=>({
    label:LABELS[key]||key,help:HELP[key]||'',control:configControl(key)
  }))));
 }
 heading(page,'其他操作');
 const extras=UI.GroupedList([{label:'运行日志',help:'查看审计和失败任务',control:UI.Button('查看 ›',()=>setPage('logs'),'text'),icon:'logs'}]);
 page.append(extras);
 renderSaveActions();
}
async function saveSettings(){
 if(!appState.dirty)return;
 try{
  await api('/api/v1/settings',{method:'PUT',body:JSON.stringify({values:appState.pending})});
  appState.settings={...appState.settings,...appState.pending};
  for(const key of SECRETS)if(key in appState.pending)appState.settings[key]='********';
  appState.pending={};appState.dirty=false;renderSaveActions();renderConfig();
  UI.Toast('设置已保存');
 }catch(e){showFailure(e)}
}
function resetSettings(){appState.pending={};appState.dirty=false;renderSaveActions();renderConfig();UI.Toast('已还原未保存修改')}
async function renderMutes(){
 const page=$('page-content');clear(page);
 const add=UI.Button('新建屏蔽',showNewMute,'primary','plus');
 heading(page,'当前生效的屏蔽',add);
 const host=n('div','grouped');host.append(n('div','group-row','','读取中…'));page.append(host);
 page.append(n('p','footnote','仅影响飞书新问题告警及配对的恢复通知，不修改 Zabbix 监控规则。'));
 try{
  const rows=await api('/api/v1/alert-mutes');clear(host);
  if(appState.page!=='mutes')return;
  if(!rows.length){host.append(n('div','group-row','','当前没有生效的屏蔽'));return}
  for(const item of rows){
   const mins=Math.max(0,Number(item.expires_at)*1000-Date.now())/1000;
   const b=UI.Button('解除',()=>confirmUnmute(item),'danger');
   const group=UI.GroupedList([{label:'主机 '+item.host_id+' · 触发器 '+item.trigger_id,
     help:'剩余 '+formatDuration(mins),control:b,icon:'clock'}]);
   host.append(...group.childNodes);
  }
 }catch(e){host.replaceChildren(n('div','group-row','',e.message))}
}
function showNewMute(){
 let hours=1;
 const wrap=n('div','form-stack');
 const label1=n('label','form-label','主机 ID'),input1=n('input','field');
 input1.placeholder='Zabbix 数字主机 ID';input1.inputMode='numeric';wrap.append(label1,input1);
 const label2=n('label','form-label','触发器 ID'),input2=n('input','field');
 input2.placeholder='Zabbix 数字触发器 ID';input2.inputMode='numeric';wrap.append(label2,input2);
 wrap.append(n('label','form-label','屏蔽时长'));
 wrap.append(UI.Segmented([{label:'1小时',value:1},{label:'4小时',value:4},{label:'1天',value:24},{label:'3天',value:72},{label:'7天',value:168}],1,v=>hours=v));
 UI.Sheet({title:'新建告警屏蔽',description:'Zabbix 会继续正常产生事件；只有飞书通知会暂时屏蔽。',content:wrap,action:'开始屏蔽',onConfirm:async()=>{
  const host_id=input1.value.trim(),trigger_id=input2.value.trim();
  if(!/^\d{1,20}$/.test(host_id)||!/^\d{1,20}$/.test(trigger_id)){UI.Toast('请输入有效的数字 ID','error');return false}
  await api('/api/v1/alert-mutes',{method:'POST',body:JSON.stringify({host_id,trigger_id,hours})});
  UI.Toast('已设置屏蔽');renderMutes();return true;
 }});
}
function confirmUnmute(item){
 UI.Sheet({title:'解除告警屏蔽',description:'将立即恢复此主机、此触发器的新问题告警推送。',action:'解除屏蔽',danger:true,onConfirm:async()=>{
  await api('/api/v1/alert-mutes/'+encodeURIComponent(item.host_id)+'/'+encodeURIComponent(item.trigger_id),{method:'DELETE'});
  UI.Toast('已解除屏蔽');renderMutes();return true;
 }});
}
async function renderDebug(){
 const page=$('page-content');clear(page);
 page.append(n('div','group-title','连接测试'));
 const rows=n('div','grouped');page.append(rows);
 const tests=[
  {key:'redis',label:'Redis',help:'数据库连接与缓存队列',path:'/api/v1/status',method:'GET'},
  {key:'mcp',label:'Zabbix MCP',help:'发现只读监控工具',path:'/api/v1/test/mcp',method:'POST'},
  {key:'ai',label:'AI 模型',help:'验证 Responses API 调用',path:'/api/v1/test/ai',method:'POST'}
 ];
 for(const entry of tests){
  const row=n('div','group-row'),leading=n('div','leading');
  const label=n('div');label.append(n('div','row-title',entry.label),n('div','row-help',entry.help));leading.append(UI.icon('activity'),label);row.append(leading);
  const status=n('span','footnote','未测试'),btn=UI.Button('测试',async()=>{
   const begin=performance.now();btn.disabled=true;btn.replaceChildren(n('span','loader'));status.textContent='测试中…';
   try{
    const data=await api(entry.path,{method:entry.method});
    const duration=((performance.now()-begin)/1000).toFixed(2);
    status.replaceChildren(UI.StatusDot('成功 · '+duration+'秒','green'));
    let detail=row.nextSibling;
    if(detail?.classList?.contains('test-result'))detail.remove();
    detail=n('details','code-details test-result');detail.append(n('summary','','查看详细信息'),n('pre','mono',JSON.stringify(data,null,2)));
    rows.insertBefore(detail,row.nextSibling);
   }catch(e){const duration=((performance.now()-begin)/1000).toFixed(2);status.replaceChildren(UI.StatusDot('失败 · '+duration+'秒','red'));UI.Toast(e.message,'error')}
   finally{btn.replaceChildren(document.createTextNode('测试'));btn.disabled=false}
  },'secondary');
  row.append(status,btn);rows.append(row);
 }
}
function renderAsk(){
 const page=$('page-content');clear(page);
 const shell=n('section','chat-shell'),history=n('div','chat-history'),form=n('form','chat-input');
 history.setAttribute('aria-live','polite');history.id='chat-history';
 if(!appState.chat.length){const hello=n('div','bubble ai','你好，我是你的只读 Zabbix 运维助手。可以查询主机状态、告警和性能趋势。');history.append(hello)}
 for(const msg of appState.chat){const bubble=n('div','bubble '+msg.role,msg.text);history.append(bubble)}
 const input=n('textarea','field');input.placeholder='询问主机 CPU、当前告警、历史趋势…';input.rows=1;input.setAttribute('aria-label','输入问题');
 input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
 const send=UI.Button('发送',null,'primary','send');send.type='submit';
 form.append(input,send);shell.append(history,form);page.append(shell);
 form.addEventListener('submit',async e=>{
  e.preventDefault();const question=input.value.trim();if(!question)return;
  input.value='';input.disabled=true;send.disabled=true;
  appState.chat.push({role:'user',text:question});
  history.append(n('div','bubble user',question));
  const waiting=n('div','bubble ai');const dots=n('span','typing');
  for(let i=0;i<3;i++)dots.append(n('b'));
  waiting.append(dots);history.append(waiting);history.scrollTop=history.scrollHeight;
  try{
   const answer=await api('/api/v1/ask',{method:'POST',body:JSON.stringify({question})});
   const text=answer.answer||'未返回内容';appState.chat.push({role:'ai',text});
   waiting.textContent=text;
  }catch(err){const text='请求失败：'+err.message;appState.chat.push({role:'ai',text});waiting.textContent=text}
  finally{input.disabled=false;send.disabled=false;input.focus();history.scrollTop=history.scrollHeight}
 });
}
async function renderLogs(){
 const page=$('page-content');clear(page);
 const header=n('div','section-heading');header.append(n('h2','','运行记录'));
 header.append(UI.Segmented([{label:'审计',value:'audit'},{label:'失败任务',value:'failed'}],appState.logMode,v=>{appState.logMode=v;renderLogs()}));page.append(header);
 const container=n('div','grouped');container.append(n('div','group-row','','正在读取…'));page.append(container);
 try{
  const data=await api('/api/v1/logs');clear(container);if(appState.page!=='logs')return;
  if(appState.logMode==='audit'){
   const days=new Map();
   for(const item of data.audit||[]){const day=(item.time||'未知日期').slice(0,10);if(!days.has(day))days.set(day,[]);days.get(day).push(item)}
   if(!days.size){container.append(n('div','group-row','','暂无审计记录'));return}
   for(const [day,items] of days){const dayTitle=n('div','group-title',day);container.append(dayTitle);
    for(const x of items){const row=n('div','group-row');const div=n('div','leading');
     const info=n('div');info.append(n('div','row-title',x.action),n('div','row-help',x.key||''));
     div.append(UI.icon('logs'),info);row.append(div,n('span','row-value nums',(x.time||'').slice(11)));container.append(row)}
   }
  }else{
   if(!data.failed_jobs?.length){container.append(n('div','group-row','','暂无失败任务'));return}
   for(const job of data.failed_jobs){const row=n('div','group-row');row.append(n('span','row-title',job.queue),n('span','row-value mono',job.id));container.append(row)}
  }
 }catch(e){container.replaceChildren(n('div','group-row','',e.message))}
}
async function signOut(){
 try{await api('/api/v1/auth/logout',{method:'POST'})}catch(e){UI.Toast(e.message,'error')}
 location.assign('/');
}
function initHeader(user){
 $('user-name').textContent=user.name||'管理员';
 $('user-avatar').textContent=(user.name||'A').slice(0,1).toUpperCase();
 $('signout').addEventListener('click',signOut);
 $('save-reset').addEventListener('click',resetSettings);
 $('save-submit').addEventListener('click',saveSettings);
 const onScroll=()=>$('frosted-title').classList.toggle('visible',window.scrollY>40);
 window.addEventListener('scroll',onScroll,{passive:true});
 const query=new URLSearchParams(location.search);
 const host=query.get('mute_host'),trigger=query.get('mute_trigger');
 if(/^\d{1,20}$/.test(host||'')&&/^\d{1,20}$/.test(trigger||'')){
  setPage('mutes');
  history.replaceState(null,'',location.pathname);
  setTimeout(()=>showNewMute(),200);
 }else setPage('dashboard');
}
async function bootstrap(){
 try{
  const user=await api('/api/v1/auth/me');appState.user=user;appState.csrf=user.csrf||'';
  setVisibleLoggedIn(true);initHeader(user);
 }catch{showLogin()}
}
bootstrap();
