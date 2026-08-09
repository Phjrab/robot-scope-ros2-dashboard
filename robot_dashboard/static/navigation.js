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

    numberField('desired_linear_vel', 'controller', 'Desired linear velocity', 0.25, 0.05, 0.3, 0.01, 'm/s', 'Go2 실내 보행 안전속도이며 bridge 상한 0.30 m/s를 넘을 수 없습니다.'),
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

  function finiteNumber(value, name) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new TypeError(`${name} must be a finite number`);
    return number;
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
  });
}));
