import { createCockpitSceneHost } from './scene_host.js';
import { createPanelManager } from './panel_manager.js';
import { createPanelRegistry } from './panel_registry.js';
import { createSensorLauncher } from './sensor_launcher.js';
import { COCKPIT_LAYOUT_MODES, createLayoutModeController } from './layout_mode.js';
import { createLayoutDocument, layoutPanelsToPixels } from './layout_schema.js';
import { createLayoutStore } from './layout_store.js';
import { createLayoutLibrary } from './layout_library.js';
import { createSafetyHud } from './safety_hud.js';
import { createControllerStateStore, createGamepadUiMapper, dispatchGamepadUiAction, projectControllerStatus } from './gamepad_ui.js';
import { createCockpitMapStore } from './map_state.js';

export function cockpitGamepadUiBlocked(documentValue) {
  const activeElement = documentValue?.activeElement;
  if (activeElement?.matches?.('input, textarea, select, [contenteditable="true"]')) return true;
  return Boolean(documentValue?.querySelector?.('dialog[open], [role="dialog"]:not([hidden]), [aria-modal="true"]:not([hidden])'));
}

export function projectCockpitPointcloud(options = {}) {
  const cloud = options.cloud?.offline_snapshot ? null : options.cloud;
  const lastFrameAt = Number(options.lastFrameAt) || 0;
  const sessionStartedAt = Number(options.sessionStartedAt) || 0;
  const now = Number(options.now) || Date.now();
  const ageMs = lastFrameAt ? Math.max(0, now - lastFrameAt) : null;
  const currentSessionFrame = lastFrameAt >= sessionStartedAt;
  if (cloud?.points?.length && currentSessionFrame && options.sourceMatches !== false && ageMs != null && ageMs <= 5000 && options.ready) {
    return { cloud, freshness: 'LIVE', ageMs };
  }
  if (cloud?.points?.length && currentSessionFrame && ageMs != null) {
    return { cloud: null, freshness: 'STALE', ageMs };
  }
  return { cloud: null, freshness: 'WAITING', ageMs: null };
}

export function createCockpitWorkspace(options = {}) {
  const root = options.root;
  if (!root) throw new TypeError('Cockpit workspace root is required.');

  const statusElement = options.statusElement;
  const statusNote = options.statusNote;
  const modelElement = options.modelElement;
  let active = false;
  let destroyed = false;
  const controllerState = createControllerStateStore();
  const gamepadUi = createGamepadUiMapper({ now: options.now });
  const mapState = createCockpitMapStore();
  const panelRegistry = options.panelLayer ? createPanelRegistry({ document: options.document, cameraDemand: options.cameraDemand, controllerState, mapState, navigationEngine: options.navigationEngine }) : null;
  let panelManager = null;
  let sensorLauncher = null;
  let safetyHud = null;
  let layoutLibrary = null;
  let releaseCameraCatalog = null;
  let currentProfileId = '';
  let gamepadTimer = 0;

  function syncLayoutMode(state = layoutMode.snapshot()) {
    const editable = state.mode === COCKPIT_LAYOUT_MODES.EDIT && !state.armed;
    root.dataset.layoutMode = state.mode;
    panelManager?.setLayoutEditable(editable);
    sensorLauncher?.setLayoutEditable(editable);
    layoutLibrary?.setLayoutEditable(editable);
    safetyHud?.setLayoutState(state);
  }

  const layoutMode = createLayoutModeController({ onChange: syncLayoutMode });

  function syncLauncher() {
    const snapshot = panelManager?.diagnostics();
    sensorLauncher?.update(snapshot?.panels || [], snapshot?.activePanelId || '');
  }

  function renderSnapPreview(preview) {
    const element = options.snapPreviewElement;
    if (!element) return;
    element.hidden = !preview;
    if (!preview) return;
    const geometry = preview.geometry;
    element.dataset.snapKind = preview.kind;
    element.style.width = `${geometry.width}px`;
    element.style.height = `${geometry.height}px`;
    element.style.transform = `translate3d(${geometry.x}px, ${geometry.y}px, 0)`;
  }

  panelManager = panelRegistry ? createPanelManager({
    host: options.panelLayer,
    registry: panelRegistry,
    document: options.document,
    onError: options.onError,
    onStateChange: syncLauncher,
    onActivePanelChange: syncLauncher,
    onSnapPreview: renderSnapPreview,
    layoutEditable: false,
  }) : null;
  const allowedPanelTypes = panelRegistry?.list().map((descriptor) => descriptor.panelType) || [];
  const panelIdsByType = Object.fromEntries((panelRegistry?.list() || []).map((descriptor) => [descriptor.panelType, descriptor.id]));
  const layoutStore = createLayoutStore({ storage: options.storage, allowedPanelTypes, panelIdsByType, onError: options.onError });

  function handleLayoutAction(action) {
    const activeId = panelManager?.diagnostics().activePanelId;
    if (action.startsWith('dock-') && activeId) panelManager.dockPanel(activeId, action.slice(5));
    else if (action === 'undock' && activeId) panelManager.undockPanel(activeId);
    else if (['split', 'tile', 'cascade', 'recover'].includes(action)) panelManager?.arrangePanels(action);
    syncLauncher();
  }

  if (panelRegistry && options.launcherRoot) {
    sensorLauncher = createSensorLauncher({
      root: options.launcherRoot,
      registry: panelRegistry,
      document: options.document,
      onOpen(panelType) {
        panelManager?.openPanel(panelType);
        syncLauncher();
      },
      onLayoutAction: handleLayoutAction,
      onSnapOptions: (nextOptions) => panelManager?.setSnapOptions(nextOptions),
    });
    syncLauncher();
    releaseCameraCatalog = options.cameraDemand?.subscribe((catalog) => sensorLauncher?.updateAvailability(catalog.sources));
  }

  if (options.safetyHudRoot) {
    safetyHud = createSafetyHud({
      root: options.safetyHudRoot,
      document: options.document,
      getSnapshot: options.getSafetySnapshot,
      layoutState: layoutMode.snapshot(),
      onRequestEdit: () => layoutMode.requestEdit(),
      onApply: () => layoutMode.apply(),
      onStop: options.onSoftwareStop,
      onProjection: (projected, input) => layoutMode.updateControl({ armed: projected.layoutArmed, generation: Number(input.controlGeneration) || 0 }),
    });
  }
  syncLayoutMode();

  function setFreshness(freshness, note = '') {
    const state = ['LIVE', 'STALE'].includes(freshness) ? freshness : 'WAITING';
    if (statusElement) {
      statusElement.className = `cockpit-status cockpit-status-${state.toLowerCase()}`;
      statusElement.textContent = state;
    }
    if (statusNote) {
      statusNote.textContent = note || (state === 'LIVE'
        ? '공용 PointCloud transport의 최신 프레임'
        : state === 'STALE' ? '새 LiDAR 프레임이 없어 장면을 비웠습니다.' : '실시간 LiDAR 프레임을 기다리고 있습니다.');
    }
    root.dataset.freshness = state.toLowerCase();
  }

  const sceneHost = createCockpitSceneHost({
    canvas: options.canvas,
    Renderer: options.Renderer,
    controls: options.controls,
    maxPoints: options.maxPoints,
    now: options.now,
    onPointBudgetRequest: options.onPointBudgetRequest,
    onModelState(state, profile) {
      if (modelElement) modelElement.textContent = `${String(profile?.model?.label || profile?.label || 'ROBOT MODEL').toUpperCase()} · ${state}`;
    },
    onError: options.onError,
  });
  const releaseMapScene = mapState.subscribe((state) => sceneHost.setMapState(state));

  function captureLayout(name) {
    const snapshot = panelManager?.diagnostics();
    return createLayoutDocument({
      name,
      profileId: currentProfileId,
      scene: sceneHost.sceneSnapshot(),
      panels: snapshot?.panels || [],
      viewport: snapshot?.viewport || {},
      allowedPanelTypes,
      panelIdsByType,
    });
  }

  function applyLayout(document) {
    if (!document || document.profile_id !== currentProfileId) return false;
    const viewport = panelManager?.diagnostics().viewport || {};
    const panels = layoutPanelsToPixels(document, viewport);
    panelManager?.restoreValidatedLayout(panels);
    sceneHost.applySceneLayout(document.scene);
    syncLauncher();
    return true;
  }

  function resetLayout() {
    panelManager?.restoreValidatedLayout([]);
    sceneHost.applySceneLayout({ view: 'isometric', follow_robot: false, point_size: 2, range_m: 150 });
    syncLauncher();
  }

  if (options.layoutLibraryRoot && panelRegistry) {
    layoutLibrary = createLayoutLibrary({
      root: options.layoutLibraryRoot,
      document: options.document,
      store: layoutStore,
      captureLayout,
      applyLayout,
      resetLayout,
    });
  }
  syncLayoutMode();

  function pollGamepadUi() {
    if (!active || typeof options.gamepadProvider !== 'function') return;
    const context = options.getControllerSnapshot?.() || {};
    const sample = gamepadUi.sample(options.gamepadProvider(), {
      enabled: layoutMode.snapshot().mode === COCKPIT_LAYOUT_MODES.OPERATE,
      blocked: cockpitGamepadUiBlocked(options.document),
    });
    controllerState.update(projectControllerStatus(sample, context));
    if (sample.deadmanReleased) options.onGamepadUiZeroIntent?.();
    if (sample.disconnected) {
      panelManager?.clearGamepadSelection();
      options.onGamepadDisconnect?.();
    }
    for (const action of sample.actions) dispatchGamepadUiAction(action, sample, {
      hasSelection: () => Boolean(panelManager?.diagnostics().gamepadSelectedPanelId), ensureZero: options.onGamepadUiZeroIntent,
      previousPanel: () => panelManager?.cycleGamepadSelection(-1), nextPanel: () => panelManager?.cycleGamepadSelection(1),
      focus: () => panelManager?.toggleSelectedPanel('focus'), compact: () => panelManager?.toggleSelectedPanel('compact'),
      launcher: () => sensorLauncher?.setExpanded(!sensorLauncher.diagnostics().expanded),
      menu: () => layoutLibrary?.setExpanded(!layoutLibrary.diagnostics().expanded),
    });
  }

  function activate() {
    if (destroyed || active) return diagnostics();
    active = true;
    root.dataset.lifecycle = 'active';
    sceneHost.activate();
    panelManager?.activate();
    safetyHud?.activate();
    gamepadUi.reset();
    pollGamepadUi();
    if (typeof options.gamepadProvider === 'function' && !gamepadTimer) gamepadTimer = (options.setInterval || globalThis.setInterval)(pollGamepadUi, 50);
    return diagnostics();
  }

  function deactivate() {
    if (!active) return diagnostics();
    active = false;
    root.dataset.lifecycle = 'inactive';
    if (gamepadTimer) (options.clearInterval || globalThis.clearInterval)(gamepadTimer);
    gamepadTimer = 0;
    gamepadUi.reset();
    panelManager?.clearGamepadSelection();
    controllerState.update(projectControllerStatus());
    safetyHud?.deactivate();
    panelManager?.deactivate('workspace_inactive');
    sceneHost.deactivate();
    return diagnostics();
  }

  function updatePointcloud(cloud, freshness = 'WAITING', note = '') {
    setFreshness(freshness, note);
    sceneHost.setCloud(freshness === 'LIVE' ? cloud : null, freshness);
  }

  function setProfile(profile) {
    sceneHost.setProfile(profile);
    const profileId = String(profile?.id || 'generic');
    if (profileId === currentProfileId) return;
    currentProfileId = profileId;
    layoutStore.setProfile(profileId);
    layoutLibrary?.setProfile(profileId);
    const storedDefault = layoutStore.getDefault();
    if (storedDefault) applyLayout(storedDefault);
    else resetLayout();
  }

  function setRobotState(state) {
    sceneHost.setRobotState(state);
    mapState.update(options.getMapSnapshot?.() || {});
  }

  function resize() {
    if (active) {
      sceneHost.resize();
      panelManager?.recoverViewport();
    }
  }

  function setPointLimit(value) {
    sceneHost.setPointLimit(value);
  }

  function diagnostics() {
    return Object.freeze({
      active,
      destroyed,
      scene: sceneHost.diagnostics(),
      panels: panelManager?.diagnostics() || null,
      launcher: sensorLauncher?.diagnostics() || null,
      layout: layoutMode.snapshot(),
      safety: safetyHud?.diagnostics() || null,
      layoutLibrary: layoutLibrary?.diagnostics() || layoutStore.snapshot(),
      controller: controllerState.snapshot(),
      map: mapState.diagnostics(),
    });
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    releaseCameraCatalog?.();
    sensorLauncher?.destroy();
    safetyHud?.destroy();
    layoutLibrary?.destroy();
    panelManager?.destroy();
    releaseMapScene();
    sceneHost.destroy();
    destroyed = true;
    root.dataset.lifecycle = 'destroyed';
  }

  setFreshness('WAITING');
  return Object.freeze({
    activate,
    deactivate,
    updatePointcloud,
    pollGamepadUi,
    setProfile,
    setRobotState,
    setPointLimit,
    resize,
    diagnostics,
    destroy,
  });
}

export function initializeCockpitWorkspace(options = {}) {
  const documentValue = options.document || globalThis.document;
  const root = documentValue?.querySelector('#cockpitWorkspace');
  const canvas = documentValue?.querySelector('#cockpitSceneCanvas');
  if (!root || !canvas || typeof options.Renderer !== 'function') return null;
  return createCockpitWorkspace({
    ...options,
    root,
    canvas,
    statusElement: documentValue.querySelector('#cockpitPointcloudStatus'),
    statusNote: documentValue.querySelector('#cockpitPointcloudNote'),
    modelElement: documentValue.querySelector('#cockpitModelState'),
    panelLayer: documentValue.querySelector('#cockpitPanelLayer'),
    snapPreviewElement: documentValue.querySelector('#cockpitSnapPreview'),
    launcherRoot: documentValue.querySelector('#cockpitSensorLauncher'),
    layoutLibraryRoot: documentValue.querySelector('#cockpitLayoutLibrary'),
    safetyHudRoot: documentValue.querySelector('#cockpitSafetyHud'),
    cameraDemand: options.cameraDemand,
    document: documentValue,
    controls: {
      reset: documentValue.querySelector('#cockpitSceneReset'),
      top: documentValue.querySelector('#cockpitSceneTop'),
      front: documentValue.querySelector('#cockpitSceneFront'),
      follow: documentValue.querySelector('#cockpitSceneFollow'),
      axes: documentValue.querySelector('#cockpitSceneAxes'),
      mapOverlay: documentValue.querySelector('#cockpitMapOverlay'),
      quality: documentValue.querySelector('#cockpitPointQuality'),
      adaptive: documentValue.querySelector('#cockpitPointAdaptive'),
      pointSize: documentValue.querySelector('#cockpitPointSize'),
      heightColor: documentValue.querySelector('#cockpitHeightColor'),
      nearField: documentValue.querySelector('#cockpitNearField'),
      metrics: documentValue.querySelector('#cockpitPointMetrics'),
    },
  });
}
