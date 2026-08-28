import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { createCockpitSceneHost } from '../robot_dashboard/static/features/cockpit/scene_host.js';
import { projectCockpitPointcloud } from '../robot_dashboard/static/features/cockpit/workspace.js';
import { createPointcloudTransport } from '../robot_dashboard/static/features/sensors/pointcloud_transport.js';

const load = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

test('Cockpit route is additive and keeps every existing workspace route', () => {
  const indexSource = load('../robot_dashboard/static/index.html');
  const appSource = load('../robot_dashboard/static/app.js');
  for (const route of ['overview', 'cockpit', 'mapping', 'maps', 'sensors', 'topics', 'controls', 'navigation', 'settings']) {
    assert.match(indexSource, new RegExp(`data-nav=["']${route}["']`));
    assert.match(indexSource, new RegExp(`data-page=["']${route}["']`));
  }
  assert.match(appSource, /cockpit: \['Robot Cockpit'/);
  assert.match(indexSource, /\/static\/features\/cockpit\/cockpit\.css/);
});

test('Cockpit SceneHost start and stop stay idempotent over 20 route cycles', async () => {
  const instances = [];
  let resolveModel;
  class FakeRenderer {
    constructor() {
      this.destroyed = false;
      this.cloudUpdates = 0;
      this.modelPromise = new Promise((resolve) => { resolveModel = resolve; });
      instances.push(this);
    }
    bindControls() {}
    setStatus() {}
    setPointCloud() { this.cloudUpdates += 1; }
    clearPointCloud() {}
    setRobotPose() {}
    setTrail() {}
    resetRobotJointPositions() {}
    configureOfficialRobot() {}
    loadOfficialRobotModel() { return this.modelPromise; }
    resize() {}
    destroy() { this.destroyed = true; }
  }

  const host = createCockpitSceneHost({ canvas: {}, Renderer: FakeRenderer });
  host.setProfile({ id: 'go2', label: 'Go2', model: { asset_url: '/go2.json' } });
  for (let index = 0; index < 20; index += 1) {
    host.activate();
    host.activate();
    assert.equal(host.diagnostics().rendererCount, 1);
    host.deactivate();
    host.deactivate();
    assert.equal(host.diagnostics().rendererCount, 0);
  }
  assert.equal(instances.length, 20);
  assert.ok(instances.every((instance) => instance.destroyed));
  assert.deepEqual(
    { starts: host.diagnostics().starts, stops: host.diagnostics().stops, peak: host.diagnostics().peakRenderers },
    { starts: 20, stops: 20, peak: 1 },
  );

  host.activate();
  const finalInstance = instances.at(-1);
  host.setCloud({ seq: 1, points: [0, 0, 0] }, 'LIVE');
  assert.equal(finalInstance.cloudUpdates, 1, 'the active reused renderer receives the shared live cloud');
  const staleModelResolution = resolveModel;
  host.deactivate();
  host.setCloud({ seq: 2, points: [1, 1, 1] }, 'LIVE');
  assert.equal(finalInstance.cloudUpdates, 1, 'inactive Cockpit performs no renderer update');
  staleModelResolution();
  await Promise.resolve();
  assert.equal(host.diagnostics().active, false, 'stale model completion must not reactivate the scene');
  host.destroy();
  host.destroy();
});

test('Cockpit scene layout applies bounded view, follow, point size, and range settings across reactivation', () => {
  class LayoutRenderer {
    constructor(_canvas, options) {
      this.options = { ...options };
      this.camera = { target: [0, 0, 0], distance: 8, yaw: Math.PI / 4, pitch: 33 * Math.PI / 180 };
      this.cameraMode = 'world';
    }
    bindControls() {}
    setViewPreset(view) {
      if (view === 'top') this.camera = { ...this.camera, yaw: -Math.PI / 2, pitch: 88 * Math.PI / 180 };
      else if (view === 'front') this.camera = { ...this.camera, yaw: 0, pitch: 8 * Math.PI / 180 };
      else this.camera = { ...this.camera, yaw: Math.PI / 4, pitch: 33 * Math.PI / 180 };
    }
    setCameraMode(mode) { this.cameraMode = mode; }
    setStatus() {}
    clearPointCloud() {}
    setRobotPose() {}
    setTrail() {}
    resetRobotJointPositions() {}
    configureOfficialRobot() {}
    resize() {}
    destroy() {}
  }
  const host = createCockpitSceneHost({ canvas: {}, Renderer: LayoutRenderer });
  host.activate();
  assert.deepEqual(host.applySceneLayout({ view: 'top', follow_robot: false, point_size: 3, range_m: 40 }), {
    view: 'top', follow_robot: false, point_size: 3, range_m: 40,
  });
  host.deactivate();
  host.activate();
  assert.deepEqual(host.sceneSnapshot(), { view: 'top', follow_robot: false, point_size: 3, range_m: 40 });
  host.applySceneLayout({ view: 'robot-follow', follow_robot: true, point_size: 2, range_m: 30 });
  assert.equal(host.sceneSnapshot().view, 'robot-follow');
  host.destroy();
});

test('Cockpit HIGH stays capped by the current server delivery limit', () => {
  let onChange;
  let requested = 0;
  const quality = {
    value: 'low',
    addEventListener(name, callback) { if (name === 'change') onChange = callback; },
    removeEventListener() {},
  };
  const host = createCockpitSceneHost({
    canvas: {}, Renderer: class {}, maxPoints: 18_000, controls: { quality },
    onPointBudgetRequest(budget) { requested = budget; },
  });
  quality.value = 'high';
  onChange();
  assert.equal(requested, 60_000);
  assert.equal(host.diagnostics().quality.effectiveBudget, 18_000);
  host.setPointLimit(30_000);
  assert.equal(host.diagnostics().quality.effectiveBudget, 30_000);
  host.setPointLimit(1_000_000);
  assert.equal(host.diagnostics().quality.effectiveBudget, 60_000);
  host.destroy();
});

test('Cockpit never labels a cached prior-session frame as LIVE', () => {
  const cloud = { seq: 7, points: [0, 0, 0] };
  assert.equal(projectCockpitPointcloud({ cloud, lastFrameAt: 900, sessionStartedAt: 1000, now: 1100, ready: true }).freshness, 'WAITING');
  assert.equal(projectCockpitPointcloud({ cloud, lastFrameAt: 1001, sessionStartedAt: 1000, now: 7002, ready: true }).freshness, 'STALE');
  assert.equal(projectCockpitPointcloud({ cloud, lastFrameAt: 1001, sessionStartedAt: 1000, now: 1100, ready: true }).freshness, 'LIVE');
  assert.equal(projectCockpitPointcloud({ cloud: { ...cloud, offline_snapshot: true }, lastFrameAt: 1001, sessionStartedAt: 1000, now: 1100, ready: true }).freshness, 'WAITING');
});

test('Mapping and Cockpit share exactly one PointCloud transport', () => {
  const sockets = [];
  const frames = [];
  const scheduledFrames = [];
  class FakeSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      sockets.push(this);
    }
    close() {
      this.readyState = 3;
      this.onclose?.();
    }
  }
  const transport = createPointcloudTransport({
    decodeFrame: () => ({ seq: frames.length + 1, stream_id: 'stream-a', points: [0, 0, 0] }),
    fetchFn: async () => ({ status: 204, ok: true }),
    socketFactory: (url) => new FakeSocket(url),
    location: { protocol: 'http:', host: 'dashboard.test' },
    requestAnimationFrame: (callback) => { scheduledFrames.push(callback); return scheduledFrames.length; },
    cancelAnimationFrame: () => {},
    setTimeout: () => 1,
    clearTimeout: () => {},
  });
  transport.subscribe('shared-cloud-store', (cloud) => frames.push(cloud));

  transport.replaceDemand(['mapping']);
  assert.equal(sockets.length, 1);
  for (let index = 0; index < 20; index += 1) {
    transport.replaceDemand(index % 2 ? ['mapping'] : ['cockpit']);
    assert.equal(sockets.length, 1, 'changing the active scene must reuse the same socket');
  }
  sockets[0].readyState = 1;
  sockets[0].onmessage?.({ data: new ArrayBuffer(4) });
  scheduledFrames.shift()();
  assert.equal(frames.length, 1, 'one binary frame is decoded and fanned out once');
  assert.ok(frames[0].transport_metrics.decode_ms >= 0);
  assert.equal(frames[0].transport_metrics.dropped_frames, 0);

  transport.replaceDemand([]);
  assert.equal(sockets[0].readyState, 3);
  transport.replaceDemand(['cockpit']);
  assert.equal(sockets.length, 2, 'a new session opens only after all prior demand was released');
  sockets[0].onmessage?.({ data: new ArrayBuffer(4) });
  assert.equal(scheduledFrames.length, 0, 'old-session callbacks are fenced');
  assert.equal(transport.diagnostics().activeConsumers[0], 'cockpit');
  transport.destroy();
});

test('the shared owner is the only PointCloud WebSocket construction site', () => {
  const appSource = load('../robot_dashboard/static/app.js');
  const transportSource = load('../robot_dashboard/static/features/sensors/pointcloud_transport.js');
  assert.doesNotMatch(appSource, /new WebSocket\([^\n]*pointcloud/i);
  assert.equal((transportSource.match(/new environment\.WebSocket\(/g) || []).length, 1);
  assert.match(appSource, /replaceDemand\(pointcloudDemandConsumers\(\)\)/);
  assert.match(appSource, /activePage === 'cockpit' \|\| \(activePage === 'mapping' && desiredMapView\(\) !== 'occupancy'\)/);
});
