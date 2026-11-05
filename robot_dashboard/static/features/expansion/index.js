import {createTransport} from './transport.js';
const config=JSON.parse(document.querySelector('#expansion-config').textContent);
const host=document.querySelector('#expansion-host'), nav=document.querySelector('#expansion-nav'), status=document.querySelector('#expansion-status');
let current=null, currentName=null, generation=0, closed=false;
const reviewSession=config.auth==='REVIEW_SESSION';
const sessionPanel=document.querySelector('#expansion-session'), login=document.querySelector('#expansion-login');
const codeInput=document.querySelector('#expansion-code'), activeSession=document.querySelector('#expansion-session-active');
const sessionInfo=document.querySelector('#expansion-session-info'), sessionStatus=document.querySelector('#expansion-session-status');
let sessionRole=null, authenticated=false, sessionEpoch=0, sessionTimer=null, sessionAbort=null, sessionBusy=false;
function syncSession(){
  if(!reviewSession)return;
  sessionPanel.hidden=false;login.hidden=authenticated || sessionBusy;activeSession.hidden=!authenticated;
  for(const [name,button] of buttons)button.disabled=!authenticated && name!=='replay';
}
function clearSession(message, {preserveReplay=false, pending=false}={}){
  sessionEpoch++;sessionAbort?.abort();sessionAbort=null;clearTimeout(sessionTimer);sessionTimer=null;
  sessionRole=null;authenticated=false;sessionBusy=pending;codeInput.value='';sessionInfo.textContent='';
  if(!(preserveReplay && currentName==='replay')) {
    generation++;dispose();
    for(const button of buttons.values())button.setAttribute('aria-pressed','false');
  }
  sessionStatus.textContent=message;syncSession();
}
function installSession(value, epoch){
  if(closed||epoch!==sessionEpoch)return false;
  if(!value || !['read','review'].includes(value.role) || !Number.isSafeInteger(value.remaining_seconds) || value.remaining_seconds<=0)throw new Error('SESSION_INVALID');
  sessionRole=value.role;authenticated=true;sessionBusy=false;sessionInfo.textContent=value.role==='review'?'검토 권한':'읽기 권한';
  sessionStatus.textContent='세션이 연결되었습니다.';syncSession();
  clearTimeout(sessionTimer);sessionTimer=setTimeout(()=>clearSession('세션이 만료되었습니다. 다시 로그인해 주세요.', {preserveReplay:true}),Math.min(value.remaining_seconds*1000,2147483647));
  return true;
}
async function checkSession(){
  const epoch=++sessionEpoch;sessionAbort?.abort();sessionAbort=new AbortController();
  const request=createTransport({signal:sessionAbort.signal});
  try {const value=await request('/api/v1/extensions/session');if(installSession(value,epoch)&&buttons.size&&!current)open(buttons.keys().next().value);}
  catch {if(!closed&&epoch===sessionEpoch)clearSession('로그인이 필요합니다.', {preserveReplay:true});}
}

const buttons=new Map();
function stylesheet(name){const href=`/static/features/${name}`;if(document.querySelector(`link[href="${href}"]`))return;
  const link=document.createElement('link');link.rel='stylesheet';link.href=href;document.head.append(link);}
function dispose(){current?.destroy();current=null;currentName=null;host.replaceChildren();}
async function open(name){
  if(closed || (reviewSession && !authenticated && name!=='replay'))return;
  const mine=++generation;dispose();status.textContent=config.auth==='BLOCKED_AUTH'?'BLOCKED_AUTH · 서버 인증 포트가 연결되지 않아 지도·관측 API는 차단되어 있습니다.':'ADVISORY_ONLY · 검토 사본 / 관측 진단';
  for(const [key,button] of buttons)button.setAttribute('aria-pressed',String(key===name));
  const abort=new AbortController(),handles=[];currentName=name;current={destroy(){abort.abort();for(const item of handles.reverse())item.destroy();}};
  const request=createTransport({signal:abort.signal,onUnauthorized:()=>{if(reviewSession && mine===generation && !closed)clearSession('세션이 만료되었거나 종료되었습니다.', {preserveReplay:true});}});
  try {
    if(name==='multimap') {
      const [{mount,createRobotSceneRenderer},{createC1Ports}]=await Promise.all([import('../multimap_fusion/index.js'),import('../multimap_fusion/c1_ports.js')]);
      if(mine!==generation||closed)return;
      const ports=createC1Ports(request);handles.push(mount(host,{...ports,readOnly:reviewSession && sessionRole==='read',renderer:createRobotSceneRenderer(window.RobotScene3D)}));
      if(config.flags.usability){stylesheet('operator_usability/operator_usability.css');const {mountOperatorUsability}=await import('../operator_usability/index.js');
        if(mine!==generation||closed)return;handles.push(mountOperatorUsability(host.querySelector('.mmf'),'multimap'));}
    } else {
      const {mountObservationReview}=await import('./scene.js');
      if(mine!==generation||closed)return;
      handles.push(await mountObservationReview(host,{name,request,signal:abort.signal,usability:config.flags.usability,onError:error=>{if(mine===generation&&!closed)status.textContent=error.message;}}));
    }
  } catch(error){if(mine===generation&&!closed)status.textContent=error.message;}
}
for(const [name,label] of [['multimap','여러 지도 · Multimap Fusion'],['scene','관측 진단 · ADVISORY'],['replay','기록 검토 · REPLAY']]) {
  if(!config.flags[name])continue;const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.feature=name;
  button.addEventListener('click',()=>open(name));buttons.set(name,button);nav.append(button);
}
document.querySelector('#expansion-theme').addEventListener('click',()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='light'?'dark':'light';});
login.addEventListener('submit',async event=>{
  event.preventDefault();if(!reviewSession||closed||sessionBusy)return;
  const code=codeInput.value;codeInput.value='';
  const epoch=++sessionEpoch;sessionAbort?.abort();sessionAbort=new AbortController();
  sessionBusy=true;sessionStatus.textContent='로그인 확인 중입니다.';syncSession();
  const request=createTransport({signal:sessionAbort.signal});
  try {
    await request('/api/v1/extensions/session',{method:'POST',body:code});
    if(epoch!==sessionEpoch||closed)return;
    const value=await request('/api/v1/extensions/session');
    if(installSession(value,epoch)&&buttons.size&&!current)open(buttons.keys().next().value);
  } catch {if(epoch===sessionEpoch&&!closed)clearSession('로그인하지 못했습니다. 코드를 확인해 주세요.', {preserveReplay:true});}
  finally {if(epoch===sessionEpoch){sessionBusy=false;syncSession();}}
});
document.querySelector('#expansion-logout').addEventListener('click',async()=>{
  if(!reviewSession||closed)return;
  clearSession('로그아웃 중입니다.', {pending:true});const epoch=sessionEpoch;
  sessionAbort=new AbortController();
  try {await createTransport({signal:sessionAbort.signal})('/api/v1/extensions/session/logout',{method:'POST'});
    if(epoch===sessionEpoch&&!closed)sessionStatus.textContent='로그아웃되었습니다.';
  } catch {if(epoch===sessionEpoch&&!closed)sessionStatus.textContent='화면을 지웠습니다. 서버 로그아웃을 확인하지 못했습니다.';}
  finally {if(epoch===sessionEpoch){sessionBusy=false;syncSession();}}
});
addEventListener('pagehide',()=>{closed=true;if(reviewSession)clearSession('다시 로그인 상태를 확인합니다.');else {generation++;dispose();}});
addEventListener('pageshow',event=>{if(event.persisted){closed=false;if(reviewSession)checkSession();else if(buttons.size)open(buttons.keys().next().value);}});
if(reviewSession){syncSession();checkSession();}else if(buttons.size)open(buttons.keys().next().value);
