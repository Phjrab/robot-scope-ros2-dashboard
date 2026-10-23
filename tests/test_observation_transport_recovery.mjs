import assert from 'node:assert/strict';
import test from 'node:test';
import { createPoseTransport, createSocketWatchdog } from '../robot_dashboard/static/features/sensors/socket_watchdog.js';
import { createPointcloudTransport } from '../robot_dashboard/static/features/sensors/pointcloud_transport.js';
import { LiveMapObservation } from '../robot_dashboard/static/features/maps/live_observation_contract.js';

function fixture() {
  let now = 0, id = 0;
  const timers = new Map(), sockets = [], frames = new Map();
  const setTimeout = (fn, delay) => { const key = ++id; timers.set(key, { at: now + delay, fn }); return key; };
  const clearTimeout = key => timers.delete(key);
  function tick(ms) {
    const end = now + ms;
    for (;;) {
      const next = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      timers.delete(next[0]); now = next[1].at; next[1].fn();
    }
    now = end;
  }
  const socketFactory = () => {
    const socket = { readyState: 1, close() { this.readyState = 3; this.onclose?.(); } };
    sockets.push(socket); return socket;
  };
  return { now: () => now, setTimeout, clearTimeout, tick, timers, sockets, socketFactory, frames,
    requestAnimationFrame(fn) { const key = ++id; frames.set(key, fn); return key; },
    cancelAnimationFrame(key) { frames.delete(key); } };
}

test('silent OPEN pose socket reconnects without waiting for close; late old messages cannot update pose', () => {
  const f = fixture(), values = [];
  const t = createPoseTransport({ ...f, url: 'ws://test/pose', onSnapshot: value => values.push(value) });
  t.start();
  const old = f.sockets[0];
  const original = { seq: 1, observation: { source_stamp_ns: '123', received_monotonic_s: 10 } };
  old.onmessage({ data: JSON.stringify(original) });
  f.tick(600);
  assert.equal(f.sockets.length, 2);
  old.onmessage({ data: JSON.stringify({ seq: 999 }) });
  assert.deepEqual(values, [original], 'recovery cannot invent a fresh pose or rewrite its clocks');
  f.sockets[1].onmessage({ data: JSON.stringify({ seq: 2 }) });
  assert.equal(values.at(-1).seq, 2);
  t.destroy(); f.tick(10000);
  assert.equal(f.sockets.length, 2);
  assert.equal(f.timers.size, 0);
});

test('pose reconnect is bounded when handshake or first message never arrives', () => {
  const f = fixture();
  const t = createPoseTransport({ ...f, url: 'ws://test/pose', onSnapshot() {} });
  t.start(); t.start(); f.tick(2999); assert.equal(f.sockets.length, 1);
  f.tick(1); assert.equal(f.sockets.length, 2);
  t.destroy();
});

test('stopped watchdog ignores callbacks already queued by the browser', () => {
  const f = fixture(); let fired = 0;
  const w = createSocketWatchdog(() => fired++, f);
  const queued = [...f.timers.values()][0].fn;
  w.stop(); queued(); w.received(); f.tick(10000);
  assert.equal(fired, 0); assert.equal(f.timers.size, 0);
});

function cloudTransport(f, values) {
  return createPointcloudTransport({ ...f, fetchFn: async () => ({ status: 204, ok: true }),
    decodeFrame: buffer => ({ seq: new Uint8Array(buffer)[0], stream_id: 'same-stream',
      points: [1, 2, 3], observation: { source_stamp_ns: '456', received_monotonic_s: 20 } }),
  });
}

test('pointcloud ingestion continues when animation frames are suspended; late RAF does not duplicate delivery', () => {
  const f = fixture(), values = [], t = cloudTransport(f);
  t.subscribe('test', v => values.push(v)); t.replaceDemand(['maps']);
  f.sockets[0].onmessage({ data: new Uint8Array([1]).buffer });
  const delayedRAF = [...f.frames.values()][0];
  f.tick(100); assert.equal(values.length, 1);
  assert.equal(values[0].observation.source_stamp_ns, '456');
  assert.equal(values[0].observation.received_monotonic_s, 20);
  delayedRAF(); assert.equal(values.length, 1);
  t.destroy();
});

test('pointcloud timeout replaces silent connection and fences late old messages, not source generation', () => {
  const f = fixture(), values = [], t = cloudTransport(f);
  t.subscribe('test', v => values.push(v)); t.replaceDemand(['maps']);
  const old = f.sockets[0]; old.onmessage({ data: new Uint8Array([1]).buffer });
  f.tick(600); assert.equal(f.sockets.length, 2);
  old.onmessage({ data: new Uint8Array([99]).buffer });
  f.sockets[1].onmessage({ data: new Uint8Array([2]).buffer });
  f.tick(100);
  assert.deepEqual(values.map(v => v.seq), [1, 2]);
  assert.equal(t.diagnostics().streamId, 'same-stream');
  t.replaceDemand([]); f.tick(10000);
  assert.equal(f.sockets.length, 2); assert.equal(f.timers.size, 0);
  t.destroy();
});

test('healthy pointcloud input reuses one socket and releasing demand cancels queued ingestion', () => {
  const f = fixture(), values = [], t = cloudTransport(f);
  t.subscribe('test', v => values.push(v)); t.replaceDemand(['maps']);
  for (let seq = 1; seq < 20; seq++) {
    f.sockets[0].onmessage({ data: new Uint8Array([seq]).buffer }); f.tick(200);
  }
  assert.equal(f.sockets.length, 1);
  f.sockets[0].onmessage({ data: new Uint8Array([20]).buffer });
  const queued = [...f.frames.values()][0];
  t.replaceDemand([]); queued(); f.tick(10000);
  assert.equal(values.length, 19); assert.equal(f.timers.size, 0);
  t.destroy();
});

test('moving IMU estimate survives brief socket silence, paused RAF and same-map refresh but never stale input', () => {
  const f = fixture(), model = new LiveMapObservation(f.now);
  const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), kind: 'pointcloud3d' };
  const reference = { revision: map.revision, frame_id: 'map', points: [1, 2, 3] };
  model.enable(true); model.setContinuousEstimate(true); model.setMap(map, reference);
  const observed = (seq, epoch) => ({ observer_id: 'd'.repeat(32), publisher_epoch: epoch.repeat(32),
    publisher_gid: epoch.repeat(32), publisher_count: 1, identity_status: 'OBSERVED_PUBLISHER',
    source_stamp_ns: String(1792309179130175352n + BigInt(seq)), received_monotonic_s: 100 + f.now() / 1000,
    receipt_clock: 'OBSERVER_HOST_MONOTONIC' });
  const pt = createPoseTransport({ ...f, url: 'ws://test/pose', onSnapshot: v => model.ingestPose(v) });
  const ct = createPointcloudTransport({ ...f, fetchFn: async () => ({ status: 204, ok: true }),
    // Synthetic geometry exercises transport/state only, never registration accuracy.
    decodeFrame: b => JSON.parse(new TextDecoder().decode(b)) });
  pt.start(); ct.subscribe('model', v => model.ingestCloud(v)); ct.replaceDemand(['maps']);
  function deliver(poseSocket, cloudSocket, seq, x, yaw = 0, epoch = 'c') {
    poseSocket.onmessage({ data: JSON.stringify({ seq, topic: '/Odometry', frame_id: 'camera_init', child_frame_id: 'body',
      state: 'ok', age_s: 0, position: { x, y: 0, z: .3 }, orientation: { x: 0, y: 0, z: Math.sin(yaw / 2), w: Math.cos(yaw / 2) },
      observation: observed(seq, epoch) }) });
    cloudSocket.onmessage({ data: new TextEncoder().encode(JSON.stringify({ seq, stream_id: 'same-source',
      topic: '/cloud_registered', pipeline_stage: 'registered', frame_id: 'camera_init', units: 'm',
      points: [1, 2, 3], observation: observed(seq, epoch) })).buffer });
  }
  const [oldPose, oldCloud] = f.sockets;
  deliver(oldPose, oldCloud, 1, 0); f.tick(100);
  model.setAnchor({ x: 0, y: 0, z: .3, roll: 0, pitch: 0, yaw: 0 }, true); model.snapshot();
  f.tick(250); deliver(oldPose, oldCloud, 2, .2); f.tick(100); model.snapshot();
  const generation = model.generation;
  f.tick(600); // Both watchdogs replace sockets, without changing publisher identity.
  assert.equal(f.sockets.length, 4);
  model.setMap({ ...map, name: 'Refreshed label', point_count: 41073 }, reference);
  deliver(oldPose, oldCloud, 99, 99, 0, 'e'); // Fenced late callbacks must not change source or pose.
  deliver(f.sockets[2], f.sockets[3], 3, .4, .3); f.tick(100);
  const moving = model.snapshot();
  assert.equal(model.generation, generation); assert.equal(moving.status, 'SAME_START_ODOMETRY_ESTIMATE');
  assert.equal(moving.pose.x, .4); assert.ok(Math.abs(moving.pose.yaw - .3) < 1e-8);
  assert.equal(moving.trail[0].x, 0); assert.equal(moving.trail.length, 3);
  assert.equal(moving.source_stamp_ns, String(1792309179130175355n));
  assert.equal(model.cloud.value.observation.received_monotonic_s, 101.05);
  f.tick(1001);
  const stale = model.snapshot();
  assert.equal(stale.status, 'STALE'); assert.equal(stale.pose, null); assert.equal(model.anchor, null);
  deliver(f.sockets[4], f.sockets[5], 4, .5); f.tick(100);
  assert.equal(model.snapshot().pose, null, 'fresh recovery cannot silently restore an invalidated anchor');
  assert.deepEqual(model.trail, []);
  pt.destroy(); ct.destroy();
  assert.equal(f.timers.size, 0);
});
