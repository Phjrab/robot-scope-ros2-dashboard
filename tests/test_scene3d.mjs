import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const sceneSource = readFileSync(
  new URL('../robot_dashboard/static/scene3d.js', import.meta.url),
  'utf8',
);
const indexSource = readFileSync(
  new URL('../robot_dashboard/static/index.html', import.meta.url),
  'utf8',
);
const appSource = readFileSync(
  new URL('../robot_dashboard/static/app.js', import.meta.url),
  'utf8',
);
const stylesSource = readFileSync(
  new URL('../robot_dashboard/static/styles.css', import.meta.url),
  'utf8',
);

function storageHarness(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    storage: {
      getItem(key) {
        return values.has(key) ? values.get(key) : null;
      },
      setItem(key, value) {
        values.set(key, String(value));
      },
    },
  };
}

function context2d() {
  return {
    setTransform() {},
    clearRect() {},
  };
}

function canvasHarness(context = context2d()) {
  const attributes = new Map();
  return {
    width: 640,
    height: 360,
    clientWidth: 640,
    clientHeight: 360,
    style: {},
    getContext: () => context,
    getBoundingClientRect: () => ({ width: 640, height: 360 }),
    hasAttribute: (name) => attributes.has(name),
    setAttribute: (name, value) => attributes.set(name, String(value)),
    addEventListener() {},
    removeEventListener() {},
  };
}

function sceneHarness({ storage, stored = {}, options = {} } = {}) {
  const preference = storageHarness(stored);
  const sandbox = {
    Float32Array,
    Math,
    Number,
    Object,
    devicePixelRatio: 1,
    localStorage: storage || preference.storage,
    requestAnimationFrame: () => 1,
    cancelAnimationFrame() {},
    addEventListener() {},
    removeEventListener() {},
  };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  runInNewContext(sceneSource, sandbox);
  const canvas = canvasHarness();
  const scene = new sandbox.RobotScene3D(canvas, {
    axesStorageKey: 'robot-scope.navigation-model.axes.v1',
    ...options,
  });
  return { scene, canvas, preference, sandbox };
}

test('point-cloud preview without advertised bounds uses its sampled bounds', () => {
  const { scene } = sceneHarness();
  scene.render = () => {};
  assert.equal(scene.setPointCloud({ points: [[0, 0, 0], [1, 0, 0], [0, 1, 1]], frame_id: 'map' }), 3);
  assert.deepEqual(Array.from(scene.cloud.bounds.min), [0, 0, 0]);
  assert.deepEqual(Array.from(scene.cloud.bounds.max), [1, 1, 1]);
  scene.destroy();
});

test('main-area FIT changes only the view while full FIT keeps distant extrema', () => {
  const { scene } = sceneHarness();
  const input = Array.from({ length: 400 }, (_, index) => [index % 20 / 10 - 1, Math.floor(index / 20) / 10 - 1, index % 5 / 10]);
  input.push([-100, 0, 0], [100, 0, 0]);
  const original = JSON.stringify(input);
  scene.setPointCloud({ points: input, frame_id: 'map' });
  const cloud = scene.cloud;
  const buffer = scene.cloud.points;
  const bytes = Array.from(buffer);
  const bounds = JSON.stringify(cloud.bounds);
  scene.fitToPointCloud(false);
  const full = scene.camera.distance;
  assert.equal(scene.getViewAvailability().fit, true);
  assert.equal(scene.fitToMainPointCloud(false), true);
  assert.ok(scene.camera.distance < full / 20, 'central room should not shrink to fit two distant points');
  assert.ok(Math.abs(scene.camera.target[0]) < 0.2);
  assert.strictEqual(scene.cloud, cloud);
  assert.strictEqual(scene.cloud.points, buffer);
  assert.deepEqual(Array.from(buffer), bytes);
  assert.equal(JSON.stringify(cloud.bounds), bounds);
  assert.equal(JSON.stringify(input), original);
  scene.fitToPointCloud(false);
  assert.equal(scene.camera.distance, full);
  scene.destroy();
});

test('main-area FIT retains sparse-cloud extrema and is a no-op without points', () => {
  const { scene } = sceneHarness();
  const camera = JSON.stringify(scene.camera);
  assert.equal(scene.getViewAvailability().fit, false);
  assert.equal(scene.fitToMainPointCloud(false), false);
  assert.equal(JSON.stringify(scene.camera), camera);
  scene.setPointCloud({ points: [[-50, 0, 0], [0, 0, 0], [50, 0, 0]], frame_id: 'map' });
  scene.fitToPointCloud(false);
  const full = JSON.stringify(scene.camera);
  assert.equal(scene.fitToMainPointCloud(false), true);
  assert.equal(JSON.stringify(scene.camera), full);
  scene.clearPointCloud();
  assert.equal(scene.getViewAvailability().fit, false);
  scene.destroy();
});

test('position centering needs an explicit matching pose frame and preserves zoom and data', () => {
  const { scene } = sceneHarness();
  scene.setPointCloud({ points: [[0, 0, 0], [1, 1, 1]], frame_id: 'map' });
  const camera = JSON.stringify(scene.camera);
  assert.equal(scene.getViewAvailability().center, false);
  assert.equal(scene.centerOnPose(false), false);
  for (const frameId of ['', 'odom']) {
    scene.setRobotPose({ x: 5, y: 6, z: 7, frameId });
    assert.equal(scene.getViewAvailability().center, false);
    assert.equal(scene.centerOnPose(false), false);
    assert.equal(JSON.stringify(scene.camera), camera);
  }
  scene.setRobotPose({ x: 5, y: 6, z: 7, frameId: 'map' });
  const cloud = scene.cloud;
  const pose = scene.robotPose;
  const { distance, yaw, pitch } = scene.camera;
  const mode = scene.cameraMode;
  assert.equal(scene.getViewAvailability().center, true);
  assert.equal(scene.centerOnPose(false), true);
  assert.deepEqual(Array.from(scene.camera.target), [5, 6, 7]);
  assert.equal(scene.camera.distance, distance);
  assert.equal(scene.camera.yaw, yaw);
  assert.equal(scene.camera.pitch, pitch);
  assert.equal(scene.cameraMode, mode);
  assert.strictEqual(scene.cloud, cloud);
  assert.strictEqual(scene.robotPose, pose);
  scene.setRobotPose(null);
  assert.equal(scene.getViewAvailability().center, false);
  scene.destroy();
});

test('main-area FIT leaves a shared prevalidated typed buffer and advertised bounds intact', () => {
  const { scene } = sceneHarness();
  const input = new Float32Array(Array.from({ length: 600 }, (_, index) => (index % 60) / 10));
  input[0] = -80;
  input[input.length - 3] = 80;
  const source = Array.from(input);
  const advertised = { min: [-100, -100, -100], max: [100, 100, 100] };
  scene.setPointCloud({ points: input, prevalidated: true, frame_id: 'map', bounds: advertised });
  const cloud = scene.cloud;
  scene.fitToMainPointCloud(false);
  assert.strictEqual(scene.cloud, cloud);
  assert.deepEqual(Array.from(input), source);
  assert.deepEqual(Array.from(scene.cloud.bounds.min), advertised.min);
  assert.deepEqual(Array.from(scene.cloud.bounds.max), advertised.max);
  scene.fitToPointCloud(false);
  assert.deepEqual(Array.from(scene.camera.target), [0, 0, 0]);
  assert.ok(scene.camera.distance > 400);
  scene.destroy();
});

test('cockpit first follow pose centers and pan disables following until reset', () => {
  const { scene } = sceneHarness({ options: { autoFitOnFirstCloud: false, manualPanStopsFollow: true } });
  scene.setCameraMode('follow'); scene.setRobotPose({ x: 20, y: -9, z: 0.4 });
  assert.deepEqual(Array.from(scene.camera.target), [20, -9, 0.4]);
  const event = { pointerId: 1, button: 2, clientX: 10, clientY: 10, preventDefault() {} };
  scene._onPointerDown(event); scene._onPointerMove({ ...event, clientX: 60 });
  assert.equal(scene.cameraMode, 'world');
  const target = Array.from(scene.camera.target);
  scene.setRobotPose({ x: 25, y: -5, z: 0.4 });
  assert.deepEqual(Array.from(scene.camera.target), target);
  scene.resetView(); assert.equal(scene.cameraMode, 'follow');
  assert.deepEqual(Array.from(scene.camera.target), [25, -5, 0.4]);
  assert.equal(scene.camera.distance, 8); scene.destroy();
});

function controlHarness() {
  const handlers = new Map();
  const attributes = new Map();
  return {
    title: '',
    addEventListener(name, handler) {
      handlers.set(name, handler);
    },
    removeEventListener(name, handler) {
      if (handlers.get(name) === handler) handlers.delete(name);
    },
    setAttribute(name, value) {
      attributes.set(name, String(value));
    },
    attribute(name) {
      return attributes.get(name);
    },
    click() {
      handlers.get('click')?.();
    },
  };
}

test('trail requires a live pose and a single explicit cloud coordinate frame', () => {
  const { scene } = sceneHarness();
  scene.cloud.frameId = 'hesai_lidar';
  scene.trail = [{ x: 3, y: 2, z: 0, frameId: 'camera_init' }];
  scene.robotPose = null;
  assert.equal(scene._displayTrail().length, 0);
  scene.robotPose = { x: 3, y: 2, z: 0, frameId: 'camera_init' };
  assert.equal(scene._displayTrail().length, 0);
  scene.cloud.frameId = 'camera_init';
  assert.equal(scene._displayTrail().length, 1);
  scene.trail.push({ x: 0, y: 0, z: 0, frameId: 'odom' });
  assert.equal(scene._displayTrail().length, 0);
  scene.cloud.frameId = '';
  assert.equal(scene._displayTrail().length, 0);
});

test('XYZ axes default to the existing visible behavior and persist only their preference', () => {
  const { scene, preference } = sceneHarness();
  assert.equal(scene.axesVisible, true);

  const cloud = scene.cloud;
  const trail = scene.trail;
  const robotPose = scene.robotPose;
  const robotVisible = scene.robotVisible;
  const trailVisible = scene.trailVisible;
  scene._staticDirty = false;

  assert.equal(scene.setAxesVisible(false), false);
  assert.equal(
    preference.values.get('robot-scope.navigation-model.axes.v1'),
    'false',
  );
  assert.equal(scene._staticDirty, true);
  assert.strictEqual(scene.cloud, cloud);
  assert.strictEqual(scene.trail, trail);
  assert.strictEqual(scene.robotPose, robotPose);
  assert.equal(scene.robotVisible, robotVisible);
  assert.equal(scene.trailVisible, trailVisible);

  const restored = sceneHarness({
    stored: { 'robot-scope.navigation-model.axes.v1': 'false' },
  }).scene;
  assert.equal(restored.axesVisible, false);
});

test('axes toggle is storage-failure safe and keeps its pressed state across view controls', () => {
  const blockedStorage = {
    getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
  };
  const { scene } = sceneHarness({ storage: blockedStorage });
  const axes = controlHarness();
  const reset = controlHarness();
  scene.bindControls({ axes, reset });

  assert.equal(scene.axesVisible, true);
  assert.equal(axes.attribute('aria-pressed'), 'true');
  assert.equal(axes.title, 'XYZ 축 숨기기');
  assert.doesNotThrow(() => axes.click());
  assert.equal(scene.axesVisible, false);
  assert.equal(axes.attribute('aria-pressed'), 'false');
  assert.equal(axes.title, 'XYZ 축 표시');

  reset.click();
  assert.equal(axes.attribute('aria-pressed'), 'false');
});

test('rendering skips only the axes helper while grid, cloud, model and trail stay intact', () => {
  const { scene } = sceneHarness();
  scene._staticCanvas = null;
  scene._staticCtx = null;
  scene.resizeIfNeeded = () => {};
  scene._fillBackground = () => {};
  scene._cameraBasis = () => ({});

  function drawCounts(axesVisible) {
    const counts = { grid: 0, cloud: 0, axes: 0, trail: 0, robot: 0, hud: 0 };
    scene.axesVisible = axesVisible;
    scene._drawGrid = () => { counts.grid += 1; };
    scene._drawPointCloud = () => { counts.cloud += 1; };
    scene._drawWorldAxes = () => { counts.axes += 1; };
    scene._drawTrail = () => { counts.trail += 1; };
    scene._drawRobot = () => { counts.robot += 1; };
    scene._drawHud = () => { counts.hud += 1; };
    scene._draw();
    return counts;
  }

  assert.deepEqual(drawCounts(false), {
    grid: 1, cloud: 1, axes: 0, trail: 1, robot: 1, hud: 1,
  });
  assert.deepEqual(drawCounts(true), {
    grid: 1, cloud: 1, axes: 1, trail: 1, robot: 1, hud: 1,
  });
});

test('empty cloud keeps the centered waiting message without the upper point and frame readout', () => {
  const text = [];
  const context = {
    save() {}, restore() {}, beginPath() {}, arc() {}, fill() {}, stroke() {},
    measureText(value) { return { width: String(value).length * 5 }; },
    fillText(value) { text.push(String(value)); },
  };
  const { scene } = sceneHarness();
  scene.ctx = context;
  scene.width = 640;
  scene.height = 360;
  scene._roundedRectPath = () => {};
  scene.status = { online: null, lidarOnline: false, snapshot: false, message: 'UNITREE GO2 · LIDAR WAITING' };
  scene.cloud = { points: new Float32Array(), sourcePoints: 0, frameId: '' };

  scene._drawHud();
  assert.equal(text.includes('NO POINT CLOUD'), false);
  assert.equal(text.some((value) => value.startsWith('FRAME ')), false);
  assert.equal(text.includes('UNITREE GO2 · LIDAR WAITING'), true);
  assert.equal(text.includes('로봇 모델은 미리보기로 계속 조작할 수 있습니다'), true);

  text.length = 0;
  scene.cloud = { points: new Float32Array([1, 2, 3]), sourcePoints: 1, frameId: 'lidar' };
  scene._drawHud();
  assert.equal(text.includes('1 / 1 POINTS'), true);
  assert.equal(text.includes('FRAME lidar'), true);
});

test('point projection scratch uses bounded typed arrays and is reused across renders', () => {
  const context = {
    setTransform() {}, clearRect() {}, save() {}, restore() {}, beginPath() {}, rect() {}, fill() {},
  };
  const { scene } = sceneHarness({ options: { maxPoints: 60_000 } });
  scene.ctx = context;
  scene.width = 640;
  scene.height = 360;
  scene._basis = {
    position: [0, 0, -5], forward: [0, 0, 1], right: [1, 0, 0], up: [0, 1, 0], focal: 100,
  };
  const points = new Float32Array(30_000);
  for (let index = 0; index < points.length; index += 3) {
    points[index] = (index % 90) / 100;
    points[index + 1] = (index % 60) / 100;
    points[index + 2] = (index % 30) / 100;
  }
  scene.cloud = { ...scene.cloud, points, bounds: { min: [0, 0, 0], max: [1, 1, 1] } };
  scene._drawPointCloud();
  const firstScratch = scene._pointScratch;
  assert.equal(scene.performanceSnapshot().scratchAllocations, 2);
  scene._drawPointCloud();
  assert.strictEqual(scene._pointScratch, firstScratch);
  assert.equal(scene.performanceSnapshot().scratchAllocations, 2);
  assert.equal(scene.setHeightColor(false), false);
  assert.equal(scene.setNearFieldEmphasis(false), false);
});

test('removed navigation model preview leaves no XYZ control in the page', () => {
  assert.doesNotMatch(indexSource, /id="navigationRobotAxesButton"/);
  assert.match(stylesSource, /\.scene-controls \.scene-axes-toggle\[aria-pressed="true"\]/);
});

test('diagnostic overlay is bounded, colored and cleared on base replacement or frame mismatch', () => {
  const { scene } = sceneHarness({ options: { pointColor: '#50adc7' } });
  scene.setPointCloud({ points: [[0, 0, 0]], frame_id: 'map' });
  const overlay = { points: [[1, 2, 3]], frame_id: 'map', color: '#ffad54' };
  assert.equal(scene.setPointCloudOverlay(overlay), true);
  assert.equal(scene.pointCloudOverlay.color, '#ffad54');
  const layers = []; scene._drawCloudPoints = (points, bounds, color) => { layers.push(color); return points.length / 3; };
  scene._drawPointCloud(); assert.deepEqual(layers, ['#50adc7', '#ffad54']);
  assert.equal(scene._performance.renderedPoints, 2);
  scene.setPointCloud({ points: [[0, 0, 0]], frame_id: 'other' });
  assert.equal(scene.pointCloudOverlay, null);
  assert.equal(scene.setPointCloudOverlay(overlay), false);
  assert.equal(scene.setPointCloudOverlay({ ...overlay, frame_id: 'other', points: [[Infinity, 0, 0]] }), false);
  scene.setPointCloudOverlay({ ...overlay, frame_id: 'other' }); scene.clearPointCloud();
  assert.equal(scene.pointCloudOverlay, null);
});

test('fallback robot world dimensions and full attitude stay fixed across zoom', () => {
  const { scene } = sceneHarness();
  scene.ctx = new Proxy({ measureText: () => ({ width: 1 }) }, { get: (o, k) => o[k] || (() => {}) });
  scene._project = () => ({ x: 1, y: 1, depth: 2 });
  scene.setRobotPose({ x: 0, y: 0, z: 0, yaw: 0, frameId: 'map' });
  const sizes = [];
  scene._drawCuboid = (center, dimensions) => { sizes.push(Array.from(dimensions)); };
  scene.camera.distance = 2; scene._drawRobot();
  scene.camera.distance = 200; scene._drawRobot();
  assert.deepEqual(sizes.slice(0, 3), sizes.slice(3));
  assert.equal(sizes[0][0], .7);
  const p = scene._robotWorldPoint([1, 0, 0], { x: 0, y: 0, z: 0, pitch: Math.PI / 2, roll: 0, yaw: 0 }, 1);
  assert.ok(Math.abs(p[0]) < 1e-8); assert.equal(p[2], -1);
});
