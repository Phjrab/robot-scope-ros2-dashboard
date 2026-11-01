import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {adaptC1ScenePacket} from '../../robot_dashboard/static/features/obstacle_scene/c1_adapter.js';
import {createSceneConsumer} from '../../robot_dashboard/static/features/obstacle_scene/consumer.js';
import {coneDimensions,coneStatus} from '../../robot_dashboard/static/features/obstacle_scene/cone_display.js';
import {createOverlayPainter} from '../../robot_dashboard/static/features/obstacle_scene/draw.js';
const original=JSON.parse(execFileSync('python',['-m','tests.integration_i0.cone_wire'],{encoding:'utf8'}));
function harness(){
  let now=0,context=structuredClone(original.context);
  const consumer=createSceneConsumer({getMap:()=>context,clock:()=>now});
  return {consumer,context,advance:n=>now+=n,setContext:c=>context=c,
    ingest(w=structuredClone(original.wire),age=0){const a=adaptC1ScenePacket(w,context,{transportAgeMs:age});assert.ok(a.packet,a.reason);return consumer.ingest(a.packet);}};
}
test('real legacy → C1 → C3 retains radius/height, null confidence, exact receipt and qualified flat space',()=>{
 const h=harness();h.ingest();const v=h.consumer.snapshot(),o=v.obstacles.value.obstacles[0];
 assert.deepEqual(coneDimensions(o),{radius:.1,height:.25});assert.equal(o.class_score,null);
 assert.equal(v.obstacles.value.receipt_source_ns,'9007199254740993');assert.match(coneStatus(v,true),/SIMULATED · VALID · ISOLATED_DEMO_ONLY/);
 assert.match(coneStatus(v,true),/HEIGHT_UNVERIFIED/);assert.equal(v.collision.value,null);
});
test('server age + transport + local elapsed expires at C1 TTL independently of pending requests',()=>{
 const h=harness(),w=structuredClone(original.wire);w.sources.obstacle_frame.received_age_ms=800;
 h.ingest(w,100);h.advance(101);assert.equal(h.consumer.snapshot().obstacles.reason,'STALE');
 assert.match(coneStatus(h.consumer.snapshot(),true),/SIMULATED · STALE/);
});
test('same stamp with a renewed receipt/sequence cannot resurrect expired display',()=>{
 const h=harness();h.ingest();h.advance(1001);const w=structuredClone(original.wire);
 w.sequence++;w.obstacle_frame.sequence++;w.sources.obstacle_frame.sequence++;
 w.obstacle_frame.received_monotonic_ns='9007199255741993';h.ingest(w);
 assert.equal(h.consumer.snapshot().obstacles.value,null);assert.equal(h.consumer.snapshot().obstacles.reason,'STALE');
});
test('same frame but foreign space, generation, session and source identity invalidate previous geometry',()=>{
 for(const change of [{space_kind:'MAP'},{generation:2},{source_epoch:'other'},{source_identity:'other'}]){
  const h=harness();h.ingest();h.setContext({...h.context,...change});assert.equal(h.consumer.snapshot().ready,false);
 }
 const h=harness(),w=structuredClone(original.wire);h.context.space_kind='MAP';h.ingest(w);
 assert.equal(h.consumer.snapshot().obstacles.value.obstacles.length,0);
 assert.match(coneStatus(h.consumer.snapshot(),true),/UNALIGNED/);
});
test('LIVE evidence cannot promote XY-only cone geometry',()=>{
 const h=harness(),w=structuredClone(original.wire);w.evidence_kind='LIVE';w.obstacle_frame.evidence_kind='LIVE';
 assert.equal(adaptC1ScenePacket(w,h.context).packet.obstacle_frame,null);
 w.sources.obstacle_frame.evidence_kind='LIVE';h.ingest(w);
 assert.equal(h.consumer.snapshot().obstacles.value.obstacles.length,0);
});
test('empty observed sample remains distinguishable from expired empty sample',()=>{
 const h=harness(),w=structuredClone(original.wire);w.obstacle_frame.obstacles=[];h.ingest(w);
 assert.match(coneStatus(h.consumer.snapshot(),true),/VALID.*0개/);h.advance(1001);
 assert.match(coneStatus(h.consumer.snapshot(),true),/STALE/);assert.doesNotMatch(coneStatus(h.consumer.snapshot(),true),/WAITING/);
});
test('server invalidation rejects late same-sequence geometry and destroy retains nothing',()=>{
 const h=harness();h.ingest();const w=structuredClone(original.wire);w.obstacle_frame=null;w.sources.obstacle_frame.status='expired';h.ingest(w);h.ingest();
 assert.equal(h.consumer.snapshot().obstacles.value,null);h.consumer.destroy();assert.equal(h.consumer.snapshot().ready,false);
 assert.equal(h.consumer.diagnostics().retainedPackets,0);
});
test('cone toggle defaults require explicit layer, one existing renderer uses true dimensions, invalid cone suppressed',()=>{
 const h=harness();h.ingest();const v=h.consumer.snapshot(),points=[];
 const ctx=new Proxy({},{get:(t,k)=>t[k]??(()=>{})}),canvas={getContext:()=>ctx};
 const scene={canvas:{getBoundingClientRect:()=>({width:400,height:300})},project:p=>{points.push([...p]);return{x:p[0]*100,y:p[1]*100-p[2]*100};}};
 const painter=createOverlayPainter(canvas,scene);painter.draw(v,{obstacles:true,cones:false},'','dark');assert.equal(points.length,0);
 painter.draw(v,{obstacles:true,cones:true},'','dark');assert.equal(painter.diagnostics().renderedObjects,5);
 assert.ok(points.some(p=>p[2]===.25));assert.ok(points.some(p=>p[2]===0));
 const object=v.obstacles.value.obstacles[0];object.provenance.radius_m=true;assert.equal(coneDimensions(object),null);
});
