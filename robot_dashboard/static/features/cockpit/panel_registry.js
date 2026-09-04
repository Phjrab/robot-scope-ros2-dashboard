import { createCameraPanel } from './panels/camera_panel.js';
import { createControllerPanel } from './panels/controller_panel.js';
import { createMapPanel } from './panels/map_panel.js';
import { createMissionPanel } from './panels/mission_panel.js';
import { createNavigationPanel } from './panels/navigation_panel.js';
import { createRoutePlannerPanel } from './panels/route_planner_panel.js';

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
    title: 'Map & Localization',
    label: 'Map',
    icon: '⌖',
    kind: 'map',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-09 · READ ONLY MAP',
    description: '선택한 저장 지도와 localization 상태를 리비전에 고정해 표시합니다.',
    defaultGeometry: Object.freeze({ x: 420, y: 138, width: 380, height: 280 }),
    bounds: Object.freeze({ minWidth: 300, minHeight: 190, maxWidth: 820, maxHeight: 640, compactWidth: 300, compactHeight: 58 }),
  }),
  Object.freeze({
    id: 'navigation-main',
    panelType: 'navigation.main',
    title: 'Navigation & Takeover',
    label: 'Navigation',
    icon: '◈',
    kind: 'navigation',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-10 · SERVER AUTHORITATIVE',
    description: '기존 Nav2 상태와 명시적 takeover cleanup을 제어합니다.',
    defaultGeometry: Object.freeze({ x: 520, y: 92, width: 520, height: 520 }),
    bounds: Object.freeze({ minWidth: 390, minHeight: 360, maxWidth: 980, maxHeight: 760, compactWidth: 340, compactHeight: 58 }),
  }),
  Object.freeze({
    id: 'mission-main',
    panelType: 'mission.main',
    title: 'Mission Route Sequencer',
    label: 'Mission',
    icon: '◆',
    kind: 'mission',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-11 · REVISION PINNED',
    description: '서버가 소유하는 bounded annotation waypoint route입니다.',
    defaultGeometry: Object.freeze({ x: 28, y: 84, width: 560, height: 560 }),
    bounds: Object.freeze({ minWidth: 410, minHeight: 390, maxWidth: 980, maxHeight: 780, compactWidth: 350, compactHeight: 58 }),
  }),
  Object.freeze({
    id: 'route-planner',
    panelType: 'route-planner.main',
    title: 'Competition Route Planner',
    label: 'Route Planner',
    icon: '↝',
    kind: 'route-planner',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'TRACK G · SERVER AUTHORITATIVE',
    description: '주문서 추천 경로를 수동 Guidance와 Mission draft에 함께 사용합니다.',
    defaultGeometry: Object.freeze({ x: 72, y: 58, width: 680, height: 650 }),
    bounds: Object.freeze({ minWidth: 460, minHeight: 440, maxWidth: 1120, maxHeight: 860, compactWidth: 380, compactHeight: 58 }),
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
        return createCameraPanel({ descriptor, document: documentValue, cameraDemand: options.cameraDemand, perception: options.perception });
      }
      if (descriptor.kind === 'controller') {
        return createControllerPanel({ descriptor, document: documentValue, controllerState: options.controllerState });
      }
      if (descriptor.kind === 'map') {
        return createMapPanel({ descriptor, document: documentValue, mapState: options.mapState, navigationEngine: options.navigationEngine });
      }
      if (descriptor.kind === 'navigation') {
        return createNavigationPanel({ descriptor, document: documentValue, adapter: options.navigationAdapter, navigationEngine: options.navigationEngine });
      }
      if (descriptor.kind === 'mission') {
        return createMissionPanel({
          descriptor,
          document: documentValue,
          client: options.missionClient,
          navigationAdapter: options.navigationAdapter,
          getContext: options.getMissionContext,
        });
      }
      if (descriptor.kind === 'route-planner') {
        return createRoutePlannerPanel({ descriptor, document: documentValue, client: options.routePlannerClient });
      }
      return createPlaceholderContent(descriptor, documentValue);
    },
  });
}

export { PLACEHOLDER_DESCRIPTORS };
