import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const bridgeSource = readFileSync(new URL('../robot_dashboard/static/features/control/bridge_service.js', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

function functionSource(name, nextName) {
  const plainStart = bridgeSource.indexOf(`function ${name}(`);
  const asyncStart = bridgeSource.indexOf(`async function ${name}(`);
  const starts = [plainStart, asyncStart].filter((value) => value >= 0);
  const start = starts.length ? Math.min(...starts) : -1;
  const plainEnd = bridgeSource.indexOf(`\nfunction ${nextName}(`, start);
  const asyncEnd = bridgeSource.indexOf(`\nasync function ${nextName}(`, start);
  const exportEnd = bridgeSource.indexOf(`\nexport function ${nextName}(`, start);
  const ends = [plainEnd, asyncEnd, exportEnd].filter((value) => value > start);
  const end = ends.length ? Math.min(...ends) : -1;
  assert.ok(start >= 0 && end > start, `${name} source must exist`);
  return bridgeSource.slice(start, end);
}

test('Settings exposes a fixed bridge service panel with an explicit safety acknowledgement', () => {
  for (const id of [
    'controlBridgeServiceState', 'controlBridgeServiceName',
    'controlBridgeServiceActive', 'controlBridgeServiceSub',
    'controlBridgeServiceOperation', 'controlBridgeServiceConfirm',
    'controlBridgeServiceStart', 'controlBridgeServiceStop',
    'controlBridgeServiceMessage',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  const settingsStart = indexSource.indexOf('data-page="settings"');
  const bridgePanel = indexSource.indexOf('id="controlBridgeServiceHeading"');
  assert.ok(settingsStart >= 0 && bridgePanel > settingsStart);
  assert.match(indexSource, /탑재 Jetson의 고정 Control Bridge만 시작·중지합니다/);
  assert.match(indexSource, /시작해도 ARM, lease, deadman 또는 로봇 동작은 자동 실행하지 않습니다/);
  assert.match(indexSource, /Control은 DISARM, Navigation은 STOP/);
  assert.doesNotMatch(indexSource, /controlBridgeServiceAdmin|관리 키/);
  assert.doesNotMatch(indexSource, /<input[^>]+(?:service|unit)[^>]*(?:text|password)/i);
});

test('bridge start and stop use only the fixed API and strict confirmation body', () => {
  const request = functionSource('requestControlBridgeService', 'initializeControlBridgeServiceFeature');
  assert.match(bridgeSource, /api\('\/api\/v1\/control\/bridge-service'\)/);
  assert.match(request, /!\['start', 'stop'\]\.includes\(action\)/);
  assert.match(request, /api\(`\/api\/v1\/control\/bridge-service\/\$\{action\}`/);
  assert.match(request, /method: 'POST'/);
  assert.match(request, /JSON\.stringify\(\{ confirmed: true \}\)/);
  assert.match(request, /window\.confirm\(warning\)/);
  assert.doesNotMatch(request, /service_name|unit_name|admin|token|reboot|poweroff|shutdown/i);
});

test('both controls require server permission and a fresh local acknowledgement', () => {
  const render = functionSource('renderControlBridgeService', 'refreshControlBridgeService');
  assert.match(render, /Boolean\(controlUi\.bridgeServiceConfirm\.checked\)/);
  assert.match(render, /controlUi\.bridgeServiceStart\.disabled = locked \|\| !snapshot\?\.can_start \|\| !locallyConfirmed/);
  assert.match(render, /controlUi\.bridgeServiceStop\.disabled = locked \|\| !snapshot\?\.can_stop \|\| !locallyConfirmed/);
  assert.match(render, /controlBridgeServiceOperationActive\(snapshot\)/);
  assert.match(render, /systemd\.transitioning/);
  assert.match(requestControlSource(), /controlUi\.bridgeServiceConfirm\.checked = false/);
});

function requestControlSource() {
  return functionSource('requestControlBridgeService', 'initializeControlBridgeServiceFeature');
}

test('systemd RUNNING stays separate from the signed runtime BRIDGE readiness', () => {
  const render = functionSource('renderControlBridgeService', 'refreshControlBridgeService');
  assert.match(render, /label = 'RUNNING'/);
  assert.doesNotMatch(render, /label = 'READY'/);
  assert.match(render, /실제 명령 연결은 위 BRIDGE 상태에서 별도로 확인하세요/);
  assert.match(appSource, /controlUi\.bridgeState\.textContent = bridgeState\.toUpperCase\(\)/);
});

test('unknown or unloaded systemd status stays fail-closed in the UI', () => {
  const render = functionSource('renderControlBridgeService', 'refreshControlBridgeService');
  assert.match(render, /!systemd\.available/);
  assert.match(render, /load_state/);
  assert.match(render, /unit_file_state/);
  assert.match(render, /!snapshot\?\.can_start/);
  assert.match(render, /!snapshot\?\.can_stop/);
});

test('transition matching rejects stale operations and requires the observed systemd result', () => {
  const desired = functionSource('controlBridgeServiceDesiredState', 'controlBridgeServiceTransitionOutcome');
  const outcomeSource = functionSource('controlBridgeServiceTransitionOutcome', 'bindExpectedControlBridgeServiceOperation');
  const context = {};
  vm.runInNewContext(`
    const CONTROL_BRIDGE_SERVICE_FAILED_STATES = new Set(['failed', 'blocked', 'cancelled']);
    ${desired}
    ${outcomeSource}
    this.outcome = controlBridgeServiceTransitionOutcome;
  `, context);
  const expected = { action: 'start', operationId: 'new-operation' };
  assert.deepEqual(
    { ...context.outcome(expected, {
      operation: { id: 'old-operation', action: 'start', state: 'failed', error: 'old' },
      systemd: { available: true, running: false, transitioning: false, active_state: 'inactive' },
    }) },
    { state: 'pending' },
  );
  assert.deepEqual(
    { ...context.outcome(expected, {
      operation: { id: 'new-operation', action: 'start', state: 'succeeded' },
      systemd: { available: true, running: true, transitioning: false, active_state: 'active' },
    }) },
    { state: 'complete' },
  );
  assert.deepEqual(
    { ...context.outcome(expected, {
      operation: { id: 'new-operation', action: 'start', state: 'succeeded' },
      systemd: { available: true, running: false, transitioning: true, active_state: 'activating' },
    }) },
    { state: 'pending' },
  );
});

test('poll generations and page lifecycle prevent stale Safari BFCache responses from winning', () => {
  const bind = functionSource('bindExpectedControlBridgeServiceOperation', 'completeExpectedControlBridgeServiceTransition');
  const refresh = functionSource('refreshControlBridgeService', 'requestControlBridgeService');
  const request = requestControlSource();
  assert.match(bind, /operation\.id === expected\.baselineOperationId/);
  assert.match(bind, /requestedAt < expected\.startedAt - 2_000/);
  assert.match(refresh, /const generation = \+\+controlBridgeServiceRequestGeneration/);
  assert.match(refresh, /generation !== controlBridgeServiceRequestGeneration/);
  assert.ok(
    request.indexOf('controlBridgeServiceRequestGeneration += 1')
      < request.indexOf('controlBridgeServiceExpected = {'),
    'a mutation must invalidate older GET responses before installing its expectation',
  );
  assert.match(bridgeSource, /window\.addEventListener\('pagehide',[\s\S]*?controlBridgeServiceRequestGeneration \+= 1/);
  assert.match(bridgeSource, /window\.addEventListener\('pageshow',[\s\S]*?refreshControlBridgeService\(true\)/);
  assert.match(bridgeSource, /setInterval\(refreshControlBridgeService, 1000\)/);
  assert.match(bridgeSource, /\['controls', 'navigation', 'settings'\]/);
  assert.match(appSource, /activePage === 'settings'[\s\S]*?controlBridgeServiceFeature\?\.refresh\(\)/);
});

test('bridge service panel collapses safely on tablet and phone widths', () => {
  assert.match(stylesSource, /\.control-bridge-service-body \{ display:grid; grid-template-columns:/);
  assert.match(stylesSource, /@media \(max-width: 800px\)[\s\S]*?\.control-bridge-service-body \{ grid-template-columns:1fr; \}/);
  assert.match(stylesSource, /@media \(max-width: 520px\)[\s\S]*?\.control-bridge-service-status, \.control-bridge-service-buttons \{ grid-template-columns:1fr; \}/);
  assert.match(stylesSource, /\.settings-grid > \.control-bridge-service-panel \{ grid-column:1\/-1; \}/);
});
