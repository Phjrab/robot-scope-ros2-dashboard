import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

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
  assert.equal(navigation.FIELD_BY_KEY.desired_linear_vel.maximum, 1.0);
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
  assert.equal(navigation.parameterValues(tuned({ desired_linear_vel: 1.0 })).desired_linear_vel, 1.0);
  assert.throws(() => navigation.parameterValues(tuned({ desired_linear_vel: 1.000001 })), /between/);
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
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  for (const endpoint of [
    '/api/v1/navigation', '/api/v1/navigation/parameters', '/api/v1/navigation/start',
    '/api/v1/navigation/stop', '/api/v1/navigation/initial-pose', '/api/v1/navigation/goal',
    '/api/v1/navigation/cancel', '/api/v1/navigation/clear-costmaps',
  ]) assert.ok(appSource.includes(endpoint), `missing ${endpoint}`);
  assert.doesNotMatch(appSource, /navigation[^\n]{0,120}(?:file_path|yaml_path|launch_path)/i);
});

test('Navigation renders bounded localization health and a read-only calibration assistant', () => {
  for (const id of [
    'navigationHealthState', 'navigationHealthReason', 'navigationHealthMetrics',
    'navigationCalibrationList',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  const panelStart = indexSource.indexOf('class="navigation-health-grid"');
  const panelEnd = indexSource.indexOf('class="panel navigation-log-panel"', panelStart);
  const panels = indexSource.slice(panelStart, panelEnd);
  assert.match(panels, /BOUNDED TELEMETRY · NO SCORE/);
  assert.match(panels, /READ-ONLY ASSISTANT/);
  assert.doesNotMatch(panels, /<input|<select|contenteditable/);
  const renderStart = appSource.indexOf('function renderNavigationHealth(');
  const renderEnd = appSource.indexOf('\nfunction renderNavigationStatus(', renderStart);
  const render = appSource.slice(renderStart, renderEnd);
  assert.ok(renderStart >= 0 && renderEnd > renderStart);
  assert.match(render, /textContent/);
  assert.match(render, /replaceChildren/);
  assert.doesNotMatch(render, /innerHTML|fetch\(|api\(|method:\s*['"](?:POST|PATCH|DELETE)/);
  for (const metric of [
    'cloud_frequency_hz', 'cloud_jitter_s', 'cloud_age_s', 'runtime_health_age_s',
    'odometry_frequency_hz', 'odometry_age_s', 'tf_age_s',
    'map_to_odom_age_s', 'odom_to_base_age_s', 'translation_jump_count',
    'heading_jump_count', 'accepted_points', 'goal_progress_rate_mps',
    'controller_stall_duration_s', 'costmap_clear_count',
  ]) assert.ok(render.includes(metric), `missing localization metric ${metric}`);
});

test('navigation retains the 2D map without the removed robot model preview', () => {
  const sectionStart = indexSource.indexOf('data-page="navigation"');
  const sectionEnd = indexSource.indexOf('data-page="settings"', sectionStart);
  const section = indexSource.slice(sectionStart, sectionEnd);
  assert.equal((section.match(/id="navigationMapCanvas"/g) || []).length, 1);
  assert.doesNotMatch(section, /navigationRobotCanvas|navigation-robot-panel|로봇 모델 미리보기/);
  const mapStage = section.slice(section.indexOf('class="navigation-map-stage"'), section.indexOf('class="navigation-pose-toolbar"'));
  assert.match(mapStage, /id="navigationMapCanvas"/);
  assert.doesNotMatch(mapStage, /id="navigationRobotCanvas"/);
});

test('navigation 3D preview reuses profile assets and gates every live joint path', () => {
  assert.match(appSource, /const navigationScene3d = window\.RobotScene3D/);
  assert.match(appSource, /const navigationScene3d[\s\S]{0,360}initialDistance: 3/);
  assert.match(appSource, /renderer: navigationScene3d, poseOrigin: 'ground', adaptiveScale: false/);
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
  assert.match(appSource, /const canStop = safety\.can_stop === true \|\| pipelineActive/);
  assert.match(appSource, /navigationStopButton\.disabled = \(navigationOperationBusy && navigationOperationKind !== 'start'\) \|\| !canStop/);
  assert.match(appSource, /navigationSnapshot\?\.safety\?\.can_stop === true \|\|\s*navigationEngine\?\.pipelineActive\(navigationSnapshot\)/);
  assert.match(appSource, /navigationCancelGoal\.disabled = [^;]+!goalActive/);
  assert.doesNotMatch(appSource, /navigationStopButton\.disabled = [^;]+robotOnline/);
  assert.doesNotMatch(appSource, /navigationCancelGoal\.disabled = [^;]+robotOnline/);
  assert.doesNotMatch(appSource, /async function stopNavigation\(\)[\s\S]{0,300}window\.confirm/);
});

test('background navigation startup phases are friendly and keep cleanup available', () => {
  const constantsStart = appSource.indexOf('const NAVIGATION_STARTUP_PHASES');
  const constantsEnd = appSource.indexOf('let navigationLogFeature', constantsStart);
  const functionStart = appSource.indexOf('function navigationStartupPresentation(');
  const functionEnd = appSource.indexOf('\nfunction navigationBlockerMessage(', functionStart);
  assert.ok(constantsStart >= 0 && constantsEnd > constantsStart && functionStart >= 0 && functionEnd > functionStart);
  const context = {};
  vm.runInNewContext(`
    ${appSource.slice(constantsStart, constantsEnd)}
    ${appSource.slice(functionStart, functionEnd)}
    this.present = navigationStartupPresentation;
  `, context);
  const expected = {
    starting_localization: 'STARTING LOCALIZATION',
    waiting_localization: 'WAITING SENSOR',
    starting_navigation: 'STARTING NAV2',
    warming_navigation: 'WARMING',
    activating: 'ACTIVATING',
    active: 'RUNNING',
    failed: 'FAILED',
  };
  for (const [phase, label] of Object.entries(expected)) {
    const presentation = context.present({ localization_pipeline: { phase, pending: phase !== 'active' } });
    assert.equal(presentation.label, label);
  }
  assert.equal(context.present({ localization_pipeline: { phase: 'failed', error: 'bounded failure' } }).message, 'bounded failure');
  assert.equal(context.present({ localization_pipeline: { phase: 'unknown' } }), null);

  assert.match(appSource, /navigationStartButton\.textContent = startupPending \? 'STARTING…' : 'START NAV2'/);
  assert.match(appSource, /navigationStopButton\.textContent = startupPending \? 'STOP STARTUP' : 'STOP'/);
  assert.match(appSource, /navigationOperationKind = path\.endsWith\('\/start'\) \? 'start'/);
  assert.match(appSource, /finally \{[\s\S]{0,180}navigationOperationBusy = false;[\s\S]{0,180}void refreshNavigation\(\)/);
  assert.match(appSource, /setInterval\(refreshNavigation, 1000\)/);
  assert.doesNotMatch(appSource, /매핑을 중지한 뒤 Nav2를 시작하세요|Mapping 페이지/);
});

test('locked parameters and occupancy safety are enforced by the rendered controls', () => {
  assert.match(appSource, /field\?\.locked === true/);
  assert.match(appSource, /occupancyCellAtCanvas\(navigationMapLayout, navigationMapCells, point\)/);
  assert.match(appSource, /!occupancy\.free/);
  assert.match(indexSource, /SOFTWARE STOP은 물리 E-stop이 아니므로/);
});

test('active navigation map is pinned to its exact catalog revision', async () => {
  const source = readFileSync(new URL('../robot_dashboard/static/features/navigation/pose_draft.js', import.meta.url), 'utf8');
  const { navigationActiveMapMatches: matches } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  const active = { id: 'map-id', revision: 'revision' };
  assert.equal(matches(true, active, active, active, [active]), true);
  for (const [selected, loaded, catalog] of [
    [{ ...active, id: 'other' }, active, [active]],
    [{ ...active, revision: 'other' }, active, [active]],
    [active, { ...active, revision: 'other' }, [active]],
    [active, active, [{ ...active, id: 'other' }]],
    [active, active, [{ ...active, revision: 'other' }]],
    [null, active, [active]],
  ]) assert.equal(matches(true, active, selected, loaded, catalog), false);
  assert.equal(matches(true, {}, active, active, [active]), false);
  assert.match(appSource, /function navigationActiveMapMatchesSelection\(\)/);
  assert.match(appSource, /return navigationActiveMapMatches\(navigationEngine\?\.pipelineActive\(navigationSnapshot\), navigationSnapshot\?\.map,\s*navigationSelectedMapMeta, navigationMapSnapshot, navigationMapCandidates\(\)\)/);
  assert.match(appSource, /pipelineActive && !exactActiveMap/);
  assert.match(appSource, /!navigationActiveMapMatchesSelection\(\)/);
  assert.match(appSource, /navigationSelectedMapMeta\?\.revision \|\| ''\) !== serverMapRevision/);
});

test('parameter conflicts preserve the draft and wait for an explicit refresh', async () => {
  const start = appSource.indexOf('async function applyNavigationParameters()');
  const end = appSource.indexOf('function redrawActiveMap()', start);
  const draft = { ...navigation.TUNED_VALUES, desired_linear_vel: .5 };
  const context = {
    navigationParameterSnapshot: { revision: 'revision', values: navigation.TUNED_VALUES },
    navigationParameterDraft: draft, navigationParameterBusy: false,
    navigationEngine: navigation, navigationSnapshot: { pipeline: { state: 'idle' } },
    api: async () => { const error = new Error('409 conflict'); error.status = 409; throw error; },
    showToast() {}, syncNavigationParameterControls() {}, renderNavigationStatus() {},
    refreshNavigationParameters() { assert.fail('must preserve edited values'); },
  };
  vm.createContext(context);
  vm.runInContext(appSource.slice(start, end), context);
  assert.match(await context.applyNavigationParameters(), /현재 적용 실패/);
  assert.equal(context.navigationParameterDraft, draft);
  assert.equal(context.navigationParameterBusy, false);
});

test('navigation health metrics show unknown values without inventing zero and retain measured zero', () => {
  const start = appSource.indexOf('function formatNavigationMetric(');
  const end = appSource.indexOf('\nfunction renderNavigationStatus(', start);
  assert.ok(start >= 0 && end > start);
  const element = () => ({ children: [], textContent: '', className: '',
    append(...nodes) { this.children.push(...nodes); }, replaceChildren(...nodes) { this.children = nodes; } });
  const ui = { navigationHealthState: element(), navigationHealthReason: element(), navigationHealthMetrics: element(), navigationCalibrationList: element() };
  const context = { ui, document: { createElement: element }, setStatePill: (node, tone, state) => { node.textContent = state; } };
  vm.runInNewContext(`${appSource.slice(start, end)}\nthis.format = formatNavigationMetric; this.render = renderNavigationHealth;`, context);
  for (const value of [null, undefined, '', ' ', '0', '1.2', false, true, [], {}, NaN, Infinity, -Infinity, Symbol('missing')]) {
    assert.equal(context.format(value, ' Hz'), '—', `invalid metric ${String(value)}`);
  }
  assert.equal(context.format(0, ' Hz'), '0.00 Hz');
  assert.equal(context.format(1.25, ' Hz'), '1.25 Hz');
  const rows = () => Object.fromEntries(ui.navigationHealthMetrics.children.map(row => [row.children[0].textContent, { value: row.children[1].textContent, note: row.children[2].textContent }]));
  const zeros = { cloud_frequency_hz: 0, cloud_jitter_s: 0, cloud_age_s: 0, runtime_health_age_s: 0,
    odometry_frequency_hz: 0, odometry_jitter_s: 0, odometry_age_s: 0, tf_age_s: 0, map_to_odom_age_s: 0, odom_to_base_age_s: 0,
    translation_jump_count: 0, heading_jump_count: 0, accepted_points: 0, input_points: 0, goal_progress_rate_mps: 0,
    goal_remaining_distance_m: 0, controller_stall_duration_s: 0, costmap_clear_count: 0, fresh_sequence_count: 0 };
  context.render({ pipeline: { state: 'idle' }, localization_health: { state: 'UNAVAILABLE', reason_code: 'NAVIGATION_INACTIVE', metrics: zeros } });
  assert.equal(ui.navigationHealthState.textContent, 'UNAVAILABLE');
  assert.match(ui.navigationHealthReason.textContent, /NAVIGATION_INACTIVE/);
  assert.equal(rows().POINTCLOUD.value, '—'); assert.match(rows().POINTCLOUD.note, /age —/);
  assert.equal(rows()['TF AGE'].value, '—'); assert.equal(rows()['FAST-LIO JUMPS'].value, '— / —');
  assert.equal(rows()['SCAN POINTS'].value, '— / —'); assert.equal(rows()['COSTMAP CLEARS'].value, '—');
  assert.equal(rows()['COSTMAP CLEARS'].note, 'fresh sequence —');
  for (const [state, reason] of [['FRAME_MISMATCH', 'FRAME_CONTRACT_MISMATCH'], ['DISCONTINUITY', 'ODOMETRY_DISCONTINUITY'], ['UNAVAILABLE', 'SOURCE_PUBLISHER_CONFLICT']]) {
    context.render({ session_mode: 'idle', pipeline: { state: 'idle' }, localization_health: { state, reason_code: reason, metrics: zeros } });
    assert.equal(ui.navigationHealthState.textContent, state); assert.match(ui.navigationHealthReason.textContent, new RegExp(reason));
    assert.equal(rows().POINTCLOUD.value, '—', `${reason} while inactive`); assert.match(rows().POINTCLOUD.note, /age —/);
    assert.equal(rows()['TF AGE'].value, '—'); assert.equal(rows()['FAST-LIO JUMPS'].value, '— / —');
    assert.equal(rows()['SCAN POINTS'].value, '— / —'); assert.equal(rows()['COSTMAP CLEARS'].value, '—');
  }
  context.render({ session_mode: 'localization_only', localization_health: { state: 'FRAME_MISMATCH', reason_code: 'FRAME_CONTRACT_MISMATCH', metrics: zeros } });
  assert.equal(rows().POINTCLOUD.value, '0.00 Hz'); assert.equal(ui.navigationHealthState.textContent, 'FRAME_MISMATCH');
  context.render({ pipeline: { state: 'running' }, localization_health: { state: 'READY', reason_code: 'HEALTHY', metrics: zeros } });
  assert.equal(rows().POINTCLOUD.value, '0.00 Hz'); assert.match(rows().POINTCLOUD.note, /age 0\.000 s/);
  assert.equal(rows()['TF AGE'].value, '0.000 s'); assert.equal(rows()['FAST-LIO JUMPS'].value, '0 / 0');
  assert.equal(rows()['SCAN POINTS'].value, '0 / 0'); assert.equal(rows()['COSTMAP CLEARS'].value, '0');
  assert.equal(rows()['COSTMAP CLEARS'].note, 'fresh sequence 0');
  context.render({ localization_health: { state: 'READY', metrics: { cloud_frequency_hz: null, cloud_age_s: '', tf_age_s: false,
    translation_jump_count: '0', heading_jump_count: -1, accepted_points: 1.5, input_points: 12,
    costmap_clear_count: {}, fresh_sequence_count: Infinity } } });
  assert.equal(rows().POINTCLOUD.value, '—'); assert.match(rows().POINTCLOUD.note, /age —/); assert.equal(rows()['TF AGE'].value, '—');
  assert.equal(rows()['FAST-LIO JUMPS'].value, '— / —'); assert.equal(rows()['SCAN POINTS'].value, '— / 12');
  assert.equal(rows()['COSTMAP CLEARS'].value, '—'); assert.equal(rows()['COSTMAP CLEARS'].note, 'fresh sequence —');
});
