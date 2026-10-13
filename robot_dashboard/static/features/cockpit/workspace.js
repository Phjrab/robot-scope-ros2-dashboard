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
import { createCockpitNavigationAdapter } from './navigation_adapter.js';
import { createMissionClient } from './mission_client.js';
import { initializeMissionPage } from './mission_page.js';
import { createCompetitionStatus } from './competition_status.js';
import { createRoutePlannerClient } from './route_planner_client.js';
import { missionPresetDocument, MISSION_PRESETS } from './mission_presets.js';
import { createMissionInspector } from './mission_inspector.js';

export { initializeCockpitWindowMode } from './window_mode.js';

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
    return { cloud, freshness: cloud.data_provenance === 'SYNTHETIC_FIXTURE' ? 'FIXTURE' : cloud.data_provenance === 'REPLAY' ? 'REPLAY' : 'LIVE', ageMs };
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
  const missionClient = createMissionClient({ api: options.api || (() => Promise.reject(new Error('Mission API unavailable.'))) });
  const routePlannerClient = createRoutePlannerClient({ api: options.api || (() => Promise.reject(new Error('Route Planner API unavailable.'))) });
  const navigationAdapter = createCockpitNavigationAdapter({ getSnapshot: () => ({ ...options.getNavigationSnapshot?.(), controller: controllerState.snapshot(), navigationEngine: options.navigationEngine, mission: missionClient.snapshot() }), actions: { ...options.navigationActions, abortMission: () => missionClient.abortActive() } });
  const panelRegistry = options.panelLayer ? createPanelRegistry({ document: options.document, cameraDemand: options.cameraDemand, perception: options.perception, controllerState, mapState, navigationAdapter, navigationEngine: options.navigationEngine, missionClient, routePlannerClient, getMissionContext: options.getNavigationSnapshot }) : null;
  const missionPage = initializeMissionPage({ client: missionClient, navigationAdapter, getContext: options.getNavigationSnapshot, document: options.document });
  let panelManager = null;
  let sensorLauncher = null;
  let safetyHud = null;
  let layoutLibrary = null;
  let competitionStatus = null;
  let releaseCameraCatalog = null;
  let currentProfileId = '';
  let gamepadTimer = 0;
  let releaseRouteScene = null;
  const inspector = createMissionInspector(options.inspectorRoot);
  const presetSelect = options.presetRoot?.querySelector('select');
  const presetStatus = options.presetRoot?.querySelector('[role="status"]');
  let currentPreset = 'observation';
  const listeners = new AbortController();
  if (presetSelect) {
    const saved = options.document.createElement('option');
    saved.value = 'saved';
    saved.textContent = 'Saved layout';
    saved.disabled = true;
    presetSelect.append(saved);
    for (const preset of MISSION_PRESETS) {
      const item = options.document.createElement('option');
      item.value = preset.id;
      item.textContent = preset.label;
      presetSelect.append(item);
    }
    presetSelect.addEventListener('change', () => {
      if (!applyMissionPreset(presetSelect.value)) presetSelect.value = currentPreset;
    }, { signal: listeners.signal });
  }

  function syncLayoutMode(state = layoutMode.snapshot()) {
    const editable = state.mode === COCKPIT_LAYOUT_MODES.EDIT && !state.armed;
    root.dataset.layoutMode = state.mode;
    panelManager?.setLayoutEditable(editable);
    sensorLauncher?.setLayoutEditable(editable);
    if (editable && options.presetRoot) sensorLauncher?.setExpanded(true);
    layoutLibrary?.setLayoutEditable(editable);
    safetyHud?.setLayoutState(state);
    if (presetSelect) presetSelect.disabled = !editable;
    if (presetStatus) presetStatus.textContent = editable ? '배치 선택 후 APPLY / EXIT로 저장' : state.armed ? '제어 사용 중 · 배치 잠금' : 'Safety 상세 → EDIT LAYOUT에서 배치 선택';
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
    viewportProvider: options.presetRoot ? () => {
      const rect = options.panelLayer.getBoundingClientRect();
      return { width: Math.max(1, rect.width), height: Math.max(1, rect.height), padding: 12, reservedBottom: 12 };
    } : undefined,
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
    if (options.presetRoot) sensorLauncher.setExpanded(false);
    releaseCameraCatalog = options.cameraDemand?.subscribe((catalog) => sensorLauncher?.updateAvailability(catalog.sources));
  }

  if (options.safetyHudRoot) {
    safetyHud = createSafetyHud({
      root: options.safetyHudRoot,
      document: options.document,
      getSnapshot: () => ({
        ...options.getSafetySnapshot?.(),
        competition: competitionStatus?.snapshot().projected || null,
        dataset: options.getDatasetSnapshot?.() || null,
      }),
      layoutState: layoutMode.snapshot(),
      onRequestEdit: () => { safetyHud?.setLayoutSaveStatus(''); layoutMode.requestEdit(); },
      onApply: () => {
        if (layoutMode.snapshot().mode !== COCKPIT_LAYOUT_MODES.EDIT || layoutMode.snapshot().armed) return;
        try {
          layoutStore.saveApplied(captureLayout('Last applied'));
          layoutMode.apply();
          safetyHud?.setLayoutSaveStatus('배치 저장 완료 · 이 브라우저에서 다시 열 때 복원됩니다.');
        } catch (error) {
          safetyHud?.setLayoutSaveStatus('배치 저장 실패 · 브라우저 저장 공간/권한을 확인한 뒤 다시 Apply해 주세요.');
          options.onError?.(new Error(`레이아웃 저장 실패: ${error.message} · 편집 상태를 유지합니다.`));
        }
      },
      onStop: options.onSoftwareStop,
      onProjection: (projected, input) => {
        layoutMode.updateControl({ armed: projected.layoutArmed, generation: Number(input.controlGeneration) || 0 });
        inspector?.render({ ...input, map: mapState.snapshot(), navigation: options.getNavigationSnapshot?.(),
          mission: missionClient.snapshot(), dataset: options.getDatasetSnapshot?.(), cameras: options.cameraDemand?.snapshot?.(),
          freshness: root.dataset.freshness?.toUpperCase() });
      },
    });
  }
  if (options.competitionStatusRoot) {
    competitionStatus = createCompetitionStatus({
      root: options.competitionStatusRoot,
      document: options.document,
      api: options.api,
      cameraDemand: options.cameraDemand,
      perception: options.perception,
      getDatasetSnapshot: options.getDatasetSnapshot,
      onError: options.onError,
    });
  }
  syncLayoutMode();

  // Keep the persistent summary/STOP visible; expanded details belong to the
  // previous task and must not cover the next route's inspector controls.
  options.document?.addEventListener('robot-scope:page-change', () => safetyHud?.setExpanded(false), { signal: listeners.signal });

  function setFreshness(freshness, note = '') {
    const state = ['LIVE', 'STALE', 'FIXTURE', 'REPLAY', 'NOT_CONNECTED'].includes(freshness) ? freshness : 'WAITING';
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

  function applyLayout(document, { restoreScene = true } = {}) {
    if (!document || document.profile_id !== currentProfileId) return false;
    const viewport = panelManager?.diagnostics().viewport || {};
    const panels = layoutPanelsToPixels(document, viewport);
    panelManager?.restoreValidatedLayout(panels);
    if (restoreScene) sceneHost.applySceneLayout(document.scene);
    currentPreset = 'saved';
    root.dataset.missionPreset = 'saved';
    if (presetSelect) presetSelect.value = 'saved';
    syncLauncher();
    return true;
  }

  function resetLayout() {
    panelManager?.restoreValidatedLayout([]);
    // Reset floating panels without discarding the operator's map viewpoint.
    syncLauncher();
  }

  function applyMissionPreset(id, initial = false) {
    const mode = layoutMode.snapshot();
    if (!initial && (mode.mode !== COCKPIT_LAYOUT_MODES.EDIT || mode.armed)) return false;
    if (!panelRegistry || !currentProfileId) return false;
    const document = missionPresetDocument(id, currentProfileId, panelRegistry, panelManager.diagnostics().viewport);
    if (!applyLayout(document, { restoreScene: false })) return false;
    currentPreset = id;
    root.dataset.missionPreset = id;
    if (presetSelect) presetSelect.value = id;
    resize();
    return true;
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
    if (!releaseRouteScene) releaseRouteScene = routePlannerClient.subscribe((state) => sceneHost.setRouteState(state));
    panelManager?.activate();
    safetyHud?.activate();
    competitionStatus?.activate();
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
    if (!options.persistentSafety) safetyHud?.deactivate();
    competitionStatus?.deactivate();
    releaseRouteScene?.();
    releaseRouteScene = null;
    sceneHost.setRouteState(null);
    panelManager?.deactivate('workspace_inactive');
    sceneHost.deactivate();
    return diagnostics();
  }

  function updatePointcloud(cloud, freshness = 'WAITING', note = '') {
    setFreshness(freshness, note);
    sceneHost.setCloud(['LIVE', 'FIXTURE', 'REPLAY'].includes(freshness) ? cloud : null, freshness);
  }

  function setProfile(profile) {
    sceneHost.setProfile(profile);
    const profileId = String(profile?.id || 'generic');
    if (profileId === currentProfileId) return;
    currentProfileId = profileId;
    layoutStore.setProfile(profileId);
    layoutLibrary?.setProfile(profileId);
    const applied = layoutStore.getApplied();
    const storedDefault = layoutStore.getDefault();
    // The camera has its own exact persistence; panel restoration must not reset it.
    if (applied) applyLayout(applied, { restoreScene: false });
    else if (storedDefault) applyLayout(storedDefault);
    else if (options.presetRoot) applyMissionPreset('observation', true);
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
      competition: competitionStatus?.snapshot() || null,
      layoutLibrary: layoutLibrary?.diagnostics() || layoutStore.snapshot(),
      controller: controllerState.snapshot(),
      map: mapState.diagnostics(),
      navigation: navigationAdapter.diagnostics(),
      mission: missionClient.diagnostics(),
      routePlanner: routePlannerClient.diagnostics(),
    });
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    releaseCameraCatalog?.();
    sensorLauncher?.destroy();
    safetyHud?.destroy();
    competitionStatus?.destroy();
    layoutLibrary?.destroy();
    panelManager?.destroy();
    releaseMapScene();
    navigationAdapter.destroy();
    missionPage?.destroy();
    missionClient.destroy();
    routePlannerClient.destroy();
    sceneHost.destroy();
    destroyed = true;
    root.dataset.lifecycle = 'destroyed';
    listeners.abort();
  }

  setFreshness('WAITING');
  if (options.persistentSafety) safetyHud?.activate();
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
    panelLayer: documentValue.querySelector('#cockpitPanelLayer'),
    snapPreviewElement: documentValue.querySelector('#cockpitSnapPreview'),
    launcherRoot: documentValue.querySelector('#cockpitSensorLauncher'),
    layoutLibraryRoot: documentValue.querySelector('#cockpitLayoutLibrary'),
    safetyHudRoot: documentValue.querySelector('#cockpitSafetyHud'),
    competitionStatusRoot: documentValue.querySelector('#cockpitCompetitionStatus'),
    inspectorRoot: documentValue.querySelector('#missionInspector'),
    presetRoot: documentValue.querySelector('#missionPresetBar'),
    persistentSafety: true,
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
