import { createCameraPanelView } from './camera_panel_view.js';

export const CAMERA_PANEL_STALE_MS = 3000;

function finite(value, fallback = null) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function projectCameraPanelState(source = {}, lastRenderedAt = 0, now = Date.now(), staleMs = CAMERA_PANEL_STALE_MS) {
  const localAgeMs = lastRenderedAt ? Math.max(0, Number(now) - Number(lastRenderedAt)) : null;
  const metadata = source.metadata || {};
  const reportedAge = metadata.age_s ?? source.age_s;
  const reportedAgeMs = reportedAge == null ? null : finite(reportedAge * 1000);
  const stateValue = String(metadata.state || source.state || '').toLowerCase();
  const stale = Boolean(lastRenderedAt) && (
    !Number.isFinite(localAgeMs) || localAgeMs > staleMs || (Number.isFinite(reportedAgeMs) && reportedAgeMs > staleMs)
    || stateValue === 'stale'
  );
  const error = source.error || stateValue === 'error';
  const live = Boolean(lastRenderedAt) && !stale && !error && source.connection === 'live';
  const state = error ? 'ERROR' : stale ? 'STALE' : live ? 'LIVE' : 'WAITING';
  const width = Number(metadata.width || source.width || 0);
  const height = Number(metadata.height || source.height || 0);
  const fps = finite(metadata.fps ?? source.fps);
  const ageMs = localAgeMs ?? reportedAgeMs;
  return Object.freeze({
    state,
    fps: fps == null ? '—' : `${fps.toFixed(fps >= 10 ? 1 : 2)} FPS`,
    age: ageMs == null ? '—' : `${(ageMs / 1000).toFixed(1)} s`,
    resolution: width > 0 && height > 0 ? `${width}×${height}` : '—',
    transport: String(metadata.transport || source.transport || '—').toUpperCase(),
    reconnect: source.reconnecting ? 'RECONNECTING' : state === 'ERROR' ? 'ERROR' : source.connection === 'live' || source.connection === 'connected' ? 'CONNECTED' : 'WAITING',
    overlay: state === 'LIVE' ? '' : state === 'STALE' ? `STALE · ${ageMs == null ? 'AGE UNKNOWN' : `${(ageMs / 1000).toFixed(1)} s`}` : state === 'ERROR' ? 'CAMERA ERROR' : 'WAITING FOR FRAME',
  });
}

export function createCameraPanel(options = {}) {
  const descriptor = options.descriptor;
  const demand = options.cameraDemand;
  const documentValue = options.document || globalThis.document;
  const now = options.now || Date.now;
  const setIntervalValue = options.setInterval || globalThis.setInterval?.bind(globalThis);
  const clearIntervalValue = options.clearInterval || globalThis.clearInterval?.bind(globalThis);
  if (!descriptor?.sourceId || !demand) throw new TypeError('CameraPanel requires a fixed source descriptor and demand controller.');
  let view = null;
  let token = null;
  let timer = 0;
  let active = false;
  let destroyed = false;
  let sourceState = demand.sourceSnapshot(descriptor.sourceId);
  let lastRenderedAt = 0;
  let renders = 0;
  let activations = 0;
  let deactivations = 0;

  function refresh() {
    view?.render(projectCameraPanelState(sourceState, lastRenderedAt, now()));
  }

  function mount(root) {
    if (destroyed || view) return;
    view = (options.viewFactory || createCameraPanelView)({ root, document: documentValue, label: descriptor.label });
    refresh();
  }

  function activate() {
    if (destroyed || active || !view) return;
    active = true;
    activations += 1;
    token = demand.acquire(descriptor.sourceId, {
      onState(nextState) {
        if (!active) return;
        sourceState = nextState;
        refresh();
      },
      onFrame(frame) {
        if (!active || !view.renderFrame(frame)) return;
        sourceState = frame.source;
        lastRenderedAt = Number(frame.lastFrameAt) || now();
        renders += 1;
        refresh();
      },
    });
    timer = setIntervalValue?.(refresh, 500) || 0;
    refresh();
  }

  function deactivate() {
    if (!active) return;
    active = false;
    deactivations += 1;
    if (timer) clearIntervalValue?.(timer);
    timer = 0;
    token?.release();
    token = null;
    lastRenderedAt = 0;
    view?.clearFrame();
    refresh();
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    view?.destroy();
    view = null;
    destroyed = true;
  }

  function diagnostics() {
    return Object.freeze({ active, destroyed, sourceId: descriptor.sourceId, demand: Boolean(token), renders, activations, deactivations, state: projectCameraPanelState(sourceState, lastRenderedAt, now()).state });
  }

  return Object.freeze({ mount, activate, deactivate, destroy, diagnostics });
}
