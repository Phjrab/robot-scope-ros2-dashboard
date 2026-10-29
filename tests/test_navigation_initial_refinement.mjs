import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const nav = createRequire(import.meta.url)('../robot_dashboard/static/navigation.js');
const status = (state, extra={}) => nav.operationalLocalizationStatus({operational_localization:{fresh:true,ready:false,state,...extra}});

test('accepted initial seed remains aligning until actual tracking is ready', () => {
  assert.equal(nav.operationalLocalizationStatus({}), null);
  assert.equal(status('WAITING_EXPLICIT_INITIAL_POSE').label, 'NEED POSE');
  assert.equal(status('WAITING_MAP_CORRECTION').label, 'ALIGNING');
  assert.match(status('INITIAL_REFINEMENT_CONFIRMING',{metrics:{initial_confirmations:2}}).note,/2\/3/);
  assert.equal(status('MAP_TRACKING',{ready:true}).label, 'READY');
  assert.equal(status('MAP_TRACKING',{ready:true,fresh:false}).label, 'WAIT');
});
test('rejected and stale registration show actual blocker instead of asking for first pose', () => {
  for (const state of ['CORRECTION_JUMP_RESEED_REQUIRED','INITIAL_REFINEMENT_OUT_OF_BOUNDS','INITIAL_REFINEMENT_REQUIRES_STOP','MAP_CORRECTION_STALE']) {
    const result=status(state);
    assert.equal(result.label,'BLOCKED');
    assert.notEqual(result.note,'초기 위치 필요');
  }
});
