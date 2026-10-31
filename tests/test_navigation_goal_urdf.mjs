import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const nav = createRequire(import.meta.url)('../robot_dashboard/static/navigation.js');

function context() {
  const stack = [];
  return { globalAlpha: 0.8, save() { stack.push(this.globalAlpha); }, restore() { this.globalAlpha = stack.pop(); } };
}

test('initial stays a dot while staged and sent goals reuse the metric URDF projection', () => {
  for (const ratio of [1, 2]) {
    const layout = nav.mapLayout({ width: 80, height: 45, resolution: .05, origin: [2, -1, .7] }, 900 * ratio, 500 * ratio);
    const point = nav.canvasToWorld(layout, { x: 400 * ratio, y: 250 * ratio });
    const poses = ['initial', 'goal'].map(mode => Object.freeze({ mode, x: point.x, y: point.y, yaw: 1.2 }));
    const ctx = context();
    const calls = [];
    const scene = { drawRobotMapPreview(c, pose, project, color) {
      calls.push({ c, pose, color });
      assert.deepEqual(project(pose), nav.worldToCanvas(layout, pose));
      const a = project(pose), b = project({ x: pose.x + 1, y: pose.y });
      assert.ok(Math.abs(Math.hypot(b.x - a.x, b.y - a.y) - layout.scale / layout.resolution) < 1e-8);
      assert.ok(c.globalAlpha < .8);
      return true;
    } };
    assert.deepEqual(nav.navigationPosePreview(scene, ctx, layout, poses[0]), { drawn: false, color: '#5dded8', label: 'INITIAL · 입력 중' });
    assert.deepEqual(nav.navigationPosePreview(scene, ctx, layout, poses[1]), { drawn: true, color: '#ffc66d', label: 'GOAL · STAGED' });
    assert.deepEqual(nav.navigationPosePreview(scene, ctx, layout, poses[1], 'active'), { drawn: true, color: '#a28bff', label: 'GOAL · ACTIVE' });
    assert.equal(ctx.globalAlpha, .8);
    assert.equal(calls[0].pose, poses[1]);
    assert.equal(calls.length, 2);
  }
});

test('unloaded, missing and failed model preserve fallback and canvas state', () => {
  for (const scene of [null, { drawRobotMapPreview: () => false }]) {
    const ctx = context();
    const value = nav.navigationPosePreview(scene, ctx, {}, { mode: 'goal' });
    assert.equal(value.drawn, false);
    assert.equal(value.label, 'GOAL · STAGED');
    assert.equal(ctx.globalAlpha, .8);
  }
  const ctx = context();
  const warn = console.warn;
  try {
    console.warn = () => {};
    assert.equal(nav.navigationPosePreview({ drawRobotMapPreview() { assert.fail('initial must never draw robot'); } }, ctx, {}, { mode: 'initial' }).label, 'INITIAL · 입력 중');
    assert.equal(ctx.globalAlpha, .8);
  } finally { console.warn = warn; }
});

test('sent goal overlay requires matching goal evidence and selected map revision, including terminal states', () => {
  const map = { id: 'map', revision: 'revision', frame_id: 'map' };
  const snapshot = { map, goal: { goal_id: 'goal', state: 'active', pose: { x: 1, y: 2, yaw: .4 },
    precision_evidence: { goal_id: 'goal', context: { map_id: map.id, map_revision: map.revision } } } };
  for (const state of ['pending', 'active', 'canceling', 'canceled', 'succeeded', 'failed', 'rejected']) {
    snapshot.goal.state = state;
    assert.equal(nav.goalPoseOverlay(snapshot, map).state, state === 'pending' ? 'sent' : state);
    assert.equal(nav.goalPoseOverlay(snapshot, map).pose, snapshot.goal.pose);
  }
  const original = JSON.stringify(snapshot);
  for (const selected of [{ ...map, id: 'other' }, { ...map, revision: 'new' }, { ...map, frame_id: 'odom' }]) assert.equal(nav.goalPoseOverlay(snapshot, selected), null);
  assert.equal(JSON.stringify(snapshot), original);
  for (const mutate of [s => { s.goal.precision_evidence = null; }, s => { s.goal.pose.yaw = null; },
    s => { s.goal.precision_evidence.goal_id = 'old'; }, s => { s.goal.precision_evidence.context.map_revision = 'old'; },
    s => { s.map = null; }, s => { s.goal.state = 'idle'; }]) {
    const copy = structuredClone(snapshot); mutate(copy); assert.equal(nav.goalPoseOverlay(copy, map), null);
  }
});

test('real map_id response retains sent goal and current robot without relaxing map identity', () => {
  const map = { map_id: 'map', revision: 'revision', frame_id: 'map' };
  const pose = Object.freeze({ x: 1, y: 2, yaw: .4 });
  const snapshot = { map: { id: 'map', revision: 'revision' },
    localization: { state: 'localized', pose },
    goal: { goal_id: 'goal', state: 'active', pose,
      precision_evidence: { goal_id: 'goal', context: { map_id: 'map', map_revision: 'revision' } } } };
  assert.equal(nav.goalPoseOverlay(snapshot, map).pose, pose);
  const robot = nav.currentRobotOverlay(snapshot, map);
  assert.deepEqual(robot, { ...pose, mode: 'robot' });
  assert.equal(pose.mode, undefined);
  const ctx = context();
  const scene = { drawRobotMapPreview(c, p, _project, color) {
    assert.equal(c.globalAlpha, .8);
    assert.equal(p, robot);
    assert.equal(color, '#7df0b6');
    return true;
  } };
  assert.deepEqual(nav.navigationPosePreview(scene, ctx, {}, robot, 'current'),
    { drawn: true, color: '#7df0b6', label: 'ROBOT' });
  for (const mismatch of [{ ...map, map_id: 'other' }, { ...map, id: 'contradiction' },
    { ...map, revision: 'other' }, { ...map, frame_id: 'odom' }]) {
    assert.equal(nav.goalPoseOverlay(snapshot, mismatch), null);
    assert.equal(nav.currentRobotOverlay(snapshot, mismatch), null);
  }
  snapshot.localization.state = 'lost';
  assert.equal(nav.currentRobotOverlay(snapshot, map), null);
  snapshot.localization = { state: 'localized', pose: { x: 1, y: 2, yaw: null } };
  assert.equal(nav.currentRobotOverlay(snapshot, map), null);
});

test('successful model suppresses only the duplicate circle/line marker; fallback retains them', () => {
  const layout = nav.mapLayout({ width: 80, height: 60, resolution: .05, origin: [0, 0, 0] }, 500, 300);
  for (const drawn of [true, false]) {
    const calls = [];
    const ctx = new Proxy({ measureText: () => ({ width: 100 }) }, { get(target, key) { return target[key] ?? ((...args) => calls.push([key, ...args])); } });
    nav.drawPoseMarker(ctx, layout, { x: 2, y: 1, yaw: .4 }, '#ffc66d', 'GOAL · STAGED', 1, false, drawn);
    assert.equal(calls.filter(c => c[0] === 'arc').length, drawn ? 0 : 2);
    assert.equal(calls.filter(c => c[0] === 'lineTo').length, drawn ? 0 : 1);
    assert.equal(calls.filter(c => c[0] === 'fillText').length, 1);
  }
});

test('real official mesh uses default joints and metre scale independently of live scene; foreign profiles fall back', async () => {
  const asset = JSON.parse(readFileSync(new URL('../robot_dashboard/static/assets/go2/go2-official-lite.json', import.meta.url), 'utf8'));
  const sandbox = { console, fetch: async () => ({ ok: true, json: async () => asset }) };
  vm.runInNewContext(readFileSync(new URL('../robot_dashboard/static/go2_official_model.js', import.meta.url), 'utf8'), sandbox);
  class Scene { _drawRobot() {} render() {} }
  sandbox.Go2OfficialModel.install(Scene);
  const scene = new Scene();
  await scene.loadOfficialRobotModel();
  scene._robotModelType = 'go2';
  scene.robotPose = { x: 200, y: 400, yaw: 2 };
  const ctx = new Proxy({ canvas: { width: 1000, height: 1000 } }, { get(target, key) { return target[key] ?? (() => {}); } });
  const pose = { x: 1, y: 1, yaw: .4 };
  const draw = () => {
    const points = [];
    assert.equal(scene.drawRobotMapPreview(ctx, pose, p => { points.push([p.x, p.y]); return { x: p.x * 200, y: p.y * 200 }; }), true);
    assert.ok(points.length > 100);
    return points;
  };
  const points = draw();
  scene.configureOfficialRobot({ scale: 10 });
  scene.setRobotJointPositions({ FR_hip_joint: 1, FR_thigh_joint: 2, FR_calf_joint: 3 });
  assert.deepEqual(draw(), points);
  assert.deepEqual(scene.robotPose, { x: 200, y: 400, yaw: 2 });
  const tiltedPoints = [];
  assert.equal(scene.drawRobotMapPreview(ctx, { ...pose, mode: 'robot', z: .34, roll: .15, pitch: .3 }, p => {
    tiltedPoints.push([p.x, p.y]); return { x: p.x * 200, y: p.y * 200 };
  }), true);
  assert.notDeepEqual(tiltedPoints, points, 'measured body roll/pitch must affect top-down URDF footprint');
  const goalPoints = [];
  scene.drawRobotMapPreview(ctx, { ...pose, mode: 'goal', z: .34, roll: .15, pitch: .3 }, p => {
    goalPoints.push([p.x, p.y]); return { x: p.x * 200, y: p.y * 200 };
  });
  assert.deepEqual(goalPoints, points, 'planar target preview stays independent from measured body tilt');
  scene._robotModelType = 'other';
  assert.equal(scene.drawRobotMapPreview(ctx, pose, () => {}), false);
  scene._robotModelType = 'go2';
  scene._go2OfficialLoadedUrl = '/old-asset.json';
  assert.equal(scene.drawRobotMapPreview(ctx, pose, () => {}), false);
});
