import { mountObstacleScene } from '/robot_dashboard/static/features/obstacle_scene/index.js';
import { makeContext, makePacket, makeReference, SCENARIOS } from './fixture.js';

const actualCase=new URLSearchParams(location.search).get('actual');
let context=actualCase ? await (await fetch(`/c3-context/${encodeURIComponent(actualCase)}`)).json() : makeContext(), seq=0, replayTimer=null, scenarioIndex=0, referenceVisible=true;
let reference=actualCase ? null : makeReference();
const canvas=document.querySelector('#scene');
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
  document.querySelector('.fixture-caption').textContent='실제 C1 HTTP · 합성 D2/D3 core 입력 · m/map. Reference는 실제 D1→C1 저장 합성 merged preview입니다. 공식 URDF는 시각화용; D3 합성 body-box와 동일 collision geometry 아님. Path/costmap은 test host 제공값. 로컬 ROS/native 실행 NOT_RUN.';
  document.querySelector('.fixture-status').textContent='READ-ONLY LOCAL HTTP · ADVISORY_ONLY/ACTIVE 상태는 입력 그대로 · 로봇/공용 제품 미연결';
  const {adaptC1ScenePacket,parseC1SceneJSON}=await import('/robot_dashboard/static/features/obstacle_scene/c1_adapter.js');
  const {createC1AssetCache}=await import('/robot_dashboard/static/features/obstacle_scene/c1_assets.js');
  // C1 assets are opaque. Only this isolated test host selects this decoder;
  // the production host must supply its own versioned display format.
  const cache=createC1AssetCache({fetchAsset:path=>fetch(`/actual/${encodeURIComponent(actualCase)}${path}`,{headers:{Authorization:'Bearer public-c3-synthetic-offline-test-bearer'}}),
    decode(bytes,ref,binding){
      const value=JSON.parse(new TextDecoder().decode(bytes));
      if(value.profile!=='c3-test-display-v1' || ['map_id','revision','generation'].some(k=>value.map_binding?.[k]!==binding[k]))throw new Error('ASSET_PROFILE_OR_MAP_MISMATCH');
      if(value.points_m && (!Array.isArray(value.points_m)||value.points_m.length>4096||!value.points_m.every(p=>Array.isArray(p)&&p.length===3&&p.every(Number.isFinite))))throw new Error('ASSET_POINT_LIMIT');
      if(value.costmap){
        const c=value.costmap;
        if(!Number.isSafeInteger(c.width)||!Number.isSafeInteger(c.height)||c.width<=0||c.height<=0||c.width*c.height>1000000
          ||!Array.isArray(c.cells)||c.cells.length!==c.width*c.height||!c.cells.every(v=>Number.isInteger(v)&&v>=-1&&v<=255))throw new Error('ASSET_COSTMAP_INVALID');
        if(c.cells.length>4096){
          let step=Math.ceil(Math.sqrt(c.cells.length/4096));
          while(step<=Math.min(c.width,c.height)&&(c.width%step||c.height%step))step++;
          if(step>Math.min(c.width,c.height))throw new Error('ASSET_EXACT_GRID_DECIMATION_UNAVAILABLE');
          const width=c.width/step,height=c.height/step,cells=[];
          for(let y=0;y<c.height;y+=step)for(let x=0;x<c.width;x+=step){
            const block=[];for(let j=y;j<Math.min(y+step,c.height);j++)for(let i=x;i<Math.min(x+step,c.width);i++)block.push(c.cells[j*c.width+i]);
            cells.push(block.includes(-1)?-1:Math.max(...block));
          }
          value.costmap={...c,width,height,cells,resolution_m:c.resolution_m*step};
          value.display_transform={kind:'DISPLAY_ONLY_BLOCK_MAX_UNKNOWN_PRESERVED',step,original_width:c.width,original_height:c.height};
        }
      }
      return value;
    }});
  let timer=null,inFlight=false,last=null,referenceRevision='';
  async function poll(){
    if(inFlight)return; inFlight=true;
    try {
      const start=performance.now();
      const response=await fetch(`/actual/${encodeURIComponent(actualCase)}/api/v1/extensions/scene/snapshot`,{headers:{Authorization:'Bearer public-c3-synthetic-offline-test-bearer'}});
      if(!response.ok)throw new Error(`C1 HTTP ${response.status}`);
      const raw=await response.text(), wire=parseC1SceneJSON(raw);
      const assets=await cache.resolve(wire);
      const ref=assets.find(a=>a.status==='READY'&&a.ref.role==='saved_reference_cloud'&&a.value.points_m);
      if((ref?.ref.revision || '')!==referenceRevision){
        referenceRevision=ref?.ref.revision || '';reference=ref?{points:new Float32Array(ref.value.points_m.flat()),frame_id:context.frame_id,source_points:ref.value.points_m.length,data_provenance:'SYNTHETIC_MERGED_DISPLAY'}:null;
        if(referenceVisible&&reference)renderer.setPointCloud(reference);else renderer.clearPointCloud();
      }
      const adapted=adaptC1ScenePacket(wire,context,{transportAgeMs:performance.now()-start,displayAssets:assets});
      const fingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw))),n=>n.toString(16).padStart(2,'0')).join('');
      last={wire,fingerprint,reason:adapted.reason,assets:assets.map(a=>({ref:a.ref,status:a.status})),cache:cache.diagnostics(),reference_points:reference?.source_points || 0};
      if(!adapted.packet)throw new Error(adapted.reason);
      emitPacket(adapted.packet);
    } finally {inFlight=false;}
  }
  window.c3Actual={poll,get last(){return last;},stop(){clearInterval(timer);timer=null;},dispose(){clearInterval(timer);cache.dispose();},start(){if(!timer)timer=setInterval(()=>poll().catch(e=>console.error(e)),100);}};
  addEventListener('pagehide',()=>window.c3Actual.dispose(),{once:true});
  if(actualCase==='NATIVE_REPLAY'){
    document.querySelector('.fixture-banner strong').textContent='ACTUAL C1 HTTP / RECORDED D3 NATIVE SIM / REPLAY';
    document.querySelector('.fixture-caption').textContent='D3 native run 40840774827 · fa8e26e · NavFn + direct RPP. 실제 기록 plan/costmap만 재생; C3에서 ROS/native 재실행 없음. 원래 source/host receipt 보존. Joints/collision/merged map 미제공. 추가 D3 URDF 보호는 원본 실행에서 ADVISORY_ONLY.';
    renderer.camera.target=[4,3,0];renderer.setStatus({snapshot:false,provenance:'REPLAY',message:'RECORDED NATIVE SIM · plan/costmap'});
  }
  await poll(); window.c3Actual.start();
}
