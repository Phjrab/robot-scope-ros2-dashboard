import test from 'node:test';
import assert from 'node:assert/strict';
import { observationSessionView } from '../robot_dashboard/static/features/maps/observation_session.js';

test('service readiness is distinct from alignment and countdown uses elapsed duration', () => {
  const view = observationSessionView({state:'READY',remaining_s:120,session_id:'a'.repeat(32),can_stop:true},61);
  assert.equal(view.label,'입력 준비 완료'); assert.equal(view.ready,true);
  assert.equal(view.canStart,false); assert.equal(view.canStop,true);
  assert.match(view.detail,/남은 1분/);
  assert.equal(observationSessionView({state:'WAITING_INPUTS'}).ready,false);
});
test('unknown service and invalid session never expose an executable stop', () => {
  assert.equal(observationSessionView().canStart,false);
  assert.equal(observationSessionView({can_stop:true,session_id:'other-unit'}).canStop,false);
  assert.equal(observationSessionView({state:'STOPPED',can_start:true}).canStart,true);
  assert.match(observationSessionView({state:'UNAVAILABLE'}).label,/사용 불가/);
});
