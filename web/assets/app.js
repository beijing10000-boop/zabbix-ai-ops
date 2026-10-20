'use strict';
const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
const el = (tag, className='', text='') => {const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=String(text);return n;};
const labelMap={overview:'总览',config:'配置',mutes:'屏蔽',debug:'调试',assistant:'AI 助手',logs:'日志'};
const icons={
 overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
 config:'<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.9l.06.06-1.9 1.9-.06-.06a1.7 1.7 0 0 0-1.9-.34 1.7 1.7 0 0 0-1 1.56V21h-2.7v-.12a1.7 1.7 0 0 0-1-1.56 1.7 1.7 0 0 0-1.9.34l-.06.06-1.9-1.9.06-.06A1.7 1.7 0 0 0 7 15.86a1.7 1.7 0 0 0-1.56-1H5v-2.7h.12a1.7 1.7 0 0 0 1.56-1 1.7 1.7 0 0 0-.34-1.9L6.28 9.2l1.9-1.9.06.06a1.7 1.7 0 0 0 1.9.34 1.7 1.7 0 0 0 1-1.56V6h2.7v.12a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.9-.34l.06-.06 1.9 1.9-.06.06a1.7 1.7 0 0 0-.34 1.9 1.7 1.7 0 0 0 1.56 1H20v2.7h-.12a1.7 1.7 0 0 0-1.56 1Z"/>',
 mutes:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4M4 4l16 16"/>',
 debug:'<path d="M4 17h3l3-8 4 12 3-7h3"/><circle cx="12" cy="12" r="10"/>',
 assistant:'<path d="M4 4h16v13H8l-4 4V4Z"/><path d="M8 9h8M8 13h5"/>',
 logs:'<path d="M7 4h13v16H7zM3 7h4M3 12h4M3 17h4M10 8h7M10 12h7M10 16h4"/>'
};
function icon(name){const span=el('span','nav-icon');span.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(icons[name]||icons.overview)+'</svg>';return span;}
function button(text,action,variant='quiet'){const b=el('button','button '+variant,text);b.type='button';if(action)b.addEventListener('click',action);return b;}
function statusDot(text,state='gray'){const w=el('span','row-trailing');w.append(el('span','status-dot '+state),el('span','',text));return w;}
function card(className=''){return el('div','card '+className);}
function groupList(rows){const root=el('div','group-list');rows.forEach(row=>root.append(row));return root;}
function groupRow(title,caption='',right=null){const row=el('div','group-row');const body=el('div','row-body');body.append(el('div','row-title',title));if(caption)body.append(el('div','row-caption',caption));row.append(body);if(right){const trailing=el('div','row-trailing');trailing.append(right);row.append(trailing);}return row;}
function toggle(checked,onChange){const b=el('button','switch');b.type='button';b.setAttribute('role','switch');b.setAttribute('aria-checked',String(!!checked));b.setAttribute('aria-label','切换');b.addEventListener('click',()=>{const yes=b.getAttribute('aria-checked')!=='true';b.setAttribute('aria-checked',String(yes));onChange(yes)});return b;}
function segmented(choices,selected,onChange){const root=el('div','segmented');for(const [value,caption] of choices){const b=el('button','',caption);b.type='button';b.setAttribute('aria-selected',String(value===selected));b.addEventListener('click',()=>{$$('button',root).forEach(x=>x.setAttribute('aria-selected',String(x===b)));onChange(value)});root.append(b);}return root;}
let toastTimeout;
function toast(message){const t=$('#toast');t.textContent=message;t.hidden=false;clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>{t.hidden=true},2500);}
function sheet(title,build,confirmText='确定',onConfirm=null,destructive=false){const box=$('#sheet'),body=$('#sheet-body'),confirm=$('#sheet-confirm');$('#sheet-title').textContent=title;body.replaceChildren();build(body);confirm.textContent=confirmText;confirm.className='button '+(destructive?'danger':'primary');$('#sheet-backdrop').hidden=false;box.hidden=false;const last=document.activeElement;const close=()=>{box.hidden=true;$('#sheet-backdrop').hidden=true;last?.focus?.()};$('#sheet-cancel').onclick=close;$('#sheet-backdrop').onclick=close;confirm.onclick=async()=>{try{const shouldClose=onConfirm?await onConfirm(body):true;if(shouldClose!==false)close()}catch(err){toast('操作失败：'+err.message)}};confirm.focus();return close;}
function drawer(title,render){$('#drawer-title').textContent=title;const body=$('#drawer-body');body.replaceChildren();render(body);$('#drawer-backdrop').hidden=false;$('#detail-drawer').hidden=false;$('[data-action="close-drawer"]').focus();}
function closeDrawer(){$('#detail-drawer').hidden=true;$('#drawer-backdrop').hidden=true;}
function detail(title,text){const node=el('div','detail-item');node.append(el('strong','',title),el('p','',text));return node;}
function heading(section){const h=el('div','group-section');h.append(el('div','group-label',section));return h;}
function userNameFromAuth(auth){return auth.name||'管理员';}
