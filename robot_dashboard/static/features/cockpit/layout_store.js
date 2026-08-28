import { COCKPIT_LAYOUT_MAX_BYTES, COCKPIT_LAYOUT_MAX_PRESETS, normalizeLayoutName, parseLayoutDocument } from './layout_schema.js';

const STORAGE_PREFIX = 'robot-scope.cockpit.layouts.v1.';

function emptyCatalog(profileId) {
  return { schema_version: 1, profile_id: profileId, default_preset: null, presets: [] };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function createLayoutStore(options = {}) {
  let storage = options.storage;
  if (!storage) {
    try { storage = globalThis.localStorage; } catch (error) { options.onError?.(error); }
  }
  const allowedPanelTypes = options.allowedPanelTypes || [];
  const panelIdsByType = options.panelIdsByType || {};
  let profileId = '';
  let catalog = emptyCatalog('generic');
  let corrupted = false;

  function key() { return `${STORAGE_PREFIX}${profileId}`; }

  function parseCatalog(raw) {
    if (new TextEncoder().encode(raw).byteLength > COCKPIT_LAYOUT_MAX_BYTES) throw new RangeError('Stored layout catalog is too large.');
    const value = JSON.parse(raw);
    const keys = value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value) : [];
    if (keys.some((item) => !['schema_version', 'profile_id', 'default_preset', 'presets'].includes(item)) || value.schema_version !== 1 || value.profile_id !== profileId || !Array.isArray(value.presets) || value.presets.length > COCKPIT_LAYOUT_MAX_PRESETS) throw new TypeError('Stored layout catalog is invalid.');
    const presets = value.presets.map((preset) => parseLayoutDocument(preset, { profileId, allowedPanelTypes, panelIdsByType }));
    const names = new Set(presets.map((preset) => preset.name));
    if (names.size !== presets.length) throw new TypeError('Stored layout names must be unique.');
    const defaultPreset = value.default_preset == null ? null : normalizeLayoutName(value.default_preset);
    if (defaultPreset && !names.has(defaultPreset)) throw new TypeError('Stored default layout is missing.');
    return { schema_version: 1, profile_id: profileId, default_preset: defaultPreset, presets };
  }

  function setProfile(nextProfileId) {
    profileId = String(nextProfileId || '');
    catalog = emptyCatalog(profileId);
    corrupted = false;
    try {
      const raw = storage?.getItem(key());
      if (raw) catalog = parseCatalog(raw);
    } catch (error) {
      corrupted = true;
      options.onError?.(error);
    }
    return snapshot();
  }

  function persist(next) {
    const raw = JSON.stringify(next);
    if (new TextEncoder().encode(raw).byteLength > COCKPIT_LAYOUT_MAX_BYTES) throw new RangeError('Layout catalog is too large.');
    if (!storage) throw new Error('Browser layout storage is unavailable.');
    storage.setItem(key(), raw);
    catalog = next;
    corrupted = false;
    return snapshot();
  }

  function save(document, { setDefault = false } = {}) {
    const parsed = parseLayoutDocument(document, { profileId, allowedPanelTypes, panelIdsByType });
    const existing = catalog.presets.findIndex((preset) => preset.name === parsed.name);
    const presets = catalog.presets.slice();
    if (existing >= 0) presets[existing] = parsed;
    else {
      if (presets.length >= COCKPIT_LAYOUT_MAX_PRESETS) throw new RangeError('Preset limit reached.');
      presets.push(parsed);
    }
    const defaultPreset = setDefault || !catalog.default_preset ? parsed.name : catalog.default_preset;
    return persist({ schema_version: 1, profile_id: profileId, default_preset: defaultPreset, presets });
  }

  function remove(name) {
    name = normalizeLayoutName(name);
    const presets = catalog.presets.filter((preset) => preset.name !== name);
    if (presets.length === catalog.presets.length) return snapshot();
    return persist({ schema_version: 1, profile_id: profileId, default_preset: catalog.default_preset === name ? presets[0]?.name || null : catalog.default_preset, presets });
  }

  function setDefault(name) {
    name = normalizeLayoutName(name);
    if (!catalog.presets.some((preset) => preset.name === name)) throw new RangeError('Preset does not exist.');
    return persist({ ...catalog, default_preset: name });
  }

  function reset() {
    storage?.removeItem(key());
    catalog = emptyCatalog(profileId);
    corrupted = false;
    return snapshot();
  }

  function get(name) {
    const preset = catalog.presets.find((item) => item.name === name);
    return preset ? parseLayoutDocument(clone(preset), { profileId, allowedPanelTypes, panelIdsByType }) : null;
  }

  function previewImport(text) {
    return parseLayoutDocument(text, { profileId, allowedPanelTypes, panelIdsByType });
  }

  function snapshot() {
    return Object.freeze({ profileId, defaultPreset: catalog.default_preset, corrupted, storageAvailable: Boolean(storage), presets: Object.freeze(catalog.presets.map((preset) => Object.freeze({ name: preset.name, panelCount: preset.panels.length }))) });
  }

  return Object.freeze({ setProfile, save, remove, setDefault, reset, get, getDefault: () => catalog.default_preset ? get(catalog.default_preset) : null, previewImport, exportJson: (name) => JSON.stringify(get(name), null, 2), snapshot });
}
