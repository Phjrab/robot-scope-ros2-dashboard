import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const streamSource = readFileSync(new URL('../robot_dashboard/static/pointcloud_stream.js', import.meta.url), 'utf8');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');

const sandbox = {
  ArrayBuffer,
  DataView,
  Float32Array,
  TextDecoder,
  Uint8Array,
};
sandbox.globalThis = sandbox;
sandbox.window = sandbox;
runInNewContext(streamSource, sandbox);
const stream = sandbox.RobotPointCloudStream;

function encodeFrame(metadata, values) {
  const json = new TextEncoder().encode(JSON.stringify({
    ...metadata,
    encoding: 'float32le',
    point_count: values.length / 3,
  }));
  const payloadOffset = (16 + json.byteLength + 3) & ~3;
  const buffer = new ArrayBuffer(payloadOffset + values.length * 4);
  const view = new DataView(buffer);
  for (const [index, value] of [0x52, 0x53, 0x50, 0x43].entries()) view.setUint8(index, value);
  view.setUint8(4, 1);
  view.setUint8(5, 0);
  view.setUint16(6, json.byteLength, true);
  view.setUint32(8, values.length / 3, true);
  view.setUint32(12, values.length * 4, true);
  new Uint8Array(buffer, 16, json.byteLength).set(json);
  new Float32Array(buffer, payloadOffset, values.length).set(values);
  return buffer;
}

test('binary decoder returns aligned float32 XYZ without JSON point expansion', () => {
  const frame = encodeFrame({ seq: 4, stream_id: 'server-A', topic: '/Laser_map' }, [1, 2, 3, -4, 5.5, 6]);
  const decoded = stream.decodeFrame(frame);
  assert.equal(decoded.seq, 4);
  assert.equal(decoded.stream_id, 'server-A');
  assert.equal(decoded.point_count, 2);
  assert.deepEqual(Array.from(decoded.points), [1, 2, 3, -4, 5.5, 6]);
  assert.equal(decoded.points.buffer, frame, 'aligned payload should remain zero-copy');
  assert.equal(decoded.prevalidated, true);
});

test('binary decoder rejects bad magic, bad lengths and oversized claims', () => {
  const frame = encodeFrame({ seq: 1 }, [1, 2, 3]);
  const badMagic = frame.slice(0);
  new Uint8Array(badMagic)[0] = 0;
  assert.throws(() => stream.decodeFrame(badMagic), /magic/);
  assert.throws(() => stream.decodeFrame(frame.slice(0, -1)), /length/);
  const badCount = frame.slice(0);
  new DataView(badCount).setUint32(8, 2_000_000, true);
  assert.throws(() => stream.decodeFrame(badCount), /payload size/);
});

test('registered-cloud reservoir is bounded, idempotent and source-scoped', () => {
  const reservoir = new stream.RegisteredCloudReservoir(1000);
  const values = new Float32Array(1500 * 3);
  for (let index = 0; index < 1500; index += 1) {
    values[index * 3] = index;
    values[index * 3 + 1] = index / 2;
    values[index * 3 + 2] = 1;
  }
  const first = reservoir.ingest({ seq: 1, topic: '/Laser_map', frame_id: 'map', source_points: 1500, points: values }, null);
  assert.equal(first.sent_points, 1000);
  assert.equal(first.points.length, 3000);
  assert.equal(first.display_capped, true);
  assert.equal(reservoir.ingest({ seq: 1, topic: '/Laser_map', frame_id: 'map', points: values }, null), first);

  const nextSource = reservoir.ingest({ seq: 1, topic: '/lidar_points', frame_id: 'hesai', points: Float32Array.of(1, 2, 3) }, 1000);
  assert.equal(nextSource.sent_points, 1);
  assert.equal(nextSource.points.length, 3);
});

test('mapping transport is page-aware, view-aware and resets on server epoch change', () => {
  const activateStart = appSource.indexOf('function activatePage(');
  const activateEnd = appSource.indexOf('\nfunction showToast', activateStart);
  const activate = appSource.slice(activateStart, activateEnd);
  assert.match(activate, /syncPointcloudTransport\(\)/);
  assert.match(activate, /syncCameraTransport\(\)/);
  assert.match(appSource, /function pointcloudTransportWanted\(\)[\s\S]{0,160}activePage === 'mapping'[\s\S]{0,160}desiredMapView\(\) !== 'occupancy'/);
  assert.match(appSource, /streamChanged \|\| legacySequenceRollback/);
  assert.match(appSource, /resetPointcloudStream\(incomingStreamId\)/);
  assert.match(appSource, /document\.addEventListener\('visibilitychange',[\s\S]{0,360}syncPointcloudTransport\(\)/);
});

test('camera relay is requested only while the Sensors page is visible', () => {
  assert.match(appSource, /function cameraTransportWanted\(\)[\s\S]{0,120}activePage === 'sensors' && !document\.hidden/);
  assert.match(appSource, /function disconnectCamera\(\)[\s\S]{0,500}cameraSocketGeneration \+= 1/);
  assert.doesNotMatch(appSource, /initializeRobotProfiles\(\);\s*connectCamera\(\)/);
});
