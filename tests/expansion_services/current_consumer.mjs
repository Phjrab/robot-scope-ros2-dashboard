// Exact C1 HTTP bytes -> pinned C3 parser/adapter/stateful consumer. No DTO copies.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const base=`${input.deps}/C3/robot_dashboard/static/features/obstacle_scene`;
const {parseC1SceneJSON,adaptC1ScenePacket}=await import(pathToFileURL(`${base}/c1_adapter.js`));
const {createSceneConsumer}=await import(pathToFileURL(`${base}/consumer.js`));
const adapt=(name,options={})=>{
 const row=input.responses[name], wire=parseC1SceneJSON(row.raw);
 const out=adaptC1ScenePacket(wire,row.context,options);
 assert.equal(wire.schema_version,'0.2');assert.equal(out.reason,'');assert(out.packet);
 return out.packet;
};
let now=0,context=input.responses.ready.context;
const consumer=createSceneConsumer({getMap:()=>context,clock:()=>now});
const ready=adapt('ready'),newer=adapt('newer');
assert(consumer.ingest(ready));
const initial=consumer.snapshot();
assert(initial.obstacles.value.obstacles.length>0);
assert.equal(initial.pose.value,null);assert.equal(initial.joints.value,null);
assert.equal(initial.collision.value,null);
assert.equal(ready.collision_assessment.severity,'UNKNOWN');
assert.equal(ready.collision_assessment.references_verified,null); // Missing actual pose reference.
assert.equal(ready.collision_assessment.envelope_geometry_status,'UNAVAILABLE');
assert.equal(ready.collision_assessment.protection_mode,'ACTIVE_CONSTRAINT');
assert(consumer.ingest(newer));assert.equal(consumer.ingest(ready),false);
const oldSequenceReason=consumer.diagnostics().error;
assert(consumer.offer(adapt('expired'))); // Expiry invalidation while presentation is paused.
assert.equal(consumer.snapshot().obstacles.value,null);
assert(consumer.ingest(newer)); // Equal-sequence response may arrive; cannot revive retired source.
assert.equal(consumer.snapshot().obstacles.value,null);
const delayed=adapt('ready',{transportAgeMs:1500});
assert(delayed.collision_assessment.remaining_ms<0);
const late=createSceneConsumer({getMap:()=>context,clock:()=>now});
assert(late.ingest(delayed));assert.equal(late.snapshot().obstacles.value,null);
const queued=createSceneConsumer({getMap:()=>context,clock:()=>now});
const arrival=queued.offer(ready);now=2600;
assert(queued.ingest(ready,arrival));assert.equal(queued.snapshot().obstacles.value,null);
now=0;context=input.responses.restart.context;
assert(consumer.ingest(adapt('restart')));
assert(consumer.snapshot().obstacles.value);
assert.equal(consumer.ingest(newer),false);
const oldEpochReason=consumer.diagnostics().error;
context=input.responses.map_reset.context;
assert(consumer.ingest(adapt('map_reset')));
assert.equal(consumer.snapshot().obstacles.value,null);
const wrongMap=adaptC1ScenePacket(parseC1SceneJSON(input.responses.ready.raw),context);
assert.equal(wrongMap.reason,'C1_MAP_GENERATION_MISMATCH');
const unknown=adapt('wrong_host_clock');
const noClock=createSceneConsumer({getMap:()=>input.responses.wrong_host_clock.context,clock:()=>0});
assert(noClock.ingest(unknown));assert.equal(noClock.snapshot().obstacles.value,null);
assert.equal(unknown.obstacle_frame,null);
const high=adapt('high_ns');
assert.equal(high.obstacle_frame.receipt_source_ns,input.high_receipt_ns);
assert.throws(()=>parseC1SceneJSON(input.responses.ready.raw+' '.repeat(128*1024)),/C1_DOCUMENT_LIMIT/);
process.stdout.write(JSON.stringify({result:'PASS',accepted_canonical_v02:true,
 obstacle_count:initial.obstacles.value.obstacles.length,collision:'UNAVAILABLE',
 collision_reason:initial.collision.reason,pose:'MISSING',joints:'MISSING',
 drawable_envelope:'UNAVAILABLE',unknown_preserved:true,old_sequence:oldSequenceReason,
 old_epoch:oldEpochReason,map_revision:wrongMap.reason,delayed_ttl:'EXPIRED',
 paused_receipt:'ORIGINAL_AGE_PRESERVED',expired_response_replay:'NOT_REVIVED',
 wrong_host_clock:'UNAVAILABLE',transport_limit:'REJECTED',high_ns:'LOSSLESS',
 scope:'ACTUAL_JS_CONSUMER_NOT_BROWSER_OR_ROBOT'}));
