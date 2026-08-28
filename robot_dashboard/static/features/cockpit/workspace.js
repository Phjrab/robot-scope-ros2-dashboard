import { createCockpitSceneHost } from './scene_host.js';
import { createPanelManager } from './panel_manager.js';
import { createPanelRegistry } from './panel_registry.js';
import { createSensorLauncher } from './sensor_launcher.js';

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
  const panelRegistry = options.panelLayer ? createPanelRegistry({ document: options.document }) : null;
  let panelManager = null;
  let sensorLauncher = null;

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
  }) : null;

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
  }

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
    onModelState(state, profile) {
      if (modelElement) modelElement.textContent = `${String(profile?.model?.label || profile?.label || 'ROBOT MODEL').toUpperCase()} · ${state}`;
    },
    onError: options.onError,
  });

  function activate() {
    if (destroyed || active) return diagnostics();
    active = true;
    root.dataset.lifecycle = 'active';
    sceneHost.activate();
    panelManager?.activate();
    return diagnostics();
  }

  function deactivate() {
    if (!active) return diagnostics();
    active = false;
    root.dataset.lifecycle = 'inactive';
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
  }

  function setRobotState(state) {
    sceneHost.setRobotState(state);
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
    });
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    sensorLauncher?.destroy();
    panelManager?.destroy();
    sceneHost.destroy();
    destroyed = true;
    root.dataset.lifecycle = 'destroyed';
  }

  setFreshness('WAITING');
  return Object.freeze({
    activate,
    deactivate,
    updatePointcloud,
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
    document: documentValue,
    controls: {
      reset: documentValue.querySelector('#cockpitSceneReset'),
      top: documentValue.querySelector('#cockpitSceneTop'),
      front: documentValue.querySelector('#cockpitSceneFront'),
      follow: documentValue.querySelector('#cockpitSceneFollow'),
      axes: documentValue.querySelector('#cockpitSceneAxes'),
    },
  });
}
