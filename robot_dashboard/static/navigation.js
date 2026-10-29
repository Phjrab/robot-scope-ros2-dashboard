(function navigationModule(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RobotNavigation = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function buildNavigation() {
  'use strict';

  const GROUPS = Object.freeze([
    Object.freeze({ id: 'core', label: 'Core behavior', description: 'Rotation Shim과 목표 방향 정렬' }),
    Object.freeze({ id: 'controller', label: 'Controller', description: '속도, 전방주시와 회전 응답' }),
    Object.freeze({ id: 'costmap', label: 'Costmaps', description: 'Go2 차체 반경, 감지 범위와 완충' }),
    Object.freeze({ id: 'goal', label: 'Goal & progress', description: '도착 판정과 진행 정체 감지' }),
    Object.freeze({ id: 'planner', label: 'Planner & bridge', description: 'NavFn A*와 cmd_vel 호환' }),
  ]);

  function numberField(key, group, label, value, minimum, maximum, step, unit, help) {
    return Object.freeze({ key, group, label, type: 'number', tuned: value, minimum, maximum, step, unit, help });
  }

  function booleanField(key, group, label, value, help, locked = false) {
    return Object.freeze({ key, group, label, type: 'boolean', tuned: value, help, locked });
  }

  const FIELDS = Object.freeze([
    booleanField('use_rotate_to_heading', 'core', 'RPP rotate-to-heading', false, '제자리 회전 고착을 줄이기 위해 RPP 기능은 끕니다. Go2 안전 profile 고정값입니다.', true),
    booleanField('rotation_shim_enabled', 'core', 'Rotation Shim controller', true, '주행 전 방향 정렬은 별도 Shim이 담당합니다. Go2 안전 profile 고정값입니다.', true),
    booleanField('rotate_to_goal_heading', 'core', 'Rotate at goal', true, '도착 위치에서 목표 yaw까지 정렬합니다. Go2 안전 profile 고정값입니다.', true),

    numberField('desired_linear_vel', 'controller', 'Desired linear velocity', 0.25, 0.05, 1.0, 0.01, 'm/s', '전후진 상한 1.0 m/s. 목표 속도와 실제 속도는 다르므로 증속 전 현장 검증이 필요합니다.'),
    numberField('controller_frequency', 'controller', 'Controller frequency', 10, 10, 20, 1, 'Hz', '200 ms watchdog보다 충분히 빠른 10–20 Hz 범위입니다.'),
    numberField('lookahead_time', 'controller', 'Lookahead time', 0.8, 0.2, 2, 0.05, 's', '작을수록 경로에 더 밀착합니다.'),
    numberField('min_lookahead_dist', 'controller', 'Minimum lookahead', 0.25, 0.1, 0.6, 0.01, 'm', '저속에서도 유지할 최소 전방주시 거리입니다.'),
    booleanField('use_velocity_scaled_lookahead_dist', 'controller', 'Velocity-scaled lookahead', true, '속도에 따라 전방주시 거리를 바꿉니다.'),
    numberField('rotate_to_heading_angular_vel', 'controller', 'Rotate angular velocity', 0.5, 0.1, 0.5, 0.05, 'rad/s', 'PDF 기준 0.9 rad/s 대신 bridge 안전 상한 0.50 rad/s를 적용합니다.'),
    numberField('max_angular_accel', 'controller', 'Maximum angular acceleration', 1.2, 0.1, 1.2, 0.1, 'rad/s²', 'PDF 기준 2.0 rad/s² 대신 bridge 안전 상한 1.2 rad/s²를 적용합니다.'),
    numberField('transform_tolerance', 'controller', 'Transform tolerance', 0.3, 0.05, 1, 0.05, 's', 'TF 지터를 허용할 시간 여유입니다.'),
    booleanField('closed_loop', 'controller', 'Rotation Shim closed loop', false, 'Go2 odometry 특성상 open-loop 회전을 사용합니다. Go2 안전 profile 고정값입니다.', true),
    numberField('angular_dist_threshold', 'controller', 'Shim angular threshold', 0.785, 0.1, 3.14, 0.005, 'rad', '이 각도 이상 차이나면 제자리 방향 정렬을 시작합니다.'),

    numberField('robot_radius', 'costmap', 'Robot radius', 0.22, 0.15, 0.4, 0.01, 'm', 'Go2 몸통 크기에 맞춘 원형 반경입니다.'),
    numberField('inflation_radius', 'costmap', 'Inflation radius', 0.25, 0.16, 1, 0.01, 'm', '좁은 통로를 과도하게 막지 않는 완충 반경입니다.'),
    numberField('cost_scaling_factor', 'costmap', 'Cost scaling factor', 5, 1, 20, 0.1, '', '장애물에서 멀어질수록 비용이 감소하는 곡선입니다.'),
    numberField('min_obstacle_height', 'costmap', 'XT16 slice lower Z', -0.5, -1, 1, 0.05, 'm', 'PointCloud2를 LaserScan으로 투영하기 전에 유지할 라이다 기준 아래쪽 높이입니다.'),
    numberField('max_obstacle_height', 'costmap', 'XT16 slice upper Z', 2, 0.1, 3, 0.1, 'm', 'PointCloud2를 LaserScan으로 투영하기 전에 유지할 라이다 기준 위쪽 높이입니다.'),
    numberField('obstacle_max_range', 'costmap', 'Obstacle maximum range', 8, 0.5, 12, 0.5, 'm', '장애물로 표시할 최대 거리입니다.'),
    numberField('raytrace_max_range', 'costmap', 'Raytrace maximum range', 10, 0.5, 15, 0.5, 'm', '광선으로 자유공간을 지울 최대 거리입니다.'),
    booleanField('always_send_full_costmap', 'costmap', 'Always send full costmap', true, '증분 누락 없이 전체 costmap을 발행합니다.'),
    booleanField('track_unknown_space', 'costmap', 'Track unknown space', true, '전역 지도에서 미탐색 영역을 구분합니다.'),

    numberField('xy_goal_tolerance', 'goal', 'XY goal tolerance', 0.35, 0.05, 1, 0.01, 'm', '4족보행 위치 오차를 고려한 도착 반경입니다.'),
    numberField('yaw_goal_tolerance', 'goal', 'Yaw goal tolerance', 0.45, 0.05, 1.57, 0.01, 'rad', '마지막 방향 hunting을 줄이는 허용 오차입니다.'),
    numberField('required_movement_radius', 'goal', 'Required movement radius', 0.2, 0.05, 1, 0.01, 'm', '진행 검사에서 움직임으로 인정할 거리입니다.'),

    booleanField('use_astar', 'planner', 'NavFn A*', true, '전역 planner에서 A*를 사용합니다.'),
    booleanField('enable_stamped_cmd_vel', 'planner', 'Stamped cmd_vel', false, 'Go2 cmd_vel bridge와 호환되는 plain Twist를 사용합니다. 고정값입니다.', true),
  ]);

  const FIELD_BY_KEY = Object.freeze(Object.fromEntries(FIELDS.map((field) => [field.key, field])));
  const FIELD_KEYS = Object.freeze(FIELDS.map((field) => field.key));
  const TUNED_VALUES = Object.freeze(Object.fromEntries(FIELDS.map((field) => [field.key, field.tuned])));
  const PIPELINE_ACTIVE_STATES = Object.freeze(['starting', 'running', 'stopping']);
  const GOAL_ACTIVE_STATES = Object.freeze(['pending', 'active', 'canceling']);

  function operationalLocalizationStatus(snapshot) {
    const source = snapshot?.operational_localization;
    if (!source) return null;
    if (!source.fresh) return {label: 'WAIT', note: '3D 위치추정 상태 수신 대기', tone: 'waiting'};
    if (source.ready) return {label: 'READY', note: '저장 3D 지도 정합 완료', tone: 'ok'};
    const state = source.state;
    if (['WAITING_MAP_CORRECTION', 'WAITING_EXACT_STAMP_PAIR', 'INITIAL_REFINEMENT_CONFIRMING'].includes(state)) {
      const count = source.metrics?.initial_confirmations || 0;
      return {label: 'ALIGNING', note: `초기 위치 접수 · 정지 상태에서 3D 정합 확인 중 (${count}/3)`, tone: 'waiting'};
    }
    if (state === 'WAITING_EXPLICIT_INITIAL_POSE') return {label: 'NEED POSE', note: '주행 지도에서 현재 위치와 방향을 지정하세요.', tone: 'waiting'};
    const reasons = {
      CORRECTION_JUMP_RESEED_REQUIRED: '추적 위치 보정 한도 초과 · 초기 위치 재지정 필요',
      INITIAL_REFINEMENT_OUT_OF_BOUNDS: '초기 정합이 클릭 위치에서 너무 벗어남 · 초기 위치 재지정 필요',
      INITIAL_REFINEMENT_REQUIRES_STOP: '초기 정합 중 움직임 감지 · 정지 후 초기 위치 재지정 필요',
      INITIAL_REFINEMENT_LOW_OVERLAP: '지도와 겹치는 점 부족 · 초기 정합 대기',
      MAP_CORRECTION_STALE: '3D 정합 결과가 오래됨 · Goal 전송 대기',
    };
    return {label: 'BLOCKED', note: reasons[state] || `3D 정합 대기: ${state || '상태 미확인'}`, tone: 'error'};
  }

  function finiteNumber(value, name) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new TypeError(`${name} must be a finite number`);
    return number;
  }

  function navigationPosePreview(scene, context, layout, pose, state = 'staged') {
    const initial = pose?.mode === 'initial';
    const robot = pose?.mode === 'robot';
    const staged = state === 'staged';
    const color = robot ? '#7df0b6' : initial ? '#5dded8' : staged ? '#ffc66d' : '#a28bff';
    let drawn = false;
    context.save();
    try {
      context.globalAlpha *= robot ? 1 : staged ? 0.9 : 0.75;
      drawn = scene?.drawRobotMapPreview?.(context, pose, point => worldToCanvas(layout, point), color) === true;
    } catch (error) {
      console.warn('Navigation pose model preview unavailable:', error);
    } finally {
      context.restore();
    }
    return { drawn, color, label: robot ? 'ROBOT' : initial ? `INITIAL · ${drawn ? 'URDF' : 'STAGED'}` : `GOAL · ${state.toUpperCase()}` };
  }

  function matchingPoseMap(snapshot, map) {
    // SavedMaps /data uses map_id; catalogue/navigation metadata uses id.
    // Reject contradictory aliases instead of selecting one silently.
    const id = map?.map_id || map?.id;
    return Boolean(id && map.revision && map.frame_id === 'map'
      && !(map.map_id && map.id && map.map_id !== map.id)
      && snapshot?.map?.id === id && snapshot?.map?.revision === map.revision);
  }

  function currentRobotOverlay(snapshot, map) {
    const pose = snapshot?.localization?.pose;
    if (!matchingPoseMap(snapshot, map) || snapshot?.localization?.state !== 'localized'
        || !['x', 'y', 'yaw'].every(key => Number.isFinite(pose?.[key]))) return null;
    return { ...pose, mode: 'robot' };
  }

  // Render-only association: an old goal must not move onto a newly selected map.
  // Missing metrology/map evidence hides the overlay, never changes admission.
  function goalPoseOverlay(snapshot, map) {
    const goal = snapshot?.goal;
    const evidence = goal?.precision_evidence;
    const pin = evidence?.context;
    const state = String(goal?.state || '').toLowerCase();
    if (!['pending', 'active', 'canceling', 'canceled', 'cancelled', 'succeeded', 'failed', 'rejected'].includes(state)
        || !goal?.goal_id || evidence?.goal_id !== goal.goal_id
        || !matchingPoseMap(snapshot, map)
        || pin?.map_id !== (map.map_id || map.id) || pin?.map_revision !== map.revision
        || !['x', 'y', 'yaw'].every(key => Number.isFinite(goal.pose?.[key]))) return null;
    return { pose: goal.pose, state: state === 'pending' ? 'sent' : state };
  }

  function drawPoseMarker(context, layout, pose, color, label, ratio = 1, dashed = false, modelDrawn = false) {
    if (!pose) return;
    let projected;
    try { projected = worldToCanvas(layout, pose); }
    catch (_) { return; }
    if (!projected.inside) return;
    const radius = 6 * ratio;
    const arrow = 28 * ratio;
    context.save();
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.strokeStyle = color;
    context.fillStyle = color;
    context.lineWidth = 2 * ratio;
    if (!modelDrawn) {
      if (dashed) context.setLineDash([5 * ratio, 4 * ratio]);
      context.beginPath();
      context.arc(projected.x, projected.y, radius, 0, Math.PI * 2);
      context.stroke();
      const tipX = projected.x + Math.cos(projected.heading) * arrow;
      const tipY = projected.y + Math.sin(projected.heading) * arrow;
      context.beginPath();
      context.moveTo(projected.x, projected.y);
      context.lineTo(tipX, tipY);
      context.stroke();
      context.setLineDash([]);
      context.beginPath();
      context.arc(tipX, tipY, 2.5 * ratio, 0, Math.PI * 2);
      context.fill();
    }
    context.font = globalThis.RobotScopeTypography?.canvasFont('mono', 13 * ratio, 400) || `400 ${13 * ratio}px "IBM Plex Mono", "IBM Plex Sans KR", monospace`;
    if (modelDrawn) {
      const margin = 5 * ratio;
      const textWidth = context.measureText(label).width;
      const offset = Math.max(18 * ratio, 0.46 * layout.scale / layout.resolution);
      const x = Math.max(margin, Math.min(layout.canvasWidth - textWidth - margin, projected.x - textWidth / 2));
      const y = Math.max(18 * ratio, Math.min(layout.canvasHeight - margin, projected.y + (dashed ? -offset : offset + 14 * ratio)));
      context.fillStyle = 'rgba(4,16,13,.92)';
      context.fillRect(x - margin, y - 14 * ratio, textWidth + 2 * margin, 18 * ratio);
      context.fillStyle = color;
      context.fillText(label, x, y);
    } else {
      context.fillText(label, projected.x + 9 * ratio, projected.y - 9 * ratio);
    }
    context.restore();
  }

  function normalizeYaw(value) {
    const angle = finiteNumber(value, 'yaw');
    return Math.atan2(Math.sin(angle), Math.cos(angle));
  }

  function coerceParameterValue(key, value) {
    const field = FIELD_BY_KEY[key];
    if (!field) throw new RangeError(`unsupported navigation parameter: ${key}`);
    if (field.type === 'boolean') {
      if (typeof value === 'boolean') return value;
      if (value === 'true' || value === '1' || value === 1) return true;
      if (value === 'false' || value === '0' || value === 0) return false;
      throw new TypeError(`${key} must be a boolean`);
    }
    const number = finiteNumber(value, key);
    if (number < field.minimum || number > field.maximum) {
      throw new RangeError(`${key} must be between ${field.minimum} and ${field.maximum}`);
    }
    return number;
  }

  function parameterValues(values, { requireAll = true } = {}) {
    if (!values || typeof values !== 'object' || Array.isArray(values)) {
      throw new TypeError('navigation parameter values must be an object');
    }
    const unknown = Object.keys(values).filter((key) => !FIELD_BY_KEY[key]);
    if (unknown.length) throw new RangeError(`unsupported navigation parameters: ${unknown.join(', ')}`);
    if (requireAll) {
      const missing = FIELD_KEYS.filter((key) => !Object.hasOwn(values, key));
      if (missing.length) throw new RangeError(`missing navigation parameters: ${missing.join(', ')}`);
    }
    const result = {};
    for (const key of FIELD_KEYS) {
      if (Object.hasOwn(values, key)) {
        result[key] = coerceParameterValue(key, values[key]);
        if (FIELD_BY_KEY[key].locked && result[key] !== FIELD_BY_KEY[key].tuned) {
          throw new RangeError(`${key} is locked to ${FIELD_BY_KEY[key].tuned}`);
        }
      }
    }
    if (Object.hasOwn(result, 'min_obstacle_height') && Object.hasOwn(result, 'max_obstacle_height') &&
        result.min_obstacle_height >= result.max_obstacle_height) {
      throw new RangeError('min_obstacle_height must be less than max_obstacle_height');
    }
    if (Object.hasOwn(result, 'obstacle_max_range') && Object.hasOwn(result, 'raytrace_max_range') &&
        result.obstacle_max_range > result.raytrace_max_range) {
      throw new RangeError('obstacle_max_range must not exceed raytrace_max_range');
    }
    if (Object.hasOwn(result, 'robot_radius') && Object.hasOwn(result, 'inflation_radius') &&
        result.inflation_radius < result.robot_radius) {
      throw new RangeError('inflation_radius must be at least robot_radius');
    }
    return result;
  }

  function normalizeParameterSnapshot(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new TypeError('parameter snapshot is invalid');
    const revision = String(payload.revision || '').trim();
    if (!revision || revision.length > 128) throw new TypeError('parameter revision is missing or invalid');
    const values = parameterValues(payload.values, { requireAll: true });
    const presets = Array.isArray(payload.presets) ? payload.presets.map((preset) => {
      const id = String(preset?.id || '').trim();
      const label = String(preset?.label || '').trim();
      if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(id) || !label) throw new TypeError('navigation preset is invalid');
      return Object.freeze({
        id,
        label,
        description: String(preset.description || ''),
        values: Object.freeze(parameterValues(preset.values, { requireAll: true })),
      });
    }) : [];
    return Object.freeze({
      revision,
      active_preset: String(payload.active_preset || ''),
      requires_restart: payload.requires_restart !== false,
      values: Object.freeze(values),
      presets: Object.freeze(presets),
    });
  }

  function changedParameterValues(applied, draft) {
    const before = parameterValues(applied, { requireAll: true });
    const after = parameterValues(draft, { requireAll: true });
    const changes = {};
    for (const key of FIELD_KEYS) {
      if (before[key] !== after[key]) changes[key] = after[key];
    }
    return changes;
  }

  function parameterPatch(baseRevision, applied, draft) {
    const revision = String(baseRevision || '').trim();
    if (!revision || revision.length > 128) throw new TypeError('base_revision is missing or invalid');
    return { base_revision: revision, values: changedParameterValues(applied, draft) };
  }

  function mapGeometry(map) {
    const width = finiteNumber(map?.width, 'map width');
    const height = finiteNumber(map?.height, 'map height');
    const resolution = finiteNumber(map?.resolution, 'map resolution');
    if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0 || resolution <= 0) {
      throw new RangeError('map dimensions and resolution must be positive');
    }
    const origin = Array.isArray(map.origin) ? map.origin : [];
    if (origin.length < 2) throw new TypeError('map origin is missing');
    return {
      width,
      height,
      resolution,
      originX: finiteNumber(origin[0], 'map origin x'),
      originY: finiteNumber(origin[1], 'map origin y'),
      originYaw: normalizeYaw(origin[2] || 0),
    };
  }

  function mapLayout(map, canvasWidth, canvasHeight, paddingRatio = 0.06) {
    const geometry = mapGeometry(map);
    const width = finiteNumber(canvasWidth, 'canvas width');
    const height = finiteNumber(canvasHeight, 'canvas height');
    if (width <= 0 || height <= 0) throw new RangeError('canvas dimensions must be positive');
    const padding = Math.max(0, Math.min(0.2, Number(paddingRatio) || 0));
    const scale = Math.min((width * (1 - padding * 2)) / geometry.width, (height * (1 - padding * 2)) / geometry.height);
    const drawWidth = geometry.width * scale;
    const drawHeight = geometry.height * scale;
    return Object.freeze({
      ...geometry,
      canvasWidth: width,
      canvasHeight: height,
      scale,
      drawWidth,
      drawHeight,
      left: (width - drawWidth) / 2,
      top: (height - drawHeight) / 2,
    });
  }

  function canvasToWorld(layout, point, { clamp = false } = {}) {
    if (!layout || typeof layout !== 'object') throw new TypeError('map layout is required');
    let x = finiteNumber(point?.x, 'canvas x');
    let y = finiteNumber(point?.y, 'canvas y');
    const inside = x >= layout.left && x <= layout.left + layout.drawWidth &&
      y >= layout.top && y <= layout.top + layout.drawHeight;
    if (!inside && !clamp) return null;
    if (clamp) {
      x = Math.max(layout.left, Math.min(layout.left + layout.drawWidth, x));
      y = Math.max(layout.top, Math.min(layout.top + layout.drawHeight, y));
    }
    const localX = ((x - layout.left) / layout.scale) * layout.resolution;
    const localY = ((layout.top + layout.drawHeight - y) / layout.scale) * layout.resolution;
    const cos = Math.cos(layout.originYaw);
    const sin = Math.sin(layout.originYaw);
    return {
      x: layout.originX + cos * localX - sin * localY,
      y: layout.originY + sin * localX + cos * localY,
      inside,
    };
  }

  function worldToCanvas(layout, pose) {
    if (!layout || typeof layout !== 'object') throw new TypeError('map layout is required');
    const dx = finiteNumber(pose?.x, 'world x') - layout.originX;
    const dy = finiteNumber(pose?.y, 'world y') - layout.originY;
    const cos = Math.cos(layout.originYaw);
    const sin = Math.sin(layout.originYaw);
    const localX = cos * dx + sin * dy;
    const localY = -sin * dx + cos * dy;
    return {
      x: layout.left + (localX / layout.resolution) * layout.scale,
      y: layout.top + layout.drawHeight - (localY / layout.resolution) * layout.scale,
      heading: -(normalizeYaw(pose?.yaw || 0) - layout.originYaw),
      inside: localX >= 0 && localX <= layout.width * layout.resolution &&
        localY >= 0 && localY <= layout.height * layout.resolution,
    };
  }

  function poseFromDrag(layout, start, end, defaultYaw = 0) {
    const origin = canvasToWorld(layout, start);
    if (!origin) return null;
    const target = canvasToWorld(layout, end || start, { clamp: true });
    const dxPixels = finiteNumber(end?.x ?? start?.x, 'drag end x') - finiteNumber(start?.x, 'drag start x');
    const dyPixels = finiteNumber(end?.y ?? start?.y, 'drag end y') - finiteNumber(start?.y, 'drag start y');
    const yaw = Math.hypot(dxPixels, dyPixels) < 4
      ? normalizeYaw(defaultYaw)
      : normalizeYaw(Math.atan2(target.y - origin.y, target.x - origin.x));
    return Object.freeze({ x: origin.x, y: origin.y, yaw });
  }

  function occupancyCellAtCanvas(layout, cells, point) {
    if (!layout || typeof layout !== 'object') throw new TypeError('map layout is required');
    if (!cells || typeof cells.length !== 'number' || cells.length !== layout.width * layout.height) {
      throw new TypeError('occupancy cells do not match the map dimensions');
    }
    const world = canvasToWorld(layout, point);
    if (!world) return Object.freeze({ inside: false, free: false, value: null, cellX: -1, cellY: -1 });
    const dx = world.x - layout.originX;
    const dy = world.y - layout.originY;
    const cos = Math.cos(layout.originYaw);
    const sin = Math.sin(layout.originYaw);
    const localX = cos * dx + sin * dy;
    const localY = -sin * dx + cos * dy;
    const cellX = Math.floor(localX / layout.resolution);
    const cellY = Math.floor(localY / layout.resolution);
    if (cellX < 0 || cellX >= layout.width || cellY < 0 || cellY >= layout.height) {
      return Object.freeze({ inside: false, free: false, value: null, cellX, cellY });
    }
    const raw = Number(cells[cellY * layout.width + cellX]);
    const value = raw > 127 ? raw - 256 : raw;
    return Object.freeze({ inside: true, free: value === 0, value, cellX, cellY });
  }

  function goalPrecisionText(goal) {
    const evidence = goal?.precision_evidence;
    const result = String(goal?.state || 'idle').toUpperCase();
    const lines = [`Nav2 결과: ${result} · 남은 경로 거리 0은 좌표 오차 0을 뜻하지 않습니다.`];
    if (!evidence || evidence.goal_id !== goal?.goal_id) return [...lines, '목표 오차·정지 증거: 미확인'].join('\n');
    const number = (value, digits = 3) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '미확인';
    const sample = (label, value) => {
      if (!value?.error) return `${label}: 미확인`;
      const yaw = value.error.yaw_rad;
      const degrees = typeof yaw === 'number' && Number.isFinite(yaw) ? yaw * 180 / Math.PI : null;
      return `${label}: XY ${number(value.error.xy_m)} m · yaw ${number(yaw)} rad (${number(degrees, 2)}°) · source ns ${value.stamp_ns || '미확인'}`;
    };
    lines.push(sample(evidence.current?.fresh ? '현재 오차' : '마지막 오차 (현재 신선도 미충족)', evidence.current));
    lines.push(sample('결과 수신 부근 표본', evidence.near_result));
    lines.push(`성공 원시 시각: 미제공 · 결과 수신 ROS ns: ${evidence.result?.received_ros_ns || '미확인'} · 표본 시간차 ${number(evidence.near_result?.offset_from_result_receipt_s)} s`);
    lines.push(sample('2초 정지 관측 후 첫 표본', evidence.after_stop));
    lines.push(`정지 확인: ${evidence.stop?.confirmed_now ? '현재 측정 확인' : '현재 미확인'} · 10cm / 0.10rad 충족: ${evidence.precision?.satisfied_now === true ? '충족' : evidence.precision?.satisfied_now === false ? '미충족' : '미확인'}`);
    lines.push(`pose: ${evidence.current?.frame_id || '미확인'} → ${evidence.current?.body_frame_id || '미확인'} · source ns ${evidence.current?.stamp_ns || '미확인'} · age ${number(evidence.current?.age_s)} s`);
    const window = evidence.stop?.window;
    if (window) lines.push(`정지 관측 ${number(window.observed_stopped_seconds, 2)} s · 후속 ${window.samples} 표본 · 최대 XY ${number(window.max_xy_error_m)} m / yaw ${number(window.max_abs_yaw_error_rad)} rad`);
    const change = evidence.motion_vs_correction;
    lines.push(change ? `결과 부근→정지: 본체 odom 이동 ${number(change.body_odom_translation_m)} m / 회전 ${number(change.body_odom_rotation_rad)} rad · map→odom 변화 ${number(change.map_odom_translation_m)} m / ${number(change.map_odom_rotation_rad)} rad` : '본체 이동 / 지도 보정 분리: 동시각 pose 쌍 미확인');
    const plan = evidence.plan_endpoint;
    lines.push(plan?.request_error ? `관측 경로 끝점 차이: XY ${number(plan.request_error.xy_m)} m / yaw ${number(plan.request_error.yaw_rad)} rad · /plan은 action ID를 포함하지 않아 목표 연관 미확정` : '관측 경로 끝점: 미확인');
    lines.push(`ZERO 전달: ${evidence.zero_command_issued ? '기존 경로 발행 완료 (실제 정지와 별도)' : '미확인'} · bridge ACK: ${evidence.zero_command_issued?.bridge_ack || '미확인'}`);
    lines.push(`goal ${evidence.goal_id} · job ${evidence.context?.job_id || '미확인'} · map revision ${evidence.context?.map_revision || '미확인'}`);
    lines.push(`설정 revision ${evidence.context?.parameters_revision || '미확인'} · 결과 시 live ROS readback ${evidence.effective_at_result?.status || '미확인'}`);
    return lines.join('\n');
  }

  function parameterEvidenceText(evidence) {
    const num = (v) => typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '미확인';
    const saved = evidence?.saved_and_generated?.stored;
    const generated = evidence?.saved_and_generated?.generated_job_yaml;
    const live = evidence?.live_ros;
    const gc = generated?.parameters?.['/controller_server'];
    const lc = live?.parameters?.['/controller_server'];
    return [
      `저장 설정: XY ${num(saved?.values?.xy_goal_tolerance)} m / yaw ${num(saved?.values?.yaw_goal_tolerance)} rad`,
      `job 생성 YAML: XY ${num(gc?.['goal_checker.xy_goal_tolerance'])} m / yaw ${num(gc?.['goal_checker.yaw_goal_tolerance'])} rad · job ${generated?.job_id || '미확인'}`,
      `실행 ROS readback (${live?.status || '미확인'}): XY ${num(lc?.['goal_checker.xy_goal_tolerance'])} m / yaw ${num(lc?.['goal_checker.yaw_goal_tolerance'])} rad · age ${num(live?.age_s)} s`,
    ].join('\n');
  }

  function pipelineActive(snapshot) {
    return PIPELINE_ACTIVE_STATES.includes(String(snapshot?.pipeline?.state || '').toLowerCase());
  }

  function goalActive(snapshot) {
    return GOAL_ACTIVE_STATES.includes(String(snapshot?.goal?.state || '').toLowerCase());
  }

  function manualControlActive(controlSnapshot, localLeaseId = '') {
    if (String(localLeaseId || '').trim()) return true;
    const lease = controlSnapshot?.lease;
    if (!lease?.active) return false;
    const declaredSources = [lease.source, lease.input_source]
      .filter((value) => value !== undefined && value !== null && String(value).trim())
      .map((value) => String(value).trim());
    // A server-owned navigation motion gate is not a manual-control lease.
    // Missing, unknown or conflicting source metadata remains fail-closed.
    return !declaredSources.length || !declaredSources.every((source) => source === 'navigation');
  }

  return Object.freeze({
    GROUPS,
    FIELDS,
    FIELD_KEYS,
    FIELD_BY_KEY,
    TUNED_VALUES,
    PIPELINE_ACTIVE_STATES,
    GOAL_ACTIVE_STATES,
    normalizeYaw,
    coerceParameterValue,
    parameterValues,
    normalizeParameterSnapshot,
    changedParameterValues,
    parameterPatch,
    mapGeometry,
    mapLayout,
    canvasToWorld,
    worldToCanvas,
    poseFromDrag,
    occupancyCellAtCanvas,
    pipelineActive,
    goalActive,
    manualControlActive,
    goalPrecisionText,
    parameterEvidenceText,
    operationalLocalizationStatus,
    navigationPosePreview,
    drawPoseMarker,
    goalPoseOverlay,
    currentRobotOverlay,
  });
}));
