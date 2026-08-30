import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  COMPETITION_STALE_MS,
  projectCompetitionStatus,
  reduceCompetitionState,
} from '../robot_dashboard/static/features/cockpit/competition_status.js';

const NOW = 20_000;

function backend(overrides = {}) {
  return {
    generation: 4,
    updatedAt: NOW - 100,
    competition: {
      operation_mode: 'MANUAL', requested_mode: 'MANUAL', locked: false,
      motion_authority: 'NONE', perception_mode: 'SHADOW',
    },
    models: {
      active: { lane: { model_id: 'lane-v2' }, object: { model_id: 'yolo-v3' } },
      previous: { lane: 'lane-v1', object: 'yolo-v2' },
    },
    ...overrides,
  };
}

test('competition reducer rejects stale generations and reset never restores authority', () => {
  const live = reduceCompetitionState(undefined, { type: 'SUCCESS', generation: 8, updatedAt: NOW, competition: { requested_mode: 'MANUAL' }, models: {} });
  const stale = reduceCompetitionState(live, { type: 'SUCCESS', generation: 7, updatedAt: NOW + 1, competition: { requested_mode: 'AUTO' }, models: {} });
  assert.equal(stale.competition.requested_mode, 'MANUAL');
  const reset = reduceCompetitionState(stale, { type: 'RESET' });
  assert.equal(reset.competition, null);
  assert.equal(reset.updatedAt, 0);
});

test('competition projection separates network, camera, perception, model and dataset status', () => {
  const projection = projectCompetitionStatus({
    state: backend(),
    dataset: { capture: { active: true, sessionId: 'session-7' } },
    cameraCatalog: { sources: [
      { id: 'go2_front', connection: 'live', fps: 14 },
      { id: 'realsense_color', connection: 'live', metadata: {
        fps: 15, age_s: 0.1, receive_bitrate_mbps: 4.2, receive_fps: 14.9,
        browser_reconnects: 2, cross_host_latency_state: 'UNVERIFIED_CLOCK_DOMAIN',
        relay_health: { wifi: { state: 'LIVE', rssi_dbm: -52, link_mbps: 433 } },
        browser_decode: { decodedFrames: 20, decodeFailures: 1, supersededFrames: 3 },
      } },
    ] },
    perception: { updatedAt: NOW - 100, snapshot: { transport_state: 'LIVE', results: [
      { task: 'lane', result_status: 'LIVE', model_id: 'lane-v2', model_sha256: 'a'.repeat(64), sequence: 8, source_sequence: 108, source_epoch: 7, input_age_s: 0.2, last_receive_age: 0.1, inference_fps: 12, inference_p95_ms: 8, confidence: 0.91 },
      { task: 'object', result_status: 'LIVE', model_id: 'yolo-v3', model_sha256: 'b'.repeat(64), sequence: 9, source_sequence: 109, source_epoch: 7, input_age_s: 0.2, last_receive_age: 0.1, inference_fps: 10, inference_p95_ms: 18, confidence: 0.82 },
      { task: 'depth_summary', result_status: 'LIVE', model_id: 'depth-v1', model_sha256: 'c'.repeat(64), sequence: 10, source_sequence: 110, source_epoch: 7, input_age_s: 0.2, last_receive_age: 0.1, inference_fps: 8, inference_p95_ms: 22, confidence: 0.75 },
    ] } },
  }, NOW);
  assert.equal(projection.operationMode, 'MANUAL');
  assert.equal(projection.authority, 'NONE');
  assert.equal(projection.perceptionMode, 'SHADOW');
  assert.equal(projection.dataset, 'CAPTURING · session-7');
  assert.match(projection.robotWifi, /RSSI -52 dBm · LINK 433\.0 Mbps/);
  assert.match(projection.rtt, /^UNAVAILABLE/);
  assert.equal(projection.tasks.lane.state, 'LIVE');
  assert.equal(projection.tasks.lane.sourceSequence, '108');
  assert.equal(projection.tasks.lane.sourceEpoch, '7');
  assert.equal(projection.tasks.lane.inputAge, '0.30 s');
  assert.match(projection.tasks.lane.model, /lane-v2 · a{12}/);
  assert.match(projection.tasks.lane.performance, /P95 8\.0 ms/);
  assert.equal(projection.pointcloudMode, 'SUMMARY');
  assert.equal(projection.activeModel.includes('TRANSITION'), false);
  assert.match(projection.previousModel, /lane:lane-v1/);
});

test('stale backend and perception fail closed without showing cached live authority', () => {
  const stale = projectCompetitionStatus({
    state: backend({ updatedAt: NOW - COMPETITION_STALE_MS - 1 }),
    perception: { updatedAt: NOW - 3000, snapshot: { transport_state: 'LIVE', results: [{ task: 'lane', result_status: 'LIVE', model_id: 'lane-v2', sequence: 1, source_sequence: 1, source_epoch: 1, input_age_s: 0.1, last_receive_age: 0.1 }] } },
  }, NOW);
  assert.match(stale.operationMode, /^SAFE_STOP/);
  assert.equal(stale.lock, 'UNKNOWN · BLOCKED');
  assert.equal(stale.authority, 'NONE');
  assert.equal(stale.tasks.lane.state, 'STALE');
});

test('model mismatch is explicit TRANSITION and implementation creates no sensor viewer', () => {
  const transition = projectCompetitionStatus({
    state: backend(),
    perception: { updatedAt: NOW, snapshot: { transport_state: 'LIVE', results: [{ task: 'lane', result_status: 'LIVE', model_id: 'lane-old', model_sha256: 'd'.repeat(64), sequence: 2, source_sequence: 2, source_epoch: 1, input_age_s: 0.1, last_receive_age: 0.1 }] } },
  }, NOW);
  assert.match(transition.activeModel, /^TRANSITION/);
  const source = readFileSync(new URL('../robot_dashboard/static/features/cockpit/competition_status.js', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /cameraDemand\?\.acquire|new\s+WebSocket|VideoDecoder/);
  assert.match(source, /ASSISTED.*AUTO/s);
  assert.match(source, /hardware acceptance and competition-rule review required/);
});
