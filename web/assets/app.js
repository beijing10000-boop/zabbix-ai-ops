"use strict";
const $=id=>document.getElementById(id);
const state={csrf:"",user:null,page:"dashboard",status:null,settings:{},baseline:{},draft:{},chat:[],toastTimer:null,logsTab:"audit"};
const NAV=[
 {id:"dashboard",label:"总览",icon:"layout-dashboard",hint:"系统状态与告警概况"},
 {id:"config",label:"系统设置",icon:"settings",hint:"连接、模型、飞书与告警策略"},
 {id:"mutes",label:"告警屏蔽",icon:"bell-off",hint:"管理当前暂停的同类飞书通知"},
 {id:"debug",label:"连接调试",icon:"activity",hint:"诊断服务、MCP 与 AI 连通性"},
 {id:"ask",label:"AI 助手",icon:"message-circle",hint:"通过只读 MCP 查询运维问题"},
 {id:"logs",label:"运行日志",icon:"list",hint:"操作审计与失败任务"}
];
const ICONS={
 "layout-dashboard":['rect:3,3,7,7,1','rect:14,3,7,7,1','rect:3,14,7,7,1','rect:14,14,7,7,1'],
 settings:['circle:12,12,3','path:M12 2v3 M12 19v3 M4.93 4.93l2.12 2.12 M16.95 16.95l2.12 2.12 M2 12h3 M19 12h3 M4.93 19.07l2.12-2.12 M16.95 7.05l2.12-2.12'],
 "bell-off":['path:M13 5a7 7 0 0 1 7 7c0 3 1 4 2 5H6 M10 5A7 7 0 0 0 4 12c0 3-1 4-2 5h2 M10 21h4 M2 2l20 20'],
 activity:['path:M2 12h4l3-7 5 14 3-7h5'],
 "message-circle":['path:M21 11.5a8.4 8.4 0 0 1-.9 3.8A8.5 8.5 0 0 1 12.5 20a8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7A8.4 8.4 0 0 1 4 11.5a8.5 8.5 0 0 1 8.5-8.5A8.5 8.5 0 0 1 21 11.5Z'],
 list:['path:M8 6h13 M8 12h13 M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01'],
 chevron:['path:m9 18 6-6-6-6'],arrow:['path:M5 12h14 M13 6l6 6-6 6'],plus:['path:M12 5v14 M5 12h14'],
 "shield-check":['path:M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z M9 12l2 2 4-4'],
 "clock":['circle:12,12,9','path:M12 7v5l3 2'],
 send:['path:M22 2 11 13 M22 2 15 22l-4-9-9-4 20-7Z']
};
function el(tag,cls,text){const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=String(text);return x}
function icon(name){
 const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
 svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("fill","none");svg.setAttribute("stroke","currentColor");
 svg.setAttribute("stroke-width","1.75");svg.setAttribute("stroke-linecap","round");svg.setAttribute("stroke-linejoin","round");svg.setAttribute("aria-hidden","true");
 for(const shape of ICONS[name]||ICONS.chevron){
   const [kind,attr]=shape.split(":");const node=document.createElementNS("http://www.w3.org/2000/svg",kind==="rect"?"rect":kind==="circle"?"circle":"path");
   if(kind==="path")node.setAttribute("d",attr);
   else{const v=attr.split(",");(kind==="rect"?["x","y","width","height","rx"]:["cx","cy","r"]).forEach((k,i)=>node.setAttribute(k,v[i]))}
   svg.append(node);
 }return svg
}
function button(text,handler,kind="secondary",cls=""){
 const b=el("button","btn "+(kind==="primary"?"btn-primary":kind==="danger"?"btn-danger":kind==="text"?"btn-text":"")+" "+cls,text);
 b.type="button";if(handler)b.addEventListener("click",handler);return b
}
function group(rows){const box=el("div","group");rows.forEach(row=>box.append(row));return box}
function row(label,value,options={}){
 const wrap=el(options.onClick?"button":"div","group-row"+(options.onClick?" button-row":""));
 if(options.onClick){wrap.type="button";wrap.addEventListener("click",options.onClick)}
 const name=el("span","row-title",label);wrap.append(name);
 if(value!==null&&value!==undefined){wrap.append(value instanceof Node?value:el("span","row-value",value))}
 if(options.onClick){wrap.append(el("span","row-chevron","›"))}
 return wrap
}
function card(title,value,extra){const c=el("article","card");c.append(el("p","card-title",title));const v=el("div","card-number",value);c.append(v);if(extra)c.append(extra);return c}
function statusDot(text,tone){const c=el("span","card-status");c.append(el("span","status-dot dot-"+tone),el("span","",text));return c}
function sectionTitle(title){return el("h2","section-title",title)}
function segmented(options,selected,onChange){const box=el("div","segmented scrollable");box.setAttribute("role","group");options.forEach(opt=>{
 const b=el("button","segment",opt.label);b.type="button";b.setAttribute("aria-pressed",String(selected===opt.value));
 b.addEventListener("click",()=>{selected=opt.value;box.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));onChange(opt.value)});
 box.append(b);
});return box}
function toggle(checked,onChange,label){const b=el("button","switch");b.type="button";b.setAttribute("role","switch");b.setAttribute("aria-checked",String(checked));b.setAttribute("aria-label",label);b.addEventListener("click",()=>{checked=!checked;b.setAttribute("aria-checked",String(checked));onChange(checked)});return b}
function toast(message){const t=$("toast");clearTimeout(state.toastTimer);t.textContent=message;t.hidden=false;state.toastTimer=setTimeout(()=>t.hidden=true,2500)}
async function api(path,options={}){const headers={"Content-Type":"application/json","X-CSRF-Token":state.csrf,...(options.headers||{})};const res=await fetch(path,{credentials:"same-origin",...options,headers});const raw=await res.text();let data;try{data=JSON.parse(raw)}catch{throw Error("HTTP "+res.status)}if(!res.ok)throw Error(typeof data.detail==="string"?data.detail:"HTTP "+res.status);return data}
function showSheet(title,content,confirmText,onConfirm,kind="primary"){
 $("sheet-title").textContent=title;$("sheet-content").replaceChildren(content);
 const cancel=button("取消",closeSheet);const confirm=button(confirmText,async()=>{
  try{const result=await onConfirm();if(result!==false)closeSheet()}catch(e){toast("操作失败："+e.message)}
 },kind);
 $("sheet-actions").replaceChildren(cancel,confirm);$("overlay").hidden=false;
 const focus=content.querySelector("input,textarea,button,select")||confirm;focus.focus();
}
function closeSheet(){$("overlay").hidden=true;$("sheet-content").replaceChildren()}
function openDrawer(title,content){$("drawer-title").textContent=title;$("drawer-body").replaceChildren(content);$("drawer-overlay").hidden=false;$("drawer-close").focus()}
function closeDrawer(){$("drawer-overlay").hidden=true;$("drawer-body").replaceChildren()}
function navButton(item,compact=false){const b=el("button",compact?"tab-item":"nav-item");b.dataset.page=item.id;b.type="button";b.append(icon(item.icon),el("span","",item.label));b.setAttribute("aria-label",item.label);b.addEventListener("click",()=>navigate(item.id));return b}
function renderNav(){const side=$("sidebar-nav"),mobile=$("mobile-nav");side.replaceChildren(...NAV.map(x=>navButton(x)));mobile.replaceChildren(...NAV.filter(x=>x.id!=="debug").map(x=>navButton(x,true)));updateNav()}
function updateNav(){document.querySelectorAll("[data-page]").forEach(x=>{const active=x.dataset.page===state.page;x.classList.toggle("selected",active);if(active)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current")})}
function navigate(id){const n=NAV.find(x=>x.id===id);if(!n)return;state.page=id;updateNav();$("large-title").textContent=n.label;$("compact-title").textContent=n.label;$("page-description").textContent=n.hint;window.scrollTo({top:0,behavior:"instant"});const pages={dashboard,config,mutes,debug,ask,logs};pages[id]()}
async function bootstrap(){try{state.user=await api("/api/v1/auth/me");state.csrf=state.user.csrf||"";$("login").hidden=true;$("app").hidden=false;$("username").textContent=state.user.name||"管理员";renderNav();navigate("dashboard");try{const h=await api("/healthz");$("app-version").textContent="版本 v"+(h.version||"未知")}catch{$("app-version").textContent="版本未知"}}catch{$("login-error").textContent="请使用已授权的飞书管理员账号登录"}}
function metricCard(label,value,kind){const c=card(label,value);c.classList.add("metric");c.type="button";const b=el("button","metric-arrow");b.type="button";b.setAttribute("aria-label","查看"+label+"明细");b.append(el("span","hint","查看明细"),icon("chevron"));b.addEventListener("click",()=>detail(kind,label));c.append(b);return c}
async function dashboard(){
 const root=$("page-content");const health=el("div","card-grid");const metrics=el("div","card-grid");
 const statusCards=["数据库","Redis","告警队列","问答队列"].map(label=>card(label,"—",statusDot("检查中","gray")));health.append(...statusCards);
 root.replaceChildren(sectionTitle("服务状态"),health,sectionTitle("告警与分析"),metrics,sectionTitle("服务健康"));
 const sys=group([row("服务状态","加载中…")]);root.append(sys);
 const details=document.createElement("details");details.className="group";const summary=el("summary","","显示详细信息");const pre=el("pre");details.append(summary,pre);root.append(el("div","spacer"),details);
 try{
  const [s,a,q]=await Promise.all([api("/api/v1/status"),api("/api/v1/alert-stats"),api("/api/v1/qa-stats")]);
  state.status=s;
  const values=[s.database==="ok"?"正常":"异常",s.redis==="ok"?"正常":"异常",s.queues?.["ai-alerts"]??0,s.queues?.["ai-questions"]??0];
  statusCards.forEach((c,i)=>{c.querySelector(".card-number").textContent=values[i];c.querySelector(".card-status").replaceWith(statusDot(i<2?(values[i]==="正常"?"运行正常":"服务异常"):(values[i]?"正在处理":"无待处理任务"),i<2?(values[i]==="正常"?"green":"red"):(values[i]?"orange":"green")))});
  metrics.replaceChildren(metricCard("接收告警",a.problems,"problems"),metricCard("接收恢复",a.recoveries,"recoveries"),metricCard("自动 AI 分析",a.ai_analyses,"ai"),metricCard("AI 问答",q.total,"qa"));
  sys.replaceChildren(row("数据库",s.database==="ok"?"正常":"异常"),row("Redis",s.redis==="ok"?"正常":"异常"),row("只读 MCP 安全模式","系统仅使用只读 MCP，不修改 Zabbix"),row("刷新状态","›",{onClick:dashboard}));
  pre.textContent=JSON.stringify(s,null,2);
 }catch(e){toast("加载监控数据失败："+e.message);sys.replaceChildren(row("无法读取运行状态",e.message))}
}
async function detail(kind,title){const root=el("div");root.append(el("p","section-caption","按时间倒序，最近 100 条记录"));openDrawer(title,root);
 try{const records=await api(kind==="qa"?"/api/v1/qa-events?limit=100":"/api/v1/alert-events?kind="+encodeURIComponent(kind)+"&limit=100");if(!records.length)root.append(el("p","hint","暂无记录"));
 records.forEach(x=>{const entry=el("div","detail-row");const name=el("strong","detail-name",kind==="qa"?x.question:x.event_name);const info=el("div","detail-meta");[kind==="qa"?x.source:x.host_name,kind==="qa"?x.status:x.notify_status,kind==="qa"?x.created_at:x.received_at].forEach(v=>info.append(el("span","",v||"—")));entry.append(name,info);if(kind!=="qa")entry.append(el("div","detail-sub","事件 ID "+x.event_id+" · 严重级别 "+["未分类","信息","警告","一般严重","严重","灾难"][Number(x.severity)]+" · AI "+x.ai_status));else entry.append(el("div","detail-sub",x.error_type||x.completed_at||""));root.append(entry)})
 }catch(e){root.append(el("p","hint","读取失败："+e.message))}
}
const CONFIG=[
 {name:"访问",fields:[["web_protocol","Web 访问协议","protocol"],["web_public_host","外部访问地址","text"]]},
 {name:"AI 模型",fields:[["openai_base_url","API 地址","text"],["openai_model","模型部署名称","text"],["openai_api_key","API 密钥","secret"]]},
 {name:"提示词",fields:[["ai_alert_prompt","自动分析提示词","prompt"],["ai_qa_prompt","问答提示词","prompt"],["ai_prompt","旧版提示词","prompt"]]},
 {name:"Zabbix MCP",fields:[["mcp_url","只读 MCP 地址","text"],["mcp_token","只读 MCP Token","secret"]]},
 {name:"飞书",fields:[["lark_app_id","企业应用 App ID","text"],["lark_app_secret","企业应用 App Secret","secret"],["allowed_chat_ids","允许群聊 ID","text"],["feishu_alert_chat_ids","告警群 ID","text"],["feishu_enabled","启用飞书通知","switch"]]},
 {name:"告警策略",fields:[["ai_min_severity","AI 自动分析最低等级","severity"],["zabbix_webhook_secret","Zabbix Webhook 密钥","secret"],["min_severity","兼容性最低等级","text"]]}
];
function hasChanges(){return Object.keys(state.draft).some(key=>state.draft[key]!==state.baseline[key])}
function setDraft(key,value){state.draft[key]=value;const b=$("edit-bar");if(b)b.hidden=!hasChanges()}
function fieldRow(key,label,type){
 const value=state.draft[key]??"";
 if(type==="switch")return row(label,toggle(value==="true",x=>setDraft(key,String(x)),label));
 if(type==="protocol")return row(label,segmented([{value:"http",label:"HTTP"},{value:"https",label:"HTTPS"}],value,v=>setDraft(key,v)));
 if(type==="severity")return row(label,segmented(["未分类","信息","警告","一般严重","严重","灾难"].map((label,i)=>({label,value:String(i)})),value,v=>setDraft(key,v)));
 if(type==="secret"){const b=button(value==="********"?"已设置 · 修改":"未设置 · 设置",()=>editValue(key,label,true));return row(label,b)}
 if(type==="prompt"){const v=value?"已设置":"未设置";return row(label,v,{onClick:()=>editValue(key,label,false,true)})}
 return row(label,value||"未设置",{onClick:()=>editValue(key,label)})
}
function editValue(key,label,secret=false,prompt=false){
 const wrap=el("div","sheet-field");const l=el("label","",label);const input=el(prompt?"textarea":"input");if(secret){input.type="password";input.autocomplete="new-password";input.placeholder="输入新密钥（留空不修改）"}else input.value=state.draft[key]||"";wrap.append(l,input);
 showSheet(label,wrap,"应用修改",()=>{if(secret&&!input.value)return true;setDraft(key,input.value);renderConfigGroups();return true});
}
function renderConfigGroups(){const area=$("config-groups");if(!area)return;area.replaceChildren();CONFIG.forEach(g=>{area.append(el("p","section-caption",g.name),group(g.fields.map(([key,label,type])=>fieldRow(key,label,type))))})}
async function config(){const root=$("page-content");root.replaceChildren(el("p","hint","读取系统设置…"));try{
 const settings=await api("/api/v1/settings");state.baseline={...settings};state.draft={...settings};
 root.replaceChildren();const groups=el("div");groups.id="config-groups";root.append(groups);renderConfigGroups();
 const bar=el("div","edit-bar");bar.id="edit-bar";bar.hidden=true;bar.append(el("p","","有尚未保存的修改"));
 const actions=el("div","btn-row");actions.append(button("还原",()=>{state.draft={...state.baseline};renderConfigGroups();bar.hidden=true}),button("保存",saveConfig,"primary"));bar.append(actions);root.append(bar);
 root.append(el("div","spacer"),group([row("连接诊断","测试服务与 MCP",{onClick:()=>navigate("debug")})]));
 }catch(e){root.replaceChildren(el("p","hint","加载失败："+e.message))}
}
async function saveConfig(){const values={};for(const key of Object.keys(state.draft)){if(state.draft[key]!==state.baseline[key])values[key]=state.draft[key]}if(!Object.keys(values).length)return;try{await api("/api/v1/settings",{method:"PUT",body:JSON.stringify({values})});toast("保存成功");await config()}catch(e){toast("保存失败："+e.message)}}
function timeRemaining(expiry){const sec=Math.max(0,Number(expiry)-Math.floor(Date.now()/1000));const d=Math.floor(sec/86400),h=Math.floor((sec%86400)/3600),m=Math.floor((sec%3600)/60);return (d?d+"天 ":"")+(h?h+"小时 ":"")+m+"分钟"}
function muteSheet(){
 const root=el("div");const ids=[["host_id","主机 ID"],["trigger_id","触发器 ID"]];const values={hours:1};
 const inputNodes={};
 ids.forEach(([id,label])=>{const wrap=el("div","sheet-field"),name=el("label","",label),input=el("input");input.inputMode="numeric";input.placeholder="输入 Zabbix 数字 ID";inputNodes[id]=input;wrap.append(name,input);root.append(wrap)});
 root.append(el("label","section-caption","屏蔽时长"),segmented([{value:1,label:"1小时"},{value:4,label:"4小时"},{value:24,label:"1天"},{value:72,label:"3天"},{value:168,label:"7天"}],1,v=>values.hours=v));
 showSheet("新增告警屏蔽",root,"确认屏蔽",async()=>{
  const host_id=inputNodes.host_id.value.trim(),trigger_id=inputNodes.trigger_id.value.trim();
  if(!/^\d{1,20}$/.test(host_id)||!/^\d{1,20}$/.test(trigger_id)){toast("请填写有效的主机及触发器 ID");return false}
  await api("/api/v1/alert-mutes",{method:"POST",body:JSON.stringify({host_id,trigger_id,hours:values.hours})});toast("屏蔽已生效");await mutes();return true
 });
}
async function mutes(){const root=$("page-content");const header=el("div","section-header");header.append(sectionTitle("生效中的屏蔽"));const add=button("＋",muteSheet,"primary");add.setAttribute("aria-label","新增屏蔽");add.classList.add("icon-button");header.append(add);root.replaceChildren(header);
 try{const rows=await api("/api/v1/alert-mutes");if(!rows.length){root.append(group([row("暂无屏蔽规则","新告警正常推送")]));return}
 const records=rows.map(x=>{const box=el("div","group-row");const title=el("div","row-title");title.append(el("div","mute-id","主机 "+x.host_id+" · 触发器 "+x.trigger_id),el("small","","还剩 "+timeRemaining(x.expires_at)));box.append(title);box.append(button("解除",()=>{const body=el("p","","确定立即恢复该主机与触发器的飞书通知？");showSheet("解除告警屏蔽",body,"解除",async()=>{await api("/api/v1/alert-mutes/"+x.host_id+"/"+x.trigger_id,{method:"DELETE"});toast("已解除屏蔽");await mutes();return true},"danger")},"danger"));return box});
 root.append(group(records))
 }catch(e){root.append(el("p","hint","读取失败："+e.message))}
}
async function debug(){const root=$("page-content");root.replaceChildren();const defs=[["Redis","/api/v1/status"],["MCP","/api/v1/test/mcp"],["AI 模型","/api/v1/test/ai"]];const rows=defs.map(([name,path])=>{const status=el("span","row-value","未测试");const b=button("测试",async()=>{status.textContent="测试中…";b.disabled=true;const start=performance.now();try{const result=await api(path,{method:name==="Redis"?"GET":"POST"});status.textContent="✓ 正常 · "+Math.round(performance.now()-start)+"ms";b.dataset.result=JSON.stringify(result,null,2)}catch(e){status.textContent="异常 · "+e.message}finally{b.disabled=false}}, "secondary");const groupRow=el("div","group-row");groupRow.append(el("div","row-title",name),status,b);groupRow.addEventListener("dblclick",()=>{if(b.dataset.result){const pre=el("pre","",b.dataset.result);showSheet(name+" 详细结果",pre,"关闭",()=>true)}});return groupRow});root.append(group(rows));root.append(el("p","section-caption","双击测试行可查看成功返回的详细数据。"))}
function bubble(role,text){const b=el("div","bubble "+role,text);return b}
function redrawChat(){const stream=$("chat-messages");if(!stream)return;stream.replaceChildren(...state.chat.map(x=>{if(x.pending){const wrap=el("div","bubble assistant");const dot=el("div","typing");dot.append(el("i"),el("i"),el("i"));wrap.append(dot);return wrap}return bubble(x.role,x.text)}));stream.scrollTop=stream.scrollHeight}
async function ask(){const root=$("page-content");root.replaceChildren();const frame=el("section","chat-window");const stream=el("div","chat-messages");stream.id="chat-messages";frame.append(stream);const form=el("form","chat-composer");const input=el("textarea");input.id="chat-input";input.placeholder="向 Zabbix 提问…";input.rows=1;input.maxLength=3000;const submit=button("",null,"primary","chat-send");submit.type="submit";submit.setAttribute("aria-label","发送消息");submit.append(icon("send"));form.append(input,submit);frame.append(form);root.append(frame);redrawChat();
 input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
 form.addEventListener("submit",async e=>{e.preventDefault();const question=input.value.trim();if(!question)return;input.value="";state.chat.push({role:"user",text:question},{pending:true});redrawChat();submit.disabled=true;try{const r=await api("/api/v1/ask",{method:"POST",body:JSON.stringify({question})});state.chat[state.chat.length-1]={role:"assistant",text:r.answer||"未获取到响应"};}catch(err){state.chat[state.chat.length-1]={role:"assistant",text:"请求失败："+err.message}}finally{submit.disabled=false;redrawChat();input.focus()}});
}
async function logs(){const root=$("page-content");root.replaceChildren();root.append(segmented([{label:"审计",value:"audit"},{label:"失败任务",value:"failed"}],state.logsTab,v=>{state.logsTab=v;logs()}));const content=el("div");root.append(content);
 try{const result=await api("/api/v1/logs");if(state.logsTab==="failed"){const records=result.failed_jobs||[];content.append(el("p","section-caption","失败任务 · 共 "+records.length+" 条"));content.append(group(records.length?records.map(x=>row(x.queue,x.id)):[row("暂无失败任务","—")]));return}
 const grouped={};(result.audit||[]).forEach(x=>{const date=(x.time||"未知日期").split(" ")[0];(grouped[date]??=[]).push(x)});
 if(!Object.keys(grouped).length)content.append(el("p","hint","暂无审计记录"));
 Object.keys(grouped).forEach(date=>{content.append(el("h3","log-day",date));content.append(group(grouped[date].map(x=>row(x.action,x.key+" · "+x.time))))});
 }catch(e){content.append(el("p","hint","读取失败："+e.message))}
}
$("overlay").addEventListener("click",e=>{if(e.target===$("overlay"))closeSheet()});
$("drawer-overlay").addEventListener("click",e=>{if(e.target===$("drawer-overlay"))closeDrawer()});
$("drawer-close").addEventListener("click",closeDrawer);
$("logout").addEventListener("click",async()=>{try{await api("/api/v1/auth/logout",{method:"POST"})}finally{location.assign("/")}})
document.addEventListener("keydown",e=>{if(e.key==="Escape"){if(!$("overlay").hidden)closeSheet();else if(!$("drawer-overlay").hidden)closeDrawer()}});
window.addEventListener("scroll",()=>$("compact-header").classList.toggle("scrolled",scrollY>40),{passive:true});
bootstrap();
