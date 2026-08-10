/**
 * Live Mapping-only top-down point-cloud projection.
 *
 * This renderer deliberately consumes the same `/api/v1/pointcloud` payload
 * that powers the 3D scene. It never opens another stream and it does not
 * create or modify a Saved Maps occupancy grid.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.RobotLiveMap2D = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, lower, upper) {
    return Math.min(upper, Math.max(lower, value));
  }

  function validPose(pose) {
    return Boolean(pose && Number.isFinite(Number(pose.x)) && Number.isFinite(Number(pose.y)));
  }

  function normalizedBounds(bounds) {
    if (!bounds?.min || !bounds?.max || bounds.min.length < 2 || bounds.max.length < 2) return null;
    const min = [Number(bounds.min[0]), Number(bounds.min[1]), Number(bounds.min[2] ?? 0)];
    const max = [Number(bounds.max[0]), Number(bounds.max[1]), Number(bounds.max[2] ?? 0)];
    if (![...min, ...max].every(Number.isFinite)) return null;
    if (min[0] > max[0] || min[1] > max[1] || min[2] > max[2]) return null;
    return { min, max };
  }

  /**
   * Deduplicate XYZ points into sparse XY cells. The sparse representation
   * bounds CPU/memory by the received point budget instead of the map area.
   */
  function projectPointCloud(cloud, options = {}) {
    const points = cloud?.points;
    const available = Math.floor(Number(points?.length || 0) / 3);
    const resolution = clamp(finite(options.resolution, 0.08), 0.02, 1);
    const maxCells = Math.floor(clamp(finite(options.maxCells, 50000), 1000, 250000));
    const cells = new Map();
    const measuredMin = [Infinity, Infinity, Infinity];
    const measuredMax = [-Infinity, -Infinity, -Infinity];
    let validPoints = 0;

    for (let index = 0; index < available; index += 1) {
      const offset = index * 3;
      const x = Number(points[offset]);
      const y = Number(points[offset + 1]);
      const z = Number(points[offset + 2]);
      if (![x, y, z].every(Number.isFinite)) continue;
      validPoints += 1;
      measuredMin[0] = Math.min(measuredMin[0], x);
      measuredMin[1] = Math.min(measuredMin[1], y);
      measuredMin[2] = Math.min(measuredMin[2], z);
      measuredMax[0] = Math.max(measuredMax[0], x);
      measuredMax[1] = Math.max(measuredMax[1], y);
      measuredMax[2] = Math.max(measuredMax[2], z);
      const gridX = Math.floor(x / resolution);
      const gridY = Math.floor(y / resolution);
      const key = `${gridX}:${gridY}`;
      const previous = cells.get(key);
      if (previous) {
        previous[2] = Math.max(previous[2], z);
        previous[3] += 1;
      } else {
        cells.set(key, [(gridX + 0.5) * resolution, (gridY + 0.5) * resolution, z, 1]);
      }
    }

    const sourceCells = Array.from(cells.values());
    const selectedCount = Math.min(sourceCells.length, maxCells);
    const output = new Float32Array(selectedCount * 4);
    const stride = sourceCells.length > selectedCount ? sourceCells.length / selectedCount : 1;
    for (let index = 0; index < selectedCount; index += 1) {
      const cell = sourceCells[Math.min(sourceCells.length - 1, Math.floor(index * stride))];
      output[index * 4] = cell[0];
      output[index * 4 + 1] = cell[1];
      output[index * 4 + 2] = cell[2];
      output[index * 4 + 3] = cell[3];
    }

    const measuredBounds = validPoints ? { min: measuredMin, max: measuredMax } : null;
    return {
      cells: output,
      bounds: measuredBounds || normalizedBounds(cloud?.bounds),
      resolution,
      sourcePoints: available,
      validPoints,
      sourceCells: sourceCells.length,
      sentCells: selectedCount,
      frameId: String(cloud?.frame_id || ''),
      seq: cloud?.seq ?? null,
    };
  }

  function fitView(bounds, aspect = 1, padding = 1.18) {
    const safeBounds = normalizedBounds(bounds);
    if (!safeBounds) return { centerX: 0, centerY: 0, spanY: 20 };
    const spanX = Math.max(safeBounds.max[0] - safeBounds.min[0], 0.5);
    const spanY = Math.max(safeBounds.max[1] - safeBounds.min[1], 0.5);
    return {
      centerX: (safeBounds.min[0] + safeBounds.max[0]) / 2,
      centerY: (safeBounds.min[1] + safeBounds.max[1]) / 2,
      spanY: clamp(Math.max(spanY, spanX / Math.max(aspect, 0.1)) * padding, 2, 1000),
    };
  }

  function worldToCanvas(view, width, height, x, y) {
    const spanY = Math.max(finite(view?.spanY, 20), 0.001);
    const scale = height / spanY;
    return {
      x: width / 2 + (finite(x) - finite(view?.centerX)) * scale,
      y: height / 2 - (finite(y) - finite(view?.centerY)) * scale,
      scale,
    };
  }

  function niceGridStep(span) {
    const raw = Math.max(finite(span, 20) / 8, 0.01);
    const power = 10 ** Math.floor(Math.log10(raw));
    const ratio = raw / power;
    return (ratio >= 5 ? 5 : ratio >= 2 ? 2 : 1) * power;
  }

  class LiveMap2DRenderer {
    constructor(canvas, options = {}) {
      if (!canvas || typeof canvas.getContext !== 'function') throw new Error('LiveMap2DRenderer requires a canvas');
      this.canvas = canvas;
      this.context = canvas.getContext('2d');
      this.options = {
        resolution: clamp(finite(options.resolution, 0.08), 0.02, 1),
        maxCells: Math.floor(clamp(finite(options.maxCells, 50000), 1000, 250000)),
        maxPixelRatio: clamp(finite(options.maxPixelRatio, 2), 1, 3),
      };
      this.projection = projectPointCloud(null, this.options);
      this.pose = null;
      this.trail = [];
      this.overlayVisible = true;
      this.autoFit = true;
      this.follow = false;
      this.view = { centerX: 0, centerY: 0, spanY: 20 };
      this.targetView = { ...this.view };
      this.width = 1;
      this.height = 1;
      this.pixelRatio = 1;
      this.controls = {};
      this._listeners = [];
      this._frame = 0;
      this._drag = null;
      this._onWheel = (event) => this._handleWheel(event);
      this._onPointerDown = (event) => this._handlePointerDown(event);
      this._onPointerMove = (event) => this._handlePointerMove(event);
      this._onPointerUp = (event) => this._handlePointerUp(event);
      canvas.addEventListener?.('wheel', this._onWheel, { passive: false });
      canvas.addEventListener?.('pointerdown', this._onPointerDown);
      canvas.addEventListener?.('pointermove', this._onPointerMove);
      canvas.addEventListener?.('pointerup', this._onPointerUp);
      canvas.addEventListener?.('pointercancel', this._onPointerUp);
      this.resize();
    }

    setPointCloud(cloud, options = {}) {
      this.projection = projectPointCloud(cloud, this.options);
      if (options.fit === true || (this.autoFit && !this.follow)) this.fitToCloud(false);
      this.scheduleRender();
      return this.projection.sentCells;
    }

    clearPointCloud() {
      this.projection = projectPointCloud(null, this.options);
      this.scheduleRender();
    }

    setPose(pose) {
      this.pose = validPose(pose) ? { ...pose, x: Number(pose.x), y: Number(pose.y), yaw: finite(pose.yaw) } : null;
      if (this.follow && this.pose) {
        this.targetView.centerX = this.pose.x;
        this.targetView.centerY = this.pose.y;
      }
      this.scheduleRender();
    }

    setTrail(trail) {
      this.trail = (Array.isArray(trail) ? trail : []).filter(validPose).slice(-500).map((pose) => ({
        x: Number(pose.x), y: Number(pose.y), yaw: finite(pose.yaw), frameId: String(pose.frameId || ''),
      }));
      this.scheduleRender();
    }

    setOverlayVisible(visible) {
      this.overlayVisible = Boolean(visible);
      this.scheduleRender();
    }

    setAutoFit(enabled) {
      this.autoFit = Boolean(enabled);
      if (this.autoFit) {
        this.follow = false;
        this.fitToCloud(false);
      }
      this._syncControls();
      this.scheduleRender();
      return this.autoFit;
    }

    toggleAutoFit() {
      return this.setAutoFit(!this.autoFit);
    }

    setFollow(enabled) {
      this.follow = Boolean(enabled);
      if (this.follow) {
        this.autoFit = false;
        if (this.pose) {
          this.targetView.centerX = this.pose.x;
          this.targetView.centerY = this.pose.y;
        }
      }
      this._syncControls();
      this.scheduleRender();
      return this.follow;
    }

    toggleFollow() {
      return this.setFollow(!this.follow);
    }

    fitToCloud(render = true) {
      const aspect = this.width / Math.max(this.height, 1);
      this.targetView = fitView(this.projection.bounds, aspect);
      if (render) this.scheduleRender();
      return { ...this.targetView };
    }

    bindControls(controls = {}) {
      this._removeControlListeners();
      this.controls = controls;
      const bindings = [
        [controls.fit, () => { this.setFollow(false); this.fitToCloud(); }],
        [controls.autoFit, () => this.toggleAutoFit()],
        [controls.follow, () => this.toggleFollow()],
      ];
      bindings.forEach(([element, handler]) => {
        if (!element?.addEventListener) return;
        element.addEventListener('click', handler);
        this._listeners.push([element, handler]);
      });
      this._syncControls();
    }

    resize() {
      const ratio = Math.min(finite(globalThis.devicePixelRatio, 1), this.options.maxPixelRatio);
      const cssWidth = Math.max(1, finite(this.canvas.clientWidth, this.canvas.width || 1));
      const cssHeight = Math.max(1, finite(this.canvas.clientHeight, this.canvas.height || 1));
      const width = Math.max(1, Math.round(cssWidth * ratio));
      const height = Math.max(1, Math.round(cssHeight * ratio));
      if (this.canvas.width !== width) this.canvas.width = width;
      if (this.canvas.height !== height) this.canvas.height = height;
      this.width = width;
      this.height = height;
      this.pixelRatio = ratio;
      this.scheduleRender();
      return { width, height, ratio };
    }

    scheduleRender() {
      if (this._frame) return;
      const raf = typeof globalThis.requestAnimationFrame === 'function'
        ? globalThis.requestAnimationFrame.bind(globalThis)
        : (callback) => { callback(); return 0; };
      this._frame = raf(() => {
        this._frame = 0;
        this.render();
      });
    }

    render() {
      const difference = Math.abs(this.view.centerX - this.targetView.centerX)
        + Math.abs(this.view.centerY - this.targetView.centerY)
        + Math.abs(this.view.spanY - this.targetView.spanY);
      if (difference > 0.0005) {
        const alpha = 0.24;
        this.view.centerX += (this.targetView.centerX - this.view.centerX) * alpha;
        this.view.centerY += (this.targetView.centerY - this.view.centerY) * alpha;
        this.view.spanY += (this.targetView.spanY - this.view.spanY) * alpha;
        this.scheduleRender();
      } else {
        this.view = { ...this.targetView };
      }
      this._draw();
    }

    snapshot() {
      return {
        autoFit: this.autoFit,
        follow: this.follow,
        view: { ...this.view },
        targetView: { ...this.targetView },
        pointCount: this.projection.validPoints,
        cellCount: this.projection.sentCells,
        frameId: this.projection.frameId,
      };
    }

    destroy() {
      this._removeControlListeners();
      const canvas = this.canvas;
      canvas.removeEventListener?.('wheel', this._onWheel);
      canvas.removeEventListener?.('pointerdown', this._onPointerDown);
      canvas.removeEventListener?.('pointermove', this._onPointerMove);
      canvas.removeEventListener?.('pointerup', this._onPointerUp);
      canvas.removeEventListener?.('pointercancel', this._onPointerUp);
      if (this._frame && typeof globalThis.cancelAnimationFrame === 'function') globalThis.cancelAnimationFrame(this._frame);
      this._frame = 0;
    }

    _removeControlListeners() {
      this._listeners.forEach(([element, handler]) => element.removeEventListener?.('click', handler));
      this._listeners = [];
    }

    _syncControls() {
      if (this.controls.autoFit) {
        this.controls.autoFit.setAttribute('aria-pressed', this.autoFit ? 'true' : 'false');
      }
      if (this.controls.follow) {
        this.controls.follow.setAttribute('aria-pressed', this.follow ? 'true' : 'false');
        this.controls.follow.textContent = this.follow ? 'FOLLOW' : 'WORLD';
      }
    }

    _handleWheel(event) {
      event.preventDefault?.();
      this.autoFit = false;
      this.follow = false;
      const factor = Math.exp(clamp(finite(event.deltaY) * 0.001, -0.8, 0.8));
      this.targetView.spanY = clamp(this.targetView.spanY * factor, 1, 1000);
      this._syncControls();
      this.scheduleRender();
    }

    _handlePointerDown(event) {
      if (event.button != null && event.button !== 0) return;
      this._drag = { id: event.pointerId, x: finite(event.clientX), y: finite(event.clientY), view: { ...this.targetView } };
      this.canvas.setPointerCapture?.(event.pointerId);
    }

    _handlePointerMove(event) {
      if (!this._drag || this._drag.id !== event.pointerId) return;
      const scale = this.height / Math.max(this._drag.view.spanY, 0.001);
      this.autoFit = false;
      this.follow = false;
      this.targetView.centerX = this._drag.view.centerX - (finite(event.clientX) - this._drag.x) * this.pixelRatio / scale;
      this.targetView.centerY = this._drag.view.centerY + (finite(event.clientY) - this._drag.y) * this.pixelRatio / scale;
      this._syncControls();
      this.scheduleRender();
    }

    _handlePointerUp(event) {
      if (!this._drag || this._drag.id !== event.pointerId) return;
      this.canvas.releasePointerCapture?.(event.pointerId);
      this._drag = null;
    }

    _draw() {
      const ctx = this.context;
      const { width, height } = this;
      ctx.fillStyle = '#06100e';
      ctx.fillRect(0, 0, width, height);
      this._drawGrid(ctx);
      this._drawCells(ctx);
      if (this.overlayVisible) {
        this._drawTrail(ctx);
        this._drawRobot(ctx);
      }
      this._drawReadout(ctx);
    }

    _drawGrid(ctx) {
      const step = niceGridStep(this.view.spanY);
      const topLeft = this._worldAt(0, 0);
      const bottomRight = this._worldAt(this.width, this.height);
      const firstX = Math.floor(topLeft.x / step) * step;
      const lastX = Math.ceil(bottomRight.x / step) * step;
      const firstY = Math.floor(bottomRight.y / step) * step;
      const lastY = Math.ceil(topLeft.y / step) * step;
      ctx.save();
      ctx.strokeStyle = 'rgba(125, 240, 182, .10)';
      ctx.lineWidth = this.pixelRatio;
      ctx.font = `${7 * this.pixelRatio}px ui-monospace, SFMono-Regular, Menlo, monospace`;
      ctx.fillStyle = 'rgba(164, 196, 185, .36)';
      for (let x = firstX; x <= lastX + step * 0.5; x += step) {
        const point = worldToCanvas(this.view, this.width, this.height, x, 0);
        ctx.beginPath(); ctx.moveTo(point.x, 0); ctx.lineTo(point.x, this.height); ctx.stroke();
        ctx.fillText(`${Number(x.toFixed(2))}m`, point.x + 3 * this.pixelRatio, this.height - 8 * this.pixelRatio);
      }
      for (let y = firstY; y <= lastY + step * 0.5; y += step) {
        const point = worldToCanvas(this.view, this.width, this.height, 0, y);
        ctx.beginPath(); ctx.moveTo(0, point.y); ctx.lineTo(this.width, point.y); ctx.stroke();
      }
      ctx.restore();
    }

    _drawCells(ctx) {
      const cells = this.projection.cells;
      if (!cells.length) return;
      const zMin = finite(this.projection.bounds?.min?.[2], 0);
      const zMax = finite(this.projection.bounds?.max?.[2], zMin + 1);
      const zSpan = Math.max(zMax - zMin, 0.1);
      const scale = this.height / Math.max(this.view.spanY, 0.001);
      const size = clamp(this.projection.resolution * scale * 1.15, 1.1 * this.pixelRatio, 5 * this.pixelRatio);
      const buckets = [[], [], [], []];
      for (let index = 0; index < cells.length; index += 4) {
        const projected = worldToCanvas(this.view, this.width, this.height, cells[index], cells[index + 1]);
        if (projected.x < -size || projected.x > this.width + size || projected.y < -size || projected.y > this.height + size) continue;
        const heightRatio = clamp((cells[index + 2] - zMin) / zSpan, 0, 1);
        buckets[Math.min(3, Math.floor(heightRatio * 4))].push(projected.x, projected.y);
      }
      const colors = ['rgba(64, 205, 206, .76)', 'rgba(86, 230, 177, .82)', 'rgba(255, 198, 109, .88)', 'rgba(255, 126, 104, .92)'];
      buckets.forEach((values, bucket) => {
        ctx.fillStyle = colors[bucket];
        for (let index = 0; index < values.length; index += 2) {
          ctx.fillRect(values[index] - size / 2, values[index + 1] - size / 2, size, size);
        }
      });
    }

    _drawTrail(ctx) {
      if (this.trail.length < 2) return;
      ctx.save();
      ctx.beginPath();
      this.trail.forEach((pose, index) => {
        const point = worldToCanvas(this.view, this.width, this.height, pose.x, pose.y);
        if (index) ctx.lineTo(point.x, point.y); else ctx.moveTo(point.x, point.y);
      });
      ctx.strokeStyle = 'rgba(162, 139, 255, .82)';
      ctx.lineWidth = 1.5 * this.pixelRatio;
      ctx.setLineDash([5 * this.pixelRatio, 5 * this.pixelRatio]);
      ctx.stroke();
      ctx.restore();
    }

    _drawRobot(ctx) {
      if (!this.pose) return;
      const point = worldToCanvas(this.view, this.width, this.height, this.pose.x, this.pose.y);
      const size = 9 * this.pixelRatio;
      ctx.save();
      ctx.translate(point.x, point.y);
      ctx.rotate(-this.pose.yaw);
      ctx.shadowColor = 'rgba(125, 240, 182, .85)';
      ctx.shadowBlur = 10 * this.pixelRatio;
      ctx.fillStyle = '#d8fff0';
      ctx.beginPath();
      ctx.moveTo(size * 1.4, 0);
      ctx.lineTo(-size, size * 0.72);
      ctx.lineTo(-size * 0.62, 0);
      ctx.lineTo(-size, -size * 0.72);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }

    _drawReadout(ctx) {
      ctx.save();
      ctx.font = `600 ${8 * this.pixelRatio}px ui-monospace, SFMono-Regular, Menlo, monospace`;
      ctx.textAlign = 'right';
      ctx.fillStyle = 'rgba(190, 219, 209, .62)';
      const mode = this.follow ? 'FOLLOW' : this.autoFit ? 'AUTO-FIT' : 'WORLD';
      const readoutY = this.width / this.pixelRatio < 520 ? 125 : 70;
      ctx.fillText(`LIVE POINT PROJECTION · ${mode}`, this.width - 12 * this.pixelRatio, readoutY * this.pixelRatio);
      ctx.fillText(`${this.projection.sentCells.toLocaleString()} CELLS · ${this.projection.validPoints.toLocaleString()} POINTS`, this.width - 12 * this.pixelRatio, (readoutY + 13) * this.pixelRatio);
      if (!this.projection.cells.length) {
        ctx.textAlign = 'center';
        ctx.fillStyle = 'rgba(175, 201, 192, .72)';
        ctx.font = `500 ${10 * this.pixelRatio}px ui-sans-serif, system-ui, sans-serif`;
        ctx.fillText('실시간 포인트클라우드를 기다리고 있습니다', this.width / 2, this.height / 2);
      }
      ctx.restore();
    }

    _worldAt(canvasX, canvasY) {
      const scale = this.height / Math.max(this.view.spanY, 0.001);
      return {
        x: this.view.centerX + (canvasX - this.width / 2) / scale,
        y: this.view.centerY - (canvasY - this.height / 2) / scale,
      };
    }
  }

  return Object.freeze({
    LiveMap2DRenderer,
    projectPointCloud,
    fitView,
    worldToCanvas,
    normalizedBounds,
  });
});
