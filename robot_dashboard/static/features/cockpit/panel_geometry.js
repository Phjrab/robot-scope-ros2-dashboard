export const PANEL_MODES = Object.freeze(['compact', 'floating', 'focus']);
export const PANEL_DOCKS = Object.freeze(['left', 'right', 'top', 'bottom']);
export const PANEL_Z_MIN = 1;
export const PANEL_Z_MAX = 24;

const DEFAULT_BOUNDS = Object.freeze({
  minWidth: 240,
  minHeight: 140,
  maxWidth: 960,
  maxHeight: 720,
  compactWidth: 280,
  compactHeight: 58,
});

function finite(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

export function normalizePanelBounds(value = {}) {
  const minWidth = Math.max(160, finite(value.minWidth, DEFAULT_BOUNDS.minWidth));
  const minHeight = Math.max(58, finite(value.minHeight, DEFAULT_BOUNDS.minHeight));
  const maxWidth = Math.max(minWidth, finite(value.maxWidth, DEFAULT_BOUNDS.maxWidth));
  const maxHeight = Math.max(minHeight, finite(value.maxHeight, DEFAULT_BOUNDS.maxHeight));
  return Object.freeze({
    minWidth,
    minHeight,
    maxWidth,
    maxHeight,
    compactWidth: clamp(finite(value.compactWidth, DEFAULT_BOUNDS.compactWidth), 160, maxWidth),
    compactHeight: clamp(finite(value.compactHeight, DEFAULT_BOUNDS.compactHeight), 48, minHeight),
  });
}

export function usableViewport(value = {}) {
  const width = Math.max(1, finite(value.width, 1));
  const height = Math.max(1, finite(value.height, 1));
  const padding = Math.max(0, finite(value.padding, 12));
  const left = clamp(padding + Math.max(0, finite(value.reservedLeft, 0)), 0, width);
  const top = clamp(padding + Math.max(0, finite(value.reservedTop, 0)), 0, height);
  const right = clamp(width - padding - Math.max(0, finite(value.reservedRight, 0)), left, width);
  const bottom = clamp(height - padding - Math.max(0, finite(value.reservedBottom, 0)), top, height);
  return Object.freeze({ x: left, y: top, width: Math.max(1, right - left), height: Math.max(1, bottom - top) });
}

function fallbackGeometry(value, viewport, bounds) {
  const width = Math.min(Math.max(bounds.minWidth, viewport.width * 0.34), bounds.maxWidth, viewport.width);
  const height = Math.min(Math.max(bounds.minHeight, viewport.height * 0.32), bounds.maxHeight, viewport.height);
  return {
    x: viewport.x + Math.max(0, finite(value?.defaultX, 20)),
    y: viewport.y + Math.max(0, finite(value?.defaultY, 20)),
    width,
    height,
  };
}

export function clampPanelGeometry(value = {}, viewportValue = {}, boundsValue = {}, fallbackValue = {}) {
  const viewport = usableViewport(viewportValue);
  const bounds = normalizePanelBounds(boundsValue);
  const fallback = fallbackGeometry(fallbackValue, viewport, bounds);
  const maxWidth = Math.min(bounds.maxWidth, viewport.width);
  const maxHeight = Math.min(bounds.maxHeight, viewport.height);
  const minWidth = Math.min(bounds.minWidth, maxWidth);
  const minHeight = Math.min(bounds.minHeight, maxHeight);
  const width = clamp(finite(value.width, fallback.width), minWidth, maxWidth);
  const height = clamp(finite(value.height, fallback.height), minHeight, maxHeight);
  const x = clamp(finite(value.x, fallback.x), viewport.x, viewport.x + viewport.width - width);
  const y = clamp(finite(value.y, fallback.y), viewport.y, viewport.y + viewport.height - height);
  return Object.freeze({ x, y, width, height });
}

export function compactPanelGeometry(value, viewportValue, boundsValue) {
  const bounds = normalizePanelBounds(boundsValue);
  return clampPanelGeometry({
    ...value,
    width: bounds.compactWidth,
    height: bounds.compactHeight,
  }, viewportValue, { ...bounds, minHeight: bounds.compactHeight }, value);
}

export function resizePanelGeometry(start, handle, dx, dy, viewportValue, boundsValue) {
  const next = { ...start };
  const viewport = usableViewport(viewportValue);
  const bounds = normalizePanelBounds(boundsValue);
  const deltaX = finite(dx, 0);
  const deltaY = finite(dy, 0);
  const minWidth = Math.min(bounds.minWidth, viewport.width);
  const minHeight = Math.min(bounds.minHeight, viewport.height);
  const maxWidth = Math.min(bounds.maxWidth, viewport.width);
  const maxHeight = Math.min(bounds.maxHeight, viewport.height);
  const left = finite(start.x, viewport.x);
  const top = finite(start.y, viewport.y);
  const right = left + finite(start.width, minWidth);
  const bottom = top + finite(start.height, minHeight);
  if (String(handle).includes('e')) next.width = clamp(right + deltaX, left + minWidth, Math.min(left + maxWidth, viewport.x + viewport.width)) - left;
  if (String(handle).includes('s')) next.height = clamp(bottom + deltaY, top + minHeight, Math.min(top + maxHeight, viewport.y + viewport.height)) - top;
  if (String(handle).includes('w')) {
    next.x = clamp(left + deltaX, Math.max(viewport.x, right - maxWidth), right - minWidth);
    next.width = right - next.x;
  }
  if (String(handle).includes('n')) {
    next.y = clamp(top + deltaY, Math.max(viewport.y, bottom - maxHeight), bottom - minHeight);
    next.height = bottom - next.y;
  }
  return clampPanelGeometry(next, viewportValue, bounds, start);
}

export function movePanelGeometry(start, dx, dy, viewportValue, boundsValue) {
  return clampPanelGeometry({
    ...start,
    x: finite(start.x, 0) + finite(dx, 0),
    y: finite(start.y, 0) + finite(dy, 0),
  }, viewportValue, boundsValue, start);
}

export function focusPanelGeometry(viewportValue = {}) {
  const viewport = usableViewport(viewportValue);
  return Object.freeze({ x: viewport.x, y: viewport.y, width: viewport.width, height: viewport.height });
}

export function recoverPanelState(state, viewportValue, boundsValue) {
  if (state.mode === 'focus') return Object.freeze({ ...state, ...focusPanelGeometry(viewportValue) });
  const geometry = state.mode === 'compact'
    ? compactPanelGeometry(state, viewportValue, boundsValue)
    : clampPanelGeometry(state, viewportValue, boundsValue, state);
  return Object.freeze({ ...state, ...geometry });
}

export function restoreFocusedPanel(state, viewportValue, boundsValue) {
  const restore = state.restoreGeometry;
  const mode = PANEL_MODES.includes(restore?.mode) && restore.mode !== 'focus' ? restore.mode : 'floating';
  const base = { ...state, ...(restore || {}), mode, restoreGeometry: null };
  return recoverPanelState(base, viewportValue, boundsValue);
}

export function normalizePanelZOrder(states, activeId = '', maxZ = PANEL_Z_MAX) {
  const boundedMax = clamp(Math.floor(finite(maxZ, PANEL_Z_MAX)), PANEL_Z_MIN, PANEL_Z_MAX);
  const ordered = [...states].sort((left, right) => {
    if (left.id === activeId) return 1;
    if (right.id === activeId) return -1;
    const delta = finite(left.zIndex, PANEL_Z_MIN) - finite(right.zIndex, PANEL_Z_MIN);
    return delta || String(left.id).localeCompare(String(right.id));
  });
  if (ordered.length > boundedMax) throw new RangeError('Panel count exceeds bounded z-order capacity.');
  return ordered.map((state, index) => Object.freeze({ ...state, zIndex: index + PANEL_Z_MIN }));
}

export function panelStateSnapshot(state) {
  const restoreGeometry = state.restoreGeometry
    ? Object.freeze({
        mode: PANEL_MODES.includes(state.restoreGeometry.mode) && state.restoreGeometry.mode !== 'focus' ? state.restoreGeometry.mode : 'floating',
        dock: PANEL_DOCKS.includes(state.restoreGeometry.dock) ? state.restoreGeometry.dock : null,
        x: finite(state.restoreGeometry.x, 0),
        y: finite(state.restoreGeometry.y, 0),
        width: Math.max(1, finite(state.restoreGeometry.width, 1)),
        height: Math.max(1, finite(state.restoreGeometry.height, 1)),
      })
    : null;
  return Object.freeze({
    id: String(state.id),
    panelType: String(state.panelType),
    title: String(state.title),
    mode: PANEL_MODES.includes(state.mode) ? state.mode : 'floating',
    x: finite(state.x, 0),
    y: finite(state.y, 0),
    width: Math.max(1, finite(state.width, 1)),
    height: Math.max(1, finite(state.height, 1)),
    zIndex: clamp(Math.floor(finite(state.zIndex, PANEL_Z_MIN)), PANEL_Z_MIN, PANEL_Z_MAX),
    pinned: Boolean(state.pinned),
    locked: Boolean(state.locked),
    visible: Boolean(state.visible),
    dock: PANEL_DOCKS.includes(state.dock) ? state.dock : null,
    restoreGeometry,
  });
}
