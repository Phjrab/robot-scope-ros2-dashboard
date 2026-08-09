import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const require = createRequire(import.meta.url);
const profiles = require('../robot_dashboard/static/robot_profiles.js');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const rendererSource = readFileSync(new URL('../robot_dashboard/static/go2_official_model.js', import.meta.url), 'utf8');

test('robot type catalog normalizes the backend contract and model metadata', () => {
  const values = profiles.normalizeTypes({
    types: [{
      id: 'SO_101',
      label: 'SO-101 Lab Arm',
      description: 'table arm',
      model: { kind: 'robot-model-lite', asset_url: '/models/so101.json', urdf_url: '/models/so101.urdf', label: 'SO-101 URDF', fidelity: 'generic' },
    }],
  });
  assert.deepEqual(values, [{
    id: 'so-101',
    label: 'SO-101 Lab Arm',
    description: 'table arm',
    model: { kind: 'robot-model-lite', asset_url: '/models/so101.json', urdf_url: '/models/so101.urdf', label: 'SO-101 URDF', fidelity: 'generic' },
  }]);
});

test('fallback catalog provides selectable Go2, TurtleBot and SO-101 model assets', () => {
  const values = profiles.normalizeTypes(null);
  assert.deepEqual(values.map((value) => value.id), ['go2', 'turtlebot', 'so-101']);
  assert.ok(values.every((value) => value.model.asset_url.startsWith('/static/assets/')));
});

test('network discovery removes invalid and duplicate candidates then ranks confidence and latency', () => {
  const values = profiles.normalizeDiscovery({
    robot_type: 'go2',
    candidates: [
      { ip: '192.168.1.20', hostname: 'slow', confidence: 0.7, latency_ms: 12 },
      { ip: '999.1.1.1', hostname: 'invalid' },
      { ip: '192.168.1.21', hostname: 'best', confidence: 0.9, latency_ms: 9 },
      { ip: '192.168.1.20', hostname: 'better duplicate', confidence: 0.8, latency_ms: 4 },
    ],
  });
  assert.deepEqual(values.map((value) => value.ip), ['192.168.1.21', '192.168.1.20']);
  assert.equal(values[1].hostname, 'better duplicate');
});

test('connection payload binds the chosen type, address and discovered hostname', () => {
  assert.deepEqual(
    profiles.connectionPayload({ id: 'turtlebot' }, { ip: '10.0.0.4', hostname: 'tb4' }, '10.0.0.4'),
    { ip: '10.0.0.4', robot_type: 'turtlebot', hostname: 'tb4' },
  );
});

test('settings UI wires type selection to discovery and explicit connection', () => {
  assert.match(indexSource, /id="robotType"/);
  assert.match(indexSource, /id="selectedRobotUrdf"/);
  assert.match(indexSource, /id="discoverRobotsButton"/);
  assert.match(indexSource, /id="robotDiscoveryResults"[^>]+role="group"/);
  assert.match(appSource, /api\('\/api\/v1\/robots\/types'/);
  assert.match(appSource, /api\('\/api\/v1\/robots\/discover',[\s\S]{0,180}robot_type: selectedRobotType/);
  assert.match(appSource, /robotDiscoveryController\?\.abort\(\)/);
  assert.match(appSource, /RobotProfiles\.connectionPayload/);
  assert.match(appSource, /activateRobotType\(ui\.robotType\.value, \{ discover: true, dirty: true \}\)/);
  assert.match(appSource, /미확인 호스트/);
  assert.match(indexSource, /DDS 인터페이스·Domain·ROS workspace는 실행 중 자동 변경되지 않으므로/);
  assert.match(appSource, /범용 URDF 근사 모델 · 제조사 공식 모델 아님/);
  assert.match(indexSource, /id="controlProfileNotice"[^>]+hidden/);
  assert.match(appSource, /if \(selectedRobotType !== 'go2'\) return false/);
  assert.match(appSource, /function applyJointSnapshot\(snapshot\) \{\s*if \(!robotRuntimeDataCompatible \|\| selectedRobotType !== 'go2'\)/);
  assert.match(appSource, /function resetLiveRobotSessionView\(\)/);
  assert.match(appSource, /if \(response\.robot\?\.changed\) resetLiveRobotSessionView\(\)/);
  assert.match(appSource, /response\.robot\?\.restart_required/);
  assert.match(appSource, /ROS 재시작 전 기존 데이터 · 로봇 오버레이 숨김/);
  assert.match(appSource, /ROS\/DDS 오프라인 뷰어/);
  assert.match(appSource, /ROS\/DDS 인터페이스 준비/);
  assert.match(appSource, /if \(robotConnectionBusy\) return/);
});

test('sensor cards keep all observed streams and rank unknown categories last', () => {
  const start = appSource.indexOf('function updateSensors(sensors)');
  const end = appSource.indexOf('function updateOdometry(', start);
  assert.ok(start >= 0 && end > start, 'updateSensors implementation must exist');
  const implementation = appSource.slice(start, end);
  assert.match(implementation, /index < 0 \? priority\.length : index/);
  assert.doesNotMatch(implementation, /\.slice\(0,\s*6\)/);
});

test('model renderer accepts the official Go2 and generic robot-model-lite schemas', () => {
  assert.match(rendererSource, /robot-scope\.go2-official-lite/);
  assert.match(rendererSource, /robot-scope\.robot-model-lite/);
  assert.match(rendererSource, /SUPPORTED_SCHEMAS\.has\(asset\.schema\)/);
  assert.match(appSource, /renderer\.loadOfficialRobotModel\(assetUrl\)/);
  assert.match(rendererSource, /if \(this\._go2OfficialPromise === request\)/);
});

test('a transient model fetch failure can be retried without reloading the page', async () => {
  let fetchCount = 0;
  const asset = JSON.parse(readFileSync(new URL('../robot_dashboard/static/assets/turtlebot/generic-turtlebot-lite.json', import.meta.url), 'utf8'));
  class FakeScene {
    _drawRobot() {}
    render() {}
  }
  const sandbox = {
    RobotScene3D: FakeScene,
    fetch: async () => {
      fetchCount += 1;
      if (fetchCount === 1) return { ok: false, status: 503 };
      return { ok: true, json: async () => asset };
    },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  runInNewContext(rendererSource, sandbox);
  const scene = new FakeScene();
  await assert.rejects(scene.loadOfficialRobotModel('/models/transient.json'));
  await scene.loadOfficialRobotModel('/models/transient.json');
  assert.equal(fetchCount, 2);
  assert.equal(scene.getOfficialRobotModelStatus().state, 'ready');
});
