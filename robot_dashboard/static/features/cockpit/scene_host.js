import { COCKPIT_MAX_POINTS, COCKPIT_POINT_BUDGETS, createAdaptivePointBudgetController, createSpatialPointLod } from './point_quality.js';

function rendererStatus(profile, freshness, online) {
  const label = String(profile?.label || 'ROBOT').toUpperCase();
  if (freshness === 'LIVE') {
    return { online, lidarOnline: true, snapshot: false, message: `${label} · LIVE LIDAR` };
  }
  if (freshness === 'STALE') {
    return { online, lidarOnline: false, snapshot: false, message: `${label} · LIDAR STALE` };
  }
  return { online, lidarOnline: false, snapshot: false, message: `${label} · LIDAR WAITING` };
}

export function createCockpitSceneHost(options = {}) {
  const canvas = options.canvas;
  const Renderer = options.Renderer;
  if (!canvas) throw new TypeError('Cockpit SceneHost requires a canvas.');
  if (typeof Renderer !== 'function') throw new TypeError('Cockpit SceneHost requires RobotScene3D.');

  let renderer = null;
  let active = false;
  let destroyed = false;
  let session = 0;
  let modelGeneration = 0;
  let starts = 0;
  let stops = 0;
  let peakRenderers = 0;
  let profile = null;
  let cloud = null;
  let pose = null;
  let trail = [];
  let joints = null;
  let freshness = 'WAITING';
  let robotOnline = null;
  let modelState = 'WAITING';
  let pointLimit = options.maxPoints ?? COCKPIT_MAX_POINTS;
  let qualityMode = 'low';
  let adaptive = false;
  let nearField = true;
  let heightColor = true;
  let projectedCloud = null;
  let projectedSource = null;
  let projectedBudget = 0;
  let projectedNearField = true;
  const pointLod = createSpatialPointLod({ maxPoints: COCKPIT_MAX_POINTS });
  const adaptiveBudget = createAdaptivePointBudgetController({ initialLevel: 'low', ceiling: qualityMode });
  const controlDisposers = [];
  let requestedServerBudget = null;
  let budgetRequestActive = false;
  let sceneLayout = Object.freeze({ view: 'isometric', follow_robot: false, point_size: 2, range_m: 150 });

  const clock = () => options.now?.() ?? globalThis.performance?.now?.() ?? Date.now();
  const serverCap = () => pointLimit == null ? COCKPIT_MAX_POINTS : Math.min(COCKPIT_MAX_POINTS, Math.max(1_000, Number(pointLimit) || 1_000));
  const qualityBudget = () => Math.min(serverCap(), adaptive ? adaptiveBudget.snapshot().budget : COCKPIT_POINT_BUDGETS[qualityMode]);

  function qualityMetrics(stale = false) {
    const rendering = renderer?.performanceSnapshot?.() || {};
    const transport = cloud?.transport_metrics || {};
    return {
      frameMs: Number(rendering.frameMs) || 0,
      fps: Number(rendering.fps) || 0,
      uploadMs: Number(rendering.uploadMs) || 0,
      decodeMs: Number(transport.decode_ms) || 0,
      droppedFrames: Number(transport.dropped_frames) || 0,
      stale,
    };
  }

  function syncQualityControls() {
    const controls = options.controls || {};
    if (controls.quality) controls.quality.value = qualityMode;
    if (controls.adaptive) {
      controls.adaptive.setAttribute('aria-pressed', adaptive ? 'true' : 'false');
      controls.adaptive.textContent = adaptive ? 'AUTO ON' : 'AUTO';
    }
    if (controls.heightColor) controls.heightColor.setAttribute('aria-pressed', heightColor ? 'true' : 'false');
    if (controls.nearField) controls.nearField.setAttribute('aria-pressed', nearField ? 'true' : 'false');
    if (controls.pointSize) controls.pointSize.value = String(sceneLayout.point_size);
    if (controls.metrics) {
      const metric = qualityMetrics();
      const mode = adaptive ? `AUTO:${adaptiveBudget.snapshot().level.toUpperCase()}` : qualityMode.toUpperCase();
      controls.metrics.textContent = `${mode} · ${(qualityBudget() / 1000).toFixed(0)}K · ${metric.fps ? metric.fps.toFixed(0) : '—'} FPS`;
    }
  }

  function invalidateProjection() {
    projectedCloud = null;
    projectedSource = null;
  }

  async function requestServerBudget(budget) {
    requestedServerBudget = budget;
    if (budgetRequestActive || typeof options.onPointBudgetRequest !== 'function') return;
    budgetRequestActive = true;
    try {
      while (requestedServerBudget != null) {
        const requested = requestedServerBudget;
        requestedServerBudget = null;
        await options.onPointBudgetRequest(requested);
      }
    } catch (error) {
      options.onError?.(error);
    } finally {
      budgetRequestActive = false;
    }
  }

  function displayCloud() {
    const budget = qualityBudget();
    if (projectedSource !== cloud || projectedBudget !== budget || projectedNearField !== nearField) {
      projectedCloud = pointLod.project(cloud, budget, nearField);
      projectedSource = cloud;
      projectedBudget = budget;
      projectedNearField = nearField;
    }
    return projectedCloud;
  }

  function sceneSnapshot() {
    const cameraMode = renderer?.cameraMode;
    const camera = renderer?.camera;
    let view = sceneLayout.view;
    if (cameraMode === 'follow') view = 'robot-follow';
    else if (camera) {
      const near = (left, right) => Math.abs(Number(left) - right) < 0.02;
      view = near(camera.pitch, 88 * Math.PI / 180) ? 'top'
        : near(camera.pitch, 8 * Math.PI / 180) && near(camera.yaw, 0) ? 'front'
          : near(camera.pitch, 33 * Math.PI / 180) && near(camera.yaw, 45 * Math.PI / 180) ? 'isometric' : 'custom';
    }
    return Object.freeze({
      view,
      follow_robot: cameraMode == null ? sceneLayout.follow_robot : cameraMode === 'follow',
      point_size: Number(renderer?.options?.pointSize) * 40 || sceneLayout.point_size,
      range_m: Number(renderer?.options?.maxCloudRadius) || sceneLayout.range_m,
    });
  }

  function diagnostics() {
    const camera = renderer?.camera ? Object.freeze({
      target: Object.freeze(renderer.camera.target.slice()),
      distance: renderer.camera.distance,
      yaw: renderer.camera.yaw,
      pitch: renderer.camera.pitch,
    }) : null;
    return Object.freeze({
      active,
      destroyed,
      session,
      starts,
      stops,
      rendererCount: renderer ? 1 : 0,
      peakRenderers,
      freshness,
      modelState,
      camera,
      layout: sceneSnapshot(),
      quality: Object.freeze({ mode: qualityMode, adaptive, nearField, heightColor, effectiveBudget: qualityBudget(), adaptiveLevel: adaptiveBudget.snapshot().level, lod: pointLod.diagnostics(), metrics: Object.freeze(qualityMetrics()) }),
    });
  }

  function applySceneLayout(next = {}) {
    sceneLayout = Object.freeze({
      view: String(next.view || 'isometric'),
      follow_robot: Boolean(next.follow_robot),
      point_size: Number(next.point_size) || 2,
      range_m: Number(next.range_m) || 150,
    });
    if (!active || !renderer) return sceneSnapshot();
    if (sceneLayout.view === 'top' || sceneLayout.view === 'front') renderer.setViewPreset?.(sceneLayout.view);
    else if (sceneLayout.view !== 'custom') renderer.setViewPreset?.('isometric');
    renderer.setCameraMode?.(sceneLayout.follow_robot || sceneLayout.view === 'robot-follow' ? 'follow' : 'world');
    if (renderer.options) {
      renderer.options.pointSize = sceneLayout.point_size / 40;
      renderer.options.maxCloudRadius = sceneLayout.range_m;
    }
    renderState();
    return sceneSnapshot();
  }

  function renderState() {
    if (!active || !renderer) return;
    if (freshness === 'LIVE' && cloud?.points?.length) renderer.setPointCloud(displayCloud());
    else renderer.clearPointCloud();
    renderer.setRobotPose(pose);
    renderer.setTrail(trail);
    if (joints) renderer.setRobotJointPositions?.(joints);
    else renderer.resetRobotJointPositions?.();
    renderer.setStatus(rendererStatus(profile, freshness, robotOnline));
    syncQualityControls();
  }

  async function loadModel(expectedSession) {
    if (!renderer || !active || expectedSession !== session) return;
    const expectedModelGeneration = ++modelGeneration;
    const target = renderer;
    const assetUrl = String(profile?.model?.asset_url || '').trim();
    target._robotModelLabel = profile?.label || 'Robot';
    target._robotModelType = profile?.id || 'generic';
    target.configureOfficialRobot?.({
      enabled: Boolean(assetUrl),
      assetUrl,
      poseOrigin: 'base',
      adaptiveScale: false,
      scale: 1,
    });
    modelState = assetUrl ? 'LOADING' : 'FALLBACK';
    options.onModelState?.(modelState, profile);
    if (!assetUrl || typeof target.loadOfficialRobotModel !== 'function') {
      options.onModelState?.(modelState, profile);
      return;
    }
    try {
      await target.loadOfficialRobotModel(assetUrl);
      if (!active || renderer !== target || expectedSession !== session || expectedModelGeneration !== modelGeneration) return;
      modelState = 'READY';
      options.onModelState?.(modelState, profile);
      renderState();
    } catch (error) {
      if (!active || renderer !== target || expectedSession !== session || expectedModelGeneration !== modelGeneration) return;
      modelState = 'FALLBACK';
      options.onModelState?.(modelState, profile);
      options.onError?.(error);
      renderState();
    }
  }

  function activate() {
    if (destroyed || active) return diagnostics();
    active = true;
    session += 1;
    starts += 1;
    renderer = new Renderer(canvas, {
      maxPoints: serverCap(),
      maxCloudRadius: sceneLayout.range_m,
      pointSize: sceneLayout.point_size / 40,
      autoFitOnFirstCloud: true,
      axesStorageKey: 'robot-scope.cockpit.axes.v1',
    });
    peakRenderers = Math.max(peakRenderers, renderer ? 1 : 0);
    renderer.bindControls?.(options.controls || {});
    renderer.setHeightColor?.(heightColor);
    renderer.setNearFieldEmphasis?.(nearField);
    applySceneLayout(sceneLayout);
    renderState();
    void loadModel(session);
    renderer.resize?.();
    return diagnostics();
  }

  function deactivate() {
    if (!active) return diagnostics();
    active = false;
    session += 1;
    stops += 1;
    const previous = renderer;
    renderer = null;
    previous?.destroy?.();
    return diagnostics();
  }

  function setProfile(nextProfile) {
    const previousAsset = profile?.model?.asset_url;
    const previousId = profile?.id;
    profile = nextProfile || null;
    if (active && (previousAsset !== profile?.model?.asset_url || previousId !== profile?.id)) {
      void loadModel(session);
    }
  }

  function setCloud(nextCloud, nextFreshness = 'WAITING') {
    const normalizedCloud = nextCloud?.points?.length ? nextCloud : null;
    const normalizedFreshness = ['LIVE', 'STALE'].includes(nextFreshness) ? nextFreshness : 'WAITING';
    if (cloud === normalizedCloud && freshness === normalizedFreshness) return;
    cloud = normalizedCloud;
    freshness = normalizedFreshness;
    invalidateProjection();
    if (adaptive) adaptiveBudget.sample(qualityMetrics(freshness === 'STALE'), clock());
    if (active) renderState();
  }

  function setRobotState(state = {}) {
    pose = state.pose || null;
    trail = Array.isArray(state.trail) ? state.trail : [];
    joints = state.joints || null;
    robotOnline = state.online == null ? null : Boolean(state.online);
    if (active && renderer) {
      renderer.setRobotPose(pose);
      renderer.setTrail(trail);
      if (joints) renderer.setRobotJointPositions?.(joints);
      else renderer.resetRobotJointPositions?.();
      renderer.setStatus(rendererStatus(profile, freshness, robotOnline));
    }
  }

  function resize() {
    if (active) renderer?.resize?.();
  }

  function setPointLimit(value) {
    pointLimit = value;
    invalidateProjection();
    if (active) {
      renderer?.setPointLimit?.(serverCap());
      renderState();
    }
  }

  function bindQualityControl(element, eventName, callback) {
    if (!element?.addEventListener) return;
    element.addEventListener(eventName, callback);
    controlDisposers.push(() => element.removeEventListener?.(eventName, callback));
  }

  bindQualityControl(options.controls?.quality, 'change', () => {
    const next = String(options.controls.quality.value || 'low');
    if (!Object.hasOwn(COCKPIT_POINT_BUDGETS, next)) return;
    qualityMode = next;
    adaptiveBudget.setCeiling(next, clock(), adaptive);
    invalidateProjection();
    void requestServerBudget(COCKPIT_POINT_BUDGETS[next]);
    if (active) renderState(); else syncQualityControls();
  });
  bindQualityControl(options.controls?.adaptive, 'click', () => {
    adaptive = !adaptive;
    adaptiveBudget.setCeiling(qualityMode, clock(), adaptive);
    invalidateProjection();
    if (active) renderState(); else syncQualityControls();
  });
  bindQualityControl(options.controls?.pointSize, 'input', () => {
    sceneLayout = Object.freeze({ ...sceneLayout, point_size: Math.max(0.5, Math.min(4, Number(options.controls.pointSize.value) || 2)) });
    if (renderer?.options) renderer.options.pointSize = sceneLayout.point_size / 40;
    renderer?.render?.();
    syncQualityControls();
  });
  bindQualityControl(options.controls?.heightColor, 'click', () => {
    heightColor = !heightColor;
    renderer?.setHeightColor?.(heightColor);
    syncQualityControls();
  });
  bindQualityControl(options.controls?.nearField, 'click', () => {
    nearField = !nearField;
    invalidateProjection();
    renderer?.setNearFieldEmphasis?.(nearField);
    if (active) renderState(); else syncQualityControls();
  });

  function destroy() {
    if (destroyed) return;
    deactivate();
    destroyed = true;
    cloud = null;
    pose = null;
    trail = [];
    joints = null;
    controlDisposers.splice(0).forEach((dispose) => dispose());
  }

  return Object.freeze({
    activate,
    deactivate,
    setProfile,
    setCloud,
    setRobotState,
    setPointLimit,
    applySceneLayout,
    sceneSnapshot,
    resize,
    destroy,
    diagnostics,
  });
}
