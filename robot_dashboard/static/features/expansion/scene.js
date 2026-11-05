import {createSavedMapScene} from '../maps/saved_scene.js';
import {mountObstacleScene} from '../obstacle_scene/index.js';
import {adaptC1ScenePacket} from '../obstacle_scene/c1_adapter.js';
import {mountRunReview} from '../run_review/index.js';
import {startScenePolling} from './scene_poll.js';
import {mountOperatorUsability} from '../operator_usability/index.js';

function stylesheet(name){const href=`/static/features/${name}`;if(document.querySelector(`link[href="${href}"]`))return;
  const link=document.createElement('link');link.rel='stylesheet';link.href=href;document.head.append(link);}

export function mountObservationReview(host,{name,request,signal,usability,onError,onStatus=()=>{}}) {
  stylesheet('obstacle_scene/obstacle_scene.css');
  stylesheet('expansion/replay.css');
  if(usability)stylesheet('operator_usability/operator_usability.css');
  const viewport=document.createElement('div');viewport.className='expansion-viewport';
  const canvas=document.createElement('canvas');canvas.setAttribute('aria-label',name==='replay'?'기록 장면 REPLAY':'관측 진단 ADVISORY_ONLY');
  viewport.append(canvas);host.append(viewport);
  const spaceNote=document.createElement('p');spaceNote.className='expansion-space-note';spaceNote.hidden=true;viewport.append(spaceNote);
  const panel=document.createElement('section');host.append(panel);
  const renderer=createSavedMapScene({savedSceneCanvas:canvas},window,{showRobot:false,showTrail:false});
  renderer.configureOfficialRobot({enabled:true,poseOrigin:'base',scale:1});
  renderer.setStatus({snapshot:true,provenance:name==='replay'?'REPLAY':'ADVISORY_ONLY',message:'pose / joints / coverage UNAVAILABLE'});
  let closed=false, polling=null, context=null, receiver=null, feature=null, helper=null, framedContext=null;
  const scene={canvas,project:point=>renderer.projectWorld(point),viewKey:()=>JSON.stringify([renderer.camera,canvas.width,canvas.height]),
    setRobot(value){
      renderer.setRobotVisible(false);
      if(!value){renderer.setRobotPose(null);renderer.resetRobotJointPositions();return;}
      if(renderer.getOfficialRobotModelStatus().state!=='ready')return;
      const [x,y,z]=value.pose.position_m,[roll,pitch,yaw]=value.pose.rpy_rad;
      renderer.setRobotPose({x,y,z,roll,pitch,yaw});renderer.setRobotJointPositions(value.joints.positions_rad);renderer.setRobotVisible(true);
    },
    setReferenceVisible(){},
    focusSnapshot(packet){
      const path=packet.global_path?.data;
      const points=path?.points_m;
      if(!points?.length)return;
      const xyz=points.map(p=>[p[0],p[1],p.length===3?p[2]:path.plane_z_m]);
      if(!xyz.every(p=>p.every(Number.isFinite)))return;
      renderer.setViewPreset('isometric');
      const lo=[0,1,2].map(i=>Math.min(...xyz.map(p=>p[i]))),hi=[0,1,2].map(i=>Math.max(...xyz.map(p=>p[i])));
      renderer.camera.target=lo.map((v,i)=>(v+hi[i])/2);
      renderer.camera.distance=Math.max(5,Math.hypot(...lo.map((v,i)=>hi[i]-v))*1.8);renderer.resize();
    }};
  const clearScene=()=>{scene.setRobot(null);renderer.clearPointCloud();renderer.clearTrail();};
  // One existing renderer owns the current-model slot. Goal/Initial slots are absent.
  renderer.loadOfficialRobotModel().catch(error=>{if(!closed)onError(error);});
  if(name==='replay') {
    const mountScene=(target,options)=>{
      const mounted=mountObstacleScene(target,{...options,theme:()=>document.documentElement.dataset.theme||'dark'});
      const presentation=usability?mountOperatorUsability(target.querySelector('.obstacle-scene'),'obstacles'):null;
      return {...mounted,destroy(){presentation?.destroy();mounted.destroy();}};
    };
    feature=mountRunReview(panel,{scene,mountScene,adaptScene:adaptC1ScenePacket,clearScene});
  } else {
    feature=mountObstacleScene(panel,{scene,getMap:()=>context,theme:()=>document.documentElement.dataset.theme||'dark',
      subscribe:fn=>{receiver=fn;return()=>{receiver=null;};}});
    if(usability)helper=mountOperatorUsability(panel.querySelector('.obstacle-scene'),'obstacles');
    polling=startScenePolling({request,signal,
      onContext(next){if(JSON.stringify(next)!==JSON.stringify(context)){clearScene();context=next;}
        spaceNote.hidden=next?.space_kind!=='ISOLATED_SIMULATION';
        spaceNote.textContent='SIMULATED · 독립 평면 데모 · 실제 지도/3D 위치 미검증';},
      onPacket(packet){
        onStatus(packet.evidence_kind);
        if(context?.space_kind==='ISOLATED_SIMULATION' && framedContext!==JSON.stringify(context)){
          const points=packet.obstacle_frame?.obstacles?.map(o=>o.geometry?.center_m);
          if(points?.length && points.every(p=>Array.isArray(p)&&p.length===3&&p.every(Number.isFinite))){
            const lo=[0,1,2].map(i=>Math.min(...points.map(p=>p[i]))),hi=[0,1,2].map(i=>Math.max(...points.map(p=>p[i])));
            renderer.setViewPreset('isometric');renderer.camera.target=lo.map((v,i)=>(v+hi[i])/2);
            renderer.camera.distance=Math.max(3,Math.hypot(...lo.map((v,i)=>hi[i]-v))*1.8);renderer.resize();
            framedContext=JSON.stringify(context);
          }
        }
        receiver?.(packet);
      },onError});
  }
  function destroy(){if(closed)return;closed=true;polling?.destroy();helper?.destroy();feature?.destroy();renderer.destroy();viewport.remove();panel.remove();signal.removeEventListener('abort',destroy);}
  signal.addEventListener('abort',destroy,{once:true});if(signal.aborted)destroy();
  return {destroy};
}
