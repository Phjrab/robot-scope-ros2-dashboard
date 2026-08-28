import { COCKPIT_LAYOUT_SCHEMA_VERSION, migrateLayoutDocument } from './layout_migrations.js';
import { usableViewport } from './panel_geometry.js';

export const COCKPIT_LAYOUT_MAX_BYTES = 32768;
export const COCKPIT_LAYOUT_MAX_PANELS = 24;
export const COCKPIT_LAYOUT_NAME_MAX = 48;
export const COCKPIT_LAYOUT_MAX_PRESETS = 12;

const PROFILE_PATTERN = /^[a-z][a-z0-9_-]{0,31}$/;
const PANEL_ID_PATTERN = /^[a-z][a-z0-9-]{1,63}$/;
const PANEL_TYPE_PATTERN = /^[a-z][a-z0-9.-]{1,63}$/;
const MODES = new Set(['floating', 'compact', 'focus']);
const DOCKS = new Set(['left', 'right', 'top', 'bottom']);
const VIEWS = new Set(['isometric', 'top', 'front', 'robot-follow', 'custom']);

function exactObject(value, keys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError(`${label} must be an object.`);
  const actual = Object.keys(value);
  if (actual.some((key) => !keys.includes(key))) throw new TypeError(`${label} contains an unknown field.`);
  return value;
}

function boundedNumber(value, low, high, label) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < low || number > high) throw new RangeError(`${label} is outside the allowed range.`);
  return number;
}

function boundedToken(value, pattern, label) {
  const token = String(value || '');
  if (!pattern.test(token)) throw new TypeError(`${label} is invalid.`);
  return token;
}

export function normalizeLayoutName(value) {
  const name = String(value || '').trim();
  if (!name || name.length > COCKPIT_LAYOUT_NAME_MAX || /[\u0000-\u001f\u007f]/.test(name)) throw new TypeError('Preset name is invalid.');
  return name;
}

function jsonBytes(value) {
  return new TextEncoder().encode(value).byteLength;
}

function validateGeometry(value, label) {
  const x = boundedNumber(value.x, 0, 1, `${label}.x`);
  const y = boundedNumber(value.y, 0, 1, `${label}.y`);
  const width = boundedNumber(value.width, 0.01, 1, `${label}.width`);
  const height = boundedNumber(value.height, 0.01, 1, `${label}.height`);
  if (x + width > 1.000001 || y + height > 1.000001) throw new RangeError(`${label} must fit inside the normalized viewport.`);
  return { x, y, width, height };
}

function validateRestore(value, label) {
  if (value == null) return null;
  exactObject(value, ['mode', 'dock', 'x', 'y', 'width', 'height'], label);
  const mode = String(value.mode || '');
  if (!MODES.has(mode) || mode === 'focus') throw new TypeError(`${label}.mode is invalid.`);
  const dock = value.dock == null ? null : String(value.dock);
  if (dock && !DOCKS.has(dock)) throw new TypeError(`${label}.dock is invalid.`);
  return Object.freeze({ mode, dock, ...validateGeometry(value, label) });
}

function validatePanel(value, index, allowedTypes, panelIdsByType) {
  const label = `panels[${index}]`;
  exactObject(value, ['id', 'panel_type', 'mode', 'dock', 'x', 'y', 'width', 'height', 'z_index', 'pinned', 'locked', 'restore_geometry'], label);
  const id = boundedToken(value.id, PANEL_ID_PATTERN, `${label}.id`);
  const panelType = boundedToken(value.panel_type, PANEL_TYPE_PATTERN, `${label}.panel_type`);
  if (!allowedTypes.has(panelType)) throw new TypeError(`${label}.panel_type is not registered.`);
  if (panelIdsByType?.[panelType] && panelIdsByType[panelType] !== id) throw new TypeError(`${label}.id does not match its registered panel type.`);
  const mode = String(value.mode || '');
  if (!MODES.has(mode)) throw new TypeError(`${label}.mode is invalid.`);
  const dock = value.dock == null ? null : String(value.dock);
  if (dock && !DOCKS.has(dock)) throw new TypeError(`${label}.dock is invalid.`);
  if (typeof value.pinned !== 'boolean' || typeof value.locked !== 'boolean') throw new TypeError(`${label} flags must be boolean.`);
  const restoreGeometry = validateRestore(value.restore_geometry, `${label}.restore_geometry`);
  if (mode === 'focus' && !restoreGeometry) throw new TypeError(`${label} focus mode requires restore geometry.`);
  const zIndex = value.z_index == null ? index + 1 : boundedNumber(value.z_index, 1, COCKPIT_LAYOUT_MAX_PANELS, `${label}.z_index`);
  if (!Number.isInteger(zIndex)) throw new TypeError(`${label}.z_index must be an integer.`);
  return Object.freeze({ id, panel_type: panelType, mode, dock, ...validateGeometry(value, label), z_index: zIndex, pinned: value.pinned, locked: value.locked, restore_geometry: restoreGeometry });
}

function validateScene(value) {
  exactObject(value, ['view', 'follow_robot', 'point_size', 'range_m'], 'scene');
  const view = String(value.view || '');
  if (!VIEWS.has(view) || typeof value.follow_robot !== 'boolean') throw new TypeError('Scene view is invalid.');
  return Object.freeze({
    view,
    follow_robot: value.follow_robot,
    point_size: boundedNumber(value.point_size, 0.25, 8, 'scene.point_size'),
    range_m: boundedNumber(value.range_m, 1, 500, 'scene.range_m'),
  });
}

export function parseLayoutDocument(input, options = {}) {
  if (typeof input === 'string') {
    if (jsonBytes(input) > (options.maxBytes || COCKPIT_LAYOUT_MAX_BYTES)) throw new RangeError('Layout JSON is too large.');
    try { input = JSON.parse(input); } catch (_) { throw new SyntaxError('Layout JSON is invalid.'); }
  }
  const value = migrateLayoutDocument(input);
  exactObject(value, ['schema_version', 'name', 'profile_id', 'scene', 'panels'], 'layout');
  const profileId = boundedToken(value.profile_id, PROFILE_PATTERN, 'profile_id');
  if (options.profileId && profileId !== options.profileId) throw new TypeError('Layout profile does not match the active robot profile.');
  if (!Array.isArray(value.panels) || value.panels.length > (options.maxPanels || COCKPIT_LAYOUT_MAX_PANELS)) throw new RangeError('Layout panel count is invalid.');
  const allowedTypes = new Set(options.allowedPanelTypes || []);
  const panels = value.panels.map((panel, index) => validatePanel(panel, index, allowedTypes, options.panelIdsByType));
  const ids = new Set();
  for (const panel of panels) {
    if (ids.has(panel.id)) throw new TypeError('Layout contains a duplicate panel id.');
    ids.add(panel.id);
  }
  const document = Object.freeze({
    schema_version: COCKPIT_LAYOUT_SCHEMA_VERSION,
    name: normalizeLayoutName(value.name),
    profile_id: profileId,
    scene: validateScene(value.scene),
    panels: Object.freeze(panels),
  });
  if (jsonBytes(JSON.stringify(document)) > (options.maxBytes || COCKPIT_LAYOUT_MAX_BYTES)) throw new RangeError('Layout JSON is too large.');
  return document;
}

function normalizedGeometry(value, area) {
  const width = Math.max(0.01, Math.min(1, value.width / area.width));
  const height = Math.max(0.01, Math.min(1, value.height / area.height));
  return {
    x: Math.max(0, Math.min(1 - width, (value.x - area.x) / area.width)),
    y: Math.max(0, Math.min(1 - height, (value.y - area.y) / area.height)),
    width,
    height,
  };
}

export function createLayoutDocument(options = {}) {
  const area = usableViewport(options.viewport);
  const panels = [...(options.panels || [])].filter((panel) => panel.visible).sort((a, b) => a.zIndex - b.zIndex).map((panel) => ({
    id: panel.id,
    panel_type: panel.panelType,
    mode: panel.mode,
    dock: panel.dock || null,
    ...normalizedGeometry(panel, area),
    z_index: panel.zIndex,
    pinned: Boolean(panel.pinned),
    locked: Boolean(panel.locked),
    restore_geometry: panel.restoreGeometry ? { mode: panel.restoreGeometry.mode, dock: panel.restoreGeometry.dock || null, ...normalizedGeometry(panel.restoreGeometry, area) } : null,
  }));
  return parseLayoutDocument({ schema_version: COCKPIT_LAYOUT_SCHEMA_VERSION, name: options.name, profile_id: options.profileId, scene: options.scene, panels }, options);
}

function pixelGeometry(value, area) {
  return { x: area.x + value.x * area.width, y: area.y + value.y * area.height, width: value.width * area.width, height: value.height * area.height };
}

export function layoutPanelsToPixels(document, viewport) {
  const area = usableViewport(viewport);
  return document.panels.map((panel, index) => ({
    id: panel.id,
    panelType: panel.panel_type,
    mode: panel.mode,
    dock: panel.dock,
    ...pixelGeometry(panel, area),
    pinned: panel.pinned,
    locked: panel.locked,
    visible: true,
    zIndex: panel.z_index || index + 1,
    restoreGeometry: panel.restore_geometry ? { mode: panel.restore_geometry.mode, dock: panel.restore_geometry.dock, ...pixelGeometry(panel.restore_geometry, area) } : null,
  }));
}
