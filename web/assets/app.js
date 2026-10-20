
let csrf='',settings={},currentUser={};
const title={dashboard:'总览仪表盘',config:'系统配置',debug:'连接调试',ask:'AI 诊断助手',logs:'运行日志',mutes:'告警屏蔽'};
const configGroups=[
{name:'访问',keys:['web_protocol','web_public_host']},
{name:'AI 模型',keys:['openai_base_url','openai_model','openai_api_key']},
{name:'提示词',keys:['ai_alert_prompt','ai_qa_prompt','ai_prompt']},
{name:'Zabbix MCP',keys:['mcp_url','mcp_token']},
{name:'飞书',keys:['lark_app_id','lark_app_secret','allowed_chat_ids','feishu_enabled','feishu_alert_chat_ids']},
{name:'告警策略',keys:['zabbix_webhook_secret','ai_min_severity','min_severity']}
];
const labels={web_protocol:'Web 访问协议（http / https）',web_public_host:'Web 外部访问主机（例：zabbix.example.internal:8088）',openai_base_url:'AI API Base URL',openai_model:'AI 模型',openai_api_key:'AI API Key',mcp_url:'Zabbix MCP URL',mcp_token:'只读 MCP Token',lark_app_id:'飞书 App ID',lark_app_secret:'飞书 App Secret',allowed_chat_ids:'允许群聊 ID',feishu_enabled:'飞书通知开关（true/false）',feishu_alert_chat_ids:'企业应用告警群 Chat ID（逗号分隔；留空沿用允许群聊 ID）',zabbix_webhook_secret:'Zabbix Webhook 密钥',min_severity:'旧版最低告警等级（不再过滤通知）',ai_min_severity:'AI 分析最低级别（0–5，默认4=严重）',ai_alert_prompt:'告警分析提示词',ai_qa_prompt:'主动问答提示词',ai_prompt:'旧版提示词（兼容）'};
const secrets=new Set(['openai_api_key','mcp_token','lark_app_secret','zabbix_webhook_secret']);
async function api(path,options={}){const response=await fetch(path,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...options.headers}});let data;try{data=await response.json()}catch{throw Error('HTTP '+response.status)}if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'HTTP '+response.status);return data}
function page(id){document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.id===id));document.querySelectorAll('.nav button').forEach(el=>el.classList.toggle('active',el.dataset.page===id));document.getElementById('pagetitle').textContent=title[id];if(id==='config')loadSettings();if(id==='dashboard')refreshStatus();if(id==='logs')loadLogs();if(id==='mutes')listMutes()}
async function bootstrap(){try{currentUser=await api('/api/v1/auth/me');csrf=currentUser.csrf;document.getElementById('login').style.display='none';document.getElementById('app').style.display='block';document.getElementById('username').textContent=currentUser.name;document.getElementById('avatar').textContent=(currentUser.name||'A').slice(0,1);refreshStatus();checkMuteLink();fetch('/healthz',{cache:'no-store'}).then(r=>r.json()).then(v=>{document.getElementById('app-version').textContent='版本 v'+(v.version||'未知')}).catch(()=>{document.getElementById('app-version').textContent='版本未知'})}catch(e){document.getElementById('login-error').textContent='请点击飞书账号登录。如首次配置，确认回调地址和管理员白名单。'}}
async function logout(){try{await api('/api/v1/auth/logout',{method:'POST'})}catch(e){}location.href='/'}
function markSettingsDirty(){
 const dirty=Object.keys(labels).some(key=>{
  const el=document.getElementById('field-'+key);
  return el && el.value!==(settings[key]||'');
 });
 document.getElementById('save-toolbar').hidden=!dirty;
}
function makeGroupedRow(key){
 const row=document.createElement('div');row.className='setting-row';
 const label=document.createElement('label');label.textContent=labels[key];label.htmlFor='field-'+key;
 const type=key==='feishu_enabled'?'toggle':['web_protocol','ai_min_severity'].includes(key)?'segmented':
 secrets.has(key)?'secret':['ai_alert_prompt','ai_qa_prompt','ai_prompt'].includes(key)?'prompt':'input';
 if(['toggle','segmented','secret','prompt'].includes(type)){
  const state=document.createElement('input');state.type='hidden';state.id='field-'+key;
  state.value=settings[key]||'';
  let control;
  if(type==='toggle')control=Toggle(state);
  if(type==='segmented')control=Segmented(state,key==='web_protocol'?
   [['http','HTTP'],['https','HTTPS']]:
   [['0','未分类'],['1','信息'],['2','警告'],['3','一般'],['4','严重'],['5','灾难']]);
  if(type==='secret'||type==='prompt'){
   control=document.createElement('button');control.className='setting-action';control.type='button';
   control.textContent=type==='secret'?(state.value?'已设置 · 修改':'未设置 · 修改'):'编辑 ›';
   control.addEventListener('click',()=>editSettingValue(key,state,type,control));
  }
  row.append(label,state,control);
 } else {
  const field=document.createElement('input');field.id='field-'+key;
  field.type='text';field.autocomplete='off';field.value=settings[key]||'';
  field.addEventListener('input',markSettingsDirty);
  row.append(label,field);
 }
 return row;
}
function GroupedList(group){
 const fragment=document.createDocumentFragment();
 const heading=document.createElement('h3');heading.className='grouped-heading';heading.textContent=group.name;
 const list=document.createElement('div');list.className='settings-group';
 for(const key of group.keys)list.append(makeGroupedRow(key));
 fragment.append(heading,list);return fragment;
}
function Toggle(state){
 const button=document.createElement('button');button.type='button';button.className='toggle';
 button.setAttribute('role','switch');button.setAttribute('aria-label',labels[state.id.slice(6)]);
 const render=()=>{const active=state.value==='true';button.classList.toggle('on',active);button.setAttribute('aria-checked',String(active))};
 button.addEventListener('click',()=>{state.value=state.value==='true'?'false':'true';render();markSettingsDirty()});
 render();return button;
}
function Segmented(state,choices){
 const strip=document.createElement('div');strip.className='segmented';strip.setAttribute('role','group');
 strip.setAttribute('aria-label',labels[state.id.slice(6)]);
 for(const [value,label] of choices){
  const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.value=value;
  button.setAttribute('aria-pressed',String(state.value===value));
  button.classList.toggle('selected',state.value===value);
  button.addEventListener('click',()=>{
   state.value=value;
   strip.querySelectorAll('button').forEach(el=>{
     el.classList.toggle('selected',el.dataset.value===value);
     el.setAttribute('aria-pressed',String(el.dataset.value===value));
   });
   markSettingsDirty();
  });
  strip.append(button);
 }
 return strip;
}
function editSettingValue(key,state,type,trigger){
 const overlay=document.createElement('div');overlay.className='sheet-overlay';
 const dialog=document.createElement('div');dialog.className='sheet';dialog.setAttribute('role','dialog');
 dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-label',labels[key]);
 const heading=document.createElement('h2');heading.textContent=labels[key];
 const editor=document.createElement(type==='prompt'?'textarea':'input');
 editor.className='sheet-editor';editor.value=state.value==='********'?'':state.value;
 if(type==='secret'){editor.type='password';editor.autocomplete='new-password';editor.placeholder='输入新密钥'}
 else{editor.rows=10;editor.placeholder='输入自定义提示词'}
 const actions=document.createElement('div');actions.className='sheet-actions';
 const cancel=document.createElement('button');cancel.type='button';cancel.className='secondary';cancel.textContent='取消';
 const save=document.createElement('button');save.type='button';save.className='primary';save.textContent='确定';
 const done=()=>{
  state.value=editor.value;
  if(type==='secret')trigger.textContent=state.value?'已设置 · 修改':'未设置 · 修改';
  overlay.remove();trigger.focus();markSettingsDirty();
 };
 cancel.addEventListener('click',()=>{overlay.remove();trigger.focus()});
 save.addEventListener('click',done);
 overlay.addEventListener('click',event=>{if(event.target===overlay)cancel.click()});
 overlay.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();cancel.click()}});
 actions.append(cancel,save);dialog.append(heading,editor,actions);overlay.append(dialog);document.body.append(overlay);editor.focus();
}
async function loadSettings(){
 try{
  settings=await api('/api/v1/settings');
  const fields=document.getElementById('fields');fields.replaceChildren(...configGroups.map(GroupedList));
  document.getElementById('save-toolbar').hidden=true;
 }catch(error){toast('配置读取失败：'+error.message)}
}
async function saveSettings(){const values={};for(const key of Object.keys(labels)){const el=document.getElementById('field-'+key);if(el&&el.value!==(settings[key]||''))values[key]=el.value}try{await api('/api/v1/settings',{method:'PUT',body:JSON.stringify({values})});document.getElementById('save-result').textContent='';toast('设置已保存');await loadSettings()}catch(e){document.getElementById('save-result').textContent='保存失败：'+e.message}}
async function muteAlert(){const host_id=document.getElementById('mute-host').value.trim(),trigger_id=document.getElementById('mute-trigger').value.trim(),hours=Number(document.getElementById('mute-hours').value);const out=document.getElementById('mute-result');if(!/^\d+$/.test(host_id)||!/^\d+$/.test(trigger_id)){out.textContent='请先从告警卡片打开，或填写有效数字主机 ID、触发器 ID';return}if(!await confirmAction('确认只屏蔽此主机此触发器的飞书重复告警 '+hours+' 小时？Zabbix 监控与恢复消息不受影响。'))return;try{const r=await api('/api/v1/alert-mutes',{method:'POST',body:JSON.stringify({host_id,trigger_id,hours})});out.textContent='已设置屏蔽，到期自动恢复。结束时间：'+new Date(r.expires_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}catch(e){out.textContent='屏蔽失败：'+e.message}}
async function unmuteAlert(){const host=document.getElementById('mute-host').value.trim(),trigger=document.getElementById('mute-trigger').value.trim(),out=document.getElementById('mute-result');if(!/^\d+$/.test(host)||!/^\d+$/.test(trigger)){out.textContent='请填写要解除的主机 ID 和触发器 ID';return}if(!confirm('确认立即恢复此类飞书告警通知？'))return;try{await api('/api/v1/alert-mutes/'+encodeURIComponent(host)+'/'+encodeURIComponent(trigger),{method:'DELETE'});out.textContent='已解除屏蔽，后续同类告警将正常发送'}catch(e){out.textContent='操作失败：'+e.message}}
async function listMutes(){const out=document.getElementById('mute-result');try{const rows=await api('/api/v1/alert-mutes');out.textContent=rows.length?'':'当前没有生效的屏蔽规则';const list=document.getElementById('mute-active-list');list.replaceChildren(...rows.map(x=>{const row=document.createElement('div');row.className='grouped-row';const remaining=Math.max(0,x.expires_at-Math.floor(Date.now()/1000));const hours=Math.floor(remaining/3600),mins=Math.floor(remaining%3600/60);const text=document.createElement('span');text.textContent='主机 '+x.host_id+' · 触发器 '+x.trigger_id+' · 还剩 '+hours+' 小时 '+mins+' 分';const action=document.createElement('button');action.className='text-danger';action.textContent='解除';action.addEventListener('click',()=>{document.getElementById('mute-host').value=x.host_id;document.getElementById('mute-trigger').value=x.trigger_id;unmuteAlert()});row.append(text,action);return row}))}catch(e){out.textContent=e.message}}
function checkMuteLink(){const p=new URLSearchParams(location.search),host=p.get('mute_host'),trigger=p.get('mute_trigger');if(!host||!trigger)return;page('mutes');document.getElementById('mute-host').value=host;document.getElementById('mute-trigger').value=trigger;history.replaceState(null,'',location.pathname)}
async function refreshMetrics(){try{const m=await api('/api/v1/alert-stats');document.getElementById('metric-problems').textContent=m.problems;document.getElementById('metric-recoveries').textContent=m.recoveries;document.getElementById('metric-ai').textContent=m.ai_analyses;const q=await api('/api/v1/qa-stats');document.getElementById('metric-qa').textContent=q.total;document.getElementById('metric-qa-breakdown').textContent=`成功 ${q.success} · 失败 ${q.failed} · 待完成 ${q.pending+q.running}`}catch(e){console.warn('metric load failed')}}
async function openQaMetric(){const panel=document.getElementById('qa-detail');panel.style.display='block';const body=document.getElementById('qa-detail-body');body.replaceChildren();try{const rows=await api('/api/v1/qa-events?limit=100');const sources={feishu:'飞书',web:'Web'};const statuses={pending:'待处理',running:'分析中',success:'成功',failed:'失败'};for(const row of rows){const tr=document.createElement('tr');for(const value of [row.created_at,sources[row.source]||row.source,row.question,statuses[row.status]||row.status,row.completed_at||'—',row.error_type||'—']){const td=document.createElement('td');td.textContent=value??'';tr.append(td)}body.append(tr)}if(!rows.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=6;td.textContent='暂无问答记录';tr.append(td);body.append(tr)}}catch(e){body.textContent='读取失败：'+e.message}panel.scrollIntoView({behavior:'smooth',block:'start'})}
async function openMetric(kind){const names={problems:'接收告警明细',recoveries:'接收恢复明细',ai:'自动 AI 分析明细'};document.getElementById('metric-detail-title').textContent=names[kind];document.getElementById('metric-detail').style.display='block';const body=document.getElementById('metric-detail-body');body.replaceChildren();try{const rows=await api('/api/v1/alert-events?kind='+encodeURIComponent(kind)+'&limit=100');for(const row of rows){const tr=document.createElement('tr');for(const field of ['received_at','event_id','host_name','event_name','severity','notify_status','ai_status']){const td=document.createElement('td');if(field==='severity'){const levels=['未分类','信息','警告','一般严重','严重','灾难'];const colors=['#718096','#3b82f6','#b7791f','#dd6b20','#dc2626','#a31545'];const n=Number(row[field]);td.textContent=Number.isInteger(n)&&n>=0&&n<=5?levels[n]:'未知';td.style.fontWeight='700';td.style.color=colors[n]||'#718096'}else{td.textContent=row[field]??''}tr.append(td)}body.append(tr)}if(!rows.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=7;td.textContent='暂无记录';tr.append(td);body.append(tr)}}catch(e){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=7;td.textContent='读取失败：'+e.message;tr.append(td);body.append(tr)}document.getElementById('metric-detail').scrollIntoView({behavior:'smooth',block:'nearest'})}
async function refreshStatus(){refreshMetrics();const out=document.getElementById('status-output'),debug=document.getElementById('debug-output');try{const r=await api('/api/v1/status');renderServiceHealth(r);document.getElementById('db-state').textContent=r.database==='ok'?'正常':'异常';document.getElementById('redis-state').textContent=r.redis==='ok'?'正常':'异常';document.getElementById('alert-count').textContent=r.queues?.['ai-alerts']??0;document.getElementById('qa-count').textContent=r.queues?.['ai-questions']??0;out.textContent=JSON.stringify(r,null,2);debug.textContent=out.textContent}catch(e){out.textContent=e.message;debug.textContent=e.message}}
async function testMcp(){const out=document.getElementById('debug-output');out.textContent='正在检查 MCP...';try{out.textContent=JSON.stringify(await api('/api/v1/test/mcp',{method:'POST'}),null,2)}catch(e){out.textContent='测试失败：'+e.message}}
async function testAi(){const out=document.getElementById('debug-output');out.textContent='正在调用 AI 模型...';try{out.textContent=JSON.stringify(await api('/api/v1/test/ai',{method:'POST'}),null,2)}catch(e){out.textContent='测试失败：'+e.message}}
async function askAi(){
  const btn=document.getElementById('ask-btn'),input=document.getElementById('ask-question');
  const question=input.value.trim();if(!question)return;
  const thread=document.getElementById('chat-thread');input.value='';
  const user=document.createElement('div');user.className='chat-message user';user.textContent=question;thread.append(user);
  const reply=document.createElement('div');reply.className='chat-message ai';
  reply.innerHTML='<span class="typing-dots" aria-label="正在分析"><span></span><span></span><span></span></span>';
  thread.append(reply);thread.scrollTop=thread.scrollHeight;btn.disabled=true;
  try{
    const response=await api('/api/v1/ask',{method:'POST',body:JSON.stringify({question})});
    reply.textContent=response.answer||'模型未返回分析';
  }catch(error){reply.textContent='问答失败：'+error.message}
  finally{btn.disabled=false;thread.scrollTop=thread.scrollHeight;input.focus()}
}
async function loadLogs(){try{const r=await api('/api/v1/logs');document.getElementById('queue-info').textContent=JSON.stringify(r.queues);document.getElementById('failed-jobs').textContent=JSON.stringify(r.failed_jobs,null,2);document.getElementById('log-body').replaceChildren(...r.audit.map(row=>{const tr=document.createElement('tr');[row.time,row.action,row.key].forEach(v=>{const td=document.createElement('td');td.textContent=v||'';tr.append(td)});return tr}))}catch(e){document.getElementById('failed-jobs').textContent='读取失败：'+e.message}}
bootstrap();

/* External script event delegation: no inline handlers or JavaScript URLs. */
const actionHandlers={
  page:el=>page(el.dataset.arg),
  logout:()=>logout(),
  metric:el=>openMetric(el.dataset.arg),
  'qa-metric':()=>openQaMetric(),
  'new-mute':()=>openNewMute(),
  close:el=>{document.getElementById(el.dataset.arg).style.display='none'},
  refresh:()=>refreshStatus(),mute:()=>muteAlert(),'list-mutes':()=>listMutes(),
  unmute:()=>unmuteAlert(),save:()=>saveSettings(),'load-settings':()=>loadSettings(),
  'test-mcp':()=>testMcp(),'test-ai':()=>testAi(),ask:()=>askAi(),logs:()=>loadLogs()
};
document.addEventListener('click',event=>{
  const el=event.target.closest('[data-action]');
  if(el && actionHandlers[el.dataset.action])actionHandlers[el.dataset.action](el);
});
document.addEventListener('keydown',event=>{
  if(event.key!=='Enter' && event.key!==' ')return;
  const el=event.target.closest('[role="button"][data-action]');
  if(!el)return;
  event.preventDefault();
  if(actionHandlers[el.dataset.action])actionHandlers[el.dataset.action](el);
});

/* Shared lightweight components, native JS without any external dependencies. */
function statusDot(kind,label){
 const dot=document.createElement('span');dot.className='status-dot '+kind;
 const text=document.createElement('span');text.textContent=label;
 const row=document.createElement('span');row.className='status-row';row.append(dot,text);return row;
}
function toast(message){
 const el=document.createElement('div');el.className='toast';el.role='status';el.textContent=message;
 document.body.append(el);requestAnimationFrame(()=>el.classList.add('visible'));
 setTimeout(()=>{el.classList.remove('visible');setTimeout(()=>el.remove(),260)},2500);
}
function confirmAction(message,{danger=false,confirmText='确认'}={}){
 return new Promise(resolve=>{
 const overlay=document.createElement('div');overlay.className='sheet-overlay';
 const dialog=document.createElement('div');dialog.className='sheet';dialog.role='dialog';
 dialog.setAttribute('aria-modal','true');
 const title=document.createElement('h2');title.textContent='确认操作';
 const content=document.createElement('p');content.textContent=message;
 const actions=document.createElement('div');actions.className='sheet-actions';
 const cancel=document.createElement('button');cancel.className='secondary';cancel.textContent='取消';
 const confirm=document.createElement('button');confirm.className=danger?'secondary danger':'primary';confirm.textContent=confirmText;
 actions.append(cancel,confirm);dialog.append(title,content,actions);overlay.append(dialog);document.body.append(overlay);
 const done=value=>{overlay.remove();resolve(value)};
 cancel.addEventListener('click',()=>done(false),{once:true});
 confirm.addEventListener('click',()=>done(true),{once:true});
 overlay.addEventListener('click',event=>{if(event.target===overlay)done(false)});
 overlay.addEventListener('keydown',event=>{if(event.key==='Escape')done(false)});
 confirm.focus();
 });
}
function openNewMute(){
 const panel=document.getElementById('mute-host');panel.focus();
 document.getElementById('mute-result').textContent='输入主机与触发器 ID，选择时长并确认屏蔽。';
}
document.getElementById('ask-question').addEventListener('keydown',event=>{
 if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();askAi()}
});

function renderServiceHealth(data){
 const list=document.getElementById('service-list');if(!list)return;
 const items=[
  {label:'SQLite 数据库',kind:data.database==='ok'?'green':'red',value:data.database==='ok'?'运行正常':'连接异常'},
  {label:'Redis',kind:data.redis==='ok'?'green':'red',value:data.redis==='ok'?'运行正常':'连接异常'},
  {label:'告警队列',kind:'green',value:String(data.queues?.['ai-alerts']??0)+' 项待处理'},
  {label:'问答队列',kind:'green',value:String(data.queues?.['ai-questions']??0)+' 项待处理'}
 ];
 list.replaceChildren(...items.map(item=>{
  const row=document.createElement('div');row.className='grouped-row';
  const label=document.createElement('span');label.className='service-label';
  label.append(statusDot(item.kind,item.label));
  const value=document.createElement('span');value.className='service-value';value.textContent=item.value;
  row.append(label,value);return row;
 }));
}
window.addEventListener('scroll',()=>{
 document.querySelector('.top')?.classList.toggle('scrolled',window.scrollY>40);
},{passive:true});
