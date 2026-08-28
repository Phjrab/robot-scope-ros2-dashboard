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
  let pointLimit = options.maxPoints ?? 10000;

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
    });
  }

  function renderState() {
    if (!active || !renderer) return;
    if (freshness === 'LIVE' && cloud?.points?.length) renderer.setPointCloud(cloud);
    else renderer.clearPointCloud();
    renderer.setRobotPose(pose);
    renderer.setTrail(trail);
    if (joints) renderer.setRobotJointPositions?.(joints);
    else renderer.resetRobotJointPositions?.();
    renderer.setStatus(rendererStatus(profile, freshness, robotOnline));
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
      maxPoints: pointLimit,
      maxCloudRadius: options.maxCloudRadius ?? 150,
      pointSize: options.pointSize ?? 0.05,
      autoFitOnFirstCloud: true,
      axesStorageKey: 'robot-scope.cockpit.axes.v1',
    });
    peakRenderers = Math.max(peakRenderers, renderer ? 1 : 0);
    renderer.bindControls?.(options.controls || {});
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
    if (active) renderer?.setPointLimit?.(value);
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    destroyed = true;
    cloud = null;
    pose = null;
    trail = [];
    joints = null;
  }

  return Object.freeze({
    activate,
    deactivate,
    setProfile,
    setCloud,
    setRobotState,
    setPointLimit,
    resize,
    destroy,
    diagnostics,
  });
}
