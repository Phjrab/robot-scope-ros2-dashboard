import assert from 'node:assert/strict';
import test from 'node:test';

import { createPerceptionClient, drawPerceptionOverlay, projectPerceptionOverlay } from '../robot_dashboard/static/features/perception/result_overlay.js';

function snapshot(status = 'LIVE') {
  return {
    mode: 'SHADOW',
    transport_state: 'LIVE',
    results: [
      { task: 'lane', result_status: status, model_id: 'lane-1', sequence: 12, last_receive_age: 0.1, inference_fps: 9.8, inference_latency_ms: 21.4, input_width: 640, input_height: 480, clock_domain_verified: false, payload: { lateral_error_normalized: 0.1, curvature: 0.02, left_lane_visible: true, right_lane_visible: true } },
      { task: 'object', result_status: status, model_id: 'object-1', sequence: 11, last_receive_age: 0.2, inference_fps: 7, inference_latency_ms: 32, input_width: 640, input_height: 480, clock_domain_verified: false, payload: { detections: [{ class_name: 'cone', confidence: 0.8, x1: 10, y1: 20, x2: 100, y2: 200 }] } },
    ],
  };
}

test('shadow overlay transitions live results to visibly inactive stale state', () => {
  const live = projectPerceptionOverlay(snapshot(), 'realsense_color', 100);
  assert.equal(live.state, 'LIVE');
  assert.equal(live.visualState, 'active');
  assert.equal(live.mode, 'SHADOW');
  assert.equal(live.sequence, 12);
  assert.equal(live.clock, 'UNVERIFIED CLOCK');
  const stale = projectPerceptionOverlay(snapshot(), 'realsense_color', 2_001);
  assert.equal(stale.state, 'STALE');
  assert.equal(stale.visualState, 'inactive');
  assert.ok(stale.results.every((item) => item.result_status === 'STALE'));
  const mixed = snapshot();
  mixed.results[1].result_status = 'STALE';
  const degraded = projectPerceptionOverlay(mixed, 'realsense_color', 10);
  assert.equal(degraded.state, 'DEGRADED');
  assert.equal(degraded.visualState, 'inactive');
  const offline = snapshot();
  offline.transport_state = 'OFFLINE';
  const disconnected = projectPerceptionOverlay(offline, 'realsense_color', 10);
  assert.equal(disconnected.state, 'OFFLINE');
  assert.ok(disconnected.results.every((item) => item.result_status === 'STALE'));
  const unrelated = projectPerceptionOverlay(snapshot(), 'go2_front', 10);
  assert.equal(unrelated.state, 'OFFLINE');
  assert.equal(unrelated.results.length, 0);
});

test('overlay renderer clears old geometry before every draw and stale draw remains gray', () => {
  const calls = [];
  const context = new Proxy({}, {
    get(_target, property) {
      if (['measureText'].includes(property)) return () => ({ width: 30 });
      if (['save', 'restore', 'clearRect', 'strokeRect', 'fillRect', 'fillText', 'beginPath', 'moveTo', 'quadraticCurveTo', 'stroke', 'setLineDash'].includes(property)) return (...args) => calls.push([property, ...args]);
      return undefined;
    },
    set(_target, property, value) { calls.push([property, value]); return true; },
  });
  const canvas = { width: 1, height: 1, getContext: () => context };
  const frame = { width: 640, height: 480 };
  assert.equal(drawPerceptionOverlay(canvas, frame, projectPerceptionOverlay(snapshot(), 'realsense_color', 10)), true);
  assert.equal(calls[0][0], 'clearRect');
  calls.length = 0;
  drawPerceptionOverlay(canvas, frame, projectPerceptionOverlay(snapshot(), 'realsense_color', 3_000));
  assert.equal(calls[0][0], 'clearRect');
  assert.ok(calls.some((entry) => entry[0] === 'strokeStyle' && String(entry[1]).includes('180,190,187')));
  calls.length = 0;
  drawPerceptionOverlay(canvas, { width: 1, height: 1 }, projectPerceptionOverlay({}, 'realsense_color', Infinity));
  assert.equal(calls[0][0], 'clearRect');
});

test('perception client is read only and preserves results as offline after reconnect loss', async () => {
  let callback = null;
  let requestCount = 0;
  const states = [];
  const client = createPerceptionClient({
    api: async (path) => {
      assert.equal(path, '/api/v1/perception/latest');
      requestCount += 1;
      if (requestCount > 1) throw new Error('offline');
      return snapshot();
    },
    now: () => 1000,
    setInterval: (value) => { callback = value; return 7; },
    clearInterval: () => {},
  });
  client.subscribe((value) => states.push(value.transport_state));
  client.start();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await callback();
  assert.deepEqual(states.slice(-2), ['LIVE', 'OFFLINE']);
  assert.equal(client.snapshot().snapshot.results.length, 2);
  client.stop();
});
