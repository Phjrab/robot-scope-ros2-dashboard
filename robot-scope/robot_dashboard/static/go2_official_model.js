/*
 * Official-derived Unitree Go2 model renderer for Robot Scope.
 *
 * Load after scene3d.js.  The module automatically installs itself on
 * window.RobotScene3D, or it can be installed explicitly:
 *
 *   Go2OfficialModel.install(RobotScene3D, {
 *     assetUrl: '/static/assets/go2/go2-official-lite.json'
 *   });
 *
 * Instance API added to RobotScene3D:
 *   await scene.loadOfficialRobotModel(url?);
 *   scene.setRobotJointPositions({ FL_hip_joint: 0.1, ... });
 *   scene.setRobotJointPositions([/* FR 0..2, FL 0..2, RR 0..2, RL 0..2 *\/]);
 *   scene.configureOfficialRobot({ enabled, poseOrigin, adaptiveScale, scale });
 *   scene.getOfficialRobotModelStatus();
 *
 * The geometry is derived from Unitree Robotics unitree_ros/go2_description
 * (BSD-3-Clause).
 * Attribution: /static/assets/go2/LICENSE.txt and README.md
 */
(function installGo2OfficialModel(global) {
  'use strict';

  const DEFAULT_ASSET_URL = '/static/assets/go2/go2-official-lite.json';
  const EXPECTED_SCHEMA = 'robot-scope.go2-official-lite';
  const sharedLoads = new Map();

  function finite(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function identity() {
    return [
      1, 0, 0, 0,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 1,
    ];
  }

  function multiplyMatrix(a, b) {
    const result = new Array(16).fill(0);
    for (let row = 0; row < 4; row += 1) {
      for (let column = 0; column < 4; column += 1) {
        for (let inner = 0; inner < 4; inner += 1) {
          result[row * 4 + column] += a[row * 4 + inner] * b[inner * 4 + column];
        }
      }
    }
    return result;
  }

  function transformPoint(matrix, x, y, z) {
    return [
      matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3],
      matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7],
      matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11],
    ];
  }

  function originMatrix(origin) {
    const xyz = origin?.xyz || [0, 0, 0];
    const rpy = origin?.rpy || [0, 0, 0];
    const roll = finite(rpy[0]);
    const pitch = finite(rpy[1]);
    const yaw = finite(rpy[2]);
    const cr = Math.cos(roll), sr = Math.sin(roll);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    return [
      cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, finite(xyz[0]),
      sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, finite(xyz[1]),
      -sp, cp * sr, cp * cr, finite(xyz[2]),
      0, 0, 0, 1,
    ];
  }

  function axisAngleMatrix(axis, angle) {
    let x = finite(axis?.[0]);
    let y = finite(axis?.[1]);
    let z = finite(axis?.[2]);
    const length = Math.hypot(x, y, z);
    if (length < 1e-9 || Math.abs(angle) < 1e-12) return identity();
    x /= length; y /= length; z /= length;
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    const t = 1 - c;
    return [
      t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0,
      t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0,
      t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0,
      0, 0, 0, 1,
    ];
  }

  function rootMatrix(pose, z, scale) {
    const c = Math.cos(pose.yaw);
    const s = Math.sin(pose.yaw);
    return [
      c * scale, -s * scale, 0, pose.x,
      s * scale, c * scale, 0, pose.y,
      0, 0, scale, z,
      0, 0, 0, 1,
    ];
  }

  function parseHex(value) {
    const match = /^#?([0-9a-f]{6})$/i.exec(String(value || ''));
    const packed = match ? Number.parseInt(match[1], 16) : 0xaab0c5;
    return [(packed >> 16) & 255, (packed >> 8) & 255, packed & 255];
  }

  function shadedColor(rgb, shade, alpha) {
    const values = rgb.map((value) => clamp(Math.round(value * shade), 0, 255));
    return `rgba(${values[0]},${values[1]},${values[2]},${alpha})`;
  }

  function validateAsset(asset) {
    if (!asset || asset.schema !== EXPECTED_SCHEMA || asset.version !== 1) {
      throw new Error(`Unsupported Go2 model schema: ${asset?.schema || 'missing'}`);
    }
    if (!asset.meshes || !Array.isArray(asset.skeleton?.links) || !Array.isArray(asset.skeleton?.joints)) {
      throw new Error('Incomplete Go2 model asset.');
    }
    if (asset.source?.license !== 'BSD-3-Clause') {
      throw new Error('Go2 model asset is missing BSD-3-Clause provenance.');
    }
    return asset;
  }

  function hydrateAsset(asset) {
    validateAsset(asset);
    const meshes = {};
    Object.entries(asset.meshes).forEach(([name, mesh]) => {
      const quantization = finite(mesh.quantization_m, 0.00001);
      const vertices = new Float32Array(mesh.vertices_q.length);
      for (let index = 0; index < vertices.length; index += 1) {
        vertices[index] = finite(mesh.vertices_q[index]) * quantization;
      }
      meshes[name] = {
        vertices,
        groups: mesh.groups.map((group) => ({
          material: group.material,
          color: group.color,
          rgb: parseHex(group.color),
          indices: vertices.length / 3 <= 65535 ? new Uint16Array(group.indices) : new Uint32Array(group.indices),
        })),
        statistics: mesh.statistics,
      };
    });
    return { asset, meshes };
  }

  function loadAsset(url = DEFAULT_ASSET_URL) {
    if (sharedLoads.has(url)) return sharedLoads.get(url);
    const request = Promise.resolve()
      .then(() => {
        if (typeof global.fetch !== 'function') throw new Error('fetch is unavailable');
        return global.fetch(url, { cache: 'force-cache' });
      })
      .then((response) => {
        if (!response.ok) throw new Error(`Go2 model request failed (${response.status})`);
        return response.json();
      })
      .then(hydrateAsset)
      .catch((error) => {
        sharedLoads.delete(url);
        throw error;
      });
    sharedLoads.set(url, request);
    return request;
  }

  function jointObject(value, runtime) {
    const root = value?.values || value || {};
    const motorStates = root.motor_state || root.motorState;
    if (Array.isArray(motorStates)) {
      value = motorStates.map((state) => finite(state?.q ?? state?.position));
    }
    if (Array.isArray(value) || ArrayBuffer.isView(value)) {
      const names = runtime?.asset?.skeleton?.joint_order || [];
      return Object.fromEntries(names.map((name, index) => [name, finite(value[index])]));
    }
    if (value && typeof value === 'object') {
      return Object.fromEntries(
        Object.entries(value)
          .filter(([, position]) => Number.isFinite(Number(position)))
          .map(([name, position]) => [name, Number(position)]),
      );
    }
    return {};
  }

  function configuredJointPositions(scene, runtime) {
    const defaults = runtime.asset.skeleton.default_joint_positions || {};
    const supplied = scene._go2OfficialPendingJoints;
    const current = jointObject(supplied, runtime);
    return { ...defaults, ...current };
  }

  function linkTransforms(scene, runtime, root) {
    const transforms = { [runtime.asset.skeleton.root]: root };
    const positions = configuredJointPositions(scene, runtime);
    runtime.asset.skeleton.joints.forEach((joint) => {
      const parent = transforms[joint.parent];
      if (!parent) return;
      let angle = joint.type === 'revolute' || joint.type === 'continuous'
        ? finite(positions[joint.name])
        : 0;
      if (joint.limit && joint.type === 'revolute') {
        angle = clamp(angle, finite(joint.limit.lower, -Infinity), finite(joint.limit.upper, Infinity));
      }
      transforms[joint.child] = multiplyMatrix(
        multiplyMatrix(parent, originMatrix(joint.origin)),
        axisAngleMatrix(joint.axis, angle),
      );
    });
    return transforms;
  }

  function faceNormal(a, b, c) {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    const x = uy * vz - uz * vy;
    const y = uz * vx - ux * vz;
    const z = ux * vy - uy * vx;
    const length = Math.hypot(x, y, z) || 1;
    return [x / length, y / length, z / length];
  }

  function projectedOutside(points, width, height) {
    return (
      points.every((point) => point.x < -2) ||
      points.every((point) => point.x > width + 2) ||
      points.every((point) => point.y < -2) ||
      points.every((point) => point.y > height + 2)
    );
  }

  function drawOfficialRobot(scene, runtime) {
    const pose = scene._effectiveRobotPose();
    const asset = runtime.asset;
    const config = scene._go2OfficialConfig;
    const approximateWidth = finite(asset.model?.approximate_size_m?.[0], 0.8);
    const worldPerPixel = 2 * scene.camera.distance * Math.tan(scene.options.fov / 2) / Math.max(scene.height, 1);
    const requestedScale = clamp(finite(config.scale, 1), 0.05, 20);
    const scale = config.adaptiveScale === false
      ? requestedScale
      : clamp(Math.max(requestedScale, worldPerPixel * 58 / approximateWidth), requestedScale, 7);
    const groundAnchored = config.poseOrigin !== 'base';
    const baseHeight = finite(config.baseHeight, finite(asset.model?.base_height_m, 0.32));
    const baseZ = pose.z + (groundAnchored ? baseHeight * scale : 0);
    const root = rootMatrix(pose, baseZ, scale);
    const transforms = linkTransforms(scene, runtime, root);
    const faces = [];
    const alpha = pose.preview || pose.frameMismatch ? 0.91 : 0.98;
    const light = [0.36, -0.48, 0.80];

    asset.skeleton.links.forEach((link) => {
      const mesh = runtime.meshes[link.mesh];
      const linkMatrix = transforms[link.name];
      if (!mesh || !linkMatrix) return;
      const matrix = multiplyMatrix(linkMatrix, originMatrix(link.visual_origin));
      const world = new Array(mesh.vertices.length / 3);
      const projected = new Array(mesh.vertices.length / 3);
      for (let index = 0, vertex = 0; index < mesh.vertices.length; index += 3, vertex += 1) {
        const point = transformPoint(matrix, mesh.vertices[index], mesh.vertices[index + 1], mesh.vertices[index + 2]);
        world[vertex] = point;
        projected[vertex] = scene._project(point);
      }

      mesh.groups.forEach((group) => {
        const indices = group.indices;
        for (let index = 0; index < indices.length; index += 3) {
          const ia = indices[index], ib = indices[index + 1], ic = indices[index + 2];
          const screen = [projected[ia], projected[ib], projected[ic]];
          if (screen.some((point) => !point) || projectedOutside(screen, scene.width, scene.height)) continue;
          const area = (screen[1].x - screen[0].x) * (screen[2].y - screen[0].y) -
            (screen[1].y - screen[0].y) * (screen[2].x - screen[0].x);
          if (Math.abs(area) < 0.02) continue;
          const normal = faceNormal(world[ia], world[ib], world[ic]);
          const diffuse = Math.abs(normal[0] * light[0] + normal[1] * light[1] + normal[2] * light[2]);
          const shade = 0.43 + 0.66 * diffuse;
          faces.push({
            points: screen,
            depth: (screen[0].depth + screen[1].depth + screen[2].depth) / 3,
            fill: shadedColor(group.rgb, shade, alpha),
          });
        }
      });
    });

    faces.sort((a, b) => b.depth - a.depth);
    const ctx = scene.ctx;
    ctx.save();
    ctx.lineJoin = 'round';
    faces.forEach((face) => {
      ctx.beginPath();
      ctx.moveTo(face.points[0].x, face.points[0].y);
      ctx.lineTo(face.points[1].x, face.points[1].y);
      ctx.lineTo(face.points[2].x, face.points[2].y);
      ctx.closePath();
      ctx.fillStyle = face.fill;
      ctx.fill();
    });

    const outline = scene._project([pose.x, pose.y, baseZ + 0.24 * scale]);
    if (outline) {
      ctx.fillStyle = pose.frameMismatch || pose.preview ? '#ffd38f' : '#d8fff0';
      ctx.beginPath();
      ctx.arc(outline.x, outline.y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    const labelAnchor = scene._project([pose.x, pose.y, baseZ + 0.42 * scale]);
    if (labelAnchor) scene._drawRobotLabel(labelAnchor, pose);
  }

  function install(SceneClass, options = {}) {
    if (!SceneClass?.prototype) throw new TypeError('Go2OfficialModel.install requires RobotScene3D.');
    const prototype = SceneClass.prototype;
    if (prototype.__go2OfficialModelInstalled) return SceneClass;
    const fallbackDrawRobot = prototype._drawRobot;
    if (typeof fallbackDrawRobot !== 'function') {
      throw new Error('RobotScene3D does not expose the expected robot drawing hook.');
    }

    Object.defineProperty(prototype, '__go2OfficialModelInstalled', { value: true });
    prototype._go2OfficialDefaults = {
      enabled: options.enabled !== false,
      assetUrl: options.assetUrl || DEFAULT_ASSET_URL,
      poseOrigin: options.poseOrigin || 'ground',
      adaptiveScale: options.adaptiveScale !== false,
      scale: finite(options.scale, 1),
      baseHeight: options.baseHeight,
    };

    prototype._ensureGo2OfficialConfig = function ensureGo2OfficialConfig() {
      if (!this._go2OfficialConfig) this._go2OfficialConfig = { ...this._go2OfficialDefaults };
      return this._go2OfficialConfig;
    };

    prototype.loadOfficialRobotModel = function loadOfficialRobotModel(url) {
      const config = this._ensureGo2OfficialConfig();
      const target = url || config.assetUrl || DEFAULT_ASSET_URL;
      config.assetUrl = target;
      if (this._go2OfficialRuntime && this._go2OfficialLoadedUrl === target) {
        return Promise.resolve(this._go2OfficialRuntime.asset);
      }
      if (this._go2OfficialPromise && this._go2OfficialLoadingUrl === target) return this._go2OfficialPromise;
      this._go2OfficialState = 'loading';
      this._go2OfficialError = null;
      this._go2OfficialLoadingUrl = target;
      this._go2OfficialPromise = loadAsset(target)
        .then((runtime) => {
          this._go2OfficialRuntime = runtime;
          this._go2OfficialLoadedUrl = target;
          this._go2OfficialState = 'ready';
          this._go2OfficialError = null;
          this.render();
          return runtime.asset;
        })
        .catch((error) => {
          this._go2OfficialState = 'error';
          this._go2OfficialError = error;
          this.render();
          throw error;
        });
      return this._go2OfficialPromise;
    };

    prototype.configureOfficialRobot = function configureOfficialRobot(value = {}) {
      const config = this._ensureGo2OfficialConfig();
      if (Object.prototype.hasOwnProperty.call(value, 'enabled')) config.enabled = Boolean(value.enabled);
      if (value.assetUrl) config.assetUrl = String(value.assetUrl);
      if (value.poseOrigin === 'base' || value.poseOrigin === 'ground') config.poseOrigin = value.poseOrigin;
      if (Object.prototype.hasOwnProperty.call(value, 'adaptiveScale')) config.adaptiveScale = Boolean(value.adaptiveScale);
      if (Number.isFinite(Number(value.scale))) config.scale = clamp(Number(value.scale), 0.05, 20);
      if (Number.isFinite(Number(value.baseHeight))) config.baseHeight = Number(value.baseHeight);
      this.render();
      return { ...config };
    };

    prototype.setRobotJointPositions = function setRobotJointPositions(value) {
      this._go2OfficialPendingJoints = value;
      this.render();
      return jointObject(value, this._go2OfficialRuntime);
    };

    prototype.setRobotJointState = prototype.setRobotJointPositions;

    prototype.resetRobotJointPositions = function resetRobotJointPositions() {
      this._go2OfficialPendingJoints = null;
      this.render();
    };

    prototype.getOfficialRobotModelStatus = function getOfficialRobotModelStatus() {
      const config = this._ensureGo2OfficialConfig();
      return {
        state: this._go2OfficialState || 'idle',
        enabled: config.enabled,
        url: this._go2OfficialLoadedUrl || this._go2OfficialLoadingUrl || config.assetUrl,
        model: this._go2OfficialRuntime?.asset?.model?.name || null,
        source: this._go2OfficialRuntime?.asset?.source || null,
        error: this._go2OfficialError ? String(this._go2OfficialError.message || this._go2OfficialError) : null,
      };
    };

    prototype._drawRobot = function drawGo2OfficialOrFallback() {
      const config = this._ensureGo2OfficialConfig();
      if (!config.enabled) return fallbackDrawRobot.call(this);
      if (this._go2OfficialRuntime) return drawOfficialRobot(this, this._go2OfficialRuntime);
      if (!this._go2OfficialPromise || this._go2OfficialLoadingUrl !== config.assetUrl) {
        this.loadOfficialRobotModel(config.assetUrl).catch(() => {});
      }
      return fallbackDrawRobot.call(this);
    };

    return SceneClass;
  }

  const api = {
    DEFAULT_ASSET_URL,
    EXPECTED_SCHEMA,
    install,
    loadAsset,
    validateAsset,
  };
  global.Go2OfficialModel = api;
  if (global.RobotScene3D) install(global.RobotScene3D);
})(typeof window !== 'undefined' ? window : globalThis);
