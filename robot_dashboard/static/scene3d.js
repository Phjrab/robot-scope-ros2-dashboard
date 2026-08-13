/*
 * Robot Scope dependency-free 3D scene.
 *
 * Public API:
 *   const scene = new RobotScene3D(canvas, options?);
 *   scene.setPointCloud(cloud, { fit?: boolean });
 *   scene.setRobotPose({ x, y, z, yaw, frameId });
 *   scene.setTrail([{ x, y, z, yaw, frameId }, ...]);
 *   scene.setAxesVisible(boolean); scene.toggleAxesVisible();
 *   scene.setStatus({ online, lidarOnline, message });
 *   scene.resetView(); scene.topView(); scene.frontView();
 *   scene.bindControls({ reset, top, front, axes });
 *   scene.resize(); scene.render(); scene.destroy();
 *
 * `cloud` follows the dashboard PointCloud endpoint shape:
 *   { points: [x, y, z, ...], bounds: { min: [x,y,z], max: [x,y,z] },
 *     frame_id, source_points, sent_points }
 */
(function installRobotScene3D(global) {
  'use strict';

  const TAU = Math.PI * 2;
  const DEG = Math.PI / 180;

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function finite(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function normalizedPointLimit(value, fallback = 10000) {
    if (value == null || value === 'all' || value === Infinity) return Infinity;
    return clamp(Math.floor(finite(value, fallback)), 100, 5_000_000);
  }

  function add(a, b) {
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  }

  function subtract(a, b) {
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  }

  function multiply(a, scalar) {
    return [a[0] * scalar, a[1] * scalar, a[2] * scalar];
  }

  function dot(a, b) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  }

  function cross(a, b) {
    return [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0],
    ];
  }

  function normalize(vector, fallback = [1, 0, 0]) {
    const length = Math.hypot(vector[0], vector[1], vector[2]);
    return length > 1e-9 ? multiply(vector, 1 / length) : fallback.slice();
  }

  function quaternionYaw(value) {
    if (!value) return 0;
    const x = finite(value.x);
    const y = finite(value.y);
    const z = finite(value.z);
    const w = finite(value.w, 1);
    return Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
  }

  function normalizedPose(value) {
    if (!value) return null;
    const root = value.values || value;
    const position = root.position || root.pose?.position || root.pose?.pose?.position || root;
    const orientation = root.orientation || root.pose?.orientation || root.pose?.pose?.orientation;
    const x = Number(position?.x);
    const y = Number(position?.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    const explicitYaw = Number(root.yaw ?? value.yaw);
    return {
      x,
      y,
      z: finite(position?.z),
      roll: finite(root.roll ?? value.roll),
      pitch: finite(root.pitch ?? value.pitch),
      yaw: Number.isFinite(explicitYaw) ? explicitYaw : quaternionYaw(orientation),
      frameId: String(root.frameId || root.frame_id || value.frameId || value.frame_id || ''),
    };
  }

  function niceGridStep(span) {
    const rough = Math.max(span / 16, 0.05);
    const power = Math.pow(10, Math.floor(Math.log10(rough)));
    const fraction = rough / power;
    const factor = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    return factor * power;
  }

  function coordinateMedian(points, coordinate) {
    const available = Math.floor(points.length / 3);
    const sampleCount = Math.min(available, 10001);
    const values = new Array(sampleCount);
    const stride = sampleCount ? available / sampleCount : 1;
    for (let output = 0; output < sampleCount; output += 1) {
      const source = Math.min(available - 1, Math.floor(output * stride));
      values[output] = points[source * 3 + coordinate];
    }
    values.sort((a, b) => a - b);
    const middle = Math.floor(values.length / 2);
    return values.length % 2 ? values[middle] : values[middle - 1] / 2 + values[middle] / 2;
  }

  function reasonableAdvertisedBounds(advertised, sampledBounds, medians, maxRadius) {
    const advertisedMin = advertised?.min;
    const advertisedMax = advertised?.max;
    if (!sampledBounds || advertisedMin?.length < 3 || advertisedMax?.length < 3) return null;
    const min = advertisedMin.slice(0, 3).map(Number);
    const max = advertisedMax.slice(0, 3).map(Number);
    if (![...min, ...max].every(Number.isFinite)) return null;
    const tolerance = Math.max(1e-5, maxRadius * 1e-6);
    for (let axis = 0; axis < 3; axis += 1) {
      if (min[axis] > max[axis]) return null;
      if (min[axis] > sampledBounds.min[axis] + tolerance || max[axis] < sampledBounds.max[axis] - tolerance) return null;
      if (Math.abs(min[axis] - medians[axis]) > maxRadius + tolerance ||
          Math.abs(max[axis] - medians[axis]) > maxRadius + tolerance) return null;
    }
    return { min, max };
  }

  function boundedAdvertisedBounds(advertised, maxRadius) {
    const advertisedMin = advertised?.min;
    const advertisedMax = advertised?.max;
    if (advertisedMin?.length < 3 || advertisedMax?.length < 3) return null;
    const min = advertisedMin.slice(0, 3).map(Number);
    const max = advertisedMax.slice(0, 3).map(Number);
    if (![...min, ...max].every(Number.isFinite)) return null;
    for (let axis = 0; axis < 3; axis += 1) {
      if (min[axis] > max[axis] || max[axis] - min[axis] > maxRadius * 2.01) return null;
    }
    return { min, max };
  }

  function resolveElement(value) {
    if (!value) return null;
    if (typeof value === 'string') return global.document?.querySelector(value) || null;
    return value;
  }

  function browserStorage() {
    try {
      return global.localStorage || null;
    } catch (_) {
      return null;
    }
  }

  function storedBoolean(storage, key, fallback) {
    if (!storage || !key) return fallback;
    try {
      const value = storage.getItem(key);
      if (value === 'true') return true;
      if (value === 'false') return false;
    } catch (_) {
      // Safari private browsing and locked-down kiosk profiles can reject storage.
    }
    return fallback;
  }

  function persistBoolean(storage, key, value) {
    if (!storage || !key) return;
    try {
      storage.setItem(key, value ? 'true' : 'false');
    } catch (_) {
      // Rendering remains usable when preferences cannot be persisted.
    }
  }

  class RobotScene3D {
    constructor(canvas, options = {}) {
      if (!canvas || typeof canvas.getContext !== 'function') {
        throw new TypeError('RobotScene3D requires a canvas element.');
      }
      const context = canvas.getContext('2d', { alpha: false });
      if (!context) throw new Error('RobotScene3D could not acquire a 2D canvas context.');

      this.canvas = canvas;
      this.ctx = context;
      this.options = {
        maxPoints: normalizedPointLimit(options.maxPoints, 10000),
        fov: clamp(finite(options.fov, 48), 24, 90) * DEG,
        minDistance: Math.max(finite(options.minDistance, 0.35), 0.05),
        maxDistance: Math.max(finite(options.maxDistance, 2000), 10),
        pointSize: clamp(finite(options.pointSize, 0.045), 0.008, 0.2),
        maxCloudRadius: clamp(finite(options.maxCloudRadius, 500), 0.1, 1000000),
        groundZ: Number.isFinite(Number(options.groundZ)) ? Number(options.groundZ) : 0,
        autoFitOnFirstCloud: options.autoFitOnFirstCloud !== false,
        showRobot: options.showRobot !== false,
        showTrail: options.showTrail !== false,
        showAxes: options.showAxes !== false,
        background: options.background || '#040a09',
      };
      this._axesStorage = options.storage === undefined ? browserStorage() : options.storage;
      this._axesStorageKey = typeof options.axesStorageKey === 'string'
        ? options.axesStorageKey.trim().slice(0, 160)
        : '';
      const initialDistance = clamp(
        finite(options.initialDistance, 8),
        this.options.minDistance,
        this.options.maxDistance,
      );

      this.width = 1;
      this.height = 1;
      this.dpr = 1;
      this.camera = {
        target: [0, 0, 0.2],
        distance: initialDistance,
        yaw: 45 * DEG,
        pitch: 33 * DEG,
      };
      this._home = {
        target: this.camera.target.slice(),
        distance: this.camera.distance,
        yaw: this.camera.yaw,
        pitch: this.camera.pitch,
      };
      this.cloud = {
        points: new Float32Array(0),
        bounds: null,
        frameId: '',
        sourcePoints: 0,
        stamp: null,
        medians: null,
        rejectedPoints: 0,
        usedAdvertisedBounds: false,
        robotPoseInFrame: null,
      };
      this.robotPose = null;
      this.trail = [];
      this.robotVisible = this.options.showRobot;
      this.trailVisible = this.options.showTrail;
      this.axesVisible = storedBoolean(
        this._axesStorage,
        this._axesStorageKey,
        this.options.showAxes,
      );
      this.status = {
        online: null,
        lidarOnline: null,
        snapshot: false,
        message: '',
      };
      this._hasFittedCloud = false;
      this._destroyed = false;
      this._raf = 0;
      this._drag = null;
      this._basis = null;
      this._staticCanvas = global.document?.createElement?.('canvas') || null;
      this._staticCtx = this._staticCanvas?.getContext?.('2d', { alpha: false }) || null;
      this._staticDirty = true;
      this._interactivePreview = false;
      this._interactionTimer = 0;
      this._controlDisposers = [];
      this._controlElements = {};
      this.cameraMode = 'world';

      canvas.style.touchAction = 'none';
      canvas.style.cursor = 'grab';
      if (!canvas.hasAttribute('role')) canvas.setAttribute('role', 'img');
      if (!canvas.hasAttribute('aria-label')) {
        canvas.setAttribute('aria-label', 'Interactive 3D LiDAR map and robot model');
      }

      this._onPointerDown = this._onPointerDown.bind(this);
      this._onPointerMove = this._onPointerMove.bind(this);
      this._onPointerUp = this._onPointerUp.bind(this);
      this._onWheel = this._onWheel.bind(this);
      this._onContextMenu = (event) => event.preventDefault();
      this._onDoubleClick = () => this.resetView();
      this._onWindowResize = () => this.resize();

      canvas.addEventListener('pointerdown', this._onPointerDown);
      canvas.addEventListener('pointermove', this._onPointerMove);
      canvas.addEventListener('pointerup', this._onPointerUp);
      canvas.addEventListener('pointercancel', this._onPointerUp);
      canvas.addEventListener('wheel', this._onWheel, { passive: false });
      canvas.addEventListener('contextmenu', this._onContextMenu);
      canvas.addEventListener('dblclick', this._onDoubleClick);

      if (typeof global.ResizeObserver === 'function') {
        this._resizeObserver = new global.ResizeObserver(() => this.resize());
        this._resizeObserver.observe(canvas);
      } else {
        global.addEventListener?.('resize', this._onWindowResize);
      }

      this.resize();
    }

    setPointCloud(payload, options = {}) {
      const cloud = payload && payload.points != null ? payload : { points: payload };
      const input = cloud?.points;
      const limit = this.options.maxPoints;
      let available = 0;
      let nested = false;

      if (input && typeof input.length === 'number') {
        nested = input.length > 0 && input[0] != null && typeof input[0] !== 'number' && typeof input[0].length === 'number';
        available = nested ? input.length : Math.floor(input.length / 3);
      }

      const wanted = Math.min(available, limit);
      const prevalidated = cloud?.prevalidated === true && !nested && input instanceof Float32Array;
      if (prevalidated) {
        let points;
        if (wanted === available) {
          points = input.subarray(0, wanted * 3);
        } else {
          points = new Float32Array(wanted * 3);
          const trustedStride = wanted > 0 ? available / wanted : 1;
          for (let outputIndex = 0; outputIndex < wanted; outputIndex += 1) {
            const sourceIndex = Math.min(available - 1, Math.floor(outputIndex * trustedStride)) * 3;
            points[outputIndex * 3] = input[sourceIndex];
            points[outputIndex * 3 + 1] = input[sourceIndex + 1];
            points[outputIndex * 3 + 2] = input[sourceIndex + 2];
          }
        }
        const advertisedBounds = boundedAdvertisedBounds(cloud?.bounds, this.options.maxCloudRadius);
        let bounds = advertisedBounds;
        if (!bounds && points.length) {
          let minX = Infinity, minY = Infinity, minZ = Infinity;
          let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
          for (let index = 0; index < points.length; index += 3) {
            const x = points[index];
            const y = points[index + 1];
            const z = points[index + 2];
            minX = Math.min(minX, x); minY = Math.min(minY, y); minZ = Math.min(minZ, z);
            maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); maxZ = Math.max(maxZ, z);
          }
          bounds = { min: [minX, minY, minZ], max: [maxX, maxY, maxZ] };
        }
        this.cloud = {
          points,
          bounds,
          frameId: String(cloud?.frame_id || cloud?.frameId || ''),
          sourcePoints: Math.max(0, Math.floor(finite(cloud?.source_points, available))),
          stamp: cloud?.stamp_ns ?? cloud?.stamp ?? null,
          medians: null,
          rejectedPoints: 0,
          usedAdvertisedBounds: Boolean(advertisedBounds),
          robotPoseInFrame: normalizedPose(cloud?.robot_pose_in_frame || cloud?.robotPoseInFrame),
        };
        this._invalidateStatic();
        const shouldFit = options.fit === true ||
          (options.fit !== false && !this._hasFittedCloud && wanted > 0 && this.options.autoFitOnFirstCloud);
        if (shouldFit) {
          this.fitToPointCloud(false);
          this._hasFittedCloud = true;
        }
        this.render();
        return Math.floor(points.length / 3);
      }
      const sampled = new Float32Array(wanted * 3);
      let written = 0;
      const stride = wanted > 0 ? available / wanted : 1;

      for (let outputIndex = 0; outputIndex < wanted; outputIndex += 1) {
        const sourceIndex = Math.min(available - 1, Math.floor(outputIndex * stride));
        const source = nested ? input[sourceIndex] : input;
        const offset = nested ? 0 : sourceIndex * 3;
        const rawX = source[offset];
        const rawY = source[offset + 1];
        const rawZ = source[offset + 2];
        if (rawX == null || rawY == null || rawZ == null) continue;
        const x = Number(rawX);
        const y = Number(rawY);
        const z = Number(rawZ);
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
        sampled[written * 3] = x;
        sampled[written * 3 + 1] = y;
        sampled[written * 3 + 2] = z;
        written += 1;
      }

      const finitePoints = written === wanted ? sampled : sampled.slice(0, written * 3);
      let points = new Float32Array(0);
      let bounds = null;
      let medians = null;
      let rejectedPoints = 0;
      let usedAdvertisedBounds = false;
      if (written) {
        medians = [
          coordinateMedian(finitePoints, 0),
          coordinateMedian(finitePoints, 1),
          coordinateMedian(finitePoints, 2),
        ];
        const radiusSquared = this.options.maxCloudRadius * this.options.maxCloudRadius;
        const filtered = finitePoints;
        let accepted = 0;
        let minX = Infinity, minY = Infinity, minZ = Infinity;
        let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
        for (let index = 0; index < finitePoints.length; index += 3) {
          const x = finitePoints[index];
          const y = finitePoints[index + 1];
          const z = finitePoints[index + 2];
          const dx = x - medians[0];
          const dy = y - medians[1];
          const dz = z - medians[2];
          if (dx * dx + dy * dy + dz * dz > radiusSquared) {
            rejectedPoints += 1;
            continue;
          }
          filtered[accepted * 3] = x;
          filtered[accepted * 3 + 1] = y;
          filtered[accepted * 3 + 2] = z;
          minX = Math.min(minX, x); minY = Math.min(minY, y); minZ = Math.min(minZ, z);
          maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); maxZ = Math.max(maxZ, z);
          accepted += 1;
        }
        points = accepted === written ? filtered : filtered.slice(0, accepted * 3);
        if (accepted) {
          const sampledBounds = { min: [minX, minY, minZ], max: [maxX, maxY, maxZ] };
          const advertisedBounds = reasonableAdvertisedBounds(
            cloud?.bounds,
            sampledBounds,
            medians,
            this.options.maxCloudRadius,
          );
          bounds = advertisedBounds || sampledBounds;
          usedAdvertisedBounds = Boolean(advertisedBounds);
        }
      }

      this.cloud = {
        points,
        bounds,
        frameId: String(cloud?.frame_id || cloud?.frameId || ''),
        sourcePoints: Math.max(0, Math.floor(finite(cloud?.source_points, available))),
        stamp: cloud?.stamp_ns ?? cloud?.stamp ?? null,
        medians,
        rejectedPoints,
        usedAdvertisedBounds,
        robotPoseInFrame: normalizedPose(cloud?.robot_pose_in_frame || cloud?.robotPoseInFrame),
      };
      this._invalidateStatic();

      const shouldFit = options.fit === true ||
        (options.fit !== false && !this._hasFittedCloud && written > 0 && this.options.autoFitOnFirstCloud);
      if (shouldFit) {
        this.fitToPointCloud(false);
        this._hasFittedCloud = true;
      }
      this.render();
      return Math.floor(points.length / 3);
    }

    updatePointCloud(payload, options) {
      return this.setPointCloud(payload, options);
    }

    setCloud(payload, options) {
      return this.setPointCloud(payload, options);
    }

    clearPointCloud() {
      this.cloud = {
        points: new Float32Array(0), bounds: null, frameId: '', sourcePoints: 0, stamp: null,
        medians: null, rejectedPoints: 0, usedAdvertisedBounds: false, robotPoseInFrame: null,
      };
      this._hasFittedCloud = false;
      this._invalidateStatic();
      this.render();
    }

    setPointLimit(value) {
      this.options.maxPoints = normalizedPointLimit(value, this.options.maxPoints);
      this._invalidateStatic();
      return this.options.maxPoints;
    }

    setRobotPose(value) {
      this.robotPose = normalizedPose(value);
      if (this.cameraMode === 'follow' && this.robotPose) {
        const alpha = 0.16;
        const moveX = (this.robotPose.x - this.camera.target[0]) * alpha;
        const moveY = (this.robotPose.y - this.camera.target[1]) * alpha;
        if (Math.abs(moveX) + Math.abs(moveY) > 0.0001) {
          this.camera.target[0] += moveX;
          this.camera.target[1] += moveY;
          this._interactivePreview = true;
          if (this._interactionTimer) global.clearTimeout?.(this._interactionTimer);
          this._interactionTimer = global.setTimeout?.(() => {
            this._interactionTimer = 0;
            this._interactivePreview = false;
            this._invalidateStatic();
            this.render();
          }, 180) || 0;
          this._invalidateStatic();
        }
      }
      this.render();
      return Boolean(this.robotPose);
    }

    setCameraMode(value) {
      this.cameraMode = value === 'follow' ? 'follow' : 'world';
      const control = this._controlElements.follow;
      if (control) {
        control.textContent = this.cameraMode === 'follow' ? 'FOLLOW' : 'WORLD';
        control.setAttribute('aria-pressed', this.cameraMode === 'follow' ? 'true' : 'false');
      }
      this._invalidateStatic();
      this.render();
      return this.cameraMode;
    }

    toggleCameraMode() {
      return this.setCameraMode(this.cameraMode === 'follow' ? 'world' : 'follow');
    }

    updatePose(value) {
      return this.setRobotPose(value);
    }

    setPose(value) {
      return this.setRobotPose(value);
    }

    setTrail(values) {
      this.trail = Array.isArray(values) ? values.map(normalizedPose).filter(Boolean).slice(-400) : [];
      this.render();
    }

    addTrailPose(value) {
      const pose = normalizedPose(value);
      if (!pose) return false;
      const previous = this.trail[this.trail.length - 1];
      if (!previous || Math.hypot(pose.x - previous.x, pose.y - previous.y, pose.z - previous.z) > 0.02 ||
          Math.abs(Math.atan2(Math.sin(pose.yaw - previous.yaw), Math.cos(pose.yaw - previous.yaw))) > 0.03) {
        this.trail.push(pose);
        if (this.trail.length > 400) this.trail.splice(0, this.trail.length - 400);
        this.render();
      }
      return true;
    }

    clearTrail() {
      this.trail = [];
      this.render();
    }

    setRobotVisible(visible) {
      this.robotVisible = Boolean(visible);
      this.render();
    }

    showRobot(visible = true) {
      this.setRobotVisible(visible);
    }

    setTrailVisible(visible) {
      this.trailVisible = Boolean(visible);
      this.render();
    }

    setAxesVisible(visible, persist = true) {
      this.axesVisible = Boolean(visible);
      if (persist) {
        persistBoolean(this._axesStorage, this._axesStorageKey, this.axesVisible);
      }
      const control = this._controlElements.axes;
      if (control) {
        control.setAttribute('aria-pressed', this.axesVisible ? 'true' : 'false');
        control.title = this.axesVisible ? 'XYZ 축 숨기기' : 'XYZ 축 표시';
      }
      this._invalidateStatic();
      this.render();
      return this.axesVisible;
    }

    toggleAxesVisible() {
      return this.setAxesVisible(!this.axesVisible);
    }

    setStatus(value = {}) {
      if (typeof value === 'boolean') value = { online: value };
      if (Object.prototype.hasOwnProperty.call(value, 'online')) this.status.online = value.online == null ? null : Boolean(value.online);
      if (Object.prototype.hasOwnProperty.call(value, 'lidarOnline')) this.status.lidarOnline = value.lidarOnline == null ? null : Boolean(value.lidarOnline);
      if (Object.prototype.hasOwnProperty.call(value, 'snapshot')) this.status.snapshot = Boolean(value.snapshot);
      if (Object.prototype.hasOwnProperty.call(value, 'message')) this.status.message = String(value.message || '');
      this.render();
    }

    setOnline(online, message = '') {
      this.setStatus({ online, message });
    }

    setLidarOnline(online) {
      this.setStatus({ lidarOnline: online });
    }

    setGroundZ(z) {
      if (Number.isFinite(Number(z))) {
        this.options.groundZ = Number(z);
        this._invalidateStatic();
        this.render();
      }
    }

    fitToPointCloud(render = true) {
      const bounds = this.cloud.bounds;
      if (!bounds) {
        this.camera.target = [0, 0, 0.2];
        this.camera.distance = 8;
      } else {
        const min = bounds.min;
        const max = bounds.max;
        const center = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
        const radius = Math.max(Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2, 0.75);
        this.camera.target = center;
        this.camera.distance = clamp(radius / Math.tan(this.options.fov / 2) * 1.18, this.options.minDistance, this.options.maxDistance);
      }
      this._saveHome();
      this._invalidateStatic();
      if (render) this.render();
    }

    resetView() {
      if (this.cloud.bounds) this.fitToPointCloud(false);
      else {
        this.camera.target = this._home.target.slice();
        this.camera.distance = this._home.distance;
      }
      this.camera.yaw = 45 * DEG;
      this.camera.pitch = 33 * DEG;
      this._saveHome();
      this._updateControlState('reset');
      this._invalidateStatic();
      this.render();
    }

    topView() {
      if (this.cloud.bounds) this.fitToPointCloud(false);
      this.camera.yaw = -90 * DEG;
      this.camera.pitch = 88 * DEG;
      this._updateControlState('top');
      this._invalidateStatic();
      this.render();
    }

    frontView() {
      if (this.cloud.bounds) this.fitToPointCloud(false);
      this.camera.yaw = 0;
      this.camera.pitch = 8 * DEG;
      this._updateControlState('front');
      this._invalidateStatic();
      this.render();
    }

    isometricView() {
      this.resetView();
    }

    setViewPreset(name) {
      if (name === 'top') this.topView();
      else if (name === 'front') this.frontView();
      else this.resetView();
    }

    bindControls(controls = {}) {
      this.unbindControls();
      const actions = {
        reset: () => this.resetView(),
        top: () => this.topView(),
        front: () => this.frontView(),
        follow: () => this.toggleCameraMode(),
        axes: () => this.toggleAxesVisible(),
      };
      Object.entries(actions).forEach(([name, handler]) => {
        const element = resolveElement(controls[name]);
        if (!element) return;
        element.addEventListener('click', handler);
        this._controlElements[name] = element;
        this._controlDisposers.push(() => element.removeEventListener('click', handler));
      });
      this.setCameraMode(this.cameraMode);
      this.setAxesVisible(this.axesVisible, false);
      return () => this.unbindControls();
    }

    unbindControls() {
      this._controlDisposers.splice(0).forEach((dispose) => dispose());
      this._controlElements = {};
    }

    resize() {
      if (this._destroyed) return;
      const rect = this.canvas.getBoundingClientRect?.() || {};
      const cssWidth = Math.max(1, Math.round(rect.width || this.canvas.clientWidth || this.canvas.width || 640));
      const cssHeight = Math.max(1, Math.round(rect.height || this.canvas.clientHeight || this.canvas.height || 360));
      const dpr = clamp(finite(global.devicePixelRatio, 1), 1, 2.5);
      const pixelWidth = Math.round(cssWidth * dpr);
      const pixelHeight = Math.round(cssHeight * dpr);
      this.width = cssWidth;
      this.height = cssHeight;
      this.dpr = dpr;
      if (this.canvas.width !== pixelWidth || this.canvas.height !== pixelHeight) {
        this.canvas.width = pixelWidth;
        this.canvas.height = pixelHeight;
        this._invalidateStatic();
      }
      this.render();
    }

    render() {
      if (this._destroyed || this._raf) return;
      const request = global.requestAnimationFrame || ((callback) => global.setTimeout(callback, 16));
      this._raf = request(() => {
        this._raf = 0;
        if (!this._destroyed) this._draw();
      });
    }

    renderNow() {
      if (!this._destroyed) this._draw();
    }

    destroy() {
      if (this._destroyed) return;
      this._destroyed = true;
      const cancel = global.cancelAnimationFrame || global.clearTimeout;
      if (this._raf) cancel?.(this._raf);
      if (this._interactionTimer) global.clearTimeout?.(this._interactionTimer);
      this._raf = 0;
      this.unbindControls();
      this._resizeObserver?.disconnect();
      global.removeEventListener?.('resize', this._onWindowResize);
      this.canvas.removeEventListener('pointerdown', this._onPointerDown);
      this.canvas.removeEventListener('pointermove', this._onPointerMove);
      this.canvas.removeEventListener('pointerup', this._onPointerUp);
      this.canvas.removeEventListener('pointercancel', this._onPointerUp);
      this.canvas.removeEventListener('wheel', this._onWheel);
      this.canvas.removeEventListener('contextmenu', this._onContextMenu);
      this.canvas.removeEventListener('dblclick', this._onDoubleClick);
      this.canvas.style.cursor = '';
    }

    _saveHome() {
      this._home = {
        target: this.camera.target.slice(),
        distance: this.camera.distance,
        yaw: this.camera.yaw,
        pitch: this.camera.pitch,
      };
    }

    _updateControlState(active) {
      Object.entries(this._controlElements).forEach(([name, element]) => {
        const pressed = name === 'follow'
          ? this.cameraMode === 'follow'
          : name === 'axes'
            ? this.axesVisible
            : name === active;
        element.setAttribute('aria-pressed', pressed ? 'true' : 'false');
      });
    }

    _onPointerDown(event) {
      if (this._destroyed) return;
      const pan = event.button !== 0 || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey;
      this._drag = {
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        mode: pan ? 'pan' : 'orbit',
      };
      this._interactivePreview = true;
      this.canvas.setPointerCapture?.(event.pointerId);
      this.canvas.style.cursor = pan ? 'move' : 'grabbing';
      event.preventDefault();
    }

    _onPointerMove(event) {
      if (!this._drag || this._drag.id !== event.pointerId) return;
      const dx = event.clientX - this._drag.x;
      const dy = event.clientY - this._drag.y;
      this._drag.x = event.clientX;
      this._drag.y = event.clientY;
      if (this._drag.mode === 'orbit') {
        this.camera.yaw -= dx * 0.007;
        this.camera.pitch = clamp(this.camera.pitch - dy * 0.006, -82 * DEG, 88 * DEG);
      } else {
        const basis = this._cameraBasis();
        const worldPerPixel = 2 * this.camera.distance * Math.tan(this.options.fov / 2) / Math.max(this.height, 1);
        this.camera.target = add(
          this.camera.target,
          add(multiply(basis.right, -dx * worldPerPixel), multiply(basis.up, dy * worldPerPixel)),
        );
      }
      this._updateControlState('');
      this._invalidateStatic();
      this.render();
      event.preventDefault();
    }

    _onPointerUp(event) {
      if (!this._drag || this._drag.id !== event.pointerId) return;
      this.canvas.releasePointerCapture?.(event.pointerId);
      this._drag = null;
      this._interactivePreview = false;
      this.canvas.style.cursor = 'grab';
      this._invalidateStatic();
      this.render();
    }

    _onWheel(event) {
      this._interactivePreview = true;
      const factor = Math.exp(clamp(event.deltaY, -240, 240) * 0.0018);
      this.camera.distance = clamp(this.camera.distance * factor, this.options.minDistance, this.options.maxDistance);
      this._updateControlState('');
      this._invalidateStatic();
      this.render();
      if (this._interactionTimer) global.clearTimeout?.(this._interactionTimer);
      this._interactionTimer = global.setTimeout?.(() => {
        this._interactionTimer = 0;
        this._interactivePreview = false;
        this._invalidateStatic();
        this.render();
      }, 140) || 0;
      event.preventDefault();
    }

    _cameraBasis() {
      const { target, distance, yaw, pitch } = this.camera;
      const cosPitch = Math.cos(pitch);
      const offset = [
        distance * cosPitch * Math.cos(yaw),
        distance * cosPitch * Math.sin(yaw),
        distance * Math.sin(pitch),
      ];
      const position = add(target, offset);
      const forward = normalize(subtract(target, position), [0, 0, -1]);
      let right = normalize(cross(forward, [0, 0, 1]), [1, 0, 0]);
      if (Math.abs(dot(forward, [0, 0, 1])) > 0.9999) right = [1, 0, 0];
      const up = normalize(cross(right, forward), [0, 1, 0]);
      const focal = this.height / (2 * Math.tan(this.options.fov / 2));
      this._basis = { position, forward, right, up, focal };
      return this._basis;
    }

    _project(point) {
      const basis = this._basis || this._cameraBasis();
      const relative = subtract(point, basis.position);
      const depth = dot(relative, basis.forward);
      if (depth <= Math.max(0.015, this.camera.distance * 0.001)) return null;
      const scale = basis.focal / depth;
      return {
        x: this.width / 2 + dot(relative, basis.right) * scale,
        y: this.height / 2 - dot(relative, basis.up) * scale,
        depth,
        scale,
      };
    }

    _invalidateStatic() {
      this._staticDirty = true;
      this._basis = null;
    }

    _fillBackground(ctx) {
      const background = ctx.createLinearGradient(0, 0, 0, this.height);
      background.addColorStop(0, '#06110f');
      background.addColorStop(0.58, this.options.background);
      background.addColorStop(1, '#020706');
      ctx.fillStyle = background;
      ctx.fillRect(0, 0, this.width, this.height);
    }

    _rebuildStaticLayer() {
      if (!this._staticCanvas || !this._staticCtx) return false;
      const pixelWidth = Math.max(1, Math.round(this.width * this.dpr));
      const pixelHeight = Math.max(1, Math.round(this.height * this.dpr));
      if (this._staticCanvas.width !== pixelWidth || this._staticCanvas.height !== pixelHeight) {
        this._staticCanvas.width = pixelWidth;
        this._staticCanvas.height = pixelHeight;
      }
      const mainContext = this.ctx;
      const ctx = this._staticCtx;
      this.ctx = ctx;
      ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      ctx.clearRect(0, 0, this.width, this.height);
      this._fillBackground(ctx);
      this._basis = null;
      this._cameraBasis();
      this._drawGrid();
      this._drawPointCloud();
      if (this.axesVisible) this._drawWorldAxes();
      this.ctx = mainContext;
      this._staticDirty = false;
      return true;
    }

    _draw() {
      this.resizeIfNeeded();
      const ctx = this.ctx;
      const cached = this._staticCtx && (!this._staticDirty || this._rebuildStaticLayer());
      if (cached) {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        ctx.drawImage(this._staticCanvas, 0, 0);
      } else {
        ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        ctx.clearRect(0, 0, this.width, this.height);
        this._fillBackground(ctx);
        this._basis = null;
        this._cameraBasis();
        this._drawGrid();
        this._drawPointCloud();
        if (this.axesVisible) this._drawWorldAxes();
      }
      ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      this._basis = null;
      this._cameraBasis();
      if (this.trailVisible) this._drawTrail();
      if (this.robotVisible) this._drawRobot();
      this._drawHud();
    }

    resizeIfNeeded() {
      const rect = this.canvas.getBoundingClientRect?.();
      if (!rect?.width || !rect?.height) return;
      const width = Math.max(1, Math.round(rect.width));
      const height = Math.max(1, Math.round(rect.height));
      const dpr = clamp(finite(global.devicePixelRatio, 1), 1, 2.5);
      if (width !== this.width || height !== this.height || dpr !== this.dpr) {
        this.width = width;
        this.height = height;
        this.dpr = dpr;
        this.canvas.width = Math.round(width * dpr);
        this.canvas.height = Math.round(height * dpr);
        this._invalidateStatic();
      }
    }

    _sceneSpan() {
      const bounds = this.cloud.bounds;
      if (!bounds) return Math.max(this.camera.distance, 8);
      return Math.max(bounds.max[0] - bounds.min[0], bounds.max[1] - bounds.min[1], 2);
    }

    _drawGrid() {
      const ctx = this.ctx;
      const span = this._sceneSpan();
      const step = niceGridStep(span);
      const half = Math.ceil(Math.max(span * 0.68, step * 8) / step) * step;
      const centerX = Math.round(this.camera.target[0] / step) * step;
      const centerY = Math.round(this.camera.target[1] / step) * step;
      const z = this.options.groundZ;
      const count = Math.min(42, Math.ceil((half * 2) / step));
      const start = -Math.floor(count / 2) * step;

      ctx.save();
      ctx.lineWidth = 1;
      for (let index = 0; index <= count; index += 1) {
        const offset = start + index * step;
        const major = Math.abs(Math.round(offset / step)) % 5 === 0;
        ctx.strokeStyle = major ? 'rgba(99, 185, 159, .20)' : 'rgba(99, 185, 159, .075)';
        this._stroke3DLine([centerX + offset, centerY - half, z], [centerX + offset, centerY + half, z]);
        this._stroke3DLine([centerX - half, centerY + offset, z], [centerX + half, centerY + offset, z]);
      }
      ctx.restore();
    }

    _drawPointCloud() {
      const points = this.cloud.points;
      if (!points.length) return;
      const ctx = this.ctx;
      const bounds = this.cloud.bounds;
      const minZ = bounds?.min?.[2] ?? 0;
      const spanZ = Math.max((bounds?.max?.[2] ?? 1) - minZ, 0.15);
      const bins = Array.from({ length: 14 }, () => []);

      const available = Math.floor(points.length / 3);
      const previewLimit = this._interactivePreview ? 20000 : available;
      const stride = Math.max(1, Math.ceil(available / Math.max(1, previewLimit)));
      for (let index = 0; index < points.length; index += 3 * stride) {
        const projected = this._project([points[index], points[index + 1], points[index + 2]]);
        if (!projected || projected.x < -4 || projected.x > this.width + 4 || projected.y < -4 || projected.y > this.height + 4) continue;
        const heightRatio = clamp((points[index + 2] - minZ) / spanZ, 0, 1);
        const bin = Math.min(bins.length - 1, Math.floor(heightRatio * bins.length));
        const size = clamp(this.options.pointSize * projected.scale, 1, 4.2);
        bins[bin].push(projected.x, projected.y, size);
      }

      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      bins.forEach((values, index) => {
        if (!values.length) return;
        const ratio = index / Math.max(bins.length - 1, 1);
        const hue = 181 - ratio * 135;
        ctx.fillStyle = `hsla(${hue}, 82%, ${58 + ratio * 10}%, .76)`;
        ctx.beginPath();
        for (let pointIndex = 0; pointIndex < values.length; pointIndex += 3) {
          const x = values[pointIndex];
          const y = values[pointIndex + 1];
          const size = values[pointIndex + 2];
          ctx.rect(x - size / 2, y - size / 2, size, size);
        }
        ctx.fill();
      });
      ctx.restore();
    }

    _effectiveRobotPose() {
      const pose = this.robotPose;
      const cloudFrame = this.cloud.frameId;
      const mismatch = Boolean(pose && cloudFrame && pose.frameId && cloudFrame !== pose.frameId);
      if (pose && !mismatch) return { ...pose, preview: false, frameMismatch: false };
      if (pose && mismatch) {
        const sensorPose = this.cloud.robotPoseInFrame;
        if (!sensorPose) return null;
        return {
          ...sensorPose,
          preview: false,
          frameMismatch: true,
          sensorRelative: true,
        };
      }
      if (!pose && this.cloud.robotPoseInFrame) {
        return {
          ...this.cloud.robotPoseInFrame,
          preview: true,
          frameMismatch: true,
          sensorRelative: true,
        };
      }
      const center = this.cloud.bounds ? [
        (this.cloud.bounds.min[0] + this.cloud.bounds.max[0]) / 2,
        (this.cloud.bounds.min[1] + this.cloud.bounds.max[1]) / 2,
      ] : this.camera.target;
      return {
        x: center[0],
        y: center[1],
        z: this.options.groundZ,
        roll: pose?.roll || 0,
        pitch: pose?.pitch || 0,
        yaw: pose?.yaw || 0,
        frameId: pose?.frameId || '',
        preview: !pose,
        frameMismatch: false,
      };
    }

    _displayTrail() {
      if (!this.trail.length) return [];
      const pose = this.robotPose;
      const mismatch = Boolean(pose && this.cloud.frameId && pose.frameId && this.cloud.frameId !== pose.frameId);
      if (!mismatch) return this.trail;
      const anchor = this._effectiveRobotPose();
      if (!anchor || anchor.sensorRelative) return [];
      return this.trail.map((point) => ({
        ...point,
        x: anchor.x + point.x - pose.x,
        y: anchor.y + point.y - pose.y,
        z: anchor.z + point.z - pose.z,
      }));
    }

    _drawTrail() {
      const trail = this._displayTrail();
      if (trail.length < 2) return;
      const projected = trail.map((pose) => this._project([pose.x, pose.y, pose.z + 0.035])).filter(Boolean);
      if (projected.length < 2) return;
      const ctx = this.ctx;
      ctx.save();
      ctx.strokeStyle = 'rgba(162, 139, 255, .78)';
      ctx.lineWidth = 1.6;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      projected.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
      ctx.stroke();
      ctx.setLineDash([]);
      projected.forEach((point, index) => {
        const alpha = 0.15 + 0.55 * ((index + 1) / projected.length);
        ctx.fillStyle = `rgba(187, 169, 255, ${alpha})`;
        ctx.beginPath();
        ctx.arc(point.x, point.y, 1.2 + 1.3 * index / projected.length, 0, TAU);
        ctx.fill();
      });
      ctx.restore();
    }

    _drawWorldAxes() {
      const origin = [this.camera.target[0], this.camera.target[1], this.options.groundZ];
      const length = niceGridStep(this._sceneSpan()) * 2.2;
      const axes = [
        { end: [origin[0] + length, origin[1], origin[2]], color: '#ff737d', label: 'X' },
        { end: [origin[0], origin[1] + length, origin[2]], color: '#68e4a8', label: 'Y' },
        { end: [origin[0], origin[1], origin[2] + length], color: '#6eb7ff', label: 'Z' },
      ];
      const ctx = this.ctx;
      ctx.save();
      ctx.lineWidth = 1.8;
      axes.forEach((axis) => {
        ctx.strokeStyle = axis.color;
        this._stroke3DLine(origin, axis.end);
        const point = this._project(axis.end);
        if (!point) return;
        ctx.fillStyle = axis.color;
        ctx.font = '700 10px ui-monospace, SFMono-Regular, Menlo, monospace';
        ctx.fillText(axis.label, point.x + 4, point.y - 4);
      });
      ctx.restore();
    }

    _robotWorldPoint(local, pose, scale) {
      const cos = Math.cos(pose.yaw);
      const sin = Math.sin(pose.yaw);
      const x = local[0] * scale;
      const y = local[1] * scale;
      return [
        pose.x + cos * x - sin * y,
        pose.y + sin * x + cos * y,
        pose.z + local[2] * scale,
      ];
    }

    _drawRobot() {
      const pose = this._effectiveRobotPose();
      if (!pose) return;
      const worldPerPixel = 2 * this.camera.distance * Math.tan(this.options.fov / 2) / Math.max(this.height, 1);
      const scale = clamp(Math.max(1, worldPerPixel * 44 / 0.72), 1, 7);
      const ctx = this.ctx;
      const legs = [];
      const hips = [
        [0.25, 0.18, 0.39], [0.25, -0.18, 0.39],
        [-0.25, 0.18, 0.39], [-0.25, -0.18, 0.39],
      ];

      hips.forEach((hip) => {
        const frontSign = hip[0] > 0 ? 1 : -1;
        const sideSign = hip[1] > 0 ? 1 : -1;
        const knee = [hip[0] + frontSign * 0.065, hip[1] + sideSign * 0.025, 0.20];
        const foot = [hip[0] + frontSign * 0.14, hip[1] + sideSign * 0.045, 0.02];
        const hipWorld = this._robotWorldPoint(hip, pose, scale);
        const kneeWorld = this._robotWorldPoint(knee, pose, scale);
        const footWorld = this._robotWorldPoint(foot, pose, scale);
        const depth = [hipWorld, kneeWorld, footWorld].map((point) => this._project(point)?.depth || 0).reduce((a, b) => a + b, 0) / 3;
        legs.push({ hipWorld, kneeWorld, footWorld, depth });
      });

      ctx.save();
      ctx.shadowColor = pose.frameMismatch || pose.preview ? 'rgba(255, 198, 109, .58)' : 'rgba(125, 240, 182, .72)';
      ctx.shadowBlur = 10;
      legs.sort((a, b) => b.depth - a.depth).forEach((leg) => {
        this._drawRobotLimb(leg.hipWorld, leg.kneeWorld, '#8bbdb0', 4.6);
        this._drawRobotLimb(leg.kneeWorld, leg.footWorld, '#c9ffe6', 3.8);
        this._drawJoint(leg.hipWorld, 3.8, '#1a6b55');
        this._drawJoint(leg.kneeWorld, 3.3, '#9be7c5');
        this._drawJoint(leg.footWorld, 3.1, '#d9fff0');
      });

      this._drawCuboid(this._robotWorldPoint([0, 0, 0.44], pose, scale), [0.70 * scale, 0.31 * scale, 0.18 * scale], pose.yaw, {
        fill: pose.frameMismatch || pose.preview ? 'rgba(113, 84, 40, .88)' : 'rgba(23, 91, 70, .92)',
        side: pose.frameMismatch || pose.preview ? 'rgba(76, 58, 33, .9)' : 'rgba(12, 56, 45, .95)',
        stroke: pose.frameMismatch || pose.preview ? '#ffd38f' : '#bcffe2',
      });
      this._drawCuboid(this._robotWorldPoint([0.41, 0, 0.47], pose, scale), [0.17 * scale, 0.25 * scale, 0.15 * scale], pose.yaw, {
        fill: 'rgba(204, 255, 232, .92)', side: 'rgba(73, 145, 117, .96)', stroke: '#edfff7',
      });
      this._drawCuboid(this._robotWorldPoint([-0.04, 0, 0.555], pose, scale), [0.28 * scale, 0.20 * scale, 0.035 * scale], pose.yaw, {
        fill: 'rgba(62, 214, 163, .94)', side: 'rgba(22, 108, 81, .94)', stroke: '#9fffd6',
      });

      const nose = this._project(this._robotWorldPoint([0.51, 0, 0.49], pose, scale));
      if (nose) {
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(nose.x, nose.y, 2.7, 0, TAU);
        ctx.fill();
      }
      ctx.restore();

      const labelAnchor = this._project(this._robotWorldPoint([0, 0, 0.78], pose, scale));
      if (labelAnchor) this._drawRobotLabel(labelAnchor, pose);
    }

    _drawRobotLimb(start, end, color, width) {
      const a = this._project(start);
      const b = this._project(end);
      if (!a || !b) return;
      const ctx = this.ctx;
      ctx.strokeStyle = 'rgba(3, 12, 10, .9)';
      ctx.lineWidth = width + 2.4;
      ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }

    _drawJoint(point, radius, color) {
      const projected = this._project(point);
      if (!projected) return;
      const ctx = this.ctx;
      ctx.fillStyle = color;
      ctx.strokeStyle = 'rgba(230, 255, 244, .72)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, radius, 0, TAU);
      ctx.fill();
      ctx.stroke();
    }

    _drawCuboid(center, dimensions, yaw, colors) {
      const [dx, dy, dz] = dimensions.map((value) => value / 2);
      const local = [
        [-dx, -dy, -dz], [dx, -dy, -dz], [dx, dy, -dz], [-dx, dy, -dz],
        [-dx, -dy, dz], [dx, -dy, dz], [dx, dy, dz], [-dx, dy, dz],
      ];
      const cos = Math.cos(yaw);
      const sin = Math.sin(yaw);
      const vertices = local.map((point) => [
        center[0] + cos * point[0] - sin * point[1],
        center[1] + sin * point[0] + cos * point[1],
        center[2] + point[2],
      ]).map((point) => this._project(point));
      if (vertices.some((point) => !point)) return;
      const faces = [
        [0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1],
        [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0],
      ].map((indices, index) => ({
        indices,
        depth: indices.reduce((sum, vertex) => sum + vertices[vertex].depth, 0) / indices.length,
        fill: index === 1 ? colors.fill : colors.side,
      })).sort((a, b) => b.depth - a.depth);
      const ctx = this.ctx;
      faces.forEach((face) => {
        ctx.beginPath();
        face.indices.forEach((index, vertexIndex) => {
          const point = vertices[index];
          if (vertexIndex) ctx.lineTo(point.x, point.y); else ctx.moveTo(point.x, point.y);
        });
        ctx.closePath();
        ctx.fillStyle = face.fill;
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 0.85;
        ctx.fill();
        ctx.stroke();
      });
    }

    _drawRobotLabel(anchor, pose) {
      const ctx = this.ctx;
      const modelLabel = String(this._robotModelLabel || 'ROBOT').trim().toUpperCase();
      const primary = pose.sensorRelative ? `${modelLabel} · SENSOR EXTRINSIC` : pose.frameMismatch ? 'FRAME MISMATCH' : pose.preview ? `${modelLabel} · PREVIEW` : `${modelLabel} · LIVE POSE`;
      const secondary = this.robotPose
        ? `X ${this.robotPose.x.toFixed(2)}  Y ${this.robotPose.y.toFixed(2)}  YAW ${((this.robotPose.yaw / DEG + 360) % 360).toFixed(0)}°`
        : 'ODOMETRY WAITING';
      ctx.save();
      ctx.font = '700 9px ui-monospace, SFMono-Regular, Menlo, monospace';
      const width = Math.max(ctx.measureText(primary).width, ctx.measureText(secondary).width) + 16;
      const x = clamp(anchor.x - width / 2, 8, this.width - width - 8);
      const y = clamp(anchor.y - 54, 8, this.height - 42);
      ctx.fillStyle = 'rgba(4, 14, 12, .88)';
      ctx.strokeStyle = pose.frameMismatch || pose.preview ? 'rgba(255, 198, 109, .62)' : 'rgba(125, 240, 182, .58)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      this._roundedRectPath(ctx, x, y, width, 35, 6);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = pose.frameMismatch || pose.preview ? '#ffd38f' : '#bfffe2';
      ctx.fillText(primary, x + 8, y + 13);
      ctx.fillStyle = '#809b92';
      ctx.font = '500 8px ui-monospace, SFMono-Regular, Menlo, monospace';
      ctx.fillText(secondary, x + 8, y + 26);
      ctx.restore();
    }

    _drawHud() {
      const ctx = this.ctx;
      const cloudCount = Math.floor(this.cloud.points.length / 3);
      const sourceCount = this.cloud.sourcePoints || cloudCount;
      const chips = [];
      if (this.status.online === false) chips.push({ text: 'ROBOT OFFLINE', color: '#ffc66d' });
      else if (this.status.online === true) chips.push({ text: 'ROBOT ONLINE', color: '#7df0b6' });
      if (this.status.snapshot) chips.push({ text: 'SAVED CLOUD', color: '#5dded8' });
      else if (this.status.lidarOnline === false) chips.push({ text: 'LIDAR WAITING', color: '#ffc66d' });
      else if (this.status.lidarOnline === true) chips.push({ text: 'LIDAR LIVE', color: '#5dded8' });

      ctx.save();
      let x = 12;
      chips.forEach((chip) => {
        ctx.font = '700 8px ui-monospace, SFMono-Regular, Menlo, monospace';
        const width = ctx.measureText(chip.text).width + 18;
        ctx.fillStyle = 'rgba(4, 14, 12, .82)';
        ctx.strokeStyle = `${chip.color}66`;
        ctx.beginPath(); this._roundedRectPath(ctx, x, 12, width, 23, 11); ctx.fill(); ctx.stroke();
        ctx.fillStyle = chip.color;
        ctx.beginPath(); ctx.arc(x + 8, 23.5, 2.5, 0, TAU); ctx.fill();
        ctx.fillText(chip.text, x + 14, 26);
        x += width + 7;
      });

      ctx.textAlign = 'right';
      ctx.fillStyle = '#789089';
      ctx.font = '500 8px ui-monospace, SFMono-Regular, Menlo, monospace';
      const pointLabel = cloudCount ? `${cloudCount.toLocaleString()} / ${sourceCount.toLocaleString()} POINTS` : 'NO POINT CLOUD';
      ctx.fillText(pointLabel, this.width - 12, 19);
      ctx.fillText(`FRAME ${this.cloud.frameId || '—'}`, this.width - 12, 31);
      ctx.textAlign = 'left';

      if (!cloudCount) {
        const message = this.status.message || (this.status.lidarOnline === false ? 'LiDAR 신호를 기다리고 있습니다' : '3D point cloud waiting');
        const centerY = this.height * 0.72;
        ctx.textAlign = 'center';
        ctx.fillStyle = 'rgba(151, 178, 169, .78)';
        ctx.font = '600 10px ui-monospace, SFMono-Regular, Menlo, monospace';
        ctx.fillText(message, this.width / 2, centerY);
        ctx.fillStyle = 'rgba(102, 128, 120, .65)';
        ctx.font = '500 8px ui-monospace, SFMono-Regular, Menlo, monospace';
        ctx.fillText('로봇 모델은 미리보기로 계속 조작할 수 있습니다', this.width / 2, centerY + 15);
      }

      ctx.textAlign = 'left';
      ctx.fillStyle = 'rgba(101, 128, 120, .70)';
      ctx.font = '500 8px ui-monospace, SFMono-Regular, Menlo, monospace';
      ctx.fillText('DRAG ORBIT  ·  SHIFT/RIGHT DRAG PAN  ·  WHEEL ZOOM  ·  DOUBLE CLICK RESET', 12, this.height - 12);
      ctx.restore();
    }

    _stroke3DLine(start, end) {
      const a = this._project(start);
      const b = this._project(end);
      if (!a || !b) return;
      const ctx = this.ctx;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    _roundedRectPath(ctx, x, y, width, height, radius) {
      const r = Math.min(radius, width / 2, height / 2);
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + width - r, y);
      ctx.quadraticCurveTo(x + width, y, x + width, y + r);
      ctx.lineTo(x + width, y + height - r);
      ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
      ctx.lineTo(x + r, y + height);
      ctx.quadraticCurveTo(x, y + height, x, y + height - r);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.closePath();
    }
  }

  global.RobotScene3D = RobotScene3D;
})(typeof window !== 'undefined' ? window : globalThis);
