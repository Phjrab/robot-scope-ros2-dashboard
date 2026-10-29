// No reconstructed display slots: consume the exact C1 HTTP response bytes.
import { pathToFileURL } from 'node:url';
import { readFileSync } from 'node:fs';
const [directory, file] = process.argv.slice(2);
const { parseC1SceneJSON, adaptC1ScenePacket } = await import(pathToFileURL(`${directory}/c1_adapter.js`));
const { createSceneConsumer } = await import(pathToFileURL(`${directory}/consumer.js`));
const wire = parseC1SceneJSON(readFileSync(file, 'utf8'));
const context = {...wire.map_binding, frame_id:'odom', source_epoch:'synthetic-1', units:'m',
  clock_domain:'fixture-clock', stream_epoch:wire.stream_epoch, calibration_id:'fixture-calibration'};
const adapted = adaptC1ScenePacket(wire, context);
if (!adapted.packet) {
  console.log(JSON.stringify({status:'FAIL', reason:adapted.reason}));
  process.exitCode = 2;
} else {
  let now = 0;
  const consumer = createSceneConsumer({getMap:()=>context, clock:()=>now});
  const accepted = consumer.ingest(adapted.packet), view = consumer.snapshot();
  now = 2000;
  const expired = consumer.snapshot();
  const count = view.obstacles?.value?.obstacles?.length ?? 0;
  const ok = accepted && count === wire.obstacle_frame.obstacles.length && count > 0
    && !view.collision.value && !expired.obstacles.value;
  console.log(JSON.stringify({status:ok?'PASS':'FAIL', accepted, obstacle_count:count,
    collision_status:'UNAVAILABLE', collision_reason:view.collision.reason,
    references_verified:adapted.packet.collision_assessment?.references_verified ?? false,
    expiry_preserved:!expired.obstacles.value, schema_profile:'EXPLICIT_C1_0.1',
    scope:'ACTUAL_JS_CONSUMER_NOT_BROWSER_RENDER'}));
  process.exitCode = ok ? 0 : 2;
}
