const PERCEPTION_STALE_MS = 2000;

function finite(value, fallback = null) {
  if (typeof value === 'boolean' || value == null || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function text(value, fallback = '—') {
  const result = String(value ?? '').trim();
  return result || fallback;
}

export function projectPerceptionOverlay(snapshot = {}, sourceId = 'realsense_color', localAgeMs = 0) {
  const supported = sourceId === 'realsense_color';
  const rawResults = Array.isArray(snapshot.results) ? snapshot.results : [];
  const results = supported ? rawResults.filter((item) => item && ['lane', 'object', 'depth_summary'].includes(item.task)) : [];
  const backendState = text(snapshot.transport_state, 'OFFLINE').toUpperCase();
  const aged = !Number.isFinite(localAgeMs) || localAgeMs > PERCEPTION_STALE_MS;
  const hasResult = results.length > 0;
  const projected = results.map((item) => ({
    ...item,
    result_status: backendState === 'LIVE' && !aged && item.result_status === 'LIVE' ? 'LIVE' : 'STALE',
  }));
  const liveCount = projected.filter((item) => item.result_status === 'LIVE').length;
  const state = !supported || backendState === 'OFFLINE'
    ? 'OFFLINE'
    : liveCount === projected.length && liveCount > 0
      ? 'LIVE'
      : liveCount > 0
        ? 'DEGRADED'
        : hasResult
          ? 'STALE'
          : backendState === 'WAITING'
            ? 'WAITING'
            : 'OFFLINE';
  const visualState = state === 'LIVE' ? 'active' : 'inactive';
  const newest = projected.reduce((best, item) => !best || Number(item.sequence) > Number(best.sequence) ? item : best, null);
  const latency = newest ? finite(newest.inference_latency_ms) : null;
  const fps = newest ? finite(newest.inference_fps) : null;
  const age = newest ? Math.max(finite(newest.last_receive_age, 0) * 1000, localAgeMs) : null;
  return Object.freeze({
    mode: 'SHADOW',
    state,
    visualState,
    results: projected,
    model: newest ? text(newest.model_id) : '—',
    sequence: newest ? Number(newest.sequence) || 0 : 0,
    age: age == null ? '—' : `${(age / 1000).toFixed(2)} s`,
    fps: fps == null ? '—' : `${fps.toFixed(1)} FPS`,
    latency: latency == null ? '—' : `${latency.toFixed(1)} ms`,
    clock: newest?.clock_domain_verified === true ? 'VERIFIED' : 'UNVERIFIED CLOCK',
  });
}

function laneResult(results) {
  return results.find((item) => item.task === 'lane') || null;
}

function objectResult(results) {
  return results.find((item) => item.task === 'object') || null;
}

export function drawPerceptionOverlay(canvas, frameCanvas, projection) {
  if (!canvas || !frameCanvas) return false;
  const width = Number(frameCanvas.width) || 0;
  const height = Number(frameCanvas.height) || 0;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = Math.max(1, width);
    canvas.height = Math.max(1, height);
  }
  const context = canvas.getContext('2d');
  if (!context) return false;
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (width < 2 || height < 2 || !projection?.results?.length) return false;
  const inactive = projection.visualState !== 'active';
  const color = inactive ? 'rgba(180,190,187,.72)' : '#5dffbc';
  const labelBackground = inactive ? 'rgba(49,57,55,.82)' : 'rgba(3,31,23,.82)';
  context.save();
  context.lineWidth = Math.max(2, width / 320);
  context.strokeStyle = color;
  context.fillStyle = color;
  context.font = `${Math.max(11, width / 45)}px ui-monospace, monospace`;
  const objects = objectResult(projection.results);
  for (const item of objects?.payload?.detections || []) {
    const scaleX = width / Math.max(1, Number(objects.input_width));
    const scaleY = height / Math.max(1, Number(objects.input_height));
    const x = Number(item.x1) * scaleX;
    const y = Number(item.y1) * scaleY;
    const boxWidth = (Number(item.x2) - Number(item.x1)) * scaleX;
    const boxHeight = (Number(item.y2) - Number(item.y1)) * scaleY;
    context.strokeRect(x, y, boxWidth, boxHeight);
    const label = `${text(item.class_name, 'class')} ${(Number(item.confidence) * 100).toFixed(0)}%`;
    const labelWidth = context.measureText(label).width + 10;
    context.fillStyle = labelBackground;
    context.fillRect(x, Math.max(0, y - 20), labelWidth, 20);
    context.fillStyle = color;
    context.fillText(label, x + 5, Math.max(14, y - 5));
  }
  const lane = laneResult(projection.results);
  if (lane?.payload) {
    const offset = Math.max(-1, Math.min(1, Number(lane.payload.lateral_error_normalized) || 0));
    const curvature = Math.max(-1, Math.min(1, Number(lane.payload.curvature) || 0));
    const center = width * (0.5 + offset * 0.25);
    context.beginPath();
    context.moveTo(center, height);
    context.quadraticCurveTo(center + curvature * width * 0.35, height * 0.55, width * 0.5, height * 0.18);
    context.stroke();
    context.setLineDash([8, 7]);
    if (lane.payload.left_lane_visible) {
      context.beginPath(); context.moveTo(center - width * 0.22, height); context.quadraticCurveTo(center - width * 0.1 + curvature * width * 0.25, height * 0.55, width * 0.38, height * 0.18); context.stroke();
    }
    if (lane.payload.right_lane_visible) {
      context.beginPath(); context.moveTo(center + width * 0.22, height); context.quadraticCurveTo(center + width * 0.1 + curvature * width * 0.25, height * 0.55, width * 0.62, height * 0.18); context.stroke();
    }
  }
  context.restore();
  return true;
}

export function createPerceptionClient(options = {}) {
  const request = options.api;
  const now = options.now || Date.now;
  const setIntervalValue = options.setInterval || globalThis.setInterval?.bind(globalThis);
  const clearIntervalValue = options.clearInterval || globalThis.clearInterval?.bind(globalThis);
  let snapshot = { mode: 'SHADOW', transport_state: 'WAITING', results: [] };
  let updatedAt = 0;
  let timer = 0;
  const subscribers = new Set();

  function publish() {
    const age = updatedAt ? Math.max(0, now() - updatedAt) : Number.POSITIVE_INFINITY;
    for (const subscriber of subscribers) subscriber(snapshot, age);
  }

  async function refresh() {
    if (typeof options.shouldPoll === 'function' && !options.shouldPoll()) {
      publish();
      return;
    }
    try {
      const next = await request('/api/v1/perception/latest');
      snapshot = next && typeof next === 'object' ? next : { mode: 'SHADOW', transport_state: 'OFFLINE', results: [] };
      updatedAt = now();
    } catch (_) {
      snapshot = { ...snapshot, transport_state: 'OFFLINE' };
    }
    publish();
  }

  function start() {
    if (timer) return client;
    refresh();
    timer = setIntervalValue?.(refresh, 500) || 0;
    return client;
  }

  function stop() {
    if (timer) clearIntervalValue?.(timer);
    timer = 0;
  }

  function subscribe(callback) {
    subscribers.add(callback);
    callback(snapshot, updatedAt ? Math.max(0, now() - updatedAt) : Number.POSITIVE_INFINITY);
    return () => subscribers.delete(callback);
  }

  const client = Object.freeze({ start, stop, refresh, subscribe, snapshot: () => Object.freeze({ snapshot, updatedAt }) });
  return client;
}

export function bindSensorPerception(client, getSlots) {
  return client.subscribe((snapshot, localAgeMs) => {
    for (const slot of Object.values(getSlots())) {
      const canvas = slot.root?.querySelector?.('.perception-overlay-canvas');
      const hud = slot.root?.querySelector?.('.perception-overlay-hud');
      if (!canvas || !hud) continue;
      const projected = projectPerceptionOverlay(snapshot, slot.sourceId, localAgeMs);
      drawPerceptionOverlay(canvas, slot.canvas, projected);
      hud.dataset.state = projected.state.toLowerCase();
      hud.querySelector('strong').textContent = `SHADOW · ${projected.state}`;
      hud.querySelector('span').textContent = `MODEL ${projected.model} · SEQ ${projected.sequence} · AGE ${projected.age} · ${projected.fps} · ${projected.latency}`;
      hud.hidden = slot.sourceId !== 'realsense_color';
    }
  });
}

export { PERCEPTION_STALE_MS };
