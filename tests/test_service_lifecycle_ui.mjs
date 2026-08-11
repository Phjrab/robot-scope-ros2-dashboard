import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

function functionSource(name, nextName) {
  const start = appSource.indexOf(`function ${name}(`);
  const plainEnd = nextName ? appSource.indexOf(`\nfunction ${nextName}(`, start) : -1;
  const asyncEnd = nextName ? appSource.indexOf(`\nasync function ${nextName}(`, start) : -1;
  const candidates = [plainEnd, asyncEnd].filter((value) => value > start);
  const end = candidates.length ? Math.min(...candidates) : -1;
  assert.ok(start >= 0 && end > start, `${name} source must exist`);
  return appSource.slice(start, end);
}

test('Settings exposes dashboard-only restart and stop controls with explicit warning', () => {
  for (const id of [
    'serviceLifecycleState', 'serviceLifecycleName', 'serviceLifecycleInstance',
    'serviceLifecyclePrivilege', 'serviceLifecycleOperation',
    'serviceLifecycleConfirm', 'serviceRestartButton', 'serviceStopButton',
    'serviceLifecycleMessage',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  assert.match(indexSource, /대시보드 서비스만 제어합니다/);
  assert.match(indexSource, /Jetson 전원 종료·재부팅 기능이 아닙니다/);
  assert.match(indexSource, /SSH 또는 systemd/);
  assert.doesNotMatch(indexSource, /POWER OFF JETSON|REBOOT JETSON/);
});

test('service lifecycle confirmation does not request or transmit an admin key', () => {
  assert.doesNotMatch(indexSource, /serviceAdminToken|관리 키/);
  const request = functionSource('requestServiceLifecycle', 'formatHz');
  assert.doesNotMatch(request, /serviceAdminToken|X-Robot-Scope-Admin-Token|token/);
});

test('restart and stop use only the fixed lifecycle API contract', () => {
  const request = functionSource('requestServiceLifecycle', 'formatHz');
  assert.match(appSource, /api\('\/api\/v1\/system\/service'\)/);
  assert.match(request, /api\(`\/api\/v1\/system\/service\/\$\{action\}`/);
  assert.match(request, /method: 'POST'/);
  assert.match(request, /JSON\.stringify\(\{ confirmed: true \}\)/);
  assert.match(request, /!\['restart', 'stop'\]\.includes\(action\)/);
  assert.doesNotMatch(request, /reboot|poweroff|shutdown|arbitrary|service_name/);
});

test('buttons require server readiness and the local acknowledgement', () => {
  const render = functionSource('renderServiceLifecycle', 'completeExpectedServiceTransition');
  assert.match(render, /Boolean\(ui\.serviceLifecycleConfirm\.checked\)/);
  assert.match(render, /!snapshot\?\.can_restart \|\| !locallyConfirmed/);
  assert.match(render, /!snapshot\?\.can_stop \|\| !locallyConfirmed/);
  assert.match(render, /serviceLifecycleBusy \|\| Boolean\(expected\) \|\| serviceLifecycleOperationActive/);
});

test('restart treats a disconnect as expected and verifies a new server instance', () => {
  const outcome = functionSource('serviceLifecycleTransitionOutcome', 'completeExpectedServiceTransition');
  const complete = functionSource('completeExpectedServiceTransition', 'refreshServiceLifecycle');
  const refresh = functionSource('refreshServiceLifecycle', 'requestServiceLifecycle');
  assert.match(outcome, /snapshot\.instance_id !== expected\.instanceId/);
  assert.match(complete, /대시보드가 새 인스턴스로 재시작되었습니다/);
  assert.match(refresh, /activePage !== 'settings' && !serviceLifecycleExpected/);
  assert.match(refresh, /elapsed > 90_000/);
  assert.match(refresh, /serviceLifecycleSnapshot = null/);
});

test('a stale terminal poll cannot cancel a newly scheduled transition before its id is bound', () => {
  const source = functionSource('serviceLifecycleTransitionOutcome', 'completeExpectedServiceTransition');
  const context = {};
  vm.runInNewContext(`${source}; this.outcome = serviceLifecycleTransitionOutcome;`, context);
  const pending = { action: 'restart', instanceId: 'instance-old', operationId: '' };
  assert.deepEqual(
    { ...context.outcome(pending, { instance_id: 'instance-old', operation: { id: 'old-failure', state: 'failed', error: 'old' } }) },
    { state: 'pending' },
  );
  const bound = { ...pending, operationId: 'new-operation' };
  assert.deepEqual(
    { ...context.outcome(bound, { instance_id: 'instance-old', operation: { id: 'new-operation', state: 'failed', error: 'dispatch_rejected' } }) },
    { state: 'failed', error: 'dispatch_rejected' },
  );
  assert.deepEqual(
    { ...context.outcome(bound, { instance_id: 'instance-new', operation: null }) },
    { state: 'complete' },
  );
  const request = functionSource('requestServiceLifecycle', 'formatHz');
  assert.ok(
    request.indexOf('serviceLifecycleRequestGeneration += 1') < request.indexOf('serviceLifecycleExpected = {'),
    'an in-flight GET must be invalidated before a new expectation is installed',
  );
  assert.match(request, /if \(serviceLifecycleExpected\?\.action === action\)/);
});

test('service controls are full-width and collapse safely on small screens', () => {
  assert.match(stylesSource, /\.service-lifecycle-panel \{ grid-column:1\/-1; \}/);
  assert.match(stylesSource, /\.service-lifecycle-body \{ display:grid; grid-template-columns:/);
  assert.match(stylesSource, /@media \(max-width: 800px\)[\s\S]*?\.service-lifecycle-body \{ grid-template-columns:1fr; \}/);
  assert.match(stylesSource, /@media \(max-width: 520px\)[\s\S]*?\.service-lifecycle-status, \.service-lifecycle-buttons \{ grid-template-columns:1fr; \}/);
});
