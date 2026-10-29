import test from 'node:test';
import assert from 'node:assert/strict';
import {adaptC1ScenePacket,parseC1SceneJSON} from '../../robot_dashboard/static/features/obstacle_scene/c1_adapter.js';
import {createSceneConsumer} from '../../robot_dashboard/static/features/obstacle_scene/consumer.js';
const context={map_id:'a'.repeat(24),revision:'b'.repeat(64),generation:1,frame_id:'map',source_epoch:'sensor',stream_epoch:'scene',clock_domain:'sim',calibration_id:'cal',units:'m'};
function fixture(){
  const ns='9007199254740993';
  const observation=(data={},producer='producer')=>({schema_version:'0.1',evidence_kind:'SYNTHETIC',producer,sequence:1,source_epoch:'sensor',frame_key:{frame_id:'map',source_epoch:'sensor'},stamp_ns:ns,host_clock_id:'server',clock_domain:'sim',received_monotonic_ns:ns,map_binding:{map_id:context.map_id,revision:context.revision,generation:1},data,health:{}});
  const robot_pose=observation({position_m:[0,0,0],rpy_rad:[0,0,0],calibration_id:'cal',joint_state:{stamp_ns:ns,positions_rad:Object.fromEntries(['FL','FR','RL','RR'].flatMap(l=>['hip','thigh','calf'].map(j=>[`${l}_${j}_joint`,0])))}});
  const obstacle_frame={...observation(),calibration_id:'cal',obstacles:[{track_id:'x',geometry:{center:[1,0,0],extent:[.2,.2,.2],orientation_xyzw:[0,0,0,1]},sensor_support:'LIDAR',state:'OBSERVED',provenance:{raw:true}}],input_sources:[]};
  const ref={source_epoch:'sensor',sequence:1};
  const collision_assessment={...observation(),robot_pose_ref:ref,joint_state_ref:{stamp_ns:ns},obstacle_frame_ref:ref,path_ref:null,robot_geometry_hash:'e'.repeat(64),
    severity:'UNKNOWN',reason:'UNKNOWN',recommendation:'HOLD_FOR_VALID_INPUT',min_clearance:.5,modeled_ttc:null,freshness:{coverage:'SPARSE',protection_mode:'ACTIVE_CONSTRAINT'},validity_interval:{host_clock_id:'server',start_monotonic_ns:ns,end_monotonic_ns:String(BigInt(ns)+250000000n)}};
  const wire={schema_version:'0.1',evidence_kind:'SYNTHETIC',producer:'c1-scene',sequence:3,source_epoch:'scene',stream_epoch:'scene',map_binding:robot_pose.map_binding,robot_pose,obstacle_frame,collision_assessment,sources:{}};
  for(const [k,v]of Object.entries({robot_pose,obstacle_frame,collision_assessment}))wire.sources[k]={source_epoch:v.source_epoch,sequence:v.sequence,stamp_ns:v.stamp_ns,host_clock_id:v.host_clock_id,clock_domain:v.clock_domain,received_age_ms:0,sensor_age_ms:null};
  return wire;
}
function harness(){let now=0,c={...context};const consumer=createSceneConsumer({getMap:()=>c,clock:()=>now});return{consumer,advance:ms=>now+=ms,setContext:v=>c=v,ingest:wire=>{const a=adaptC1ScenePacket(wire,c);assert.ok(a.packet,a.reason);return consumer.ingest(a.packet);}};}
test('canonical C1 snapshot does not need sources.display; D2 geometry and UNKNOWN positive clearance preserved',()=>{
  const h=harness();assert.ok(h.ingest(fixture()));const v=h.consumer.snapshot();assert.equal(v.obstacles.value.obstacles[0].geometry.center_m[0],1);assert.equal(v.collision.value.severity,'UNKNOWN');assert.equal(v.collision.value.min_clearance_m,.5);assert.equal(v.collision.value.protection_mode,'ACTIVE_CONSTRAINT');assert.equal(v.collision.value.envelopes.length,0);assert.equal(v.source_mode,'ACTUAL_C1_SERVICE');
});
test('integer ns parser is exact beyond 2^53 and never rewrites quoted text',()=>{
  const p=parseC1SceneJSON('{"received_monotonic_ns":9007199254740993,"end_monotonic_ns":9223372036854775807,"note":"end_monotonic_ns:9007199254740993","sequence":2}');
  assert.equal(p.received_monotonic_ns,'9007199254740993');assert.equal(p.end_monotonic_ns,'9223372036854775807');assert.equal(p.note,'end_monotonic_ns:9007199254740993');assert.equal(p.sequence,2);
  const w=fixture();w.robot_pose.received_monotonic_ns=9007199254740993;assert.equal(adaptC1ScenePacket(w,context).packet.robot_pose,null);
});
test('repeated HTTP sequence/renewed receipt never renew frozen source TTL or original expiry',()=>{
  const h=harness(),w=fixture();h.ingest(w);h.advance(251);h.ingest(w);assert.equal(h.consumer.snapshot().collision.reason,'VALIDITY_EXPIRED');
  h.advance(250);w.sequence++;for(const slot of ['robot_pose','obstacle_frame','collision_assessment']){w[slot].sequence++;w.sources[slot].sequence++;}
  h.ingest(w);assert.equal(h.consumer.snapshot().pose.reason,'STALE');h.advance(800);h.ingest(w);assert.equal(h.consumer.snapshot().obstacles.reason,'STALE');
});
test('same immutable slot revisions reuse normalized geometry and remain bounded',()=>{
  const h=harness(),w=fixture();h.ingest(w);const count=h.consumer.diagnostics().geometryCopies;for(let i=0;i<300;i++)h.ingest(w);
  assert.equal(h.consumer.diagnostics().geometryCopies,count);assert.ok(h.consumer.diagnostics().cachedLayers<=8);
});
test('C1 omission at expiry is consumed on the same scene sequence',()=>{
  const h=harness(),w=fixture();h.ingest(w);assert.ok(h.consumer.snapshot().collision.value);w.collision_assessment=null;w.sources.collision_assessment.health={state:'REFERENCE_OR_VALIDITY_UNKNOWN'};
  assert.ok(h.ingest(w));assert.equal(h.consumer.snapshot().collision.value,null);
});
test('wrong host, future/expired interval, refs, missing source ages, and foreign clock cannot assert a current assessment',()=>{
  for(const mutate of [w=>w.collision_assessment.validity_interval.host_clock_id='foreign',w=>w.collision_assessment.validity_interval.start_monotonic_ns='9223372036854775807',w=>w.collision_assessment.validity_interval.end_monotonic_ns='1',w=>w.collision_assessment.obstacle_frame_ref.sequence=99,w=>w.sources.collision_assessment.received_age_ms=null,w=>w.collision_assessment.clock_domain='foreign']){
    const h=harness(),w=fixture();mutate(w);h.ingest(w);assert.equal(h.consumer.snapshot().collision.value,null);
  }
});
test('map generation/epoch/stream are fenced, no source clock inferred from stream epoch',()=>{
  const w=fixture();assert.equal(adaptC1ScenePacket(w,{...context,generation:2}).reason,'C1_MAP_GENERATION_MISMATCH');
  assert.equal(adaptC1ScenePacket(w,{...context,stream_epoch:'other'}).reason,'C1_STREAM_MISMATCH');
  const h=harness();h.ingest(w);h.setContext({...context,generation:2});assert.equal(h.consumer.snapshot().ready,false);
});
test('missing geometry is explicitly unavailable; no fake reference or paths invented',()=>{
  const h=harness(),w=fixture();h.ingest(w);const v=h.consumer.snapshot();assert.equal(v.path.value,null);assert.equal(v.local.value,null);assert.equal(v.sources.length,0);assert.equal(v.availability.reference_cloud,'UNAVAILABLE');
});

test('expired active constraints retain last reported HOLD state and a downgrade is explicit',()=>{
  const h=harness(),w=fixture();h.ingest(w);w.collision_assessment=null;h.ingest(w);
  assert.equal(h.consumer.snapshot().protection.mode,'ACTIVE_CONSTRAINT');assert.equal(h.consumer.snapshot().protection.recommendation,'HOLD_FOR_VALID_INPUT');
  const next=fixture();next.collision_assessment.freshness.protection_mode='ADVISORY_ONLY';h.ingest(next);
  assert.equal(h.consumer.snapshot().protection.transition,'REPORTED_DOWNGRADE_REQUIRES_HOST_CONFIRMATION');
});

test('late pre-expiry HTTP response cannot resurrect C1-invalidated assessment',()=>{
  const h=harness(),old=fixture(),expired=fixture();h.ingest(old);
  expired.collision_assessment=null;expired.sources.collision_assessment.health={state:'REFERENCE_OR_VALIDITY_UNKNOWN'};
  h.ingest(expired);assert.equal(h.consumer.snapshot().collision.value,null);
  h.ingest(old);assert.equal(h.consumer.snapshot().collision.reason,'SERVER_INVALIDATED');
});
test('supplied invalid cloud cannot crash authoritative D2 object rendering',()=>{
  const h=harness(),w=fixture();w.obstacle_frame.input_sources=[{...w.obstacle_frame,sensor_id:'LIDAR',kind:'LIDAR',health:'OK',points_m:[[NaN,0,0]]}];
  assert.ok(h.ingest(w));assert.equal(h.consumer.snapshot().sources[0].value,null);assert.equal(h.consumer.snapshot().obstacles.value.obstacles.length,1);
});

function v02(){const w=fixture();w.schema_version='0.2';for(const value of Object.values(w.sources))value.status='ready';return w;}
test('C1 0.2 decimal intervals preserve exact nanoseconds and coverage independently',()=>{
  const w=v02(),h=harness();w.collision_assessment.freshness.coverage={complete_for_motion:false,status:'MOTION_COVERAGE_NOT_QUALIFIED'};
  h.ingest(w);const v=h.consumer.snapshot();assert.equal(v.collision.value.validity_interval.start_monotonic_ns,'9007199254740993');assert.equal(v.collision.value.coverage.complete_for_motion,false);
  assert.equal(v.collision.value.severity,'UNKNOWN');assert.equal(v.availability.bulk_references,'C1_AUTHENTICATED_ASSETS');
});
test('C1 0.2 expired or unavailable slots retire same-sequence late responses and reset on context change',()=>{
  for(const status of ['expired','unavailable']){
    const h=harness(),old=v02(),expired=v02();h.ingest(old);
    for(const slot of ['robot_pose','obstacle_frame','collision_assessment']){expired[slot]=null;expired.sources[slot].status=status;}
    h.ingest(expired);assert.equal(h.consumer.snapshot().pose.reason,`SERVER_${status.toUpperCase()}`);
    h.ingest(old);assert.equal(h.consumer.snapshot().pose.reason,'SERVER_INVALIDATED');assert.equal(h.consumer.snapshot().obstacles.value,null);assert.equal(h.consumer.snapshot().collision.value,null);
    h.setContext({...context,generation:2});h.consumer.snapshot();h.setContext(context);h.ingest(old);assert.ok(h.consumer.snapshot().pose.value);
  }
});
test('v02 non-ready payloads cannot render even if an inconsistent server includes them',()=>{
  const w=v02();w.sources.robot_pose.status='expired';const h=harness();h.ingest(w);assert.equal(h.consumer.snapshot().pose.value,null);
});
test('canonical full source stamp accepts C1 25-digit bound without host conversion',()=>{
  const h=harness(),w=v02();for(const slot of ['robot_pose','obstacle_frame','collision_assessment']){w[slot].stamp_ns='1000000000000000000000000';w.sources[slot].stamp_ns=w[slot].stamp_ns;}
  h.ingest(w);assert.ok(h.consumer.snapshot().pose.value);assert.equal(h.consumer.snapshot().pose.value.stamp_ns,'1000000000000000000000000');
});
test('recorded native occupancy percent is explicit; unknown cell encoding is rejected',()=>{
  for(const encoding of ['OCCUPANCY_PERCENT','unrecognized']){
    const h=harness(),w=v02();w.costmap_snapshot={...w.robot_pose,data:{id:'native',width:2,height:2,origin:[0,0,0],resolution_m:.2,plane_z_m:0,representation:'2D_GROUND_PLANE',cells:[-1,0,50,100],cell_encoding:encoding}};
    w.sources.costmap_snapshot={...w.sources.robot_pose};h.ingest(w);
    if(encoding==='OCCUPANCY_PERCENT'){assert.equal(h.consumer.snapshot().costmaps[0].value.cell_encoding,encoding);assert.deepEqual(h.consumer.snapshot().costmaps[0].value.cells,[-1,0,50,100]);}
    else assert.equal(h.consumer.snapshot().costmaps[0].value,null);
  }
});
test('bulk display geometry cannot replace canonical identity, receipt or evidence; retired refs are hidden',()=>{
  const w=v02(),h=harness(),ref={id:'a'.repeat(24),revision:'b'.repeat(64),role:'costmap',source:'costmap_snapshot',media_type:'application/json',bytes:123,usage:'DISPLAY_ONLY'};
  w.sources.assets=[ref];w.costmap_snapshot={...w.robot_pose,data:{asset_ref:ref}};w.sources.costmap_snapshot={...w.sources.robot_pose};
  const asset={ref,status:'READY',value:{map_binding:w.map_binding,costmap:{id:'native',width:1,height:1,cells:[100],cell_encoding:'OCCUPANCY_PERCENT',origin:[0,0,0],resolution_m:.2,plane_z_m:0,representation:'2D_GROUND_PLANE',sequence:999,stamp_ns:'1',age_ms:0,received_monotonic_ns:'1',evidence_kind:'LIVE',producer:'forged'}}};
  const a=adaptC1ScenePacket(w,context,{displayAssets:[asset],transportAgeMs:5});h.consumer.ingest(a.packet);const c=h.consumer.snapshot().costmaps[0].value;
  assert.equal(c.evidence_kind,'SYNTHETIC');assert.equal(c.producer,w.robot_pose.producer);assert.equal(c.sequence,1);assert.equal(c.receipt_source_ns,'9007199254740993');
  assert.equal(c.stamp_ns,w.robot_pose.stamp_ns);
  w.sources.assets=[];const retired=adaptC1ScenePacket(w,context,{displayAssets:[asset]});assert.equal(retired.packet.costmaps.length,0);assert.ok(retired.packet.availability.errors.includes('costmap_snapshot:DISPLAY_ASSET_UNAVAILABLE'));
});
