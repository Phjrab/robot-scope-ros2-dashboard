const HEX24 = /^[0-9a-f]{24}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const POINT_TYPES = new Set(['HOME', 'DOCK', 'POI', 'INSPECTION_POINT']);
export const COCKPIT_MAP_LIMITS = Object.freeze({ trail: 240, path: 512, markers: 64 });

function finitePose(value) {
  const x = Number(value?.x); const y = Number(value?.y); const yaw = Number(value?.yaw || 0);
  if (![x, y, yaw].every(Number.isFinite) || Math.abs(x) > 1_000_000 || Math.abs(y) > 1_000_000) return null;
  return Object.freeze({ x, y, z: Number.isFinite(Number(value?.z)) ? Number(value.z) : 0, yaw, frameId: String(value?.frame_id || value?.frameId || '').slice(0, 128) });
}

function boundedAge(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? Math.min(number, 3_600) : null;
}

function validMapGeometry(map) {
  const width = Number(map?.width); const height = Number(map?.height); const resolution = Number(map?.resolution);
  const origin = Array.isArray(map?.origin) ? map.origin.slice(0, 3).map(Number) : [];
  return Number.isInteger(width) && width > 0 && Number.isInteger(height) && height > 0 && width * height <= 16_000_000 &&
    Number.isFinite(resolution) && resolution > 0 && resolution <= 100 && origin.length >= 2 && origin.every(Number.isFinite) &&
    typeof map?.data_b64 === 'string' && map.data_b64.length > 0;
}

function samePose(left, right) {
  return Boolean(left && right && Math.hypot(left.x - right.x, left.y - right.y) < 0.02 && Math.abs(Math.atan2(Math.sin(left.yaw - right.yaw), Math.cos(left.yaw - right.yaw))) < 0.03);
}

function boundedPoses(values, limit) {
  const result = [];
  for (const value of Array.isArray(values) ? values.slice(-limit) : []) {
    const pose = finitePose(value);
    if (pose) result.push(pose);
  }
  return Object.freeze(result);
}

function boundedMarkers(document) {
  const result = [];
  for (const value of Array.isArray(document?.points) ? document.points.slice(0, COCKPIT_MAP_LIMITS.markers) : []) {
    const id = String(value?.id || '');
    const type = String(value?.type || '');
    const pose = finitePose(value?.pose);
    if (!HEX24.test(id) || !POINT_TYPES.has(type) || !pose) continue;
    result.push(Object.freeze({ id, type, name: String(value?.name || type).slice(0, 64), pose }));
  }
  return Object.freeze(result);
}

function initialState() {
  return Object.freeze({
    status: 'WAITING', map: null, conflict: false, conflictReason: '',
    localization: Object.freeze({ state: 'UNAVAILABLE', health: 'UNAVAILABLE', reason: 'NO_MAP', pose: null, lastPose: null, fresh: false, odometryAge: null, tfAge: null }),
    trail: Object.freeze([]), path: Object.freeze([]), markers: Object.freeze([]), selectedAnnotationId: '',
    goal: null, navigationActive: false, robotRadius: 0.22, overlay: null,
  });
}

export function createCockpitMapStore(options = {}) {
  const limits = {
    trail: Math.max(1, Math.min(COCKPIT_MAP_LIMITS.trail, Number(options.maxTrail) || COCKPIT_MAP_LIMITS.trail)),
    path: Math.max(1, Math.min(COCKPIT_MAP_LIMITS.path, Number(options.maxPath) || COCKPIT_MAP_LIMITS.path)),
  };
  const subscribers = new Set();
  let state = initialState();
  let lastInput = null;
  let mapKey = '';
  let trail = [];
  let selectedAnnotationId = '';
  let updates = 0;

  function notify() {
    for (const subscriber of subscribers) subscriber(state);
  }

  function overlayFor(next) {
    if (!next.map || next.conflict) return null;
    const selected = next.markers.find((marker) => marker.id === selectedAnnotationId);
    const home = next.markers.find((marker) => marker.type === 'HOME');
    const overlayMarkers = [...new Map([home, selected].filter(Boolean).map((marker) => [marker.id, marker])).values()];
    return Object.freeze({
      mapId: next.map.id, revision: next.map.revision, frameId: next.map.frameId,
      path: next.path, trail: next.localization.fresh ? next.trail : Object.freeze([]),
      markers: Object.freeze(overlayMarkers), poseFresh: next.localization.fresh,
    });
  }

  function publish(next) {
    state = Object.freeze({ ...next, selectedAnnotationId, overlay: overlayFor(next) });
    updates += 1;
    notify();
    return state;
  }

  function update(input = {}) {
    if (lastInput && lastInput.mapMeta === input.mapMeta && lastInput.map === input.map &&
        lastInput.annotations === input.annotations && lastInput.navigation === input.navigation &&
        lastInput.robotRadius === input.robotRadius) return state;
    lastInput = input;
    const meta = input.mapMeta;
    const map = input.map;
    const navigation = input.navigation || {};
    const id = String(meta?.id || '');
    const revision = String(meta?.revision || '');
    const mapId = String(map?.id || '');
    const mapRevision = String(map?.revision || '');
    const exactMap = HEX24.test(id) && HEX64.test(revision) && id === mapId && revision === mapRevision && validMapGeometry(map);
    const nextMapKey = exactMap ? `${id}:${revision}` : '';
    if (nextMapKey !== mapKey) { mapKey = nextMapKey; trail = []; selectedAnnotationId = ''; }

    const activeMapId = String(navigation.map?.id || '');
    const activeMapRevision = String(navigation.map?.revision || '');
    const navDeclaresMap = Boolean(activeMapId || activeMapRevision);
    const navMapExact = exactMap && activeMapId === id && activeMapRevision === revision;
    const annotations = input.annotations;
    const annotationsExact = !annotations || (
      String(annotations.map_id || '') === id && String(annotations.map_revision || '') === revision
    );
    const conflict = Boolean((meta || map) && !exactMap) || (navDeclaresMap && !navMapExact) || !annotationsExact;
    const conflictReason = !exactMap && (meta || map) ? 'MAP_REVISION_MISMATCH'
      : navDeclaresMap && !navMapExact ? 'NAVIGATION_MAP_REVISION_MISMATCH'
        : !annotationsExact ? 'ANNOTATION_MAP_REVISION_MISMATCH' : '';

    const health = String(navigation.localization_health?.state || 'UNAVAILABLE').toUpperCase();
    const localizationState = String(navigation.localization?.state || 'unavailable').toUpperCase();
    const candidatePose = finitePose(navigation.localization?.pose);
    const frameMatches = !candidatePose?.frameId || !map?.frame_id || candidatePose.frameId === map.frame_id;
    const poseFresh = Boolean(exactMap && !conflict && navMapExact && frameMatches && candidatePose &&
      localizationState === 'LOCALIZED' && health === 'READY' && navigation.readiness?.odometry === true && navigation.readiness?.tf === true);
    if (poseFresh && !samePose(trail.at(-1), candidatePose)) trail.push(candidatePose);
    if (trail.length > limits.trail) trail = trail.slice(-limits.trail);
    const lastPose = trail.at(-1) || null;
    const metrics = navigation.localization_health?.metrics || {};
    const tfAges = [boundedAge(metrics.tf_age_s), boundedAge(metrics.map_to_odom_age_s), boundedAge(metrics.odom_to_base_age_s)].filter((value) => value != null);
    const markers = exactMap && annotationsExact ? boundedMarkers(annotations) : Object.freeze([]);
    if (selectedAnnotationId && !markers.some((marker) => marker.id === selectedAnnotationId)) selectedAnnotationId = '';
    const path = navMapExact && !conflict ? boundedPoses(navigation.path, limits.path) : Object.freeze([]);
    const goal = navMapExact && !conflict ? finitePose(navigation.goal?.pose) : null;
    const pipelineState = String(navigation.pipeline?.state || 'idle').toLowerCase();
    const navigationActive = ['starting', 'running', 'stopping'].includes(pipelineState) || ['pending', 'active', 'canceling'].includes(String(navigation.goal?.state || '').toLowerCase());
    const mapState = exactMap ? Object.freeze({
      id, revision, name: String(meta?.name || map?.name || 'Saved 2D map').slice(0, 96), frameId: String(map.frame_id || 'map').slice(0, 128),
      width: Number(map.width), height: Number(map.height), resolution: Number(map.resolution), origin: Object.freeze(Array.isArray(map.origin) ? map.origin.slice(0, 3).map(Number) : []), dataB64: String(map.data_b64 || ''),
    }) : null;
    const localization = Object.freeze({
      state: localizationState, health, reason: String(navigation.localization_health?.reason_code || (poseFresh ? 'HEALTHY' : 'POSE_NOT_FRESH')).slice(0, 96),
      pose: poseFresh ? candidatePose : null, lastPose, fresh: poseFresh,
      odometryAge: boundedAge(metrics.odometry_age_s ?? navigation.readiness?.odometry_age_s),
      tfAge: tfAges.length ? Math.max(...tfAges) : null,
    });
    return publish({
      status: conflict ? 'CONFLICT' : !mapState ? 'WAITING' : poseFresh ? 'LIVE' : navMapExact ? 'STALE' : 'READY',
      map: mapState, conflict, conflictReason, localization,
      trail: Object.freeze(trail.slice()), path, markers, goal, navigationActive,
      robotRadius: Math.max(0.1, Math.min(1, Number(input.robotRadius) || 0.22)),
    });
  }

  function selectAnnotation(id) {
    const next = String(id || '');
    selectedAnnotationId = state.markers.some((marker) => marker.id === next) ? next : '';
    return publish({ ...state, overlay: undefined });
  }

  function subscribe(callback) {
    if (typeof callback !== 'function') throw new TypeError('Map subscriber callback is required.');
    subscribers.add(callback);
    callback(state);
    return () => subscribers.delete(callback);
  }

  return Object.freeze({
    update, selectAnnotation, subscribe, snapshot: () => state,
    diagnostics: () => Object.freeze({ subscribers: subscribers.size, updates, trailPoints: state.trail.length, pathPoints: state.path.length, markerCount: state.markers.length }),
  });
}
