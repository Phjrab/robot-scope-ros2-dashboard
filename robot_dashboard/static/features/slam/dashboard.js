/* Additive SLAM console. All camera/engine ownership remains on the server. */
const MAX_WIRE_BYTES = 8 * 1024 * 1024;
const MAX_MAP_POINTS = 60_000;
const MAX_OBSERVATIONS = 4096;
const LABELS = { lidar_fastlio: 'LiDAR · FAST-LIO', visual_stereo: 'Stereo VSLAM · Isaac', visual_inertial: 'VIO · IMU 미검증' };
const RESOURCE_LABELS = { navigation: '내비게이션', mission: '미션', mission_route: '경로·미션',
  dataset_capture: '데이터 수집', control: '제어', lidar: 'LiDAR', lifecycle: '서비스 수명주기',
  camera: '카메라', ros_domain: 'ROS domain', broker: '실행 broker', session: 'SLAM 세션' };
const ACTIVE_PAGES = new Set(['mapping', 'maps']);
const controllers = new WeakMap();
export const SLAM_STREAM_PATH = '/api/v1/ws/slam';
export const SLAM_REQUEST_TIMEOUT_MS = 15_000;

// Cache at most two complete layers per connection. References never cross a
// session/map/frame boundary. Invalid references hide only their own channel.
export function geometryFrameHydrator() {
  let context = null;
  const layers = new Map();
  return {
    clear() { context = null; layers.clear(); },
    hydrate(frame) {
      const nextContext = JSON.stringify([frame.engine_id, frame.session_id, frame.generation, frame.map_epoch, frame.frame_id]);
      if (nextContext !== context) { layers.clear(); context = nextContext; }
      const protocol = frame.geometry_updates;
      if (protocol == null) { layers.clear(); return frame; }
      const result = { ...frame };
      for (const [name, limit] of [['global_map', MAX_MAP_POINTS], ['trajectory', 10_001]]) {
        const update = protocol.version === 1 ? protocol.layers?.[name] : null;
        const tokenValid = typeof update?.token === 'string' && /^\d{1,20}$/.test(update.token);
        const layer = frame[name];
        if (tokenValid && update.kind === 'full' && layer?.map_epoch === frame.map_epoch &&
            layer.coordinate_frame === frame.frame_id && Array.isArray(layer.points) &&
            layer.points.length <= limit && layer.points.every((point) => Array.isArray(point) &&
              point.length === 3 && point.every(Number.isFinite))) {
          layers.set(name, { token: update.token, layer });
        } else if (tokenValid && update.kind === 'reference' && layer == null && layers.get(name)?.token === update.token) {
          result[name] = layers.get(name).layer;
        } else {
          layers.delete(name); result[name] = null;
        }
      }
      return result;
    },
  };
}

// Keep one render opportunity and replace its payload, never queue old frames.
export function latestFrameRenderer(request, cancel, render) {
  let scheduled = null, latest = null;
  return {
    submit(frame) {
      latest = frame;
      if (scheduled != null) return;
      scheduled = request(() => {
        scheduled = null;
        const frame = latest; latest = null;
        if (frame) render(frame);
      });
    },
    clear() {
      if (scheduled != null) cancel(scheduled);
      scheduled = null; latest = null;
    },
  };
}

export function sameImageSource(left, right) {
  if (!sameSessionContext(left, right)) return false;
  const a = left?.image, b = right?.image;
  return Boolean(a && b && ['stamp_ns', 'frame_id', 'camera_id', 'width', 'height', 'rectified',
    'jpeg_base64', 'png_base64'].every((key) => a[key] === b[key]));
}

// One decoder, one latest pending frame and one decoded image. A new pose or
// overlay for the exact same input image can reuse that image without decoding.
export function latestImageDecoder(createImage, isCurrent, draw, failed) {
  let active = null, latest = null, cached = null, serial = 0;
  const identity = (frame) => ({ session_id: frame.session_id, generation: frame.generation,
    engine_id: frame.engine_id, map_epoch: frame.map_epoch, image: frame.image });
  function pump() {
    if (active || !latest) return;
    const frame = latest; latest = null;
    if (!isCurrent(frame)) return;
    if (cached && sameImageSource(cached.source, frame)) { draw(cached.image, frame); return; }
    const image = createImage(), ticket = serial;
    active = { image, frame };
    const finish = (error = null) => {
      if (ticket !== serial || active?.image !== image) return;
      image.onload = null; image.onerror = null;
      active = null;
      const target = latest && sameImageSource(frame, latest) ? latest : frame;
      if (target === latest) latest = null;
      if (!error && (image.naturalWidth !== frame.image.width || image.naturalHeight !== frame.image.height)) error = 'IMAGE_DIMENSION_MISMATCH';
      if (!error) cached = { source: identity(frame), image };
      if (isCurrent(target)) {
        if (error) failed(error, target);
        else draw(image, target);
      }
      pump();
    };
    image.onload = () => finish();
    image.onerror = () => finish('IMAGE_DECODE_UNAVAILABLE');
    image.src = `data:image/${frame.image.jpeg_base64 ? 'jpeg' : 'png'};base64,${frame.image.jpeg_base64 || frame.image.png_base64}`;
  }
  return {
    submit(frame) { latest = frame; pump(); },
    clear() {
      serial += 1; latest = null; cached = null;
      if (active) { active.image.onload = null; active.image.onerror = null; active.image.src = ''; }
      active = null;
    },
  };
}

export function samePointGeometry(left, right) {
  return Array.isArray(left) && Array.isArray(right) && (left === right || left.length === right.length &&
    left.every((point, index) => Array.isArray(point) && Array.isArray(right[index]) &&
      point.length === right[index].length && point.every((value, axis) => value === right[index][axis])));
}

export function sameSessionContext(left, right) {
  return Boolean(left?.session_id && right?.session_id && left.session_id === right.session_id &&
    left.generation != null && left.generation === right.generation && left.map_epoch === right.map_epoch &&
    left.engine_id && left.engine_id === right.engine_id);
}

// A Stop acknowledgement is not a cleanup result. Keep that receipt until the
// same session is read back as IDLE or reports a real cleanup failure.
export function reconcileStopProgress(request, session) {
  if (!sameSessionContext(request?.session, session)) return null;
  let phase = request.phase;
  // The server retains the previous reason while retrying cleanup, and even
  // after successful IDLE. Current lifecycle state and the explicit flag win.
  if (session.state === 'STOPPING') phase = 'stopping';
  else if (session.state === 'IDLE' && session.cleanup_required !== true) phase = 'idle';
  else if (session.cleanup_required === true || session.reason === 'CLEANUP_REQUIRED') phase = 'cleanup_failed';
  return { ...request, phase, reason: phase === 'cleanup_failed' ? session.reason || 'CLEANUP_REQUIRED' : null,
    readbackError: null };
}

export function sessionSnapshotIsValid(value) {
  if (!value || !Number.isSafeInteger(value.generation) || value.generation < 0 ||
      !Object.hasOwn(value, 'active_session')) return false;
  const next = value.active_session;
  if (next === null) return true;
  return Boolean(next && ['session_id', 'engine_id', 'map_epoch'].every((key) =>
    typeof next[key] === 'string' && next[key].length > 0) && next.generation === value.generation &&
    ['PREFLIGHT', 'STARTING', 'WAITING_INPUT', 'TRACKING', 'MAPPING', 'CAPTURING', 'LOST',
      'SAVING', 'LOCALIZING', 'STOPPING', 'ERROR', 'IDLE'].includes(next.state) &&
    (next.cleanup_required == null || typeof next.cleanup_required === 'boolean'));
}

export function sessionReadbackIsCurrent(value, session, generation, stopRequest = null) {
  if (!sessionSnapshotIsValid(value)) return false;
  if (Number.isInteger(value.generation) && Number.isInteger(generation) && value.generation < generation) return false;
  const next = value.active_session;
  if (next && next.generation !== value.generation) return false;
  // A finished generation cannot resume mapping. A new session needs its own
  // identity; a delayed snapshot cannot revive the stopped generation.
  if (sameSessionContext(session, next) && (session?.state === 'IDLE' ||
      (sameSessionContext(stopRequest?.session, session) && stopRequest.phase === 'idle')) && next.state !== 'IDLE') return false;
  return true;
}

export function describeStopProgress(request, session) {
  if (!sameSessionContext(request?.session, session)) return null;
  const phases = {
    requesting: ['STOP_REQUESTING', '중지 요청 전송 중 · 서버 수락 확인 전'],
    unconfirmed: ['STOP_UNCONFIRMED', '중지 응답 미확인 · 종료 여부 미확인 · 상태 새로고침으로 확인하세요. 중지 요청은 자동 반복하지 않습니다.'],
    accepted: ['STOP_ACCEPTED', '중지 요청 수락 · 실제 자원 정리 완료는 아직 미확인'],
    stopping: ['STOPPING', '서버 정리 중 · 실제 IDLE 확인 대기'],
    idle: ['IDLE', '서버 IDLE 확인 · 세션 정리 완료'],
    cleanup_failed: ['ERROR', `서버 정리 실패 · ${request.reason || 'CLEANUP_REQUIRED'} · 자원 해제 미확인`],
  };
  const value = phases[request.phase];
  if (!value) return null;
  return { status: value[0], message: value[1] + (request.readbackError ?
    ` · 상태 조회 실패 (${request.readbackError}) · 상태 새로고침으로 확인` : '') };
}

export function saveJobIsCurrent(job, context, session) {
  return Boolean(job?.job_id && sameSessionContext(context, session) &&
    job.session_id === context.session_id && job.generation === context.generation);
}

export function boundedPoints(points, limit = MAX_MAP_POINTS, dimensions = 3) {
  if (!Array.isArray(points)) return [];
  // Server LOD preserves spatial extent. A malformed oversized frame is rejected,
  // rather than silently relabelling a front slice as the complete map.
  if (points.length > limit) return [];
  return points.filter((point) => Array.isArray(point) && point.length === dimensions && point.every(Number.isFinite));
}

export function overlayMatchesImage(frame) {
  const image = frame?.image;
  const overlay = frame?.overlay;
  const reference = overlay?.image;
  return Boolean((image?.jpeg_base64 || image?.png_base64) && reference &&
    ['native_2d_tracks', 'current_observations_reprojected'].includes(overlay?.overlay_kind) &&
    overlay.reason == null && typeof image.stamp_ns === 'string' &&
    image.stamp_ns === reference.source_timestamp_ns &&
    image.frame_id === reference.frame_id && image.width === reference.width && image.height === reference.height &&
    (image.camera_id == null || image.camera_id === reference.camera_id) &&
    image.rectified !== false && frame.stream_connected !== false &&
    !['LOST', 'STOPPED', 'WAITING_INPUT'].includes(frame.tracking_state));
}

export function frameIsCurrent(frame, session, previous = null) {
  if (!frame || !session || frame.session_id !== session.session_id || frame.generation !== session.generation ||
      frame.engine_id !== session.engine_id || frame.map_epoch == null ||
      (session.map_epoch != null && frame.map_epoch !== session.map_epoch)) return false;
  if (previous && previous.session_id === frame.session_id && previous.generation === frame.generation) {
    try { if (BigInt(frame.sequence) <= BigInt(previous.sequence)) return false; } catch (_) { return false; }
  }
  return true;
}

export function describeCoverage(map) {
  if (!map) return '전역 지도 출력 대기 · coverage unknown';
  return [map.spatial_scope || 'unknown scope', `coverage ${map.coverage || 'unknown'}`,
    `표시 ${map.displayed_count ?? 0}`, `export ${map.exported_count ?? 'unknown'}`,
    `engine total ${map.engine_total_count ?? 'unknown'}`, `backend cap ${map.backend_limit ?? 'unknown'}`,
    `LOD ${map.decimation ? '적용' : '없음'}`, `frame ${map.coordinate_frame || 'unknown'}`,
    `snapshot ${map.snapshot_id ?? 'unknown'}`, `engine revision ${map.engine_revision ?? 'unknown'}`].join(' · ');
}

export function frameAvailability(frame, transportLive = true) {
  const freshness = frame?.readiness?.freshness || {};
  const live = transportLive === true;
  const result = (available, reason) => ({ available: Boolean(available), reason });
  const imageState = imageAvailability(frame, live);
  const pose = frame?.camera_pose;
  const vector = (value, length) => Array.isArray(value) && value.length === length && value.every(Number.isFinite);
  const poseValid = vector(pose?.position, 3) && pose.position.every((value) => Math.abs(value) <= 1_000_000) &&
    vector(pose?.quaternion_xyzw, 4) && Math.abs(pose.quaternion_xyzw.reduce((sum, value) => sum + value * value, 0) - 1) <= 0.02 &&
    typeof pose.frame_id === 'string' && pose.frame_id.length > 0 && pose.frame_id === frame?.frame_id &&
    typeof pose.stamp_ns === 'string' && /^\d{1,20}$/.test(pose.stamp_ns);
  const tracking = frame?.readiness?.tracking_state || frame?.tracking_state || 'UNKNOWN';
  const trackingValid = ['TRACKING', 'MAPPING', 'LOCALIZING'].includes(tracking);
  const map = frame?.global_map;
  const trajectory = frame?.trajectory;
  const layerValid = (layer, limit) => layer && layer.map_epoch === frame?.map_epoch &&
    layer.coordinate_frame === frame?.frame_id && Array.isArray(layer.points) &&
    layer.points.length <= limit && layer.points.every((point) => Array.isArray(point) &&
      point.length === 3 && point.every(Number.isFinite));
  const imageAvailable = imageState.available;
  const mapAvailable = layerValid(map, MAX_MAP_POINTS);
  const trajectoryAvailable = layerValid(trajectory, 10_001);
  return {
    image: imageState,
    pose: result(live && freshness.pose !== false && poseValid, !live ? 'STALE_SOURCE' : freshness.pose === false ? 'POSE_STALE' : poseValid ? 'CAMERA_POSE_RECEIVED' : 'CAMERA_POSE_UNAVAILABLE'),
    tracking: result(live && freshness.tracking !== false && trackingValid, !live ? 'STALE_SOURCE' : freshness.tracking === false ? 'TRACKING_STALE' : tracking),
    overlay: result(imageAvailable && overlayMatchesImage(frame), !live ? 'STALE_SOURCE' : frame?.overlay?.reason || (overlayMatchesImage(frame) ? frame.overlay.overlay_kind : 'IMAGE_ALIGNMENT_UNAVAILABLE')),
    global_map: result(mapAvailable, mapAvailable ? `coverage ${map.coverage || 'unknown'}` : map ? 'GLOBAL_MAP_CONTEXT_OR_POINTS_INVALID' : 'GLOBAL_MAP_UNAVAILABLE'),
    trajectory: result(trajectoryAvailable, trajectoryAvailable ? `${trajectory.trajectory_kind || 'unknown'} · ${trajectory.points.length}점` : trajectory ? 'TRAJECTORY_CONTEXT_OR_POINTS_INVALID' : 'TRAJECTORY_UNAVAILABLE'),
  };
}

function imageAvailability(frame, live) {
  const image = frame?.image, encoded = image?.jpeg_base64 || image?.png_base64;
  const valid = typeof encoded === 'string' && encoded.length > 0 && encoded.length <= MAX_WIRE_BYTES &&
    Number.isInteger(image.width) && image.width > 0 && image.width <= 1920 &&
    Number.isInteger(image.height) && image.height > 0 && image.height <= 1080;
  const fresh = frame?.readiness?.freshness?.image !== false;
  return { available: Boolean(live && fresh && valid), reason: !live ? 'STALE_SOURCE' : !fresh ? 'IMAGE_STALE' :
    valid ? 'IMAGE_RECEIVED' : image?.preview_unavailable_reason || 'IMAGE_UNAVAILABLE' };
}

export function describeCameraPose(frame, availability = frameAvailability(frame)) {
  const pose = frame?.camera_pose;
  const reference = frame?.readiness?.pose_reference || 'camera_link';
  const lines = [`카메라 6DoF · reference ${reference}`];
  if (availability.pose.available) {
    lines.push(`위치 x/y/z (m): ${pose.position.map((value) => value.toFixed(3)).join(' / ')}`,
      `자세 qx/qy/qz/qw: ${pose.quaternion_xyzw.map((value) => value.toFixed(4)).join(' / ')}`,
      `frame ${pose.frame_id} · stamp ${pose.stamp_ns} · source ${frame.pose_origin_topic || frame.readiness?.pose_source || 'unknown'}`);
  } else lines.push(`pose unavailable · ${availability.pose.reason}`);
  lines.push('Go2 body pose 미검증 · camera→Go2 extrinsic 필요 · 주행 승인 안 됨');
  return lines.join('\n');
}

export function describeLocalization(result, session = null) {
  if (!result && session?.state !== 'LOCALIZING') return '저장 지도 위치찾기 · 실행 기록 없음';
  const pending = result?.state === 'LOCALIZING' || session?.state === 'LOCALIZING';
  const truth = (value) => value === true ? 'true' : value === false ? 'false' : 'unknown';
  const reason = result?.confirmation_reason || result?.reason || session?.reason;
  const lines = [
    `공식 localization 서비스 완료: ${truth(result?.official_localization_completed)}`,
    `native load: ${result?.native_load || 'unknown'}`,
    `localize_success: ${pending ? 'pending' : truth(result?.localize_success)}`,
    `새 corrected pose / TRACKING 확인: ${pending ? 'pending' : truth(result?.fresh_pose_tracking_confirmed)}`,
  ];
  if (reason) lines.push(`확인 결과: ${reason}`);
  if (pending) lines.push('공식 서비스 결과와 이후 corrected pose / TRACKING 확인을 기다립니다.');
  else if (result?.retry_requires_new_session !== false) lines.push('추가 시도: 현재 세션을 중지하고 새 세션에서 검증 힌트와 미저장 지도 교체를 다시 확인하세요.');
  return lines.join('\n');
}

export function cameraFrustumGeometry(view, frame, rayLength = 1) {
  if (view?.available !== true || view.projection_convention !== 'rectified_optical_x_right_y_down_z_forward' ||
      view.coordinate_frame !== (frame?.frame_id || frame?.global_map?.coordinate_frame) || view.map_epoch !== frame?.map_epoch ||
      view.session_id !== frame?.session_id || view.generation !== frame?.generation || view.engine_id !== frame?.engine_id ||
      !Number.isFinite(rayLength) || rayLength < 0.05 || rayLength > 10 ||
      frame?.stream_connected === false || ['LOST', 'STOPPED', 'WAITING_INPUT'].includes(frame?.tracking_state)) return null;
  if (!['coordinate_frame', 'map_epoch', 'camera_frame_id', 'calibration_revision'].every((field) =>
    typeof view[field] === 'string' && view[field].length > 0 && view[field].length <= 256)) return null;
  const reference = frame?.overlay?.image;
  if (!reference || view.camera_frame_id !== reference.frame_id || view.width !== reference.width ||
      view.height !== reference.height || view.calibration_revision !== reference.calibration_revision ||
      view.image_source_timestamp_ns !== reference.source_timestamp_ns ||
      view.source_timestamp_ns !== view.image_source_timestamp_ns ||
      (frame.image && (view.image_source_timestamp_ns !== frame.image.stamp_ns || view.camera_frame_id !== frame.image.frame_id))) return null;
  const stamps = ['source_timestamp_ns', 'image_source_timestamp_ns', 'pose_source_timestamp_ns', 'calibration_source_timestamp_ns'];
  try {
    if (!stamps.every((field) => typeof view[field] === 'string' && view[field].length <= 20 && /^\d+$/.test(view[field]))) return null;
    const values = stamps.map((field) => BigInt(view[field]));
    if (values.some((value) => value > 18446744073709551615n)) return null;
    const min = values.reduce((a, b) => a < b ? a : b);
    const max = values.reduce((a, b) => a > b ? a : b);
    if (max - min > 20_000_000n) return null;
  } catch (_) { return null; }
  const vector = (value, length) => Array.isArray(value) && value.length === length && value.every(Number.isFinite);
  const position = view.position;
  const quaternion = view.quaternion_xyzw;
  const intrinsics = view.intrinsics;
  if (!vector(position, 3) || position.some((value) => Math.abs(value) > 1_000_000) || !vector(quaternion, 4) ||
      Math.abs(quaternion.reduce((sum, value) => sum + value * value, 0) - 1) > 0.001 ||
      !vector(intrinsics, 4) || intrinsics[0] <= 0 || intrinsics[1] <= 0 ||
      !Number.isInteger(view.width) || !Number.isInteger(view.height) || view.width < 1 || view.width > 16384 || view.height < 1 || view.height > 16384) return null;
  const [fx, fy, cx, cy] = intrinsics;
  const [qx, qy, qz, qw] = quaternion;
  const rotate = ([x, y, z]) => {
    const tx = 2 * (qy * z - qz * y), ty = 2 * (qz * x - qx * z), tz = 2 * (qx * y - qy * x);
    return [x + qw * tx + qy * tz - qz * ty, y + qw * ty + qz * tx - qx * tz, z + qw * tz + qx * ty - qy * tx];
  };
  const corners = [[0, 0], [view.width, 0], [view.width, view.height], [0, view.height]].map(([u, v]) =>
    rotate([(u - cx) / fx * rayLength, (v - cy) / fy * rayLength, rayLength]).map((value, index) => value + position[index]));
  if (corners.some((corner) => corner.some((value) => !Number.isFinite(value) || Math.abs(value) > 1_000_000))) return null;
  return { position: position.slice(), corners, frame_id: view.coordinate_frame, ray_length_m: rayLength };
}

export function errorText(value, fallback) {
  const detail = value?.detail ?? value;
  const reason = typeof detail === 'string' ? detail : detail?.reason || detail?.message || detail?.code || value?.error || fallback;
  const resources = detail?.resources || detail?.resource_conflicts || value?.resource_conflicts;
  if (!['RESOURCE_CONFLICT', 'CLEANUP_REQUIRED'].includes(reason) || !Array.isArray(resources)) return String(reason).slice(0, 512);
  const labels = resources.slice(0, 16).map((item) => {
    const resource = typeof item === 'string' ? item : item?.resource;
    const label = Object.hasOwn(RESOURCE_LABELS, resource) ? RESOURCE_LABELS[resource] : '알 수 없는 자원';
    const code = typeof item?.reason === 'string' && /^[a-z0-9_]{1,80}$/.test(item.reason) ? item.reason : null;
    return code ? `${label} (${code})` : label;
  });
  return labels.length ? `${reason} · ${labels.join(' · ')}` : reason;
}

function requestId(win) {
  return win.crypto?.randomUUID?.() || `slam-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function mountSlamDashboard(doc = document, options = {}) {
  if (controllers.has(doc)) return controllers.get(doc);
  const mappingHost = doc.querySelector('[data-page="mapping"]');
  const mapsHost = doc.querySelector('[data-page="maps"]');
  if (!mappingHost || !mapsHost) return null;
  const win = options.window || doc.defaultView || window;
  const fetcher = options.fetch || win.fetch.bind(win);
  const disposers = [];
  const el = (tag, attrs = {}, ...children) => {
    const node = doc.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'text') node.textContent = value;
      else if (key === 'className') node.className = value;
      else if (key === 'checked' || key === 'hidden' || key === 'disabled') node[key] = value;
      else node.setAttribute(key, String(value));
    }
    node.append(...children);
    return node;
  };
  const on = (node, event, handler) => {
    node.addEventListener(event, handler);
    disposers.push(() => node.removeEventListener(event, handler));
  };
  const text = (tag, value, attrs = {}) => el(tag, { ...attrs, text: value });
  const button = (value, id, handler) => {
    const node = text('button', value, { type: 'button', id });
    on(node, 'click', handler);
    return node;
  };
  const field = (caption, input) => el('label', { className: 'slam-field' }, text('span', caption), input);
  const checkbox = (caption, id, checked = false) => {
    const input = el('input', { type: 'checkbox', id, checked });
    return { input, label: el('label', { className: 'slam-check' }, input, text('span', caption)) };
  };
  const state = { activePage: doc.documentElement.dataset.activePage || win.location.hash.slice(1),
    session: null, generation: null, engines: [], packages: [], legacyMaps: [], selectedPackage: null,
    frame: null, socket: null, scene: null, previewScene: null, pending: false, disposed: false,
    pollTimer: 0, retryTimer: 0, staleTimer: 0, transportSerial: 0, imagePaintedAt: 0, paintedImage: null, cloudGeometry: null,
    refreshSerial: 0, activationSerial: 0, polling: false,
    receiveAt: 0, staleCleared: false, requestControllers: new Set(), job: null, jobSession: null, saveRequest: null,
    localizationResult: null, localizationAttempted: false, actionError: null, stopRequest: null,
    sessionReadbackError: null, sessionResetRequired: false };
  const panel = el('article', { className: 'panel slam-console', id: 'slamConsole', 'aria-label': 'SLAM 엔진과 관측' });
  const message = text('p', '서버 SLAM 상태 확인 중', { id: 'slamMessage', role: 'status', 'aria-live': 'polite' });
  const status = text('strong', 'UNKNOWN', { id: 'slamSessionState' });
  const identities = text('p', '선택 / 실행 / 운영 위치 소스 확인 중', { id: 'slamSourceIdentity', className: 'slam-muted' });
  const localizationStatus = text('pre', describeLocalization(null), { id: 'slamLocalizationStatus', className: 'slam-detail', role: 'status' });
  const engine = el('select', { id: 'slamEngine', 'aria-label': 'SLAM 엔진' });
  for (const [value, label] of Object.entries(LABELS)) engine.append(text('option', label, { value }));
  const task = el('select', { id: 'slamTask', 'aria-label': 'SLAM 작업' },
    text('option', '지도 생성 (SLAM)', { value: 'mapping' }), text('option', '추적 (VO)', { value: 'tracking' }));
  const capability = text('p', '엔진 가용성 확인 중', { id: 'slamCapability', className: 'slam-muted' });
  const confirmed = checkbox('장비·카메라 인계와 정지 상태를 확인했습니다', 'slamOperatorConfirmed');
  const name = el('input', { id: 'slamMapName', type: 'text', maxlength: 64, autocomplete: 'off', placeholder: '저장 지도 이름' });
  const create2d = checkbox('LiDAR 저장 시 2D 지도 생성', 'slamCreate2d', true);
  const start = button('선택 엔진 시작', 'slamStart', () => perform(async () => {
    await api('/sessions', { method: 'POST', body: { engine_id: engine.value, task: task.value,
      request_id: requestId(win), operator_confirmed: confirmed.input.checked } });
    confirmed.input.checked = false;
    await refresh();
  }));
  const save = button('native 지도 저장', 'slamSave', () => perform(saveMap, 'native 저장 요청 중'));
  const stop = button('세션 중지', 'slamStop', () => openStop());
  const refreshButton = button('상태 새로고침', 'slamRefresh', () => perform(async () => { await loadEngines(); await refresh(); }));
  panel.append(el('div', { className: 'slam-heading' }, el('div', {}, text('div', 'SLAM ENGINE', { className: 'eyebrow' }),
    text('h2', 'LiDAR / Stereo VSLAM')), status), identities,
    el('div', { className: 'slam-control-row' }, field('선택 엔진', engine), field('작업', task), refreshButton), capability,
    confirmed.label, el('div', { className: 'slam-control-row' }, field('저장 이름', name), create2d.label, start, save, stop), message, localizationStatus);

  const overlayToggle = checkbox('현재 관측점 오버레이', 'slamOverlay', true);
  const mapToggle = checkbox('전역 지도점', 'slamGlobalPoints', true);
  const obsToggle = checkbox('현재 관측점 3D', 'slamObservationPoints', false);
  const trailToggle = checkbox('SLAM / VO 궤적', 'slamTrajectory', true);
  const followToggle = checkbox('카메라 따라가기', 'slamFollow', false);
  const cameraToggle = checkbox('카메라 위치·시야', 'slamCameraView', true);
  followToggle.input.disabled = true;
  const imageCanvas = el('canvas', { id: 'slamCameraCanvas', width: 640, height: 480, 'aria-label': '실제 왼쪽 rectified IR 입력과 현재 관측 특징점' });
  const imageStatus = text('p', '왼쪽 rectified IR 입력 대기', { id: 'slamImageStatus', role: 'status' });
  const poseStatus = text('pre', describeCameraPose(null), { id: 'slamCameraPose', className: 'slam-detail', role: 'status' });
  const availabilityLabels = { image: '입력 이미지', pose: '카메라 6DoF', tracking: 'Tracking',
    overlay: '특징점 오버레이', global_map: '전역 지도', trajectory: '궤적' };
  const availabilityNodes = Object.fromEntries(Object.entries(availabilityLabels).map(([key, label]) =>
    [key, text('p', `${label} · 대기`, { id: `slamAvailability-${key}`, 'data-availability': 'unavailable' })]));
  const availabilityPanel = el('div', { className: 'slam-availability', id: 'slamAvailability', 'aria-label': 'VSLAM 출력별 가용성' }, ...Object.values(availabilityNodes));
  const mapCanvas = el('canvas', { id: 'slamGlobalCanvas', 'aria-label': '현재 시야 밖을 포함한 VSLAM 전역 특징점 지도' });
  const mapStatus = text('p', describeCoverage(null), { id: 'slamMapCoverage' });
  const sourceStatus = text('p', '실측 데이터 출처 대기', { id: 'slamProvenance' });
  const heartbeatStatus = text('p', 'stream 대기 · 센서→브라우저 지연 unknown', { id: 'slamHeartbeat' });
  const cameraStatus = text('p', '카메라 시야 대기 · 보정과 optical pose 필요', { id: 'slamCameraViewStatus' });
  const fit = button('전체 지도 FIT', 'slamFit', () => state.scene?.fitToPointCloud());
  const mainFit = button('주요 영역 FIT', 'slamFitMain', () => state.scene?.fitToMainPointCloud());
  const centerPose = button('현재 위치 중심', 'slamCenterPose', () => state.scene?.centerOnPose());
  for (const node of [fit, mainFit, centerPose]) node.disabled = true;
  mainFit.title = '표시점 표본의 축별 2–98% 범위 · 먼 점도 원본에는 보존됩니다';
  centerPose.title = '현재 카메라 pose를 중심으로 표시 · 확대율과 방향 유지';
  const observationViews = el('div', { className: 'slam-views', hidden: true },
    el('section', { className: 'slam-view' }, text('h3', '입력 카메라 · 현재 관측'), imageCanvas, overlayToggle.label, imageStatus, poseStatus),
    el('section', { className: 'slam-view' }, text('h3', '전역 3D 지도'), mapCanvas,
      el('div', { className: 'slam-layer-row' }, mapToggle.label, obsToggle.label, trailToggle.label, cameraToggle.label, followToggle.label, fit, mainFit, centerPose),
      text('small', '드래그 회전 · 우클릭/Shift 드래그 이동 · 휠 확대/축소 · 주요 영역 FIT는 표시 범위만 변경 · 전체 FIT로 복귀'), mapStatus, cameraStatus));
  panel.append(availabilityPanel, observationViews, sourceStatus, heartbeatStatus);
  mappingHost.prepend(panel);

  const stopDialog = el('dialog', { id: 'slamStopDialog', className: 'slam-dialog', 'aria-labelledby': 'slamStopTitle' });
  const stopMessage = text('p', '저장하지 않은 지도 처리 방법을 선택하세요.');
  const saveStop = button('저장 후 추가 관측분 버리고 중지', 'slamSaveThenStop', () => {
    stopDialog.close();
    // Mapping continues while official save completes. The explicit choice also
    // authorizes discarding observations collected after the saved snapshot.
    perform(async () => {
      const session = { ...currentSession() };
      await saveMap(true); await stopSession(true, session);
    }, 'native 저장 완료 확인 중');
  });
  const discardStop = button('저장하지 않고 중지', 'slamDiscardThenStop', () => {
    stopDialog.close(); perform(() => stopSession(Boolean(state.session?.unsaved)));
  });
  stopDialog.append(text('h2', '세션 중지 확인', { id: 'slamStopTitle' }), stopMessage,
    el('div', { className: 'slam-control-row' }, saveStop, discardStop,
      button('취소', 'slamStopCancel', () => stopDialog.close())));
  panel.append(stopDialog);

  const library = el('article', { className: 'panel slam-library', id: 'slamPackageLibrary', 'aria-label': 'LiDAR VSLAM 지도 관리' });
  const filter = el('select', { id: 'slamPackageFilter', 'aria-label': '지도 종류 필터' },
    text('option', '전체 · LiDAR / VSLAM', { value: 'all' }), text('option', 'LiDAR', { value: 'lidar' }),
    text('option', 'VSLAM native', { value: 'vslam' }), text('option', 'Nav2 점유 지도', { value: 'nav2' }));
  const packageRows = el('div', { id: 'slamPackageRows', className: 'slam-package-list' });
  const packageStatus = text('p', 'native 지도 목록 확인 중', { id: 'slamPackageStatus', role: 'status' });
  const packageLocalizationStatus = text('pre', describeLocalization(null), { id: 'slamPackageLocalizationStatus', className: 'slam-detail', role: 'status' });
  const packageDetail = text('pre', 'VSLAM native 지도를 선택하세요.', { id: 'slamPackageDetail', className: 'slam-detail' });
  const packageName = el('input', { id: 'slamPackageName', maxlength: 120, 'aria-label': 'native 지도 이름' });
  const previewCanvas = el('canvas', { id: 'slamPackageCanvas', 'aria-label': '저장 native 지도 미리보기' });
  const download = text('a', 'native ZIP 내보내기', { id: 'slamPackageExport', 'aria-disabled': 'true' });
  const previewDownload = text('a', '특징점·궤적 내보내기', { id: 'slamPackagePreviewExport', 'aria-disabled': 'true' });
  const importFile = el('input', { id: 'slamPackageImport', type: 'file', accept: '.zip,application/zip' });
  const mutate = (operation) => perform(async () => {
    const selected = state.selectedPackage;
    if (!selected) return;
    await api(`/packages/${encodeURIComponent(selected.id)}/${operation}`, { method: 'POST',
      body: { name: packageName.value, expected_revision: selected.revision } });
    await loadPackages();
  });
  const deleteButton = button('native 지도 삭제', 'slamPackageDelete', () => {
    if (!state.selectedPackage || !win.confirm(`“${state.selectedPackage.name}” native 지도를 삭제할까요?`)) return;
    perform(async () => {
      const selected = state.selectedPackage;
      await api(`/packages/${encodeURIComponent(selected.id)}?expected_revision=${encodeURIComponent(selected.revision)}`, { method: 'DELETE' });
      state.selectedPackage = null;
      await loadPackages();
    });
  });
  const renameButton = button('이름 변경', 'slamPackageRename', () => mutate('rename'));
  const copyButton = button('복사', 'slamPackageCopy', () => mutate('copy'));
  const frameInput = el('input', { id: 'slamHintFrame', placeholder: '검증된 map frame', 'aria-label': '위치 힌트 frame' });
  const positionInput = el('input', { id: 'slamHintPosition', placeholder: 'x, y, z (m)', 'aria-label': '위치 힌트 position' });
  const quaternionInput = el('input', { id: 'slamHintQuaternion', placeholder: 'qx, qy, qz, qw', 'aria-label': '위치 힌트 quaternion xyzw' });
  const verifiedHint = checkbox('이 지도 revision의 실제 위치 힌트를 검증했습니다', 'slamHintVerified');
  const replaceUnsaved = checkbox('현재 세션의 미저장 지도 교체를 확인합니다', 'slamReplaceUnsaved');
  const localize = button('scratch에서 native load / 위치찾기', 'slamPackageLocalize', () => perform(async () => {
    const session = currentSession();
    const selected = state.selectedPackage;
    if (!selected || !verifiedHint.input.checked) throw new Error('POSE_HINT_REQUIRED');
    if (!replaceUnsaved.input.checked) throw new Error('UNSAVED_MAP_CONFIRMATION_REQUIRED');
    const parse = (input, count) => {
      const pieces = input.value.split(',').map((piece) => piece.trim());
      const result = pieces.map(Number);
      if (pieces.length !== count || pieces.some((piece) => !piece) || !result.every(Number.isFinite)) throw new Error('INVALID_POSE_HINT');
      return result;
    };
    const position = parse(positionInput, 3);
    const quaternion = parse(quaternionInput, 4);
    if (!frameInput.value.trim() || Math.abs(quaternion.reduce((sum, v) => sum + v * v, 0) - 1) > 0.001) throw new Error('INVALID_POSE_HINT');
    const accepted = await api(`/sessions/${encodeURIComponent(session.session_id)}/localize`, { method: 'POST', body: {
      generation: session.generation, request_id: requestId(win), package_id: selected.id, revision: selected.revision,
      discard_unsaved: true,
      hint: { frame_id: frameInput.value.trim(), position, quaternion_xyzw: quaternion, operator_verified: true } } });
    state.localizationResult = accepted;
    state.localizationAttempted = true;
    updateLocalizationStatus();
    verifiedHint.input.checked = false;
    replaceUnsaved.input.checked = false;
    await refresh();
  }));
  library.append(el('div', { className: 'slam-heading' }, text('h2', '지도 종류 · native 패키지'), filter),
    text('p', 'LiDAR 원본 목록과 VSLAM native DB를 함께 관리합니다. 미리보기는 저장 데이터만 읽습니다.', { className: 'slam-muted' }),
    packageStatus, packageLocalizationStatus, text('a', '세션 중지·새 세션 설정 →', { href: '#mapping' }), packageRows,
    el('div', { className: 'slam-native-detail', id: 'slamNativeDetail', hidden: true }, previewCanvas, packageDetail,
      el('div', { className: 'slam-control-row' }, field('표시 이름', packageName), renameButton, copyButton, deleteButton, download, previewDownload),
      text('p', '특징점·궤적 ZIP은 저장 미리보기와 출처 기록을 내보냅니다. 궤적은 제한된 snapshot이며 전체 관측 경로를 보장하지 않습니다.', { className: 'slam-muted' }),
      el('details', {}, text('summary', '저장 지도에서 관측용 위치찾기 · 명시적 검증 힌트 필요'),
        text('p', 'native load·위치찾기 성공은 별도 결과입니다. 운영 위치 소스와 주행 지도는 자동 변경되지 않습니다.'),
        el('div', { className: 'slam-control-row' }, field('frame', frameInput), field('position', positionInput), field('quaternion xyzw', quaternionInput)),
        verifiedHint.label, replaceUnsaved.label, localize)),
    el('div', { className: 'slam-control-row' }, field('검증된 native ZIP 가져오기', importFile),
      button('지도 목록 새로고침', 'slamPackagesRefresh', () => perform(loadPackages))));
  mapsHost.prepend(library);
  const nativeDetail = library.querySelector('#slamNativeDetail');
  if (!doc.querySelector('link[data-slam-styles]')) {
    const link = el('link', { rel: 'stylesheet', href: '/static/features/slam/slam.css', 'data-slam-styles': '' });
    doc.head.append(link);
  }

  async function api(path, { method = 'GET', body, headers = {}, timeoutMs = method === 'GET' ? SLAM_REQUEST_TIMEOUT_MS : 0 } = {}) {
    const controller = new win.AbortController();
    let timedOut = false;
    const timer = timeoutMs > 0 ? win.setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs) : null;
    state.requestControllers.add(controller);
    try {
      const response = await fetcher(`/api/v1/slam${path}`, { method, credentials: 'same-origin',
        cache: 'no-store', signal: controller.signal,
        headers: body == null || body instanceof win.Blob ? headers : { 'Content-Type': 'application/json', ...headers },
        body: body == null || body instanceof win.Blob ? body : JSON.stringify(body) });
      const value = await response.json().catch(() => {
        if (response.ok) throw Object.assign(new Error('INVALID_JSON_RESPONSE'), { transportUncertain: true });
        return {};
      });
      if (!response.ok) throw new Error(errorText(value, `HTTP ${response.status}`));
      return value;
    } catch (error) {
      if (timedOut) throw Object.assign(new Error('SLAM_REQUEST_TIMEOUT'), { transportUncertain: true });
      if (error.name === 'TypeError') error.transportUncertain = true;
      throw error;
    } finally { win.clearTimeout(timer); state.requestControllers.delete(controller); }
  }

  async function perform(action, label = 'SLAM 요청 처리 중') {
    if (state.pending || state.disposed) return;
    state.pending = true; state.actionError = null;
    message.textContent = label;
    updateButtons();
    try { await action(); }
    catch (error) {
      if (!state.disposed && !error.staleAction) {
        state.actionError = error.message; message.textContent = `SLAM: ${error.message}`; packageStatus.textContent = `지도 작업: ${error.message}`;
      }
    }
    finally {
      state.pending = false;
      if (message.textContent === label) message.textContent = sessionMessage();
      updateButtons();
    }
  }

  function currentSession() {
    if (!state.session || state.session.state === 'IDLE') throw new Error('NO_ACTIVE_SESSION');
    return state.session;
  }

  function requireSession(context) {
    if (state.disposed || state.sessionResetRequired || !sameSessionContext(context, state.session)) {
      throw Object.assign(new Error('SLAM_SESSION_CHANGED'), { staleAction: true });
    }
  }

  function describeSave(job) {
    return `native 저장 ${job.state || '요청됨'} ${job.reason || ''}${job.package_id ? ` · ${job.package_id}` : ''}`;
  }

  function renderSessionStatus() {
    status.textContent = state.sessionReadbackError ? 'UNKNOWN' :
      describeStopProgress(state.stopRequest, state.session)?.status || state.session?.state || 'IDLE';
  }

  function sessionMessage() {
    return state.sessionReadbackError || describeStopProgress(state.stopRequest, state.session)?.message || state.actionError || (saveJobIsCurrent(state.job, state.jobSession, state.session) && describeSave(state.job)) ||
      (state.session?.reason && errorText({ detail: { code: state.session.reason,
        resources: state.session.resource_conflicts } }, state.session.reason)) ||
      (state.session ? `session ${state.session.session_id} · generation ${state.session.generation}` : '실행 중인 SLAM 세션 없음');
  }

  function updateButtons() {
    const active = Boolean(state.session && state.session.state !== 'IDLE');
    const untrusted = Boolean(state.sessionReadbackError || state.sessionResetRequired);
    const visualEngine = (active ? state.session.engine_id : engine.value)?.startsWith('visual_');
    observationViews.hidden = !visualEngine;
    availabilityPanel.hidden = !visualEngine;
    sourceStatus.hidden = !visualEngine;
    heartbeatStatus.hidden = !visualEngine;
    const selected = state.engines.find((value) => value.engine_id === engine.value);
    const tasks = selected?.tasks || [];
    for (const option of task.options) option.disabled = !tasks.includes(option.value);
    if (!tasks.includes(task.value) && tasks.includes('mapping')) task.value = 'mapping';
    start.disabled = state.pending || untrusted || active || !selected?.available_now || !tasks.includes(task.value) || !confirmed.input.checked;
    const unconfirmedSave = sameSessionContext(state.saveRequest?.session, state.session);
    const stopping = sameSessionContext(state.stopRequest?.session, state.session) &&
      !['idle', 'cleanup_failed'].includes(state.stopRequest.phase);
    save.textContent = unconfirmedSave ? '저장 요청 결과 확인' : 'native 지도 저장';
    save.disabled = state.pending || untrusted || stopping || (!unconfirmedSave && (state.session?.state !== 'MAPPING' || state.session?.task !== 'mapping'));
    stop.disabled = state.pending || untrusted || stopping || unconfirmedSave || !active || ['SAVING', 'LOCALIZING', 'STOPPING'].includes(state.session?.state);
    refreshButton.disabled = state.pending;
    name.disabled = state.pending || unconfirmedSave;
    panel.setAttribute('aria-busy', String(state.pending));
    engine.disabled = active || state.pending;
    task.disabled = active || state.pending;
    create2d.input.disabled = state.pending || unconfirmedSave || engine.value !== 'lidar_fastlio';
    for (const node of [renameButton, copyButton, deleteButton]) node.disabled = state.pending || untrusted || active || !state.selectedPackage;
    importFile.disabled = state.pending || untrusted || active;
    localize.disabled = state.pending || untrusted || stopping || !state.selectedPackage || state.session?.engine_id !== 'visual_stereo' ||
      !['MAPPING', 'TRACKING'].includes(state.session?.state) || !verifiedHint.input.checked || !replaceUnsaved.input.checked || state.localizationAttempted;
    download.setAttribute('aria-disabled', state.selectedPackage ? 'false' : 'true');
    previewDownload.setAttribute('aria-disabled', state.selectedPackage ? 'false' : 'true');
    const reason = selected?.blocked_reason || (selected?.available_now ? '현재 실행 가능' : 'ENGINE_UNAVAILABLE');
    capability.textContent = `${reason} · 설치 ${selected?.installed ?? 'unknown'} · software verified ${selected?.software_verified ?? false} · hardware verified ${selected?.hardware_verified ?? false}`;
  }

  async function loadEngines() {
    const value = await api('/engines');
    state.engines = value.engines || [];
    for (const option of engine.options) {
      const entry = state.engines.find((item) => item.engine_id === option.value);
      option.disabled = !entry?.available_now;
      option.textContent = `${LABELS[option.value]}${entry?.available_now ? '' : ` · ${entry?.blocked_reason || 'unavailable'}`}`;
    }
    updateButtons();
  }

  async function refresh() {
    if (!ACTIVE_PAGES.has(state.activePage) || doc.hidden || state.disposed) return;
    const serial = ++state.refreshSerial;
    let value;
    try { value = await api('/session'); }
    catch (error) {
      // An older failed read must not replace a newer success or stop receipt.
      if (serial !== state.refreshSerial || state.disposed) return;
      if (sameSessionContext(state.stopRequest?.session, state.session)) {
        state.stopRequest.readbackError = error.message;
        renderSessionStatus(); message.textContent = sessionMessage();
        return;
      }
      throw error;
    }
    if (serial !== state.refreshSerial || state.disposed) return;
    if (!sessionSnapshotIsValid(value)) {
      if (sameSessionContext(state.stopRequest?.session, state.session)) state.stopRequest.readbackError = 'INVALID_SESSION_RESPONSE';
      else state.sessionReadbackError = 'INVALID_SESSION_RESPONSE · 현재 세션 상태 미확인 · 상태 새로고침으로 확인하세요.';
      renderSessionStatus(); message.textContent = sessionMessage(); updateButtons(); return;
    }
    if (Number.isInteger(state.generation) && value.generation < state.generation) {
      state.sessionResetRequired = true;
      state.sessionReadbackError = 'SESSION_GENERATION_RESET · 서버 재시작 또는 이전 응답 가능 · 이전 세션 종료 미확인 · 페이지를 다시 열어 현재 상태를 확인하세요.';
      disconnectStream(); clearLive();
    }
    if (state.sessionResetRequired) {
      renderSessionStatus(); message.textContent = sessionMessage(); updateButtons(); return;
    }
    if (!sessionReadbackIsCurrent(value, state.session, state.generation, state.stopRequest)) return;
    state.sessionReadbackError = null;
    const previous = state.session;
    const previousStop = state.stopRequest;
    state.session = value.active_session || null;
    state.stopRequest = reconcileStopProgress(state.stopRequest, state.session);
    state.generation = value.generation;
    if (previousStop && !state.stopRequest) {
      state.actionError = null;
      message.textContent = `세션이 변경되어 이전 중지 결과 확인을 종료했습니다. ${sessionMessage()}`;
    }
    if ((state.jobSession && !sameSessionContext(state.jobSession, state.session)) ||
        (state.saveRequest && !sameSessionContext(state.saveRequest.session, state.session))) {
      state.job = null; state.jobSession = null; state.saveRequest = null; state.actionError = null;
      message.textContent = `세션이 변경되어 이전 저장 결과 확인을 종료했습니다. ${sessionMessage()}`;
    }
    if (previous?.session_id !== state.session?.session_id || previous?.generation !== state.session?.generation) {
      state.localizationResult = null; state.localizationAttempted = false;
    }
    if (state.session?.localization_result) {
      const result = state.session.localization_result;
      state.localizationResult = { ...result, reason: result.reason || state.session.reason || state.localizationResult?.reason };
      state.localizationAttempted = true;
    }
    if (previous?.session_id !== state.session?.session_id || previous?.generation !== state.session?.generation ||
        previous?.map_epoch !== state.session?.map_epoch || previous?.engine_id !== state.session?.engine_id) {
      // The first full frame for a new context may have arrived before this
      // session readback and been rejected. A new socket must reseed geometry.
      disconnectStream(); clearLive(); verifiedHint.input.checked = false; replaceUnsaved.input.checked = false;
    }
    renderSessionStatus();
    const source = value.operational_pose_source;
    identities.textContent = `선택 ${LABELS[engine.value] || engine.value} · 실행 ${state.session?.engine_id || '없음'} / ${state.session?.effective_mode || '—'} · 운영 pose ${typeof source === 'string' ? source : source?.source || 'unknown'} (generation ${source?.generation ?? 'unknown'})`;
    if (!state.pending || state.stopRequest) message.textContent = sessionMessage();
    updateButtons();
    updateLocalizationStatus();
    if (state.activePage === 'mapping') connectStream();
  }

  function updateLocalizationStatus() {
    const value = describeLocalization(state.localizationResult, state.session);
    for (const node of [localizationStatus, packageLocalizationStatus]) if (node.textContent !== value) node.textContent = value;
  }

  async function saveMap(wait = false) {
    const session = { ...currentSession() };
    if (!name.value.trim()) throw new Error('저장 지도 이름을 입력하세요.');
    const request = state.saveRequest || { session, path: `/sessions/${encodeURIComponent(session.session_id)}/save`,
      body: { generation: session.generation, request_id: requestId(win), name: name.value.trim(),
        create_2d: session.engine_id === 'lidar_fastlio' && create2d.input.checked } };
    requireSession(request.session);
    state.saveRequest = request;
    let job;
    // An aborted browser request does not cancel native work. Reuse the exact
    // idempotency body; catalogue jobs cannot identify an unacknowledged save.
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        job = await api(request.path, { method: 'POST', body: request.body, timeoutMs: SLAM_REQUEST_TIMEOUT_MS });
        requireSession(request.session);
        if (!saveJobIsCurrent(job, request.session, state.session)) {
          throw Object.assign(new Error('INVALID_SAVE_RESPONSE'), { transportUncertain: true });
        }
        break;
      } catch (error) {
        requireSession(request.session);
        if (!error.transportUncertain && !request.uncertain) { state.saveRequest = null; throw error; }
        request.uncertain = true;
        if (attempt === 1) throw new Error('SAVE_RESPONSE_UNCONFIRMED · 서버 저장은 계속될 수 있습니다. 저장 요청 결과 확인을 누르면 같은 요청 ID로 확인합니다.');
        message.textContent = '저장 응답 미확인 · 같은 요청 ID로 결과 확인 중';
      }
    }
    state.saveRequest = null;
    state.job = job; state.jobSession = request.session;
    message.textContent = describeSave(job);
    if (wait) {
      const deadline = Date.now() + 180_000;
      while (!['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state)) {
        if (state.disposed || Date.now() > deadline) throw new Error('SAVE_COMPLETION_TIMEOUT');
        await new Promise((resolve) => win.setTimeout(resolve, 500));
        requireSession(request.session);
        job = await api(`/jobs/${encodeURIComponent(job.job_id)}`);
        requireSession(request.session);
        if (!saveJobIsCurrent(job, request.session, state.session)) throw new Error('INVALID_SAVE_JOB');
        state.job = job;
        message.textContent = describeSave(job);
      }
      if (job.state !== 'SUCCEEDED') throw new Error(job.reason || 'NATIVE_SAVE_FAILED');
    }
    state.job = job;
    await refresh();
    requireSession(request.session);
    return job;
  }

  function openStop() {
    if (!state.session) return;
    const unsaved = state.session.unsaved === true;
    saveStop.hidden = !unsaved;
    saveStop.disabled = save.disabled;
    discardStop.textContent = unsaved ? '저장하지 않고 중지' : '중지';
    stopMessage.textContent = unsaved ? '저장 후 중지는 공식 저장 완료를 확인한 뒤 중지합니다. 저장된 snapshot 이후에 추가로 관측한 내용은 버립니다. 저장하지 않고 중지 또는 취소도 선택할 수 있습니다.' : '이 세션이 소유한 실행 자원만 중지합니다.';
    stopDialog.showModal();
  }

  async function stopSession(discard, expectedSession = null) {
    if (expectedSession) requireSession(expectedSession);
    const session = { ...currentSession() };
    if (sameSessionContext(state.stopRequest?.session, session) &&
        !['idle', 'cleanup_failed'].includes(state.stopRequest.phase)) return;
    const request = { session, phase: 'requesting', readbackError: null,
      request_id: requestId(win) };
    state.stopRequest = request;
    // Fence snapshots started before this mutation. The POST result is only an
    // acceptance receipt; subsequent GETs alone establish cleanup completion.
    state.refreshSerial += 1;
    renderSessionStatus(); message.textContent = sessionMessage(); updateButtons();
    try {
      const receipt = await api(`/sessions/${encodeURIComponent(session.session_id)}/stop`, { method: 'POST', body: {
        generation: session.generation, request_id: request.request_id, discard_unsaved: discard }, timeoutMs: SLAM_REQUEST_TIMEOUT_MS });
      requireSession(session);
      if (state.stopRequest?.request_id !== request.request_id) return;
      const accepted = receipt?.session_id === session.session_id && receipt.generation === session.generation && receipt.state === 'STOPPING';
      const completed = sameSessionContext(receipt?.active_session, session) && receipt.active_session.state === 'IDLE';
      if (!accepted && !completed) throw Object.assign(new Error('INVALID_STOP_RESPONSE'), { transportUncertain: true });
      // Preserve a newer terminal readback while an acknowledgement was late.
      if (!['stopping', 'idle', 'cleanup_failed'].includes(state.stopRequest.phase)) state.stopRequest.phase = 'accepted';
      state.refreshSerial += 1;
    } catch (error) {
      requireSession(session);
      if (state.stopRequest?.request_id !== request.request_id) return;
      if (['stopping', 'idle', 'cleanup_failed'].includes(state.stopRequest.phase)) {
        renderSessionStatus(); message.textContent = sessionMessage(); return;
      }
      if (!error.transportUncertain) { state.stopRequest = null; renderSessionStatus(); throw error; }
      if (!['stopping', 'idle', 'cleanup_failed'].includes(state.stopRequest.phase)) state.stopRequest.phase = 'unconfirmed';
      state.stopRequest.readbackError = error.message;
    }
    renderSessionStatus(); message.textContent = sessionMessage();
    try { await refresh(); }
    catch (error) {
      requireSession(session);
      if (state.stopRequest?.request_id !== request.request_id) return;
      state.stopRequest.readbackError = error.message;
    }
    if (sameSessionContext(session, state.session)) {
      renderSessionStatus(); message.textContent = sessionMessage();
    }
  }

  function updateMapViewControls() {
    const available = state.scene?.getViewAvailability?.();
    fit.disabled = mainFit.disabled = !available?.fit;
    centerPose.disabled = !available?.center;
  }

  function makeScene(canvas) {
    const Renderer = options.Renderer || win.RobotScene3D;
    if (!Renderer) return null;
    return new Renderer(canvas, { maxPoints: MAX_MAP_POINTS + MAX_OBSERVATIONS, showRobot: false,
      maxCloudRadius: 1_000_000, manualPanStopsFollow: true, worldFrameTrail: true, storage: null });
  }

  const frameRenderer = latestFrameRenderer(
    (callback) => win.requestAnimationFrame ? win.requestAnimationFrame(callback) : win.setTimeout(callback, 16),
    (handle) => win.cancelAnimationFrame ? win.cancelAnimationFrame(handle) : win.clearTimeout(handle), paintFrame);
  const imageDecoder = latestImageDecoder(() => new win.Image(), imageFrameIsCurrent, drawDecodedImage, imageDecodeFailed);
  const geometryHydrator = geometryFrameHydrator();
  const frameReceipts = new WeakMap();

  function imageFrameIsCurrent(frame) {
    // A bounded in-flight decode may finish after a newer frame arrives. Show
    // its own matching pixels/overlay while still fresh, then decode only the
    // newest pending frame. Requiring object equality here starves slow clients.
    return !state.disposed && !doc.hidden && state.activePage === 'mapping' && sameSessionContext(state.frame, frame) &&
      frameIsCurrent(frame, state.session) && state.socket?.readyState === 1 && Date.now() - state.receiveAt <= 1500 &&
      Date.now() - (frameReceipts.get(frame) ?? -Infinity) <= 1500 &&
      imageAvailability(state.frame, true).available && imageAvailability(frame, true).available;
  }

  function clearImage() {
    imageDecoder.clear(); state.imagePaintedAt = 0; state.paintedImage = null;
    imageCanvas.getContext('2d')?.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
  }

  function clearLive() {
    state.frame = null;
    frameRenderer.clear(); clearImage(); geometryHydrator.clear(); state.cloudGeometry = null;
    state.scene?.setPointCloud({ points: [] });
    state.scene?.setTrail([]);
    state.scene?.setRobotPose(null);
    state.scene?.setCameraFrustum?.(null);
    mapCanvas.dataset.cameraView = 'unavailable';
    followToggle.input.disabled = true;
    imageStatus.textContent = '동일 session/generation의 왼쪽 IR 입력 대기';
    mapStatus.textContent = describeCoverage(null);
    cameraStatus.textContent = '카메라 시야 대기 · 보정과 optical pose 필요';
    updateAvailability(null, false);
    updateMapViewControls();
  }

  function updateAvailability(frame, live) {
    const availability = frameAvailability(frame, live);
    for (const [key, value] of Object.entries(availability)) {
      const available = value.available ? 'available' : 'unavailable';
      if (availabilityNodes[key].dataset.availability !== available) availabilityNodes[key].dataset.availability = available;
      const snapshot = ['global_map', 'trajectory'].includes(key) && value.available && !live ? ' · 정적 snapshot 유지' : '';
      const label = `${availabilityLabels[key]} · ${available} · ${value.reason}${snapshot}`;
      if (availabilityNodes[key].textContent !== label) availabilityNodes[key].textContent = label;
    }
    const pose = describeCameraPose(frame, availability);
    if (poseStatus.textContent !== pose) poseStatus.textContent = pose;
    return availability;
  }

  function renderMap(frame) {
    if (!state.scene) state.scene = makeScene(mapCanvas);
    const live = frame.stream_connected !== false && state.socket?.readyState === 1 && Date.now() - state.receiveAt <= 1500;
    const availability = frameAvailability(frame, live);
    const map = frame.global_map;
    const global = mapToggle.input.checked && availability.global_map.available ? map.points : [];
    const observations = frame.current_observations;
    const current = live && obsToggle.input.checked && observations?.available === true && observations.map_epoch === frame.map_epoch &&
      observations.coordinate_frame === frame.frame_id ? boundedPoints(observations.points, MAX_OBSERVATIONS) : [];
    const provenance = String(map?.provenance || '').toLowerCase().includes('fixture') ? 'SYNTHETIC_FIXTURE' : map?.provenance;
    const previous = state.cloudGeometry;
    // Compare every coordinate: equal count/stamp/revision is not proof that a
    // replacement map has unchanged geometry (loop corrections can move it).
    if (!previous || previous.frameId !== frame.frame_id || previous.provenance !== provenance ||
        !sameSessionContext(previous.context, frame) || !samePointGeometry(previous.global, global) ||
        !samePointGeometry(previous.current, current)) {
      state.scene?.setPointCloud({ points: current.length ? [...global, ...current] : global,
        frame_id: frame.frame_id, data_provenance: provenance }, { fit: undefined });
      state.cloudGeometry = { global, current, frameId: frame.frame_id, provenance,
        context: { session_id: frame.session_id, generation: frame.generation, map_epoch: frame.map_epoch, engine_id: frame.engine_id } };
    }
    const trajectory = frame.trajectory;
    const trail = trailToggle.input.checked && availability.trajectory.available ? trajectory.points : [];
    // RobotScene3D's public trail cache is bounded at 400. Decimate the entire
    // trajectory evenly so early, out-of-view segments remain accessible.
    const samples = trail.length > 400 ? Array.from({ length: 400 }, (_, index) => trail[Math.round(index * (trail.length - 1) / 399)]) : trail;
    state.scene?.setTrail(samples.map(([x, y, z]) => ({ x, y, z, frameId: trajectory.coordinate_frame })));
    const geometry = live ? cameraFrustumGeometry(frame.camera_view, frame) : null;
    state.scene?.setCameraFrustum?.(cameraToggle.input.checked ? geometry : null);
    followToggle.input.disabled = !geometry;
    if (geometry) {
      const q = frame.camera_view.quaternion_xyzw;
      const yaw = Math.atan2(2 * (q[3] * q[2] + q[0] * q[1]), 1 - 2 * (q[1] ** 2 + q[2] ** 2));
      state.scene?.setRobotPose({ x: geometry.position[0], y: geometry.position[1], z: geometry.position[2], yaw, frameId: geometry.frame_id });
    } else state.scene?.setRobotPose(null);
    mapCanvas.dataset.cameraView = geometry ? (cameraToggle.input.checked ? 'visible' : 'hidden') : 'unavailable';
    cameraStatus.textContent = geometry ? `검증된 optical 카메라 위치·시야 · 표시선 ${geometry.ray_length_m}m · 실측 깊이 unknown · calibration ${frame.camera_view.calibration_revision} · ${frame.camera_view.provenance || 'unknown'}` :
      `카메라 위치·시야 unavailable · ${live ? frame.camera_view?.reason || 'CAMERA_ALIGNMENT_UNAVAILABLE' : 'STALE_SOURCE'}`;
    const cameraMode = followToggle.input.checked ? 'follow' : 'world';
    if (state.scene && state.scene.cameraMode !== cameraMode) state.scene.setCameraMode(cameraMode);
    state.scene?.setStatus({ online: live, message: `${frame.tracking_state || 'UNKNOWN'} · ${trajectory?.trajectory_kind || 'SLAM/VO unknown'}` });
    mapStatus.textContent = describeCoverage(map) + ` · 궤적 ${trajectory?.trajectory_kind || 'unknown'} ${trail.length} → ${samples.length} 표시`;
    updateMapViewControls();
  }

  function renderImage(frame) {
    const live = state.socket?.readyState === 1 && Date.now() - state.receiveAt <= 1500;
    const availability = updateAvailability(frame, live);
    if (!availability.image.available) {
      clearImage();
      imageStatus.textContent = `입력 이미지 unavailable · ${availability.image.reason} · 현재 관측점 숨김`; return;
    }
    const overlay = frame.overlay;
    const canOverlay = overlayMatchesImage(frame);
    // Keep fresh pixels during replacement decode, but never keep green tracks
    // after their channel becomes unavailable or the operator hides them.
    if ((!canOverlay || !overlayToggle.input.checked) && state.paintedImage) {
      drawDecodedImage(state.paintedImage.decoded, state.paintedImage.frame);
    }
    imageStatus.textContent = `입력 이미지 available · 오버레이 ${overlay?.overlay_kind || 'unavailable'} · ${canOverlay ? `현재 ${overlay?.displayed_count ?? 0}점` : overlay?.reason || 'IMAGE_ALIGNMENT_UNAVAILABLE'} · 수신 후 ${overlay?.receive_age_seconds == null ? 'unknown' : Number(overlay.receive_age_seconds).toFixed(2) + 's'}`;
    imageDecoder.submit(frame);
  }

  function drawDecodedImage(decoded, frame) {
    if (!imageFrameIsCurrent(frame)) return;
    const image = frame.image, context = imageCanvas.getContext('2d');
    if (!context) return;
    if (imageCanvas.width !== image.width) imageCanvas.width = image.width;
    if (imageCanvas.height !== image.height) imageCanvas.height = image.height;
    context.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
    context.drawImage(decoded, 0, 0);
    state.imagePaintedAt = frameReceipts.get(frame);
    state.paintedImage = { decoded, frame };
    availabilityNodes.image.dataset.availability = 'available';
    availabilityNodes.image.textContent = `${availabilityLabels.image} · available · IMAGE_RECEIVED`;
    const canOverlay = overlayMatchesImage(frame) && overlayMatchesImage(state.frame);
    imageStatus.textContent = `입력 이미지 available · stamp ${image.stamp_ns} · 오버레이 ${frame.overlay?.overlay_kind || 'unavailable'} · ${canOverlay ? `현재 ${frame.overlay?.displayed_count ?? 0}점` : frame.overlay?.reason || 'IMAGE_ALIGNMENT_UNAVAILABLE'}`;
    if (!overlayToggle.input.checked || !canOverlay) return;
    context.fillStyle = '#65ff9e';
    context.beginPath();
    for (const [u, v] of boundedPoints(frame.overlay.points, MAX_OBSERVATIONS, 2)) {
      if (u < 0 || v < 0 || u >= image.width || v >= image.height) continue;
      context.moveTo(u + 2.4, v); context.arc(u, v, 2.4, 0, 2 * Math.PI);
    }
    context.fill();
  }

  function imageDecodeFailed(reason, frame) {
    if (!imageFrameIsCurrent(frame)) return;
    imageCanvas.getContext('2d')?.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
    state.imagePaintedAt = 0; state.paintedImage = null;
    imageStatus.textContent = `입력 이미지 unavailable · ${reason}`;
    availabilityNodes.image.dataset.availability = 'unavailable';
    availabilityNodes.image.textContent = `${availabilityLabels.image} · unavailable · ${reason}`;
  }

  function paintFrame(frame) {
    if (state.disposed || doc.hidden || state.activePage !== 'mapping' || state.frame !== frame ||
        !frameIsCurrent(frame, state.session)) return;
    renderMap(frame); renderImage(frame);
    sourceStatus.textContent = `출처 ${frame.global_map?.provenance || frame.overlay?.provenance || 'unknown'} · engine ${frame.engine_id} · session ${frame.session_id} · generation ${frame.generation} · epoch ${frame.map_epoch}`;
    heartbeatStatus.textContent = `stream ${frame.stream_connected ? 'connected' : 'disconnected'} · runtime heartbeat ${frame.heartbeat_receive_age_seconds ?? 'unknown'}s · 지도 snapshot ${frame.global_map?.source_timestamp_ns || 'unknown'} · 센서→브라우저 지연 unknown`;
  }

  function receiveFrame(frame) {
    if (state.disposed || doc.hidden || state.activePage !== 'mapping') return false;
    if (!frameIsCurrent(frame, state.session, state.frame)) return false;
    frame = geometryHydrator.hydrate(frame);
    state.frame = frame; state.receiveAt = Date.now(); state.staleCleared = false;
    frameReceipts.set(frame, state.receiveAt);
    frameRenderer.submit(frame);
    return true;
  }

  function disconnectStream() {
    state.transportSerial += 1;
    win.clearTimeout(state.retryTimer); state.retryTimer = 0;
    geometryHydrator.clear(); frameRenderer.clear(); clearImage();
    if (state.socket) { state.socket.onclose = null; state.socket.close(); state.socket = null; }
  }

  function connectStream() {
    if (state.socket || state.disposed || doc.hidden || state.activePage !== 'mapping') return;
    const serial = ++state.transportSerial;
    geometryHydrator.clear();
    const socket = new win.WebSocket(`${win.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${win.location.host}${SLAM_STREAM_PATH}?geometry_updates=1`);
    state.socket = socket;
    socket.onmessage = (event) => {
      if (state.socket !== socket || typeof event.data !== 'string' || event.data.length > MAX_WIRE_BYTES) return;
      try { const value = JSON.parse(event.data); receiveFrame(value.frame || value.data || value); } catch (_) { imageStatus.textContent = 'INVALID_STREAM_FRAME'; }
    };
    socket.onclose = () => {
      if (state.socket !== socket || serial !== state.transportSerial) return;
      state.socket = null;
      heartbeatStatus.textContent = '시각화 연결 끊김 · 세션 상태는 서버에서 확인 중';
      geometryHydrator.clear(); frameRenderer.clear(); clearImage();
      updateAvailability(state.frame, false);
      if (state.frame) renderMap(state.frame);
      if (!doc.hidden && state.activePage === 'mapping' && !state.disposed) state.retryTimer = win.setTimeout(connectStream, 2000);
    };
  }

  async function loadPackages() {
    const value = await api('/packages');
    state.packages = value.packages || [];
    try {
      const response = await fetcher('/api/v1/saved-maps', { credentials: 'same-origin', cache: 'no-store' });
      if (response.ok) state.legacyMaps = (await response.json()).maps || [];
    } catch (_) { /* Legacy catalog independently displays its connection status. */ }
    const selectedId = state.selectedPackage?.id;
    state.selectedPackage = state.packages.find((entry) => entry.id === selectedId) || null;
    packageRows.replaceChildren();
    for (const entry of state.packages) {
      const row = text('button', `${entry.name} · ${entry.engine_id} · ${entry.native_artifacts?.length || 0} native files`, { type: 'button' });
      row.dataset.packageId = entry.id;
      row.setAttribute('aria-pressed', entry.id === state.selectedPackage?.id ? 'true' : 'false');
      packageRows.append(row);
    }
    packageStatus.textContent = `VSLAM native ${state.packages.length}개 · LiDAR ${state.legacyMaps.length}개 · 호환성은 load 시 서버 검증`;
    if (!state.selectedPackage) {
      packageDetail.textContent = 'VSLAM native 지도를 선택하세요.';
      packageName.value = ''; download.removeAttribute('href'); previewDownload.removeAttribute('href');
      state.previewScene?.setPointCloud({ points: [] });
      state.previewScene?.setTrail([]);
    }
    if (state.selectedPackage) await selectPackage(state.selectedPackage);
    applyFilter(); updateButtons();
  }

  async function selectPackage(entry) {
    state.selectedPackage = entry;
    applyFilter();
    for (const row of packageRows.querySelectorAll('[data-package-id]')) row.setAttribute('aria-pressed', String(row.dataset.packageId === entry.id));
    packageName.value = entry.name || '';
    packageDetail.textContent = [`${entry.name} · ${entry.engine_id}`, `ID ${entry.id}`, `metadata revision ${entry.revision}`,
      `native revision ${entry.native_content_revision}`, `preview revision ${entry.preview_revision || 'unavailable'} · ${entry.preview_consistency}`,
      `frame ${entry.map_frame || 'unknown'} · calibration ${entry.calibration_hash || 'unknown'}`,
      `save ${entry.save_completion?.status || 'unknown'} · native load ${entry.validation?.native_load || 'unknown'} · localization ${entry.validation?.localization_success || 'unknown'}`,
      `compatibility ${entry.compatibility?.status || 'unknown'} · sparse map → navigation unavailable`].join('\n');
    download.href = `/api/v1/slam/packages/${encodeURIComponent(entry.id)}/export?expected_revision=${encodeURIComponent(entry.revision)}`;
    download.download = `native-${entry.id}.zip`;
    previewDownload.href = `/api/v1/slam/packages/${encodeURIComponent(entry.id)}/preview-export?expected_revision=${encodeURIComponent(entry.revision)}`;
    previewDownload.download = `preview-${entry.id}.zip`;
    verifiedHint.input.checked = false;
    replaceUnsaved.input.checked = false;
    positionInput.value = ''; quaternionInput.value = ''; frameInput.value = '';
    updateButtons();
    const preview = await api(`/packages/${encodeURIComponent(entry.id)}/preview`);
    if (state.selectedPackage?.id !== entry.id) return;
    if (!state.previewScene) state.previewScene = makeScene(previewCanvas);
    const map = preview.global_map || preview;
    const trajectory = preview.trajectory;
    state.previewScene?.setPointCloud({ points: boundedPoints(map.points), frame_id: map.coordinate_frame || entry.map_frame,
      data_provenance: String(map.provenance || entry.data_provenance).toLowerCase().includes('fixture') ? 'SYNTHETIC_FIXTURE' : map.provenance }, { fit: true });
    const trail = boundedPoints(trajectory?.points || [], 10_001);
    const samples = trail.length > 400 ? Array.from({ length: 400 }, (_, index) => trail[Math.round(index * (trail.length - 1) / 399)]) : trail;
    state.previewScene?.setTrail(samples.map(([x, y, z]) => ({ x, y, z, frameId: map.coordinate_frame || entry.map_frame })));
    packageDetail.textContent += `\n${describeCoverage(preview.global_map)}\n미리보기 출처 ${map.provenance || entry.data_provenance || 'unknown'}`;
    state.previewScene?.setStatus({ online: true, snapshot: true, message: `${entry.preview_consistency} preview` });
  }

  function applyFilter() {
    const showNative = ['all', 'vslam'].includes(filter.value);
    packageRows.hidden = !showNative; nativeDetail.hidden = !showNative || !state.selectedPackage;
    const legacyLayout = mapsHost.querySelector('.saved-layout');
    if (legacyLayout) legacyLayout.hidden = filter.value === 'vslam';
    for (const tools of mapsHost.querySelectorAll('.saved-tools-grid, .map-crop-panel')) tools.hidden = filter.value === 'vslam';
    for (const row of mapsHost.querySelectorAll('[data-saved-map-id]')) {
      const entry = state.legacyMaps.find((item) => item.id === row.dataset.savedMapId);
      row.hidden = filter.value === 'nav2' && entry?.kind !== 'occupancy2d';
    }
  }

  async function tick() {
    win.clearTimeout(state.pollTimer);
    if (state.polling || state.disposed || !ACTIVE_PAGES.has(state.activePage) || doc.hidden) return;
    state.polling = true;
    try {
      await refresh();
      if (state.job?.job_id && !['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(state.job.state)) {
        const context = state.jobSession;
        const jobId = state.job.job_id;
        try {
          const job = await api(`/jobs/${encodeURIComponent(jobId)}`);
          if (state.job?.job_id === jobId && saveJobIsCurrent(job, context, state.session)) {
            state.job = job;
            if (!state.pending) message.textContent = describeSave(job);
          }
        } catch (error) {
          if (state.job?.job_id === jobId && sameSessionContext(context, state.session)) throw error;
        }
      }
    } catch (error) { if (error.name !== 'AbortError' && !state.pending) message.textContent = `SLAM 상태: ${error.message}`; }
    finally {
      state.polling = false;
      win.clearTimeout(state.pollTimer);
      if (!state.disposed && ACTIVE_PAGES.has(state.activePage) && !doc.hidden) state.pollTimer = win.setTimeout(tick, 1500);
    }
  }

  async function setActive(page) {
    const serial = ++state.activationSerial;
    state.activePage = page;
    win.clearTimeout(state.pollTimer); state.pollTimer = 0;
    if (page !== 'mapping' || doc.hidden) {
      disconnectStream(); clearLive(); state.scene?.destroy(); state.scene = null;
    }
    if (page !== 'maps' || doc.hidden) { state.previewScene?.destroy(); state.previewScene = null; }
    if (!ACTIVE_PAGES.has(page) || doc.hidden || state.disposed) return;
    try { await loadEngines(); if (page === 'maps') await loadPackages(); }
    catch (error) { message.textContent = `SLAM: ${error.message}`; packageStatus.textContent = `native 지도: ${error.message}`; }
    if (serial !== state.activationSerial || state.disposed) return;
    await tick();
  }

  for (const node of [engine, task, confirmed.input, verifiedHint.input, replaceUnsaved.input]) on(node, 'change', updateButtons);
  for (const toggle of [mapToggle, obsToggle, trailToggle, cameraToggle, followToggle]) on(toggle.input, 'change', () => { if (state.frame) renderMap(state.frame); });
  on(overlayToggle.input, 'change', () => { if (state.frame) renderImage(state.frame); });
  on(filter, 'change', applyFilter);
  on(packageRows, 'click', (event) => {
    const row = event.target.closest('[data-package-id]');
    const entry = state.packages.find((value) => value.id === row?.dataset.packageId);
    if (entry) perform(() => selectPackage(entry));
  });
  on(importFile, 'change', () => perform(async () => {
    const file = importFile.files?.[0];
    if (!file) return;
    if (file.size > 512 * 1024 * 1024) throw new Error('PACKAGE_LIMIT');
    await api('/packages/import', { method: 'POST', body: file, headers: { 'Content-Type': 'application/zip' } });
    importFile.value = ''; await loadPackages();
  }));
  on(doc, 'robot-scope:page-change', (event) => setActive(event.detail?.activePage));
  on(doc, 'visibilitychange', () => setActive(state.activePage));
  on(win, 'pagehide', (event) => {
    if (!event.persisted) { controller.dispose(); return; }
    disconnectStream(); win.clearTimeout(state.pollTimer); frameRenderer.clear(); clearImage(); state.cloudGeometry = null;
    state.scene?.destroy(); state.scene = null; state.previewScene?.destroy(); state.previewScene = null;
  });
  on(win, 'pageshow', (event) => { if (event.persisted) setActive(doc.documentElement.dataset.activePage || win.location.hash.slice(1)); });
  const observer = new win.MutationObserver(applyFilter);
  const legacyList = mapsHost.querySelector('#savedMapList');
  if (legacyList) observer.observe(legacyList, { childList: true });
  state.staleTimer = win.setInterval(() => {
    // A slow replacement decode must not keep the previous image alive merely
    // because newer transport frames continue arriving.
    if (state.imagePaintedAt && Date.now() - state.imagePaintedAt > 1500) {
      imageCanvas.getContext('2d')?.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
      state.imagePaintedAt = 0; state.paintedImage = null;
      imageStatus.textContent = '입력 이미지 unavailable · IMAGE_DISPLAY_STALE';
      availabilityNodes.image.dataset.availability = 'unavailable';
      availabilityNodes.image.textContent = `${availabilityLabels.image} · unavailable · IMAGE_DISPLAY_STALE`;
    }
    if (state.frame && !state.staleCleared && Date.now() - state.receiveAt > 1500) {
      state.staleCleared = true;
      frameRenderer.clear(); clearImage();
      renderMap(state.frame);
      updateAvailability(state.frame, false);
      imageStatus.textContent = 'STALE_SOURCE · 현재 관측점 숨김';
      heartbeatStatus.textContent = 'stream 새 frame 대기 · 정적 지도 snapshot은 유지';
    }
  }, 500);
  const controller = {
    setActive, receiveFrame,
    dispose() {
      if (state.disposed) return;
      state.disposed = true;
      disconnectStream(); win.clearTimeout(state.pollTimer); win.clearInterval(state.staleTimer);
      frameRenderer.clear(); clearImage(); state.cloudGeometry = null;
      for (const request of state.requestControllers) request.abort();
      state.scene?.destroy(); state.previewScene?.destroy(); observer.disconnect();
      disposers.splice(0).forEach((dispose) => dispose());
      panel.remove(); library.remove(); controllers.delete(doc);
    },
  };
  controllers.set(doc, controller);
  setActive(state.activePage);
  return controller;
}

if (typeof document !== 'undefined') mountSlamDashboard(document);
