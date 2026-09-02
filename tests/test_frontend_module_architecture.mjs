import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const load = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const indexSource = load('../robot_dashboard/static/index.html');
const appSource = load('../robot_dashboard/static/app.js');
const apiSource = load('../robot_dashboard/static/core/api.js');
const scrollSource = load('../robot_dashboard/static/core/log_scroll.js');
const lidarSource = load('../robot_dashboard/static/features/sensors/lidar_identity.js');
const navigationLogSource = load('../robot_dashboard/static/features/navigation/log_controller.js');
const bridgeSource = load('../robot_dashboard/static/features/control/bridge_service.js');
const lifecycleSource = load('../robot_dashboard/static/features/settings/service_lifecycle.js');

test('app entrypoint is an ES module with explicit core and feature imports', () => {
  assert.match(indexSource, /<script src="\/static\/app\.js" type="module"><\/script>/);
  for (const path of [
    './core/api.js', './core/dom.js', './core/format.js', './core/log_scroll.js',
    './features/sensors/lidar_identity.js', './features/navigation/log_controller.js',
    './features/control/bridge_service.js', './features/settings/service_lifecycle.js',
  ]) assert.match(appSource, new RegExp(`from ['"]${path.replaceAll('.', '\\.')}['"]`));
  assert.doesNotMatch(appSource, /async function api\(|function setStatePill\(|const LidarSourceIdentity =/);
  assert.ok(appSource.split('\n').length < 7500, 'incremental extraction must materially reduce app.js');
});

test('feature modules own their bounded request and lifecycle state', () => {
  assert.match(navigationLogSource, /let navigationLogRequestGeneration = 0/);
  assert.match(navigationLogSource, /api\(`\/api\/v1\/navigation\/logs\?after=/);
  assert.match(navigationLogSource, /setInterval\(refreshNavigationLogs, 1000\)/);
  assert.match(bridgeSource, /let controlBridgeServiceExpected = null/);
  assert.match(bridgeSource, /api\(`\/api\/v1\/control\/bridge-service\/\$\{action\}`/);
  assert.match(bridgeSource, /ensureControlBridgeServiceStarted/);
  assert.match(bridgeSource, /requestControlBridgeService\('start', \{ confirmed: true, prompt: false \}\)/);
  assert.match(lifecycleSource, /let serviceLifecycleExpected = null/);
  assert.match(lifecycleSource, /api\(`\/api\/v1\/system\/service\/\$\{action\}`/);
  assert.doesNotMatch(appSource, /let navigationLogRequestGeneration|let controlBridgeServiceExpected|let serviceLifecycleExpected/);
});

test('shared modules remain framework-free and expose no mutable application globals', () => {
  for (const source of [apiSource, scrollSource, lidarSource, navigationLogSource, bridgeSource, lifecycleSource]) {
    assert.doesNotMatch(source, /React|Vue|Angular|Svelte|jQuery|require\(/);
    assert.doesNotMatch(source, /window\.RobotScope[A-Za-z]*\s*=/);
  }
  assert.match(apiSource, /cache: 'no-store'/);
  assert.match(scrollSource, /const stickyLogScrollGenerations = new WeakMap\(\)/);
});

test('high-risk mutations keep fixed same-origin paths and strict confirmation payloads', () => {
  for (const source of [bridgeSource, lifecycleSource]) {
    assert.match(source, /method: 'POST'/);
    assert.match(source, /JSON\.stringify\(\{ confirmed: true \}\)/);
    assert.doesNotMatch(source, /service_name|unit_name|shell|reboot|poweroff|admin[_-]?token/i);
  }
});
