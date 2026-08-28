import {
  clampPanelGeometry,
  compactPanelGeometry,
  normalizePanelBounds,
  usableViewport,
} from './panel_geometry.js';

export const DOCK_POSITIONS = Object.freeze(['left', 'right', 'top', 'bottom']);

function finite(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function normalizeSnapOptions(value = {}) {
  return Object.freeze({
    enabled: value.enabled !== false,
    threshold: Math.max(0, Math.min(40, finite(value.threshold, 14))),
    gridSize: Math.max(4, Math.min(64, Math.round(finite(value.gridSize, 16)))),
  });
}

function nearestCandidate(position, candidates, threshold) {
  return candidates
    .map((candidate) => ({ ...candidate, distance: Math.abs(position - candidate.value) }))
    .filter((candidate) => candidate.distance <= threshold)
    .sort((left, right) => left.distance - right.distance || left.kind.localeCompare(right.kind))[0] || null;
}

function gridPosition(position, origin, size) {
  return origin + Math.round((position - origin) / size) * size;
}

export function snapPanelGeometry(value, viewportValue, peers = [], optionsValue = {}) {
  const options = normalizeSnapOptions(optionsValue);
  const viewport = usableViewport(viewportValue);
  const geometry = clampPanelGeometry(value, viewportValue, optionsValue.bounds || {}, value);
  if (!options.enabled || optionsValue.disabled) return Object.freeze({ geometry, preview: null });

  const xCandidates = [
    { value: viewport.x, kind: 'viewport-left' },
    { value: viewport.x + viewport.width - geometry.width, kind: 'viewport-right' },
  ];
  const yCandidates = [
    { value: viewport.y, kind: 'viewport-top' },
    { value: viewport.y + viewport.height - geometry.height, kind: 'viewport-bottom' },
  ];
  for (const peer of peers) {
    if (!peer?.visible || peer.mode === 'focus') continue;
    const left = finite(peer.x, 0);
    const top = finite(peer.y, 0);
    const right = left + Math.max(1, finite(peer.width, 1));
    const bottom = top + Math.max(1, finite(peer.height, 1));
    xCandidates.push(
      { value: left, kind: `panel-${peer.id}-left-align` },
      { value: right, kind: `panel-${peer.id}-right-edge` },
      { value: left - geometry.width, kind: `panel-${peer.id}-left-edge` },
      { value: right - geometry.width, kind: `panel-${peer.id}-right-align` },
    );
    yCandidates.push(
      { value: top, kind: `panel-${peer.id}-top-align` },
      { value: bottom, kind: `panel-${peer.id}-bottom-edge` },
      { value: top - geometry.height, kind: `panel-${peer.id}-top-edge` },
      { value: bottom - geometry.height, kind: `panel-${peer.id}-bottom-align` },
    );
  }

  const xMatch = nearestCandidate(geometry.x, xCandidates, options.threshold);
  const yMatch = nearestCandidate(geometry.y, yCandidates, options.threshold);
  const x = xMatch?.value ?? gridPosition(geometry.x, viewport.x, options.gridSize);
  const y = yMatch?.value ?? gridPosition(geometry.y, viewport.y, options.gridSize);
  const snapped = clampPanelGeometry({ ...geometry, x, y }, viewportValue, optionsValue.bounds || {}, geometry);
  const changed = snapped.x !== geometry.x || snapped.y !== geometry.y;
  const kinds = [xMatch?.kind, yMatch?.kind].filter(Boolean);
  if (!kinds.length && changed) kinds.push('grid');
  return Object.freeze({
    geometry: snapped,
    preview: changed || kinds.length ? Object.freeze({ kind: kinds.join('+') || 'grid', geometry: snapped }) : null,
  });
}

export function dockPanelGeometry(position, viewportValue, boundsValue = {}, fallbackValue = {}) {
  if (!DOCK_POSITIONS.includes(position)) throw new RangeError('Unknown dock position.');
  const viewport = usableViewport(viewportValue);
  const bounds = normalizePanelBounds(boundsValue);
  const vertical = position === 'left' || position === 'right';
  const target = {
    x: position === 'right' ? viewport.x + viewport.width / 2 : viewport.x,
    y: position === 'bottom' ? viewport.y + viewport.height / 2 : viewport.y,
    width: vertical ? viewport.width / 2 : viewport.width,
    height: vertical ? viewport.height : viewport.height / 2,
  };
  if (target.width < bounds.minWidth || target.height < bounds.minHeight) {
    return Object.freeze({ mode: 'compact', dock: null, geometry: compactPanelGeometry(fallbackValue, viewportValue, bounds) });
  }
  return Object.freeze({ mode: 'floating', dock: position, geometry: Object.freeze(target) });
}

function compactArrangement(entries, viewportValue) {
  const viewport = usableViewport(viewportValue);
  return entries.map((entry, index) => {
    const offset = index * 28;
    const geometry = compactPanelGeometry({
      ...entry.geometry,
      x: viewport.x + offset,
      y: viewport.y + offset,
    }, viewportValue, entry.bounds);
    return Object.freeze({ id: entry.id, mode: 'compact', dock: null, geometry });
  });
}

export function splitPanelLayout(entries, viewportValue) {
  const selected = entries.slice(0, 2);
  if (selected.length < 2) return compactArrangement(selected, viewportValue);
  const viewport = usableViewport(viewportValue);
  const gap = Math.min(12, viewport.width / 20);
  const cellWidth = (viewport.width - gap) / 2;
  if (selected.some((entry) => cellWidth < normalizePanelBounds(entry.bounds).minWidth || viewport.height < normalizePanelBounds(entry.bounds).minHeight)) {
    return compactArrangement(selected, viewportValue);
  }
  return selected.map((entry, index) => Object.freeze({
    id: entry.id,
    mode: 'floating',
    dock: index ? 'right' : 'left',
    geometry: Object.freeze({
      x: viewport.x + index * (cellWidth + gap),
      y: viewport.y,
      width: cellWidth,
      height: viewport.height,
    }),
  }));
}

export function tilePanelLayout(entries, viewportValue) {
  const selected = entries.slice(0, 4);
  const viewport = usableViewport(viewportValue);
  const gap = Math.min(12, Math.min(viewport.width, viewport.height) / 20);
  const cellWidth = (viewport.width - gap) / 2;
  const cellHeight = (viewport.height - gap) / 2;
  if (selected.some((entry) => {
    const bounds = normalizePanelBounds(entry.bounds);
    return cellWidth < bounds.minWidth || cellHeight < bounds.minHeight;
  })) return compactArrangement(selected, viewportValue);
  return selected.map((entry, index) => Object.freeze({
    id: entry.id,
    mode: 'floating',
    dock: null,
    geometry: Object.freeze({
      x: viewport.x + (index % 2) * (cellWidth + gap),
      y: viewport.y + Math.floor(index / 2) * (cellHeight + gap),
      width: cellWidth,
      height: cellHeight,
    }),
  }));
}

export function cascadePanelLayout(entries, viewportValue) {
  const viewport = usableViewport(viewportValue);
  const step = Math.max(20, Math.min(34, Math.min(viewport.width, viewport.height) / 12));
  return entries.map((entry, index) => {
    const bounds = normalizePanelBounds(entry.bounds);
    const desired = {
      ...entry.geometry,
      x: viewport.x + index * step,
      y: viewport.y + index * step,
      width: Math.min(bounds.maxWidth, Math.max(bounds.minWidth, viewport.width * 0.58)),
      height: Math.min(bounds.maxHeight, Math.max(bounds.minHeight, viewport.height * 0.56)),
    };
    const geometry = clampPanelGeometry(desired, viewportValue, entry.bounds, entry.geometry);
    return Object.freeze({ id: entry.id, mode: 'floating', dock: null, geometry });
  });
}
