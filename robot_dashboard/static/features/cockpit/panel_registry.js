import { createCameraPanel } from './panels/camera_panel.js';
import { createControllerPanel } from './panels/controller_panel.js';

const PLACEHOLDER_DESCRIPTORS = Object.freeze([
  Object.freeze({
    id: 'camera-go2-front',
    panelType: 'camera.go2-front',
    title: 'Go2 Front Camera',
    label: 'Go2 Front Camera',
    icon: '◉',
    kind: 'camera',
    sourceId: 'go2_front',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-04 · CAMERA',
    defaultGeometry: Object.freeze({ x: 28, y: 96, width: 360, height: 240 }),
    bounds: Object.freeze({ minWidth: 280, minHeight: 170, maxWidth: 760, maxHeight: 600, compactWidth: 290, compactHeight: 58 }),
  }),
  Object.freeze({
    id: 'camera-realsense-color',
    panelType: 'camera.realsense-color',
    title: 'RealSense Color Camera',
    label: 'RealSense Color Camera',
    icon: '▣',
    kind: 'camera',
    sourceId: 'realsense_color',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-04 · CAMERA',
    defaultGeometry: Object.freeze({ x: 420, y: 112, width: 380, height: 250 }),
    bounds: Object.freeze({ minWidth: 280, minHeight: 170, maxWidth: 760, maxHeight: 600, compactWidth: 300, compactHeight: 58 }),
  }),
  Object.freeze({
    id: 'placeholder-map',
    panelType: 'placeholder.map',
    title: 'Map Placeholder',
    label: 'Map',
    icon: '⌖',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-03 · PLACEHOLDER',
    description: '실제 map 또는 localization data를 읽지 않는 배치 검증용 panel입니다.',
    defaultGeometry: Object.freeze({ x: 420, y: 138, width: 380, height: 280 }),
    bounds: Object.freeze({ minWidth: 300, minHeight: 190, maxWidth: 820, maxHeight: 640, compactWidth: 300, compactHeight: 58 }),
  }),
  Object.freeze({
    id: 'placeholder-controller',
    panelType: 'placeholder.controller',
    title: 'Xbox Controller',
    label: 'Controller',
    icon: '⌁',
    kind: 'controller',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-07 · GAMEPAD',
    description: '기존 control 경로와 분리된 읽기 전용 controller 상태입니다.',
    defaultGeometry: Object.freeze({ x: 760, y: 76, width: 320, height: 210 }),
    bounds: Object.freeze({ minWidth: 250, minHeight: 150, maxWidth: 620, maxHeight: 520, compactWidth: 280, compactHeight: 58 }),
  }),
]);

function createPlaceholderContent(descriptor, documentValue) {
  let host = null;
  let active = false;
  let destroyed = false;
  let mounts = 0;
  let activations = 0;
  let deactivations = 0;

  function mount(nextHost) {
    if (destroyed || host) return;
    host = nextHost;
    mounts += 1;
    const wrapper = documentValue.createElement('div');
    wrapper.className = 'cockpit-placeholder-content';
    const eyebrow = documentValue.createElement('span');
    eyebrow.textContent = descriptor.eyebrow;
    const title = documentValue.createElement('strong');
    title.textContent = descriptor.title;
    const description = documentValue.createElement('p');
    description.textContent = descriptor.description;
    const boundary = documentValue.createElement('small');
    boundary.textContent = 'NO SENSOR · NO ROS · NO CONTROL COMMAND';
    wrapper.append(eyebrow, title, description, boundary);
    host.append(wrapper);
  }

  function activate() {
    if (destroyed || active || !host) return;
    active = true;
    activations += 1;
    host.dataset.contentLifecycle = 'active';
  }

  function deactivate() {
    if (!active) return;
    active = false;
    deactivations += 1;
    if (host) host.dataset.contentLifecycle = 'inactive';
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    destroyed = true;
    host?.replaceChildren();
    host = null;
  }

  function diagnostics() {
    return Object.freeze({ mounted: Boolean(host), active, destroyed, mounts, activations, deactivations });
  }

  return Object.freeze({ mount, activate, deactivate, destroy, diagnostics });
}

export function createPanelRegistry(options = {}) {
  const documentValue = options.document || globalThis.document;
  const descriptors = options.descriptors || PLACEHOLDER_DESCRIPTORS;
  const entries = new Map();
  for (const descriptor of descriptors) {
    if (!/^[a-z][a-z0-9.-]{1,63}$/.test(descriptor.panelType) || !/^[a-z][a-z0-9-]{1,63}$/.test(descriptor.id)) {
      throw new TypeError('Panel registry identifiers must be fixed bounded tokens.');
    }
    if (entries.has(descriptor.panelType)) throw new TypeError('Panel type must be unique.');
    if ([...entries.values()].some((entry) => entry.id === descriptor.id)) throw new TypeError('Panel id must be unique.');
    if (descriptor.singleton !== true) throw new TypeError('CWP-03 panel descriptors must be singleton.');
    entries.set(descriptor.panelType, descriptor);
  }

  return Object.freeze({
    list: () => Object.freeze([...entries.values()]),
    get: (panelType) => entries.get(String(panelType || '')) || null,
    createContent(panelType) {
      const descriptor = entries.get(String(panelType || ''));
      if (!descriptor) throw new RangeError('Unknown panel type.');
      if (descriptor.kind === 'camera') {
        return createCameraPanel({ descriptor, document: documentValue, cameraDemand: options.cameraDemand });
      }
      if (descriptor.kind === 'controller') {
        return createControllerPanel({ descriptor, document: documentValue, controllerState: options.controllerState });
      }
      return createPlaceholderContent(descriptor, documentValue);
    },
  });
}

export { PLACEHOLDER_DESCRIPTORS };
