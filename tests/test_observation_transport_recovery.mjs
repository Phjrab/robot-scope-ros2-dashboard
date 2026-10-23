import assert from 'node:assert/strict';
import test from 'node:test';
import { createPoseTransport, createSocketWatchdog } from '../robot_dashboard/static/features/sensors/socket_watchdog.js';
import { createPointcloudTransport } from '../robot_dashboard/static/features/sensors/pointcloud_transport.js';

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
  return { setTimeout, clearTimeout, tick, timers, sockets, socketFactory, frames,
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
