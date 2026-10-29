import { mountObstacleScene } from '/robot_dashboard/static/features/obstacle_scene/index.js';
import { makeContext, makePacket, makeReference, SCENARIOS } from './fixture.js';

let context=makeContext(), seq=0, replayTimer=null, scenarioIndex=0, referenceVisible=true;
const reference=makeReference(), canvas=document.querySelector('#scene');
const renderer=new window.RobotScene3D(canvas,{showRobot:false,autoFitOnFirstCloud:false,
  initialDistance:9,maxPoints:10000,pointSize:.025,background:'#101c29',showAxes:true,
  robotPoseLabel:'SYNTHETIC URDF · DISPLAY ONLY'});
renderer.configureOfficialRobot({enabled:true,assetUrl:'/robot_dashboard/static/assets/go2/go2-official-lite.json',poseOrigin:'base',adaptiveScale:false,scale:1});
// Preload once through the existing renderer's shared asset cache, never on import.
await renderer.loadOfficialRobotModel('/robot_dashboard/static/assets/go2/go2-official-lite.json');
renderer.setPointCloud(reference); renderer.setStatus({snapshot:true,provenance:'FIXTURE',message:'SYNTHETIC REFERENCE · runtime generated'});
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
  setReferenceVisible(value){if(value===referenceVisible)return;referenceVisible=value;if(value)renderer.setPointCloud(reference);else renderer.clearPointCloud();},
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
emit('multi');
