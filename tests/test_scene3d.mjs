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

test('navigation model preview exposes the persistent accessible XYZ control', () => {
  assert.match(indexSource, /id="navigationRobotAxesButton"[^>]*aria-pressed="true"[^>]*>XYZ<\/button>/);
  assert.match(appSource, /axesStorageKey: 'robot-scope\.navigation-model\.axes\.v1'/);
  assert.match(appSource, /axes: ui\.navigationRobotAxesButton/);
  assert.match(stylesSource, /\.scene-controls \.scene-axes-toggle\[aria-pressed="true"\]/);
});
