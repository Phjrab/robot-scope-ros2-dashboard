import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const text = readFileSync(new URL('../robot_dashboard/static/features/navigation/preparation.js', import.meta.url), 'utf8');
const { preparationModel, operationalPoseContextMatches } = await import(`data:text/javascript;base64,${Buffer.from(text).toString('base64')}`);
const nav = createRequire(import.meta.url)('../robot_dashboard/static/navigation.js');

function fixture() {
  const draft3d = { id: '3d', revision: '3rev', kind: 'pointcloud3d', name: 'map1' };
  const draft2d = { id: '2d', revision: '2rev', frame_id: 'map', name: 'map1_2D' };
  const selected = { generation: 'bundle', workflow: 'staged_navigation_pair',
    localization_3d: { map_id: draft3d.id, revision: draft3d.revision },
    navigation_2d: { map_id: draft2d.id, revision: draft2d.revision }, calibration: { verified: true },
    seed_geometry: { z: .34, roll: 0, pitch: .02, source: 'USER_CONFIRMED' } };
  const source = { source: 'STORED_PCD_FASTLIO', bundle_generation: 'bundle', localization_generation: 2,
    runtime_instance_generation: 'runtime', localization_map_id: '3d', localization_map_revision: '3rev',
    state: 'WAITING_EXPLICIT_INITIAL_POSE', fresh: true, ready: false, correction_sequence: 0 };
  const observation = { map_id: '2d', map_revision: '2rev', localization_map_id: '3d', localization_map_revision: '3rev',
    bundle_generation: 'bundle', localization_generation: 2, runtime_instance_generation: 'runtime',
    pose: { x: 1, y: 2, z: .34, roll: 0, pitch: .02, yaw: 1 }, stamp_ns: '1234' };
  const navigation = { map: draft2d, pipeline: { state: 'running', job_id: 'job' },
    safety: { can_set_initial_pose: true, can_send_goal: false }, operational_localization: source,
    localization: { state: 'localized', pose: { x: 40, y: 40, yaw: 1 } }, goal: { state: 'idle' } };
  return { state: { selected, pair: { can_start: true } }, navigation, draft3d, draft2d, observation };
}

test('pair selection alone never counts as runtime application or robot localization', () => {
  const value = fixture(); value.navigation = { pipeline: { state: 'idle' } };
  const model = preparationModel(value);
  assert.equal(model.steps[0].status, '완료');
  assert.equal(model.steps[1].status, '완료');
  assert.equal(model.steps[2].status, '사용자 입력 필요');
  assert.equal(model.applied, false); assert.equal(model.tracking, false); assert.equal(model.canMatch, false);
  assert.equal(nav.currentRobotOverlay(value.navigation, value.draft2d), null);
  value.navigation.map = value.draft2d;
  value.navigation.localization = { state: 'localized', pose: { x: 10, y: 20, yaw: 0 } };
  assert.equal(nav.currentRobotOverlay(value.navigation, value.draft2d, { requireOperational: true }), null,
    'missing operational health must not reveal a legacy pose for selected stored-map mode');
});

test('missing geometry is concrete and empty/null values are not silently converted to zero', () => {
  for (const geometry of [null, { z: null, roll: 0, pitch: 0 }, { z: '', roll: 0, pitch: 0 }, { z: 1, roll: undefined, pitch: 0 }]) {
    const value = fixture(); value.state.selected.seed_geometry = geometry;
    const model = preparationModel(value);
    assert.equal(model.canStart, false); assert.equal(model.steps[1].status, '사용자 입력 필요');
    assert.ok(model.issues.some(issue => issue.code === 'INITIAL_GEOMETRY_REQUIRED' && issue.remedy.includes('직접 입력')));
  }
  const value = fixture(); value.state.selected.seed_geometry = { z: 0, roll: 0, pitch: 0 };
  assert.equal(preparationModel(value).canStart, true, 'explicit finite zeros are legitimate, missing values are not');
});

test('correcting a local missing item resumes there without invalidating valid pair', () => {
  const value = fixture(); delete value.state.selected.seed_geometry;
  assert.equal(preparationModel(value).steps[1].status, '사용자 입력 필요');
  value.state.selected.seed_geometry = { z: .3, roll: .01, pitch: -.02 };
  const model = preparationModel(value);
  assert.equal(model.steps[0].status, '완료'); assert.equal(model.steps[1].status, '완료');
  assert.equal(model.steps[2].status, '완료'); assert.equal(model.steps[3].status, '사용자 입력 필요');
});

test('map renaming cannot silently bind a different id or revision even if labels match', () => {
  for (const patch of [{ id: 'renamed' }, { revision: 'new' }]) {
    const value = fixture(); Object.assign(value.draft2d, patch);
    const model = preparationModel(value);
    assert.equal(model.matched, false); assert.equal(model.canStart, false);
    assert.ok(model.issues.some(issue => issue.code === 'PAIR_NOT_APPLIED'));
  }
  const value = fixture(); value.draft2d.name = 'display name only';
  assert.equal(preparationModel(value).matched, true);
});

test('accepted initial position remains an input until explicit match produces estimate', () => {
  const value = fixture(); const source = value.navigation.operational_localization;
  source.accepted_initial_pose = { ...value.observation, accepted: true };
  source.state = 'WAITING_EXPLICIT_MAP_MATCH';
  const model = preparationModel(value);
  assert.equal(model.steps[3].status, '완료'); assert.equal(model.steps[4].status, '사용자 입력 필요');
  assert.equal(model.canMatch, true); assert.equal(model.tracking, false);
  assert.equal(nav.currentRobotOverlay(value.navigation, value.draft2d), null, 'legacy relative pose must not leak into stored-map robot');
  assert.deepEqual(nav.initialPoseOverlay(value.navigation, value.draft2d), { ...value.observation.pose, mode: 'initial' });
});

test('display restoration is read-only and initial marker is independent from corrected robot', () => {
  const value = fixture(); const source = value.navigation.operational_localization;
  source.accepted_initial_pose = { ...value.observation, accepted: true };
  source.estimated_pose = { ...value.observation, pose: { ...value.observation.pose, x: 1.03, z: .36 }, stale: false };
  source.state = 'MAP_TRACKING'; source.ready = true; source.correction_sequence = 4;
  value.navigation.safety.can_send_goal = true;
  const saved = JSON.stringify(value);
  for (let i = 0; i < 3; i++) {
    const model = preparationModel(structuredClone(value));
    assert.equal(model.tracking, true); assert.equal(model.steps[5].status, '완료');
    assert.equal(nav.initialPoseOverlay(value.navigation, value.draft2d).x, 1);
    assert.equal(nav.currentRobotOverlay(value.navigation, value.draft2d).x, 1.03);
    assert.equal(nav.currentRobotOverlay(value.navigation, value.draft2d).z, .36);
  }
  assert.equal(JSON.stringify(value), saved);
});

test('stale estimate retains last position with stale styling and cannot become goal-ready', () => {
  const value = fixture(); const source = value.navigation.operational_localization;
  source.estimated_pose = { ...value.observation, stale: true }; source.ready = false;
  source.state = 'MAP_CORRECTION_STALE'; value.navigation.safety.can_send_goal = true;
  const robot = nav.currentRobotOverlay(value.navigation, value.draft2d);
  assert.equal(robot.x, 1); assert.equal(robot.stale, true); assert.equal(preparationModel(value).tracking, false);
  const preview = nav.navigationPosePreview(null, { globalAlpha: 1, save() {}, restore() {} }, {}, robot, 'current');
  assert.match(preview.label, /오래됨/); assert.equal(preview.color, '#a3aba8');
});

test('cross map, source, process or localization generation observations are hidden', () => {
  for (const key of ['map_id', 'map_revision', 'localization_map_id', 'localization_map_revision', 'bundle_generation', 'localization_generation', 'runtime_instance_generation']) {
    const value = fixture(); const source = value.navigation.operational_localization;
    const bad = { ...value.observation, [key]: 'other' };
    source.accepted_initial_pose = { ...bad, accepted: true }; source.estimated_pose = bad;
    assert.equal(operationalPoseContextMatches(bad, source, value.draft2d), false, key);
    assert.equal(nav.initialPoseOverlay(value.navigation, value.draft2d), null, key);
    assert.equal(nav.currentRobotOverlay(value.navigation, value.draft2d), null, key);
  }
});

test('source restart invalidates runtime steps while valid map geometry stays prepared', () => {
  const value = fixture(); const source = value.navigation.operational_localization;
  source.accepted_initial_pose = { ...value.observation, accepted: true }; source.localization_generation++;
  const model = preparationModel(value);
  assert.equal(model.steps[0].status, '완료'); assert.equal(model.steps[1].status, '완료');
  assert.equal(model.marker, null); assert.equal(model.canMatch, false); assert.equal(model.steps[3].status, '사용자 입력 필요');
});

test('legacy mode remains available, while configured server blocker is respected', () => {
  assert.equal(preparationModel({ state: { selected: null }, navigation: null }).canStart, true);
  const value = fixture(); value.state.pair.can_start = false;
  assert.equal(preparationModel(value).canStart, false);
  value.state.pair.can_start = true;
  assert.equal(preparationModel({ ...value, available: false }).canStart, false);
});

test('server pair revalidation failures and geometry reuse identify the correct restart step', () => {
  const value = fixture();
  value.state.pair = { valid: false, can_start: false, restart_from_step: 1,
    checks: [{ code: 'CALIBRATION_CHANGED_REAPPLY_PAIR', current: '교정 변경', required: '현재 교정', remedy: '지도 연결 재확인' }] };
  let model = preparationModel(value);
  assert.equal(model.steps[0].status, '오류'); assert.equal(model.matched, false);
  assert.ok(model.issues.some(item => item.code === 'CALIBRATION_CHANGED_REAPPLY_PAIR' && item.step === 1));
  value.state.pair = { valid: true, can_start: false, restart_from_step: 2,
    checks: [{ code: 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED', current: '이전 실행 높이', required: '현재 높이', remedy: '② 현재 값 재확인' }] };
  model = preparationModel(value);
  assert.equal(model.steps[0].status, '완료'); assert.equal(model.steps[1].status, '사용자 입력 필요'); assert.equal(model.canStart, false);
  assert.ok(model.issues.some(item => item.code === 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED' && item.step === 2));
});

test('old successful goal cannot complete the new execution and stale receipt cannot certify nodes', () => {
  const value = fixture(); const source = value.navigation.operational_localization;
  source.accepted_initial_pose = { ...value.observation, accepted: true };
  value.navigation.goal = { goal_id: 'goal', state: 'succeeded', pose: value.observation.pose,
    precision_evidence: { goal_id: 'goal', context: { job_id: 'old-job', map_id: '2d', map_revision: '2rev' } } };
  assert.equal(preparationModel(value).steps[6].status, '미시작');
  assert.equal(nav.goalPoseOverlay(value.navigation, value.draft2d), null);
  source.fresh = false;
  assert.notEqual(preparationModel(value).steps[2].status, '완료');
  assert.ok(preparationModel(value).issues.some(item => item.code === 'RUNTIME_STATUS_STALE'));
});
