import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const liveMap2d = require('../robot_dashboard/static/live_map2d.js');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

test('top-down projection filters invalid XYZ values and deduplicates sparse XY cells', () => {
  const cloud = {
    frame_id: 'map',
    seq: 7,
    points: Float32Array.from([
      0.01, 0.01, 0.1,
      0.04, 0.03, 0.8,
      1.01, -0.02, 0.4,
      Number.NaN, 2, 3,
    ]),
  };
  const projection = liveMap2d.projectPointCloud(cloud, { resolution: 0.1 });
  assert.equal(projection.sourcePoints, 4);
  assert.equal(projection.validPoints, 3);
  assert.equal(projection.sourceCells, 2);
  assert.equal(projection.sentCells, 2);
  assert.equal(projection.frameId, 'map');
  assert.ok(Math.abs(projection.bounds.min[0] - 0.01) < 1e-5);
  assert.ok(Math.abs(projection.bounds.min[1] + 0.02) < 1e-5);
  assert.ok(Math.abs(projection.bounds.max[0] - 1.01) < 1e-5);
  assert.ok(Math.abs(projection.bounds.max[2] - 0.8) < 1e-5);
  const firstCell = Array.from(projection.cells.slice(0, 4));
  assert.ok(Math.abs(firstCell[2] - 0.8) < 1e-5, 'the highest Z in a projected cell must win');
  assert.equal(firstCell[3], 2);
});

test('projection is bounded by a client-side cell budget without creating a dense map grid', () => {
  const points = [];
  for (let index = 0; index < 2500; index += 1) points.push(index * 0.1, index * 0.1, index % 4);
  const projection = liveMap2d.projectPointCloud({ points }, { resolution: 0.02, maxCells: 1000 });
  assert.equal(projection.sourceCells, 2500);
  assert.equal(projection.sentCells, 1000);
  assert.equal(projection.cells.length, 4000);
});

test('fit and projection math preserve world center and canvas orientation', () => {
  const view = liveMap2d.fitView({ min: [-4, -2, 0], max: [6, 2, 3] }, 2, 1);
  assert.deepEqual(view, { centerX: 1, centerY: 0, spanY: 5 });
  assert.deepEqual(liveMap2d.worldToCanvas(view, 1000, 500, 1, 0), { x: 500, y: 250, scale: 100 });
  assert.equal(liveMap2d.worldToCanvas(view, 1000, 500, 1, 1).y, 150, 'positive world Y must point upward');
});

test('follow and auto-fit modes are mutually exclusive', () => {
  const noop = () => {};
  const context = new Proxy({}, { get: (target, key) => target[key] || noop, set: (target, key, value) => { target[key] = value; return true; } });
  const canvas = {
    width: 300, height: 150, clientWidth: 300, clientHeight: 150,
    getContext: () => context, addEventListener: noop, removeEventListener: noop,
  };
  const renderer = new liveMap2d.LiveMap2DRenderer(canvas);
  renderer.setPose({ x: 3, y: -2, yaw: 0.4 });
  renderer.setFollow(true);
  assert.equal(renderer.snapshot().follow, true);
  assert.equal(renderer.snapshot().autoFit, false);
  assert.deepEqual(renderer.snapshot().targetView, { centerX: 3, centerY: -2, spanY: 20 });
  renderer.setAutoFit(true);
  assert.equal(renderer.snapshot().autoFit, true);
  assert.equal(renderer.snapshot().follow, false);
  renderer.destroy();
});

test('Live Mapping exposes a separate point projection view with fit, auto-fit and follow controls', () => {
  for (const id of [
    'liveMap2dCanvas', 'liveMap2dControls', 'liveMap2dFitButton',
    'liveMap2dAutoFitButton', 'liveMap2dFollowButton', 'liveProjectionLegend',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  assert.match(indexSource, /option value="projection">LIVE 2D · POINTS<\/option>/);
  assert.match(indexSource, /option value="occupancy">ROS 2D · GRID<\/option>/);
  assert.match(indexSource, /현재 3D 프레임을 상단에서 투영 · Saved Maps와 별도/);
  assert.ok(indexSource.indexOf('/static/live_map2d.js') < indexSource.indexOf('/static/app.js'));
  assert.match(stylesSource, /#liveMap2dCanvas \{ cursor: grab; touch-action: none; \}/);
  assert.match(stylesSource, /\.live-projection-legend/);
});

test('2D projection reuses the selected live cloud and does not issue another network request', () => {
  const start = appSource.indexOf('function drawLivePointProjection(cloud)');
  const end = appSource.indexOf('\nfunction drawSavedPointcloud()', start);
  assert.ok(start >= 0 && end > start, 'drawLivePointProjection implementation must exist');
  const implementation = appSource.slice(start, end);
  assert.match(implementation, /const selectedCloud = liveSceneCloud\(cloud\)/);
  assert.match(implementation, /liveMap2d\.setPointCloud\(selectedCloud/);
  assert.doesNotMatch(implementation, /fetch\(|latestApi\(|api\(/);
  assert.match(appSource, /desired === 'projection'\) drawLivePointProjection\(lastCloudSnapshot\)/);
  assert.match(appSource, /mapViewPreference === 'occupancy'[\s\S]{0,100}liveGridReady \? 'occupancy' : 'projection'/);
  assert.match(appSource, /view === 'projection'\) drawLivePointProjection\(lastCloudSnapshot\)/);
  assert.match(appSource, /function pointcloudTransportWanted\(\)[\s\S]{0,140}desiredMapView\(\) !== 'occupancy'/);
});
