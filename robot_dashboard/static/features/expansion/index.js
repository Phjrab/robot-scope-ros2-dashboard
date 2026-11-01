import {createTransport} from './transport.js';
const config=JSON.parse(document.querySelector('#expansion-config').textContent);
const host=document.querySelector('#expansion-host'), nav=document.querySelector('#expansion-nav'), status=document.querySelector('#expansion-status');
let current=null, generation=0, closed=false;
const buttons=new Map();
function stylesheet(name){const href=`/static/features/${name}`;if(document.querySelector(`link[href="${href}"]`))return;
  const link=document.createElement('link');link.rel='stylesheet';link.href=href;document.head.append(link);}
function dispose(){current?.destroy();current=null;host.replaceChildren();}
async function open(name){
  const mine=++generation;dispose();status.textContent=config.auth==='BLOCKED_AUTH'?'BLOCKED_AUTH · 서버 인증 포트가 연결되지 않아 지도·관측 API는 차단되어 있습니다.':'ADVISORY_ONLY · 검토 사본 / 관측 진단';
  for(const [key,button] of buttons)button.setAttribute('aria-pressed',String(key===name));
  const abort=new AbortController(),handles=[];current={destroy(){abort.abort();for(const item of handles.reverse())item.destroy();}};
  const request=createTransport({signal:abort.signal});
  try {
    if(name==='multimap') {
      const [{mount,createRobotSceneRenderer},{createC1Ports}]=await Promise.all([import('../multimap_fusion/index.js'),import('../multimap_fusion/c1_ports.js')]);
      if(mine!==generation||closed)return;
      const ports=createC1Ports(request);handles.push(mount(host,{...ports,renderer:createRobotSceneRenderer(window.RobotScene3D)}));
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
addEventListener('pagehide',()=>{closed=true;generation++;dispose();},{once:true});
if(buttons.size)open(buttons.keys().next().value);
