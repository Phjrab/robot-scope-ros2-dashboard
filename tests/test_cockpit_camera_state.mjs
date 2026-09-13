import test from 'node:test';
import assert from 'node:assert/strict';
import { cameraPreferences, validCameraState } from '../robot_dashboard/static/features/cockpit/camera_state.js';
import { createCockpitSceneHost } from '../robot_dashboard/static/features/cockpit/scene_host.js';

const view = { target: [12, -4, 0.3], distance: 17, yaw: 1.2, pitch: 0.8, mode: 'world' };
test('camera persistence rejects invalid data and isolates map scopes', () => {
  let raw = '{bad'; const storage = { getItem: () => raw, setItem: (_, v) => { raw = v; } };
  const store = cameraPreferences(storage); assert.equal(store.load('a'), null);
  store.save('a', view); assert.deepEqual(cameraPreferences(storage).load('a'), view);
  for (const bad of [{ ...view, distance: NaN }, { ...view, target: [1, 2] }, { ...view, mode: 'robot-command' }, { ...view, pitch: 3 }]) assert.equal(validCameraState(bad), null);
  const blocked = cameraPreferences({ getItem() { throw Error(); }, setItem() { throw Error(); } });
  blocked.save('map-a', view); assert.deepEqual(blocked.load('map-a'), view); assert.equal(blocked.load('map-b'), null);
});

class Renderer {
  constructor(_, options) { this.options = options; this.camera = { target: [0, 0, 0.2], distance: 8, yaw: 0.7, pitch: 0.5 }; this.cameraMode = 'world'; Renderer.latest = this; }
  setCameraMode(mode) { this.cameraMode = mode; }
  setViewPreset() { this.camera = { target: [0, 0, 0.2], distance: 8, yaw: 0.7, pitch: 0.5 }; }
  restoreCameraState(value) { this.camera = { ...value, target: value.target.slice() }; delete this.camera.mode; this.cameraMode = value.mode; }
  clearPointCloud() {} setPointCloud() {} setRobotPose() {} setTrail() {} setStatus() {} destroy() {} resize() {}
}
test('Cockpit keeps exact pan zoom rotation on route cycles and fresh host', () => {
  const values = new Map(); const storage = { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v) };
  const host = createCockpitSceneHost({ canvas: {}, Renderer, storage }); host.activate();
  assert.equal(Renderer.latest.cameraMode, 'follow'); assert.equal(Renderer.latest.options.autoFitOnFirstCloud, false);
  Renderer.latest.restoreCameraState(view); host.deactivate(); host.activate();
  assert.deepEqual(host.diagnostics().camera, { target: view.target, distance: view.distance, yaw: view.yaw, pitch: view.pitch });
  assert.equal(Renderer.latest.cameraMode, 'world'); host.destroy();
  const restored = createCockpitSceneHost({ canvas: {}, Renderer, storage }); restored.activate();
  assert.deepEqual(restored.diagnostics().camera.target, view.target);
  restored.setMapState({ map: { id: 'map-b', revision: 'new' } });
  assert.equal(Renderer.latest.cameraMode, 'follow');
  Renderer.latest.restoreCameraState(view);
  restored.setMapState({ map: { id: 'map-b', revision: 'new' } });
  assert.equal(Renderer.latest.cameraMode, 'world', 'same-map refresh does not reset operator view');
  restored.deactivate(); restored.setMapState({ map: { id: 'map-c', revision: 'new' } }); restored.activate();
  assert.equal(Renderer.latest.cameraMode, 'follow', 'new map while inactive uses robot-centered default');
  restored.destroy();
});
