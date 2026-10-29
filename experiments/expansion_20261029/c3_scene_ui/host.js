import { mountObstacleScene } from '/robot_dashboard/static/features/obstacle_scene/index.js';
import { makeContext, makePacket, makeReference, SCENARIOS } from './fixture.js';

const actualCase=new URLSearchParams(location.search).get('actual');
let context=actualCase ? await (await fetch(`/c3-context/${encodeURIComponent(actualCase)}`)).json() : makeContext(), seq=0, replayTimer=null, scenarioIndex=0, referenceVisible=true;
const reference=actualCase ? null : makeReference(), canvas=document.querySelector('#scene');
const renderer=new window.RobotScene3D(canvas,{showRobot:false,autoFitOnFirstCloud:false,
  initialDistance:9,maxPoints:10000,pointSize:.025,background:'#101c29',showAxes:true,
  robotPoseLabel:'SYNTHETIC URDF · DISPLAY ONLY'});
renderer.configureOfficialRobot({enabled:true,assetUrl:'/robot_dashboard/static/assets/go2/go2-official-lite.json',poseOrigin:'base',adaptiveScale:false,scale:1});
// Preload once through the existing renderer's shared asset cache, never on import.
await renderer.loadOfficialRobotModel('/robot_dashboard/static/assets/go2/go2-official-lite.json');
if(reference)renderer.setPointCloud(reference); renderer.setStatus({snapshot:!actualCase,provenance:'FIXTURE',message:actualCase?'SYNTHETIC CORE · reference UNAVAILABLE':'SYNTHETIC REFERENCE · runtime generated'});
renderer.camera.target=[.3,0,.1]; renderer.camera.distance=9; renderer.setViewPreset('isometric');
const subscribers=new Set();
const scenePort={canvas,
  // Fixture-only read access to existing projection. Future product public hook
  // is documented; no shared prototype or render callback is patched here.
  project:p=>renderer._project(p),
  viewKey:()=>[...renderer.camera.target,renderer.camera.distance,renderer.camera.yaw,renderer.camera.pitch,renderer.width,renderer.height].join(','),
  setRobot(value){
    if(!value){renderer.setRobotVisible(false);renderer.setRobotPose(null);renderer.resetRobotJointPositions();return;}
    const [x,y,z]=value.pose.position_m,[roll,pitch,yaw]=value.pose.rpy_rad;
    renderer.setRobotPose({x,y,z,roll,pitch,yaw});renderer.setRobotJointPositions(value.joints.positions_rad);renderer.setRobotVisible(true);
  },
  setReferenceVisible(value){if(value===referenceVisible)return;referenceVisible=value;if(value && reference)renderer.setPointCloud(reference);else renderer.clearPointCloud();},
};
let feature=mount();
function mount(){return mountObstacleScene(document.querySelector('#host'),{scene:scenePort,
  subscribe:fn=>{subscribers.add(fn);return()=>subscribers.delete(fn);},getMap:()=>context,
  theme:()=>document.body.dataset.theme,clock:()=>performance.now()});}
function emitPacket(packet){for(const fn of subscribers)fn(packet);return packet;}
function emit(scenario='multi'){document.querySelector('#scenario').value=scenario;return emitPacket(makePacket(++seq,scenario,context));}
const select=document.querySelector('#scenario');
for(const value of SCENARIOS){const option=document.createElement('option');option.value=value;option.textContent=value;select.append(option);}
select.addEventListener('change',()=>emit(select.value));
document.querySelector('#next').addEventListener('click',()=>{scenarioIndex=(scenarioIndex+1)%SCENARIOS.length;emit(SCENARIOS[scenarioIndex]);});
document.querySelector('#theme').addEventListener('click',()=>{document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark';});
document.querySelector('#replay').addEventListener('click',()=>{
  if(replayTimer){clearInterval(replayTimer);replayTimer=null;return;}
  replayTimer=setInterval(()=>{scenarioIndex=(scenarioIndex+1)%SCENARIOS.length;emit(SCENARIOS[scenarioIndex]);},400);
});
window.c3Fixture={emit,emitPacket,makePacket,makeContext,
  get context(){return context;},setContext(next){context={...next};},
  get feature(){return feature;},get renderer(){return renderer;},
  subscriberCount:()=>subscribers.size,
  remount(){feature.destroy();feature=mount();},destroy(){clearInterval(replayTimer);feature.destroy();renderer.destroy();},
};
if (!actualCase) emit('multi');
else {
  for (const id of ['scenario','next','replay']) document.getElementById(id).hidden=true;
  document.querySelector('.fixture-banner strong').textContent=`ACTUAL C1 HTTP / D2 → D3 / SYNTHETIC / ${actualCase}${actualCase==='NEAR'?' (시나리오명; producer risk는 UNKNOWN)':''}`;
  document.querySelector('.fixture-caption').textContent='실제 C1 HTTP · 합성 D2/D3 core 입력 · m/map. Reference / 실제 merged 지도: UNAVAILABLE. 공식 URDF는 시각화용; D3 합성 body-box와 동일 collision geometry 아님. Path/costmap은 test host 제공값. ROS/native 실행 NOT_RUN.';
  document.querySelector('.fixture-status').textContent='READ-ONLY LOCAL HTTP · ADVISORY_ONLY/ACTIVE 상태는 입력 그대로 · 로봇/공용 제품 미연결';
  const {adaptC1ScenePacket,parseC1SceneJSON}=await import('/robot_dashboard/static/features/obstacle_scene/c1_adapter.js');
  let timer=null,inFlight=false,last=null;
  async function poll(){
    if(inFlight)return; inFlight=true;
    try {
      const start=performance.now();
      const response=await fetch(`/actual/${encodeURIComponent(actualCase)}/api/v1/extensions/scene/snapshot`,{headers:{Authorization:'Bearer public-c3-synthetic-offline-test-bearer'}});
      if(!response.ok)throw new Error(`C1 HTTP ${response.status}`);
      const raw=await response.text(), wire=parseC1SceneJSON(raw);
      const adapted=adaptC1ScenePacket(wire,context,{transportAgeMs:performance.now()-start});
      const fingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw))),n=>n.toString(16).padStart(2,'0')).join('');
      last={wire,fingerprint,reason:adapted.reason};
      if(!adapted.packet)throw new Error(adapted.reason);
      emitPacket(adapted.packet);
    } finally {inFlight=false;}
  }
  window.c3Actual={poll,get last(){return last;},stop(){clearInterval(timer);timer=null;},start(){if(!timer)timer=setInterval(()=>poll().catch(e=>console.error(e)),100);}};
  addEventListener('pagehide',()=>window.c3Actual.stop(),{once:true});
  await poll(); window.c3Actual.start();
}
