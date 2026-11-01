import {mountRunReview} from '/robot_dashboard/static/features/run_review/index.js';
import {mountObstacleScene} from '/c6-deps/obstacle_scene/index.js';
import {adaptC1ScenePacket} from '/c6-deps/obstacle_scene/c1_adapter.js';
const canvas=document.querySelector('#scene');
const renderer=new window.RobotScene3D(canvas,{showRobot:false,showAxes:true,initialDistance:8,autoFitOnFirstCloud:false});
// Same isolated host bridge as C3. Product needs a public project() renderer port.
const scene={canvas,
  focusSnapshot(packet){
    const path=packet.global_path?.data;
    const points=path?.points_m;
    if(!points?.length)return;
    const xyz=points.map(p=>[p[0],p[1],p.length===3?p[2]:path.plane_z_m]);
    if(!xyz.every(p=>p.every(Number.isFinite)))return;
    const lo=[0,1,2].map(i=>Math.min(...xyz.map(p=>p[i]))),hi=[0,1,2].map(i=>Math.max(...xyz.map(p=>p[i])));
    renderer.setViewPreset('isometric');
    renderer.camera.target=lo.map((v,i)=>(v+hi[i])/2);
    renderer.camera.distance=Math.max(5,Math.hypot(...lo.map((v,i)=>hi[i]-v))*1.8);
    renderer.resize();
  },project:p=>renderer._project(p),
  viewKey:()=>JSON.stringify(renderer.camera),
  setRobot(v){if(!v){renderer.setRobotVisible(false);renderer.setRobotPose(null);renderer.resetRobotJointPositions?.();return;}
    if(typeof renderer.setRobotJointPositions!=="function"){renderer.setRobotVisible(false);return;}
    const [x,y,z]=v.pose.position_m,[roll,pitch,yaw]=v.pose.rpy_rad;
    renderer.setRobotPose({x,y,z,roll,pitch,yaw});renderer.setRobotJointPositions(v.joints.positions_rad);renderer.setRobotVisible(true);},
  setReferenceVisible() {}};
function clearScene(){scene.setRobot(null);renderer.clearPointCloud();renderer.setTrail([]);renderer.setStatus({snapshot:true,provenance:'REPLAY',message:'ARCHIVED · REPLAY'});}
clearScene();
const review=mountRunReview(document.querySelector('#review'),{scene,mountScene:mountObstacleScene,adaptScene:adaptC1ScenePacket,clearScene});
window.c6Review=review;
window.c6Scene=renderer;
addEventListener('pagehide',()=>{review.destroy();renderer.destroy();},{once:true});
