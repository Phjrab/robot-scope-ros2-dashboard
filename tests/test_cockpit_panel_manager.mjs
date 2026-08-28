import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clampPanelGeometry,
  focusPanelGeometry,
  normalizePanelZOrder,
  recoverPanelState,
  resizePanelGeometry,
  restoreFocusedPanel,
} from '../robot_dashboard/static/features/cockpit/panel_geometry.js';
import { createPanelManager } from '../robot_dashboard/static/features/cockpit/panel_manager.js';

const viewport = { width: 1000, height: 700, padding: 12, reservedBottom: 78 };
const bounds = { minWidth: 250, minHeight: 150, maxWidth: 620, maxHeight: 500, compactWidth: 280, compactHeight: 58 };

test('geometry clamp recovers invalid and offscreen panels inside the usable viewport', () => {
  const geometry = clampPanelGeometry(
    { x: Infinity, y: -900, width: NaN, height: 4000 },
    viewport,
    bounds,
    { defaultX: 30, defaultY: 40 },
  );
  assert.ok(Number.isFinite(geometry.x) && Number.isFinite(geometry.y));
  assert.ok(geometry.x >= 12 && geometry.y >= 12);
  assert.ok(geometry.x + geometry.width <= 988);
  assert.ok(geometry.y + geometry.height <= 610);

  const recovered = recoverPanelState({ id: 'panel', mode: 'floating', x: 950, y: 650, width: 400, height: 260 }, { ...viewport, width: 520, height: 420 }, bounds);
  assert.ok(recovered.x + recovered.width <= 508);
  assert.ok(recovered.y + recovered.height <= 330);
});

test('edge and corner resize preserve anchors and enforce min/max bounds', () => {
  const start = { x: 300, y: 180, width: 360, height: 240 };
  const westMinimum = resizePanelGeometry(start, 'w', 500, 0, viewport, bounds);
  assert.equal(westMinimum.width, 250);
  assert.equal(westMinimum.x + westMinimum.width, start.x + start.width);

  const northwestMaximum = resizePanelGeometry(start, 'nw', -900, -900, viewport, bounds);
  assert.equal(northwestMaximum.width, 620);
  assert.equal(northwestMaximum.height, 408);
  assert.equal(northwestMaximum.x, 40);
  assert.equal(northwestMaximum.y, 12);

  const southeastMaximum = resizePanelGeometry(start, 'se', 900, 900, viewport, bounds);
  assert.equal(southeastMaximum.width, 620);
  assert.equal(southeastMaximum.height, 430);
});

test('bounded z-order is deterministic and brings the selected panel to front', () => {
  const states = [
    { id: 'bravo', zIndex: 999 },
    { id: 'alpha', zIndex: -2 },
    { id: 'charlie', zIndex: 999 },
  ];
  const normalized = normalizePanelZOrder(states, 'bravo');
  assert.deepEqual(normalized.map((state) => [state.id, state.zIndex]), [
    ['alpha', 1], ['charlie', 2], ['bravo', 3],
  ]);
  assert.ok(normalized.every((state) => state.zIndex <= 24));
});

test('focus restores the exact prior mode and geometry after viewport recovery', () => {
  const original = { id: 'panel', mode: 'floating', x: 220, y: 130, width: 420, height: 260, restoreGeometry: null };
  const focused = {
    ...original,
    ...focusPanelGeometry(viewport),
    mode: 'focus',
    restoreGeometry: { mode: original.mode, x: original.x, y: original.y, width: original.width, height: original.height },
  };
  const resizedFocus = recoverPanelState(focused, { ...viewport, width: 800, height: 600 }, bounds);
  assert.deepEqual(
    { x: resizedFocus.x, y: resizedFocus.y, width: resizedFocus.width, height: resizedFocus.height },
    focusPanelGeometry({ ...viewport, width: 800, height: 600 }),
  );
  const restored = restoreFocusedPanel(resizedFocus, viewport, bounds);
  assert.deepEqual(
    { mode: restored.mode, x: restored.x, y: restored.y, width: restored.width, height: restored.height, restoreGeometry: restored.restoreGeometry },
    { mode: 'floating', x: 220, y: 130, width: 420, height: 260, restoreGeometry: null },
  );
});

class FakePointerTarget {
  constructor() {
    this.listeners = new Map();
    this.captured = null;
  }
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(callback);
  }
  removeEventListener(name, callback) { this.listeners.get(name)?.delete(callback); }
  setPointerCapture(pointerId) { this.captured = pointerId; }
  hasPointerCapture(pointerId) { return this.captured === pointerId; }
  releasePointerCapture(pointerId) { if (this.captured === pointerId) this.captured = null; }
  emit(name, values = {}) {
    const event = { type: name, pointerId: 7, clientX: 0, clientY: 0, preventDefault() {}, ...values };
    for (const callback of this.listeners.get(name) || []) callback(event);
  }
}

function managerHarness() {
  const descriptor = {
    id: 'placeholder-one', panelType: 'placeholder.one', title: 'Placeholder One', eyebrow: 'TEST',
    defaultGeometry: { x: 40, y: 50, width: 320, height: 220 }, bounds,
  };
  const contentStats = { mounts: 0, activations: 0, deactivations: 0, destroys: 0 };
  const content = {
    mount() { contentStats.mounts += 1; },
    activate() { contentStats.activations += 1; },
    deactivate() { contentStats.deactivations += 1; },
    destroy() { contentStats.destroys += 1; },
    diagnostics: () => ({ ...contentStats }),
  };
  const registry = {
    list: () => [descriptor],
    get: (type) => type === descriptor.panelType ? descriptor : null,
    createContent: () => content,
  };
  const views = new Map();
  const frames = new Map();
  let nextFrame = 1;
  const manager = createPanelManager({
    host: { clientWidth: 1000, clientHeight: 700, getBoundingClientRect: () => ({ width: 1000, height: 700 }) },
    registry,
    viewportProvider: () => viewport,
    requestAnimationFrame(callback) { const id = nextFrame++; frames.set(id, callback); return id; },
    cancelAnimationFrame(id) { frames.delete(id); },
    viewFactory(options) {
      const view = {
        content: {}, states: [], destroyed: false,
        update(state) { this.states.push(state); },
        destroy() { this.destroyed = true; },
      };
      views.set(options.descriptor.id, { view, options });
      return view;
    },
  });
  return { manager, views, frames, contentStats };
}

test('pointer move is rAF-coalesced and pointer cancel/lost capture always clean up', () => {
  const { manager, views, frames, contentStats } = managerHarness();
  manager.activate();
  const callbacks = views.get('placeholder-one').options;
  const target = new FakePointerTarget();
  assert.equal(callbacks.onInteractionStart({ currentTarget: target, pointerId: 7, clientX: 100, clientY: 100 }, 'placeholder-one', 'move', ''), true);
  assert.equal(target.captured, 7);
  target.emit('pointermove', { clientX: 140, clientY: 125, altKey: true });
  target.emit('pointermove', { clientX: 180, clientY: 155, altKey: true });
  assert.equal(frames.size, 1, 'pointer moves must share one animation frame');
  target.emit('pointercancel', { clientX: 180, clientY: 155, altKey: true });
  assert.equal(manager.diagnostics().interaction, null);
  assert.equal(target.captured, null);
  assert.equal(frames.size, 0);
  const moved = manager.diagnostics().panels[0];
  assert.deepEqual({ x: moved.x, y: moved.y }, { x: 120, y: 105 });
  assert.equal(contentStats.activations, 1, 'geometry updates must not reactivate panel content');

  const secondTarget = new FakePointerTarget();
  callbacks.onInteractionStart({ currentTarget: secondTarget, pointerId: 7, clientX: 0, clientY: 0 }, 'placeholder-one', 'move', '');
  secondTarget.emit('lostpointercapture');
  assert.equal(manager.diagnostics().interaction, null);
});

test('switching to Operate cancels an active pointer operation and gates geometry mutations', () => {
  const { manager, views, frames } = managerHarness();
  manager.activate();
  const callbacks = views.get('placeholder-one').options;
  const target = new FakePointerTarget();
  callbacks.onInteractionStart({ currentTarget: target, pointerId: 7, clientX: 100, clientY: 100 }, 'placeholder-one', 'move', '');
  target.emit('pointermove', { clientX: 155, clientY: 145, altKey: true });
  assert.equal(frames.size, 1);

  manager.setLayoutEditable(false);
  const locked = manager.diagnostics();
  assert.equal(locked.layoutEditable, false);
  assert.equal(locked.interaction, null);
  assert.equal(frames.size, 0);
  assert.equal(target.captured, null);
  const settled = locked.panels[0];
  assert.deepEqual({ x: settled.x, y: settled.y }, { x: 95, y: 95 });

  const blockedTarget = new FakePointerTarget();
  assert.equal(callbacks.onInteractionStart({ currentTarget: blockedTarget, pointerId: 7, clientX: 0, clientY: 0 }, 'placeholder-one', 'resize', 'se'), false);
  assert.equal(manager.dockPanel('placeholder-one', 'left'), null);
  assert.equal(manager.closePanel('placeholder-one'), null);
  assert.equal(manager.toggleCompact('placeholder-one').mode, 'compact', 'compact remains available in Operate');
  assert.equal(manager.toggleFocus('placeholder-one').mode, 'focus', 'focus remains available in Operate');
});

test('Operate blocks panel creation and edit-only actions until Layout Edit resumes', () => {
  const { manager } = managerHarness();
  manager.activate();
  manager.closePanel('placeholder-one');
  manager.setLayoutEditable(false);
  assert.equal(manager.openPanel('placeholder.one'), null);
  manager.setLayoutEditable(true);
  assert.equal(manager.openPanel('placeholder.one').visible, true);
  const before = manager.diagnostics().panels[0];
  manager.setLayoutEditable(false);
  manager.handleAction('placeholder-one', 'pin');
  manager.arrangePanels('cascade');
  assert.deepEqual(manager.diagnostics().panels[0], before);
});

test('validated layout replacement is atomic and recovers imported geometry inside the viewport', () => {
  const { manager } = managerHarness();
  manager.activate();
  manager.setLayoutEditable(false);
  const before = manager.diagnostics().panels[0];
  assert.throws(() => manager.restoreValidatedLayout([{ ...before, id: 'wrong-panel' }]), /unknown or duplicate/);
  assert.deepEqual(manager.diagnostics().panels[0], before);

  manager.restoreValidatedLayout([{
    ...before,
    x: 990,
    y: 690,
    width: 600,
    height: 480,
    visible: true,
    zIndex: 1,
  }]);
  const restored = manager.diagnostics().panels[0];
  assert.ok(restored.x >= 12 && restored.y >= 12);
  assert.ok(restored.x + restored.width <= 988);
  assert.ok(restored.y + restored.height <= 610);
  manager.restoreValidatedLayout([]);
  assert.equal(manager.diagnostics().panels[0].visible, false);
});

test('close destroys DOM/content lifecycle and open remounts without duplicate runtime', () => {
  const { manager, views, contentStats } = managerHarness();
  manager.activate();
  assert.equal(contentStats.mounts, 1);
  assert.equal(contentStats.activations, 1);
  assert.deepEqual(Object.keys(manager.diagnostics().panels[0]).sort(), [
    'dock', 'height', 'id', 'locked', 'mode', 'panelType', 'pinned', 'restoreGeometry',
    'title', 'visible', 'width', 'x', 'y', 'zIndex',
  ]);
  manager.closePanel('placeholder-one');
  assert.equal(contentStats.destroys, 1);
  assert.equal(views.get('placeholder-one').view.destroyed, true);
  assert.equal(manager.diagnostics().panels[0].visible, false);
  manager.openPanel('placeholder.one');
  assert.equal(manager.diagnostics().panels[0].visible, true);
  assert.equal(contentStats.mounts, 2);
  manager.deactivate();
  manager.destroy();
});

test('dock, focus, and undock preserve the exact prior floating geometry', () => {
  const { manager } = managerHarness();
  manager.activate();
  const original = manager.diagnostics().panels[0];
  const docked = manager.dockPanel('placeholder-one', 'left');
  assert.equal(docked.dock, 'left');
  assert.deepEqual(docked.restoreGeometry, {
    mode: 'floating', dock: null, x: original.x, y: original.y, width: original.width, height: original.height,
  });
  manager.toggleFocus('placeholder-one');
  assert.equal(manager.diagnostics().panels[0].mode, 'focus');
  manager.toggleFocus('placeholder-one');
  assert.equal(manager.diagnostics().panels[0].dock, 'left');
  const restored = manager.undockPanel('placeholder-one');
  assert.deepEqual(
    { mode: restored.mode, dock: restored.dock, x: restored.x, y: restored.y, width: restored.width, height: restored.height, restoreGeometry: restored.restoreGeometry },
    { mode: 'floating', dock: null, x: original.x, y: original.y, width: original.width, height: original.height, restoreGeometry: null },
  );
});

test('restored focused dock keeps its original floating geometry for a later undock', () => {
  const { manager } = managerHarness();
  manager.activate();
  const original = manager.diagnostics().panels[0];
  manager.dockPanel('placeholder-one', 'left');
  manager.toggleFocus('placeholder-one');
  const persistedFocus = manager.diagnostics().panels[0];
  assert.equal(persistedFocus.mode, 'focus');
  assert.equal(persistedFocus.dock, 'left');
  assert.deepEqual(persistedFocus.restoreGeometry, {
    mode: 'floating', dock: null, x: original.x, y: original.y, width: original.width, height: original.height,
  });

  manager.restoreValidatedLayout([persistedFocus]);
  manager.toggleFocus('placeholder-one');
  assert.equal(manager.diagnostics().panels[0].dock, 'left');
  const undocked = manager.undockPanel('placeholder-one');
  assert.deepEqual(
    { x: undocked.x, y: undocked.y, width: undocked.width, height: undocked.height },
    { x: original.x, y: original.y, width: original.width, height: original.height },
  );
});
