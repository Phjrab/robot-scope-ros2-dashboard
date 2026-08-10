import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const navigation = require('../robot_dashboard/static/navigation.js');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

function tuned(overrides = {}) {
  return { ...navigation.TUNED_VALUES, ...overrides };
}

test('PDF 11 navigation parameter whitelist has complete typed tuned values', () => {
  assert.equal(navigation.FIELDS.length, 27);
  assert.equal(new Set(navigation.FIELD_KEYS).size, navigation.FIELDS.length);
  assert.equal(navigation.TUNED_VALUES.desired_linear_vel, 0.25);
  assert.equal(navigation.FIELD_BY_KEY.desired_linear_vel.maximum, 0.3);
  assert.equal(navigation.TUNED_VALUES.rotate_to_heading_angular_vel, 0.5);
  assert.equal(navigation.FIELD_BY_KEY.rotate_to_heading_angular_vel.maximum, 0.5);
  assert.equal(navigation.TUNED_VALUES.max_angular_accel, 1.2);
  assert.equal(navigation.FIELD_BY_KEY.max_angular_accel.maximum, 1.2);
  assert.equal(navigation.FIELD_BY_KEY.controller_frequency.minimum, 10);
  assert.equal(navigation.FIELD_BY_KEY.controller_frequency.maximum, 20);
  assert.equal(navigation.TUNED_VALUES.robot_radius, 0.22);
  assert.equal(navigation.TUNED_VALUES.inflation_radius, 0.25);
  assert.equal(navigation.TUNED_VALUES.max_obstacle_height, 2);
  assert.equal(navigation.TUNED_VALUES.use_astar, true);
  assert.equal(navigation.TUNED_VALUES.enable_stamped_cmd_vel, false);
  assert.deepEqual(navigation.parameterValues(tuned()), tuned());
  for (const key of [
    'use_rotate_to_heading', 'rotation_shim_enabled', 'rotate_to_goal_heading',
    'closed_loop', 'enable_stamped_cmd_vel',
  ]) assert.equal(navigation.FIELD_BY_KEY[key].locked, true, `${key} must remain locked`);
});

test('parameter snapshots fail closed on missing, unknown or unsafe values', () => {
  const good = {
    revision: 'revision-1',
    active_preset: 'go2_indoor',
    values: tuned(),
    presets: [{ id: 'go2_indoor', label: 'Go2 indoor', values: tuned() }],
    requires_restart: true,
  };
  assert.equal(navigation.normalizeParameterSnapshot(good).values.controller_frequency, 10);
  assert.throws(
    () => navigation.normalizeParameterSnapshot({ ...good, values: { ...good.values, arbitrary_path: '/tmp/x' } }),
    /unsupported navigation parameters/,
  );
  const missing = tuned();
  delete missing.robot_radius;
  assert.throws(() => navigation.normalizeParameterSnapshot({ ...good, values: missing }), /missing navigation parameters/);
  assert.throws(() => navigation.parameterValues(tuned({ desired_linear_vel: 4 })), /between/);
  assert.throws(
    () => navigation.parameterValues(tuned({ min_obstacle_height: 0.5, max_obstacle_height: 0.4 })),
    /less than/,
  );
  assert.throws(
    () => navigation.parameterValues(tuned({ obstacle_max_range: 11, raytrace_max_range: 10 })),
    /must not exceed/,
  );
  assert.throws(
    () => navigation.parameterValues(tuned({ robot_radius: 0.3, inflation_radius: 0.2 })),
    /at least robot_radius/,
  );
  assert.throws(() => navigation.parameterValues(tuned({ closed_loop: true })), /locked/);
  assert.throws(() => navigation.parameterValues(tuned({ desired_linear_vel: 0.31 })), /between/);
  assert.throws(() => navigation.parameterValues(tuned({ controller_frequency: 9 })), /between/);
});

test('parameter PATCH contains only changed whitelisted values and an exact base revision', () => {
  const before = tuned();
  const after = tuned({ desired_linear_vel: 0.2, use_astar: false });
  assert.deepEqual(navigation.parameterPatch('opaque-revision', before, after), {
    base_revision: 'opaque-revision',
    values: { desired_linear_vel: 0.2, use_astar: false },
  });
  assert.throws(() => navigation.parameterPatch('', before, after), /base_revision/);
  assert.throws(
    () => navigation.parameterPatch('opaque-revision', before, { ...after, path: '/home/user/nav.yaml' }),
    /unsupported navigation parameters/,
  );
});

test('canvas and world transforms respect map origin, resolution, yaw and Y inversion', () => {
  const map = { width: 100, height: 50, resolution: 0.1, origin: [1, 2, 0] };
  const layout = navigation.mapLayout(map, 1000, 500, 0);
  assert.deepEqual(navigation.canvasToWorld(layout, { x: 0, y: 500 }), { x: 1, y: 2, inside: true });
  assert.deepEqual(navigation.canvasToWorld(layout, { x: 1000, y: 0 }), { x: 11, y: 7, inside: true });
  assert.deepEqual(navigation.worldToCanvas(layout, { x: 1, y: 2, yaw: 0 }), {
    x: 0, y: 500, heading: -0, inside: true,
  });

  const rotated = navigation.mapLayout({ ...map, origin: [1, 2, Math.PI / 2] }, 1000, 500, 0);
  const corner = navigation.canvasToWorld(rotated, { x: 1000, y: 0 });
  assert.ok(Math.abs(corner.x + 4) < 1e-10);
  assert.ok(Math.abs(corner.y - 12) < 1e-10);
  const roundTrip = navigation.worldToCanvas(rotated, { x: corner.x, y: corner.y, yaw: Math.PI / 2 });
  assert.ok(Math.abs(roundTrip.x - 1000) < 1e-9);
  assert.ok(Math.abs(roundTrip.y) < 1e-9);
  assert.equal(roundTrip.inside, true);
});

test('pose drag requires a map hit and derives heading in the rotated map frame', () => {
  const map = { width: 100, height: 100, resolution: 0.1, origin: [0, 0, Math.PI / 2] };
  const layout = navigation.mapLayout(map, 500, 500, 0);
  assert.equal(navigation.poseFromDrag(layout, { x: -1, y: 250 }, { x: 10, y: 250 }), null);
  const pose = navigation.poseFromDrag(layout, { x: 250, y: 250 }, { x: 400, y: 250 });
  assert.ok(Math.abs(pose.yaw - Math.PI / 2) < 1e-10);
  const clickPose = navigation.poseFromDrag(layout, { x: 250, y: 250 }, { x: 251, y: 251 }, -0.7);
  assert.ok(Math.abs(clickPose.yaw + 0.7) < 1e-10);
});

test('pose placement rejects unknown and occupied occupancy cells', () => {
  const map = { width: 3, height: 2, resolution: 1, origin: [10, -4, Math.PI / 2] };
  const layout = navigation.mapLayout(map, 300, 200, 0);
  const cells = Int8Array.from([0, -1, 100, 0, 0, 0]);
  assert.deepEqual(navigation.occupancyCellAtCanvas(layout, cells, { x: 50, y: 150 }), {
    inside: true, free: true, value: 0, cellX: 0, cellY: 0,
  });
  assert.deepEqual(navigation.occupancyCellAtCanvas(layout, cells, { x: 150, y: 150 }), {
    inside: true, free: false, value: -1, cellX: 1, cellY: 0,
  });
  assert.deepEqual(navigation.occupancyCellAtCanvas(layout, cells, { x: 250, y: 150 }), {
    inside: true, free: false, value: 100, cellX: 2, cellY: 0,
  });
  assert.equal(navigation.occupancyCellAtCanvas(layout, cells, { x: -1, y: 100 }).inside, false);
});

test('navigation and manual control activity helpers are fail-safe', () => {
  assert.equal(navigation.pipelineActive({ pipeline: { state: 'running' } }), true);
  assert.equal(navigation.pipelineActive({ pipeline: { state: 'failed' } }), false);
  assert.equal(navigation.goalActive({ goal: { state: 'active' } }), true);
  assert.equal(navigation.goalActive({ goal: { state: 'succeeded' } }), false);
  assert.equal(navigation.manualControlActive({ lease: { active: true } }), true);
  assert.equal(navigation.manualControlActive({ lease: { active: false } }, 'local-lease'), true);
  assert.equal(navigation.manualControlActive({ lease: { active: true, source: 'navigation' } }), false);
  assert.equal(navigation.manualControlActive({ lease: { active: true, input_source: 'navigation' } }), false);
  assert.equal(navigation.manualControlActive({ lease: { active: true, source: 'keyboard' } }), true);
  assert.equal(navigation.manualControlActive({ lease: { active: true, source: 'navigation', input_source: 'unknown' } }), true);
  assert.equal(navigation.manualControlActive({ lease: { active: true, source: 'navigation' } }, 'local-lease'), true);
});

test('dashboard exposes a dedicated navigation route and strict API endpoints', () => {
  assert.match(indexSource, /data-nav="navigation"/);
  assert.match(indexSource, /data-page="navigation"/);
  assert.match(indexSource, /\/static\/navigation\.js/);
  for (const id of [
    'navigationMapSelect', 'navigationMapCanvas', 'navigationInitialPoseTool',
    'navigationGoalPoseTool', 'navigationPoseSend', 'navigationStartButton',
    'navigationStopButton', 'navigationCancelGoal', 'navigationClearCostmaps',
    'navigationPreset', 'navigationParameterReset', 'navigationParameterApply',
    'navigationRobotCanvas', 'navigationModelState', 'navigationModelLabel',
    'navigationRobotResetButton', 'navigationRobotTopButton', 'navigationRobotFrontButton',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  for (const endpoint of [
    '/api/v1/navigation', '/api/v1/navigation/parameters', '/api/v1/navigation/start',
    '/api/v1/navigation/stop', '/api/v1/navigation/initial-pose', '/api/v1/navigation/goal',
    '/api/v1/navigation/cancel', '/api/v1/navigation/clear-costmaps',
  ]) assert.ok(appSource.includes(endpoint), `missing ${endpoint}`);
  assert.doesNotMatch(appSource, /navigation[^\n]{0,120}(?:file_path|yaml_path|launch_path)/i);
});

test('navigation keeps the 2D map and selected robot 3D preview in separate stages', () => {
  const sectionStart = indexSource.indexOf('data-page="navigation"');
  const sectionEnd = indexSource.indexOf('data-page="settings"', sectionStart);
  const section = indexSource.slice(sectionStart, sectionEnd);
  assert.equal((section.match(/id="navigationMapCanvas"/g) || []).length, 1);
  assert.equal((section.match(/id="navigationRobotCanvas"/g) || []).length, 1);
  const mapStage = section.slice(section.indexOf('class="navigation-map-stage"'), section.indexOf('class="navigation-pose-toolbar"'));
  const robotStage = section.slice(section.indexOf('class="navigation-robot-stage"'), section.indexOf('class="navigation-robot-summary"'));
  assert.match(mapStage, /id="navigationMapCanvas"/);
  assert.doesNotMatch(mapStage, /id="navigationRobotCanvas"/);
  assert.match(robotStage, /id="navigationRobotCanvas"/);
  assert.doesNotMatch(robotStage, /id="navigationMapCanvas"/);
});

test('navigation 3D preview reuses profile assets and gates every live joint path', () => {
  assert.match(appSource, /const navigationScene3d = window\.RobotScene3D/);
  assert.match(appSource, /const navigationScene3d[\s\S]{0,360}initialDistance: 3/);
  assert.match(appSource, /renderer: navigationScene3d, poseOrigin: 'ground', adaptiveScale: true/);
  assert.doesNotMatch(appSource, /renderers\.length !== 2/);
  assert.match(appSource, /renderers\.map\(\(\{ renderer \}\) => renderer\.loadOfficialRobotModel\(assetUrl\)\)/);
  assert.match(appSource, /const liveJoints = compatible && robotModelsReady && !robotModelsFailed && profile\.id === 'go2' && jointLive/);
  assert.match(appSource, /online: compatible \? online : null/);
  assert.match(appSource, /activePage === 'navigation' && robotRuntimeDataCompatible && robotModelsReady && !robotModelsFailed && selectedRobotType === 'go2' && jointLive && renderedJointPositions/);
  assert.match(appSource, /navigationScene3d\?\.resetRobotJointPositions\?\.\(\)/);
  assert.match(appSource, /navigationScene3d\?\.setRobotPose\(null\)/);
  assert.match(appSource, /navigationApiAvailable === true && typeof navigationSnapshot\?\.robot_online === 'boolean'/);
  assert.doesNotMatch(appSource, /navigationRobotOnline\(\)[\s\S]{0,260}latestState\?\.health\?\.robot_online/);
});

test('controls and navigation help text is readable and model preview is mobile-safe', () => {
  assert.match(stylesSource, /\[data-page="controls"\] p,\s*\[data-page="controls"\] small \{ font-size:13px/);
  assert.match(stylesSource, /\[data-page="navigation"\] p,\s*\[data-page="navigation"\] small \{ font-size:13px/);
  assert.match(stylesSource, /\.navigation-robot-summary p \{[^}]*font-size:14px/);
  assert.match(stylesSource, /\[data-page="navigation"\] \.navigation-safety-banner p,[\s\S]*?font-size:14px/);
  const tabletStart = stylesSource.indexOf('@media (max-width: 800px)');
  const phoneStart = stylesSource.indexOf('@media (max-width: 520px)');
  const tablet = stylesSource.slice(tabletStart, phoneStart);
  const phone = stylesSource.slice(phoneStart);
  assert.match(tablet, /\.navigation-robot-stage \{ height:360px; \}/);
  assert.match(phone, /\.navigation-robot-stage \{ height:300px; \}/);
  assert.match(phone, /\.navigation-robot-summary \{ grid-template-columns:1fr;/);
});

test('navigation start and poses carry opaque map revisions while parameters use PATCH', () => {
  assert.match(appSource, /map_id: navigationSelectedMapMeta\.id/);
  assert.match(appSource, /map_revision: navigationSelectedMapMeta\.revision/);
  assert.match(appSource, /parameters_revision: navigationParameterSnapshot\.revision/);
  assert.match(appSource, /method: 'PATCH',[\s\S]{0,180}base_revision/);
  assert.match(appSource, /pose: \{ x: staged\.x, y: staged\.y, yaw: staged\.yaw \}/);
  assert.match(appSource, /if \(staged\.mode === 'goal'\) body\.confirmed = true;/);
  assert.match(appSource, /staged\.mode === 'goal' && !window\.confirm/);
  assert.match(appSource, /runNavigationMutation\('\/api\/v1\/navigation\/cancel', \{ goal_id: goalId \}/);
  assert.match(appSource, /runNavigationMutation\('\/api\/v1\/navigation\/clear-costmaps', \{ scope: 'both' \}/);
});

test('manual control and navigation are mutually exclusive without blocking cleanup actions', () => {
  assert.match(appSource, /function navigationManualControlConflict\(\)/);
  assert.match(appSource, /navigationEngine\.pipelineActive\(navigationSnapshot\)/);
  assert.match(appSource, /if \(navigationActivityBlocksManualControl\(\)\)/);
  assert.match(appSource, /controlUi\.arm\.disabled = [^;]+navigationActivityBlocksManualControl\(\)/);
  assert.match(appSource, /navigationStartButton\.disabled = [^;]+manualConflict/);
  assert.match(appSource, /navigationStopButton\.disabled = [^;]+!pipelineActive/);
  assert.match(appSource, /navigationCancelGoal\.disabled = [^;]+!goalActive/);
  assert.doesNotMatch(appSource, /navigationStopButton\.disabled = [^;]+robotOnline/);
  assert.doesNotMatch(appSource, /navigationCancelGoal\.disabled = [^;]+robotOnline/);
  assert.doesNotMatch(appSource, /async function stopNavigation\(\)[\s\S]{0,300}window\.confirm/);
});

test('locked parameters and occupancy safety are enforced by the rendered controls', () => {
  assert.match(appSource, /field\?\.locked === true/);
  assert.match(appSource, /occupancyCellAtCanvas\(navigationMapLayout, navigationMapCells, point\)/);
  assert.match(appSource, /!occupancy\.free/);
  assert.match(indexSource, /SOFTWARE STOP은 물리 E-stop이 아니므로/);
});

test('active navigation map is pinned to its exact catalog revision', () => {
  assert.match(appSource, /function navigationActiveMapMatchesSelection\(\)/);
  assert.match(appSource, /navigationSelectedMapMeta\?\.id === activeId/);
  assert.match(appSource, /navigationSelectedMapMeta\?\.revision \|\| ''\) === activeRevision/);
  assert.match(appSource, /navigationMapSnapshot\?\.revision \|\| ''\) === activeRevision/);
  assert.match(appSource, /entry\.id === activeId && String\(entry\.revision \|\| ''\) === activeRevision/);
  assert.match(appSource, /pipelineActive && !exactActiveMap/);
  assert.match(appSource, /!navigationActiveMapMatchesSelection\(\)/);
  assert.match(appSource, /navigationSelectedMapMeta\?\.revision \|\| ''\) !== serverMapRevision/);
});

test('parameter revision conflicts reload only after the busy guard is released', () => {
  assert.match(appSource, /let reloadAfterConflict = false;/);
  assert.match(appSource, /reloadAfterConflict = error\.status === 409 \|\| String\(error\.message\)\.includes\('409'\);/);
  assert.match(
    appSource,
    /finally \{[\s\S]{0,180}navigationParameterBusy = false;[\s\S]{0,180}if \(reloadAfterConflict\) \{[\s\S]{0,120}await refreshNavigationParameters\(true\);/,
  );
});
