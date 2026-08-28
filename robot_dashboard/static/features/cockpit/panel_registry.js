const PLACEHOLDER_DESCRIPTORS = Object.freeze([
  Object.freeze({
    id: 'placeholder-camera',
    panelType: 'placeholder.camera',
    title: 'Camera Placeholder',
    label: 'Camera',
    icon: '◉',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-03 · PLACEHOLDER',
    description: '실제 camera stream을 연결하지 않은 CWP-03 배치 검증용 panel입니다.',
    defaultGeometry: Object.freeze({ x: 28, y: 96, width: 360, height: 240 }),
    bounds: Object.freeze({ minWidth: 280, minHeight: 170, maxWidth: 760, maxHeight: 600, compactWidth: 290, compactHeight: 58 }),
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
    title: 'Controller Placeholder',
    label: 'Controller',
    icon: '⌁',
    singleton: true,
    defaultVisible: false,
    eyebrow: 'CWP-03 · PLACEHOLDER',
    description: 'control lease나 command를 만들지 않는 controller UI 자리입니다.',
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
      return createPlaceholderContent(descriptor, documentValue);
    },
  });
}

export { PLACEHOLDER_DESCRIPTORS };
