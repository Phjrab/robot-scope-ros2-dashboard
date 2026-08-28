import {
  PANEL_Z_MAX,
  clampPanelGeometry,
  compactPanelGeometry,
  focusPanelGeometry,
  movePanelGeometry,
  normalizePanelZOrder,
  panelStateSnapshot,
  recoverPanelState,
  resizePanelGeometry,
  restoreFocusedPanel,
} from './panel_geometry.js';
import { createPanelView } from './panel_view.js';
import {
  DOCK_POSITIONS,
  cascadePanelLayout,
  dockPanelGeometry,
  normalizeSnapOptions,
  snapPanelGeometry,
  splitPanelLayout,
  tilePanelLayout,
} from './snap_layout.js';

function defaultViewport(host) {
  const rect = host.getBoundingClientRect?.() || {};
  return {
    width: Math.max(1, Number(rect.width || host.clientWidth || 1)),
    height: Math.max(1, Number(rect.height || host.clientHeight || 1)),
    padding: 12,
    reservedBottom: 78,
  };
}

function restoreGeometry(state) {
  return Object.freeze({
    mode: state.mode,
    dock: state.dock || null,
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
  });
}

export function createPanelManager(options = {}) {
  const host = options.host;
  const registry = options.registry;
  const viewFactory = options.viewFactory || createPanelView;
  const requestFrame = options.requestAnimationFrame || globalThis.requestAnimationFrame?.bind(globalThis) || ((callback) => globalThis.setTimeout(callback, 16));
  const cancelFrame = options.cancelAnimationFrame || globalThis.cancelAnimationFrame?.bind(globalThis) || globalThis.clearTimeout?.bind(globalThis);
  const viewportProvider = options.viewportProvider || (() => defaultViewport(host));
  if (!host || !registry) throw new TypeError('PanelManager requires a host and registry.');

  const states = new Map();
  const runtimes = new Map();
  const compactRestore = new Map();
  const dockRestore = new Map();
  const focusRestore = new Map();
  let active = false;
  let destroyed = false;
  let interaction = null;
  let interactionFrame = 0;
  let pendingGeometry = null;
  let snapOptions = normalizeSnapOptions(options.snapOptions);
  let snapPreview = null;
  let activePanelId = '';
  let activations = 0;
  let deactivations = 0;

  function viewport() {
    return viewportProvider();
  }

  function descriptorForState(state) {
    return registry.get(state.panelType);
  }

  function setState(id, nextState) {
    const snapshot = panelStateSnapshot(nextState);
    states.set(id, snapshot);
    runtimes.get(id)?.view?.update(snapshot);
    syncContentLifecycle(id);
    options.onStateChange?.(snapshot);
    return snapshot;
  }

  function setSnapPreview(preview) {
    snapPreview = preview;
    options.onSnapPreview?.(preview);
  }

  function safeHook(runtime, name, ...args) {
    try {
      runtime?.content?.[name]?.(...args);
    } catch (error) {
      options.onError?.(error);
    }
  }

  function setContentActive(runtime, nextActive, reason) {
    if (!runtime || runtime.contentActive === nextActive) return;
    runtime.contentActive = nextActive;
    if (nextActive) safeHook(runtime, 'activate', { panelId: runtime.descriptor.id });
    else safeHook(runtime, 'deactivate', reason);
  }

  function syncContentLifecycle(id) {
    const state = states.get(id);
    const runtime = runtimes.get(id);
    if (!state || !runtime) return;
    const shouldActivate = active && state.visible && state.mode !== 'compact';
    setContentActive(runtime, shouldActivate, state.visible ? 'panel_compact_or_workspace_inactive' : 'panel_closed');
  }

  function mountRuntime(state) {
    if (runtimes.has(state.id)) return runtimes.get(state.id);
    const descriptor = descriptorForState(state);
    if (!descriptor) throw new RangeError('Unknown registered panel type.');
    const view = viewFactory({
      host,
      descriptor,
      document: options.document,
      onBringFront: bringToFront,
      onInteractionStart: beginInteraction,
      onAction: handleAction,
    });
    const content = registry.createContent(state.panelType);
    const runtime = { descriptor, view, content, contentActive: false };
    runtimes.set(state.id, runtime);
    safeHook(runtime, 'mount', view.content, { panelId: state.id, panelType: state.panelType });
    view.update(state);
    syncContentLifecycle(state.id);
    return runtime;
  }

  function normalizeZ(activeId = '') {
    const visible = [...states.values()].filter((state) => state.visible);
    for (const normalized of normalizePanelZOrder(visible, activeId, PANEL_Z_MAX)) {
      states.set(normalized.id, normalized);
      runtimes.get(normalized.id)?.view?.update(normalized);
    }
  }

  function bringToFront(id) {
    const state = states.get(id);
    if (!state?.visible) return null;
    activePanelId = id;
    normalizeZ(id);
    options.onActivePanelChange?.(id);
    return states.get(id);
  }

  function flushInteractionFrame() {
    interactionFrame = 0;
    if (!interaction || !pendingGeometry) return;
    const nextGeometry = pendingGeometry;
    pendingGeometry = null;
    const state = states.get(interaction.id);
    if (state) setState(interaction.id, { ...state, ...nextGeometry });
  }

  function scheduleInteractionGeometry(geometry) {
    pendingGeometry = geometry;
    if (!interactionFrame) interactionFrame = requestFrame(flushInteractionFrame);
  }

  function moveInteraction(event) {
    if (!interaction || event.pointerId !== interaction.pointerId) return;
    event.preventDefault?.();
    const dx = Number(event.clientX) - interaction.startX;
    const dy = Number(event.clientY) - interaction.startY;
    let geometry = interaction.kind === 'resize'
      ? resizePanelGeometry(interaction.startGeometry, interaction.handle, dx, dy, interaction.viewport, interaction.bounds)
      : movePanelGeometry(interaction.startGeometry, dx, dy, interaction.viewport, interaction.bounds);
    if (interaction.kind === 'move') {
      const snapped = snapPanelGeometry(geometry, interaction.viewport, interaction.peers, {
        ...snapOptions,
        bounds: interaction.bounds,
        disabled: Boolean(event.altKey),
      });
      geometry = snapped.geometry;
      setSnapPreview(snapped.preview);
    }
    scheduleInteractionGeometry(geometry);
  }

  function removeInteractionListeners(current) {
    current.target.removeEventListener('pointermove', moveInteraction);
    current.target.removeEventListener('pointerup', finishInteraction);
    current.target.removeEventListener('pointercancel', finishInteraction);
    current.target.removeEventListener('lostpointercapture', finishInteraction);
  }

  function finishInteraction(event) {
    const current = interaction;
    if (!current || event?.pointerId !== current.pointerId) return;
    if (interactionFrame) {
      cancelFrame?.(interactionFrame);
      interactionFrame = 0;
    }
    flushInteractionFrame();
    interaction = null;
    pendingGeometry = null;
    setSnapPreview(null);
    removeInteractionListeners(current);
    if (event?.type !== 'lostpointercapture' && current.target.hasPointerCapture?.(current.pointerId)) {
      current.target.releasePointerCapture?.(current.pointerId);
    }
  }

  function cancelInteraction() {
    if (!interaction) return;
    finishInteraction({ pointerId: interaction.pointerId, type: 'managercancel' });
  }

  function beginInteraction(event, id, kind, handle = '') {
    const state = states.get(id);
    const descriptor = descriptorForState(state || {});
    const movable = kind === 'move' && state?.mode !== 'focus' && !state?.dock;
    const resizable = kind === 'resize' && state?.mode === 'floating' && !state?.dock;
    if (!active || !state?.visible || state.locked || !descriptor || (!movable && !resizable)) return false;
    cancelInteraction();
    bringToFront(id);
    const current = states.get(id);
    const target = event.currentTarget;
    interaction = {
      id,
      kind,
      handle,
      pointerId: event.pointerId,
      target,
      startX: Number(event.clientX),
      startY: Number(event.clientY),
      startGeometry: current,
      viewport: viewport(),
      bounds: descriptor.bounds,
      peers: [...states.values()].filter((candidate) => candidate.id !== id && candidate.visible),
    };
    target.addEventListener('pointermove', moveInteraction);
    target.addEventListener('pointerup', finishInteraction);
    target.addEventListener('pointercancel', finishInteraction);
    target.addEventListener('lostpointercapture', finishInteraction);
    target.setPointerCapture?.(event.pointerId);
    return true;
  }

  function toggleCompact(id) {
    let state = states.get(id);
    const descriptor = descriptorForState(state || {});
    if (!state?.visible || !descriptor) return null;
    if (state.mode === 'focus') {
      toggleFocus(id);
      state = states.get(id);
    }
    if (state.mode === 'compact') {
      const restore = compactRestore.get(id) || descriptor.defaultGeometry;
      compactRestore.delete(id);
      if (restore.dock) {
        const docked = dockPanelGeometry(restore.dock, viewport(), descriptor.bounds, restore);
        return setState(id, { ...state, ...docked.geometry, mode: docked.mode, dock: docked.dock, restoreGeometry: restore.restoreGeometry });
      }
      return setState(id, { ...state, ...clampPanelGeometry(restore, viewport(), descriptor.bounds, descriptor.defaultGeometry), mode: 'floating' });
    }
    compactRestore.set(id, restoreGeometry(state));
    return setState(id, { ...state, ...compactPanelGeometry(state, viewport(), descriptor.bounds), mode: 'compact', dock: null });
  }

  function toggleFocus(id) {
    const state = states.get(id);
    const descriptor = descriptorForState(state || {});
    if (!state?.visible || !descriptor) return null;
    if (state.mode === 'focus') {
      const saved = focusRestore.get(id);
      focusRestore.delete(id);
      if (!saved) return setState(id, restoreFocusedPanel(state, viewport(), descriptor.bounds));
      if (saved.dock) {
        const docked = dockPanelGeometry(saved.dock, viewport(), descriptor.bounds, saved);
        return setState(id, { ...state, ...docked.geometry, mode: docked.mode, dock: docked.dock, restoreGeometry: saved.restoreGeometry });
      }
      return setState(id, { ...state, ...recoverPanelState(saved, viewport(), descriptor.bounds), restoreGeometry: saved.restoreGeometry });
    }
    focusRestore.set(id, state);
    return setState(id, {
      ...state,
      ...focusPanelGeometry(viewport()),
      mode: 'focus',
      restoreGeometry: restoreGeometry(state),
    });
  }

  function closePanel(id) {
    const state = states.get(id);
    if (!state?.visible) return null;
    if (interaction?.id === id) cancelInteraction();
    const runtime = runtimes.get(id);
    setContentActive(runtime, false, 'panel_closed');
    safeHook(runtime, 'destroy');
    runtime?.view?.destroy();
    runtimes.delete(id);
    if (activePanelId === id) {
      activePanelId = '';
      options.onActivePanelChange?.('');
    }
    const closed = setState(id, { ...state, visible: false });
    normalizeZ();
    return closed;
  }

  function openPanel(panelType) {
    const descriptor = registry.get(panelType);
    if (!descriptor) return null;
    const previous = states.get(descriptor.id);
    if (previous?.visible) return bringToFront(descriptor.id);
    const base = previous || {
      id: descriptor.id,
      panelType: descriptor.panelType,
      title: descriptor.title,
      mode: 'floating',
      ...descriptor.defaultGeometry,
      zIndex: 1,
      pinned: false,
      locked: false,
      visible: true,
      restoreGeometry: null,
      dock: null,
    };
    const docked = base.dock ? dockPanelGeometry(base.dock, viewport(), descriptor.bounds, base) : null;
    const geometry = docked
      ? { ...base, ...docked.geometry, mode: docked.mode, dock: docked.dock, visible: true }
      : recoverPanelState({ ...base, visible: true }, viewport(), descriptor.bounds);
    const state = setState(descriptor.id, geometry);
    mountRuntime(state);
    bringToFront(descriptor.id);
    return states.get(descriptor.id);
  }

  function dockPanel(id, position) {
    if (!DOCK_POSITIONS.includes(position)) return null;
    let state = states.get(id);
    const descriptor = descriptorForState(state || {});
    if (!state?.visible || !descriptor || state.locked) return null;
    if (state.mode === 'focus') {
      toggleFocus(id);
      state = states.get(id);
    }
    if (state.mode === 'compact') {
      toggleCompact(id);
      state = states.get(id);
    }
    if (!state.dock) dockRestore.set(id, restoreGeometry(state));
    const result = dockPanelGeometry(position, viewport(), descriptor.bounds, state);
    if (!result.dock) return setState(id, { ...state, ...result.geometry, mode: result.mode, dock: null });
    return setState(id, {
      ...state,
      ...result.geometry,
      mode: result.mode,
      dock: result.dock,
      restoreGeometry: dockRestore.get(id) || restoreGeometry(state),
    });
  }

  function undockPanel(id) {
    let state = states.get(id);
    const descriptor = descriptorForState(state || {});
    if (!state?.visible || !descriptor || state.locked) return null;
    if (state.mode === 'focus') {
      toggleFocus(id);
      state = states.get(id);
    }
    if (!state.dock) return state;
    const restore = dockRestore.get(id) || state.restoreGeometry || descriptor.defaultGeometry;
    dockRestore.delete(id);
    return setState(id, {
      ...state,
      ...clampPanelGeometry(restore, viewport(), descriptor.bounds, descriptor.defaultGeometry),
      mode: 'floating',
      dock: null,
      restoreGeometry: null,
    });
  }

  function arrangementEntries() {
    return [...states.values()]
      .filter((state) => state.visible && !state.locked && !state.pinned && state.mode !== 'focus')
      .sort((left, right) => left.zIndex - right.zIndex || left.id.localeCompare(right.id))
      .map((state) => ({ id: state.id, geometry: state, bounds: descriptorForState(state).bounds }));
  }

  function arrangePanels(kind) {
    if (kind === 'recover') {
      recoverViewport();
      return diagnostics();
    }
    const entries = arrangementEntries();
    const results = kind === 'split' ? splitPanelLayout(entries, viewport())
      : kind === 'tile' ? tilePanelLayout(entries, viewport())
        : kind === 'cascade' ? cascadePanelLayout(entries, viewport()) : [];
    for (const result of results) {
      const state = states.get(result.id);
      if (!state) continue;
      if (result.dock) {
        if (!state.dock) dockRestore.set(state.id, restoreGeometry(state));
        setState(state.id, { ...state, ...result.geometry, mode: result.mode, dock: result.dock, restoreGeometry: dockRestore.get(state.id) });
      } else {
        dockRestore.delete(state.id);
        setState(state.id, { ...state, ...result.geometry, mode: result.mode, dock: null, restoreGeometry: null });
      }
    }
    normalizeZ(activePanelId);
    return diagnostics();
  }

  function setSnapOptions(nextOptions = {}) {
    snapOptions = normalizeSnapOptions({ ...snapOptions, ...nextOptions });
    return snapOptions;
  }

  function handleAction(id, action) {
    const state = states.get(id);
    if (!state) return;
    if (action === 'close') closePanel(id);
    else if (action === 'compact') toggleCompact(id);
    else if (action === 'focus') toggleFocus(id);
    else if (action === 'pin') setState(id, { ...state, pinned: !state.pinned });
    else if (action === 'lock') {
      if (interaction?.id === id) cancelInteraction();
      setState(id, { ...state, locked: !state.locked });
    }
  }

  function recoverViewport() {
    cancelInteraction();
    for (const state of states.values()) {
      const descriptor = descriptorForState(state);
      if (!descriptor || !state.visible) continue;
      if (state.dock && state.mode !== 'focus') {
        const docked = dockPanelGeometry(state.dock, viewport(), descriptor.bounds, state);
        setState(state.id, { ...state, ...docked.geometry, mode: docked.mode, dock: docked.dock });
      } else setState(state.id, recoverPanelState(state, viewport(), descriptor.bounds));
    }
    normalizeZ();
  }

  function activate() {
    if (destroyed || active) return diagnostics();
    active = true;
    activations += 1;
    recoverViewport();
    return diagnostics();
  }

  function deactivate(reason = 'workspace_inactive') {
    if (!active) return diagnostics();
    cancelInteraction();
    active = false;
    deactivations += 1;
    for (const runtime of runtimes.values()) setContentActive(runtime, false, reason);
    return diagnostics();
  }

  function diagnostics() {
    return Object.freeze({
      active,
      destroyed,
      activations,
      deactivations,
      interaction: interaction ? Object.freeze({ id: interaction.id, kind: interaction.kind, handle: interaction.handle }) : null,
      activePanelId,
      snapOptions,
      snapPreview,
      panels: Object.freeze([...states.values()].map(panelStateSnapshot)),
      content: Object.freeze(Object.fromEntries([...runtimes].map(([id, runtime]) => [id, runtime.content.diagnostics?.() || null]))),
    });
  }

  function destroy() {
    if (destroyed) return;
    deactivate('workspace_destroyed');
    for (const [id, runtime] of runtimes) {
      safeHook(runtime, 'destroy');
      runtime.view.destroy();
      runtimes.delete(id);
    }
    states.clear();
    compactRestore.clear();
    dockRestore.clear();
    focusRestore.clear();
    activePanelId = '';
    setSnapPreview(null);
    destroyed = true;
  }

  for (const descriptor of registry.list()) {
    const initial = panelStateSnapshot({
      id: descriptor.id,
      panelType: descriptor.panelType,
      title: descriptor.title,
      mode: 'floating',
      ...descriptor.defaultGeometry,
      zIndex: states.size + 1,
      pinned: false,
      locked: false,
      visible: descriptor.defaultVisible !== false,
      restoreGeometry: null,
      dock: null,
    });
    states.set(initial.id, initial);
    if (initial.visible) mountRuntime(initial);
  }
  normalizeZ();

  return Object.freeze({
    activate,
    deactivate,
    openPanel,
    closePanel,
    bringToFront,
    toggleCompact,
    toggleFocus,
    dockPanel,
    undockPanel,
    arrangePanels,
    setSnapOptions,
    handleAction,
    recoverViewport,
    cancelInteraction,
    diagnostics,
    destroy,
  });
}
