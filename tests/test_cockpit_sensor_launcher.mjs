import assert from 'node:assert/strict';
import test from 'node:test';

import { createPanelRegistry, PLACEHOLDER_DESCRIPTORS } from '../robot_dashboard/static/features/cockpit/panel_registry.js';
import { nextLauncherIndex } from '../robot_dashboard/static/features/cockpit/sensor_launcher.js';

test('registry exposes two fixed camera sources, map placeholder, and Controller Panel', () => {
  const registry = createPanelRegistry({ document: {}, cameraDemand: {} });
  assert.deepEqual(registry.list().map((descriptor) => descriptor.label), ['Go2 Front Camera', 'RealSense Color Camera', 'Map', 'Controller']);
  assert.ok(registry.list().every((descriptor) => descriptor.singleton === true && descriptor.defaultVisible === false));
  assert.ok(registry.list().every((descriptor) => descriptor.icon && descriptor.defaultGeometry.width && descriptor.bounds.minWidth));
  assert.equal(registry.get('camera.go2-front').id, 'camera-go2-front');
  assert.equal(registry.get('camera.go2-front').sourceId, 'go2_front');
  assert.equal(registry.get('camera.realsense-color').sourceId, 'realsense_color');
  assert.equal(registry.get('placeholder.controller').kind, 'controller');
  assert.equal(registry.get('unknown'), null);
});

test('registry rejects duplicate singleton ids even when panel types differ', () => {
  const duplicate = { ...PLACEHOLDER_DESCRIPTORS[0], panelType: 'placeholder.camera-copy' };
  assert.throws(() => createPanelRegistry({ document: {}, descriptors: [PLACEHOLDER_DESCRIPTORS[0], duplicate] }), /id must be unique/);
});

test('launcher keyboard navigation wraps and supports Home and End', () => {
  assert.equal(nextLauncherIndex(0, 'ArrowDown', 3), 1);
  assert.equal(nextLauncherIndex(2, 'ArrowRight', 3), 0);
  assert.equal(nextLauncherIndex(0, 'ArrowUp', 3), 2);
  assert.equal(nextLauncherIndex(1, 'Home', 3), 0);
  assert.equal(nextLauncherIndex(1, 'End', 3), 2);
  assert.equal(nextLauncherIndex(1, 'Enter', 3), 1);
  assert.equal(nextLauncherIndex(0, 'ArrowDown', 0), -1);
});
