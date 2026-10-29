import fs from 'node:fs';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const {parseC1SceneJSON, adaptC1ScenePacket} = await import(pathToFileURL(
  `${input.deps}/C3/robot_dashboard/static/features/obstacle_scene/c1_adapter.js`));
const path = '/api/v1/extensions/scene/snapshot';
const denied = await fetch(input.url + path);
assert.equal(denied.status, 401);
const response = await fetch(input.url + path, {
  headers: {Authorization: 'Bearer public-c1-composition-test-only'},
});
assert.equal(response.status, 200);
const raw = await response.text();
const wire = parseC1SceneJSON(raw);
const context = {...wire.map_binding, stream_epoch: wire.stream_epoch,
  source_epoch: 'synthetic-1', frame_id: 'odom', clock_domain: 'fixture-clock', units: 'm'};
const adapted = adaptC1ScenePacket(wire, context);
if (wire.schema_version === '0.1') {
  assert.equal(adapted.reason, '');
  assert.deepEqual(adapted.packet.availability.errors, []);
  assert.equal(adapted.packet.obstacle_frame.obstacles.length, wire.obstacle_frame.obstacles.length);
  assert.deepEqual(adapted.packet.obstacle_frame.obstacles[0].geometry.center_m,
    wire.obstacle_frame.obstacles[0].geometry.center);
  const delayed = adaptC1ScenePacket(wire, context, {transportAgeMs: 25});
  assert.equal(delayed.packet.obstacle_frame.age_ms, adapted.packet.obstacle_frame.age_ms + 25);
} else {
  assert.equal(adapted.reason, 'C1_VERSION_UNSUPPORTED');
  assert.equal(adapted.packet, null);
}
process.stdout.write(JSON.stringify({schema_version: wire.schema_version,
  result: adapted.packet ? 'PASS_OBSTACLE_ONLY' : 'FAIL', reason: adapted.reason,
  bytes: Buffer.byteLength(raw), objects: adapted.packet?.obstacle_frame?.obstacles.length,
  availability: adapted.packet?.availability}));
