// Runtime-generated synthetic input only; not an observation, Nav2 plan or
// collision computation. No maps/PCD, private captures or ROS are read.
export const SCENARIOS = ['empty', 'cone', 'costmap', 'path-1', 'replan', 'trajectory',
  'moved', 'occluded', 'removed', 'lidar-only', 'depth-only', 'unmatched-yolo',
  'bad-calibration', 'clock-mismatch', 'sensor-skew', 'stale-pose', 'stale-joints', 'multi'];
export function makeContext(overrides = {}) {
  return { map_id:'synthetic-reference-A', revision:'synthetic-r1', frame_id:'map', units:'m',
    source_epoch:'fixture-epoch-1', stream_epoch:'fixture-stream-1', clock_domain:'fixture_clock',
    calibration_id:'synthetic-calibration-1', source_identity:'runtime-generated reference / no recorded robot data', ...overrides };
}
export function makeReference() {
  const points=[];
  for (let x=-4;x<=4;x+=.2) for (let y=-3;y<=3;y+=.2) {
    if (Math.abs(x)>3.7 || Math.abs(y)>2.7) for (let z=0;z<1.2;z+=.2) points.push(x,y,z);
    else points.push(x,y,0);
  }
  return { points:new Float32Array(points), frame_id:'map', source_points:points.length/3, data_provenance:'SYNTHETIC_FIXTURE',
    provenance:'SYNTHETIC / generated reference geometry, not stored merged PCD' };
}
export function makePacket(index=0, scenario='multi', context=makeContext()) {
  const tick=10000000000n+BigInt(index)*50000000n;
  const frame_key={map_id:context.map_id,revision:context.revision,frame_id:context.frame_id};
  const base={producer:'c3-fixture-generator', evidence_kind:'SYNTHETIC', sequence:index,
    source_epoch:context.source_epoch, stamp_ns:String(tick), clock_domain:context.clock_domain,
    calibration_id:context.calibration_id, frame_key,
    provenance:['SYNTHETIC: authored display fixture; no Nav2 execution or real sensor acquisition']};
  const geometry=(x,y,z=.3)=>({center_m:[x,y,z],extent_m:[.38,.38,.6],orientation_xyzw:[0,0,0,1]});
  const cone=(id,x,y,support=['LIDAR','DEPTH'])=>({track_id:id,class_name:'unknown',class_score:null,
    state:scenario==='occluded'?'OCCLUDED':'OBSERVED',novelty:'NEW_TO_REFERENCE',sensor_support:support,
    geometry:geometry(x,y),provenance:['synthetic cone cluster / class unresolved']});
  let objects=scenario==='empty'||scenario==='removed'?[]:[cone('cone-1',scenario==='moved'?1.8:1.1,.15)];
  if(scenario==='multi') objects.push(cone('cone-2',2,1.1,['LIDAR']),cone('cone-3',-.6,1.8,['DEPTH']));
  if(['lidar-only','depth-only'].includes(scenario)) objects[0].sensor_support=[scenario==='lidar-only'?'LIDAR':'DEPTH'];
  const source=(id,kind)=>({...base,id,kind,health:'OK',points_m:objects.flatMap(o=>{
    const [x,y,z]=o.geometry.center_m;
    return Array.from({length:24},(_,i)=>[x+.16*Math.cos(i*Math.PI/12),y+.16*Math.sin(i*Math.PI/12),z+(i%4)*.07]);
  })});
  const sources=scenario==='empty'?[]:[source('LIDAR','LIDAR'),source('DEPTH','DEPTH')]
    .filter(s=>scenario!=='lidar-only'||s.id==='LIDAR').filter(s=>scenario!=='depth-only'||s.id==='DEPTH');
  const pathEnabled=!['empty','cone','costmap','removed'].includes(scenario);
  // Literal paths are supplied by the fixture producer, never synthesized by
  // the overlay. They are not presented as actual planner output.
  const path=pathEnabled?{...base,generation:scenario==='path-1'?'fixture-plan-1':'fixture-plan-2',
    dimensions:2,representation:'2D_GROUND_PLANE',plane_z_m:.03,
    points_m:scenario==='path-1'?[[-2,0],[0,0],[2.6,0]]:[[-2,0],[-.5,-.7],[1.5,-.8],[2.6,0]],
    replanning_reason:scenario==='path-1'?null:'SYNTHETIC scenario event; not native Nav2 replan'}:null;
  const positions_rad=Object.fromEntries(['FR','FL','RR','RL'].flatMap(l=>[
    [`${l}_hip_joint`,0],[`${l}_thigh_joint`,.8],[`${l}_calf_joint`,-1.5]]));
  const robot_pose={...base,ref:`pose-${index}`,position_m:[-1.3,-.2,.4],rpy_rad:[0,0,0]};
  const joint_state={...base,ref:`joints-${index}`,positions_rad};
  const obstacle_frame={...base,schema_version:'robot-scope.obstacle-frame.v1',obstacles:objects,
    published_to_nav2:false,costmap_ingestion_observed:false,controller_consumption_observed:false};
  const costmaps=['empty','cone'].includes(scenario)?[]:[{...base,id:'synthetic-local-costmap',
    representation:'2D_GROUND_PLANE',width:12,height:10,resolution_m:.4,origin:[-2,-2,0],plane_z_m:.01,
    cells:Array.from({length:120},(_,i)=>[56,57,68,69].includes(i)?254:i<12?-1:0)}];
  const collision_assessment=objects.length?{...base,schema_version:'robot-scope.collision-assessment.v1',
    robot_pose_ref:robot_pose.ref,joint_state_ref:joint_state.ref,obstacle_frame_ref:index,
    path_ref:path?.generation??null,robot_geometry_hash:'SYNTHETIC-envelope-fixture-not-validated-robot-geometry',
    severity:'CAUTION',contact_state:'CONTACT_UNCONFIRMED',reason:'SYNTHETIC supplied risk; no collision solver executed',
    min_clearance_m:null,modeled_ttc_s:null,valid_until_ns:String(tick+500000000n),
    envelopes:[{id:'body-fixture',kind:'padded',geometry:{center_m:[-1.3,-.2,.45],extent_m:[.9,.5,.5],orientation_xyzw:[0,0,0,1]}},
      {id:'leg-fixture',kind:'unpadded-leg',geometry:{center_m:[-1,-.45,.2],extent_m:[.12,.12,.4],orientation_xyzw:[0,0,0,1]}},
      {id:'mount-fixture',kind:'mount',geometry:{center_m:[-1.3,-.2,.8],extent_m:[.3,.2,.2],orientation_xyzw:[0,0,0,1]}},
      {id:'sweep-fixture',kind:'supplied-sweep',geometry:{center_m:[-.7,-.2,.45],extent_m:[1.2,.7,.6],orientation_xyzw:[0,0,0,1]}}]}:null;
  const packet={...base,schema_version:'robot-scope.scene-packet.v1',stream_epoch:context.stream_epoch,
    map_identity:{...frame_key,units:'m'},robot_pose,joint_state,sources,obstacle_frame,
    global_path:path,local_trajectory:scenario==='trajectory'?{...path,generation:'fixture-local-1',
      points_m:[[-1.3,-.2],[-1,-.4],[-.6,-.6]],provenance:['SYNTHETIC supplied trajectory, no controller execution']}:null,
    costmaps,collision_assessment};
  if(scenario==='bad-calibration') {sources[1].calibration_id='wrong-calibration';obstacle_frame.calibration_id='wrong-calibration';}
  if(scenario==='clock-mismatch') sources[1].clock_domain='unmapped-device-monotonic';
  if(scenario==='sensor-skew') sources[1].stamp_ns=String(tick-350000000n);
  if(scenario==='stale-pose') robot_pose.stamp_ns=String(tick-2000000000n);
  if(scenario==='stale-joints') joint_state.stamp_ns=String(tick-2000000000n);
  if(scenario==='unmatched-yolo') objects[0].provenance.push('YOLO unmatched; no semantic association; geometry remains unknown');
  return packet;
}
