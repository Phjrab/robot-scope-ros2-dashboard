import {pathToFileURL} from 'node:url';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const [directory,file]=process.argv.slice(2);
const {parseC1SceneJSON,adaptC1ScenePacket}=await import(pathToFileURL(`${directory}/c1_adapter.js`));
const {createSceneConsumer}=await import(pathToFileURL(`${directory}/consumer.js`));
const raw=readFileSync(file,'utf8'), wire=parseC1SceneJSON(raw);
const obstacle=wire.obstacle_frame;
assert.equal(wire.schema_version,'0.2');
const context={...wire.map_binding,frame_id:obstacle.frame_key.frame_id,source_epoch:obstacle.source_epoch,
  clock_domain:obstacle.clock_domain,stream_epoch:wire.stream_epoch,calibration_id:obstacle.calibration_id,units:'m'};
const adapted=adaptC1ScenePacket(wire,context);
assert.ok(adapted.packet,adapted.reason);
let now=0;
const consumer=createSceneConsumer({getMap:()=>context,clock:()=>now});
assert.equal(consumer.ingest(adapted.packet),true);
const view=consumer.snapshot();
assert.equal(view.obstacles.value.obstacles.length,obstacle.obstacles.length);
assert.equal(view.collision.value,null);
assert.equal(view.collision.reason,'POSE_JOINT_OR_SOURCE_INSUFFICIENT');
assert.equal(String(obstacle.received_monotonic_ns),String(wire.collision_assessment.received_monotonic_ns));
now=2600;
assert.equal(consumer.snapshot().obstacles.value,null);
console.log(JSON.stringify({status:'PASS',schema:'0.2',obstacles:obstacle.obstacles.length,
  collision_drawable:'UNAVAILABLE',reason:view.collision.reason,receipt:obstacle.received_monotonic_ns,
  expiry:'PASS',scope:'EXACT_C1_HTTP_BYTES_REPLAY_IN_ACTUAL_C3_NOT_BROWSER_RENDER'}));
