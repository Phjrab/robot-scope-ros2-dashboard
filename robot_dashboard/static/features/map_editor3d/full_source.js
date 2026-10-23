import { createEditor, EDITOR_LIMITS, validateRegion, VERSION_SCHEMA, VERSION_SCHEMA_VERSION } from './core.js';

export const FULL_SOURCE_EDIT_SCHEMA = 'robot-scope.pcd-edit-request.v1';
const SOURCE_KEYS = ['map_id', 'revision', 'sha256', 'frame_id', 'units', 'asset_role'];
const IDENTITY_KEYS = ['map_id', 'revision', 'frame_id'];
const OPTIONS_KEYS = ['name', 'purpose', 'source', 'annotation'];
const VERSION_KEYS = ['schema', 'schema_version', 'version_id', 'source', 'runtime_installed', 'regions'];

function fail(message) { throw new TypeError(message); }

function exactKeys(value, expected, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) fail(`${label} must be an object`);
  const keys = Reflect.ownKeys(value);
  if (keys.length !== expected.length || keys.some((key) => !expected.includes(key))) {
    fail(`${label} must contain only ${expected.join(', ')}`);
  }
  // JSON data must not hide a sampled point buffer behind a getter or toJSON.
  if (keys.some((key) => !Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), 'value'))) {
    fail(`${label} must contain data properties`);
  }
}

function dataArray(value, label) {
  if (!Array.isArray(value)) fail(`${label} must be an array`);
  const expected = new Set(['length', ...Array.from({ length: value.length }, (_, index) => String(index))]);
  const keys = Reflect.ownKeys(value);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key)
    || !Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), 'value'))) fail(`${label} must contain array data only`);
}

function descriptor(value) {
  exactKeys(value, SOURCE_KEYS, 'Full-source descriptor');
  if (typeof value.map_id !== 'string' || !/^[a-f0-9]{24}$/.test(value.map_id)) fail('Source map_id must be 24 lowercase hex characters');
  for (const key of ['revision', 'sha256']) {
    if (typeof value[key] !== 'string' || !/^[a-f0-9]{64}$/.test(value[key])) fail(`Source ${key} must be 64 lowercase hex characters`);
  }
  if (typeof value.frame_id !== 'string' || !value.frame_id.trim() || value.frame_id.length > 128
    || /[\u0000-\u001f\u007f]/.test(value.frame_id)) fail('Source frame_id must be a nonempty frame name');
  if (value.units !== 'm') fail('Full-source coordinates must use metres (m)');
  if (value.asset_role !== 'full_source') fail('Only a server-provided full_source asset can be saved');
  return Object.freeze(Object.fromEntries(SOURCE_KEYS.map((key) => [key, value[key]])));
}

function annotationVersion(value, source) {
  exactKeys(value, VERSION_KEYS, 'Annotation');
  exactKeys(value.source, IDENTITY_KEYS, 'Annotation source');
  if (value.schema !== VERSION_SCHEMA || value.schema_version !== VERSION_SCHEMA_VERSION) fail('Unsupported annotation version schema');
  if (typeof value.version_id !== 'string' || !value.version_id.trim() || value.version_id.length > 128) fail('Invalid annotation version_id');
  if (value.runtime_installed !== false) fail('Annotation runtime_installed must be false');
  for (const key of IDENTITY_KEYS) {
    if (value.source[key] !== source[key]) fail(`Annotation source ${key} does not match the full-source descriptor; reload the source`);
  }
  if (!Array.isArray(value.regions) || value.regions.length > EDITOR_LIMITS.regions) fail(`Annotation allows at most ${EDITOR_LIMITS.regions} regions`);
  dataArray(value.regions, 'Annotation regions');
  const regions = value.regions.map((region) => {
    const keys = ['kind', 'polygon', 'z_min', 'z_max'];
    if (Object.hasOwn(region ?? {}, 'selection')) keys.push('selection');
    exactKeys(region, keys, 'Region');
    if (!Array.isArray(region.polygon) || region.polygon.length > EDITOR_LIMITS.vertices) fail(`Polygon allows at most ${EDITOR_LIMITS.vertices} vertices`);
    dataArray(region.polygon, 'Polygon');
    for (const vertex of region.polygon) {
      if (!Array.isArray(vertex) || vertex.length !== 2) fail('Polygon vertices must be [x, y] pairs');
      dataArray(vertex, 'Polygon vertex');
    }
    return validateRegion(region);
  });
  // Reuse the existing editor's import/export contract with an empty buffer.
  // The real editor keeps its sampled preview; no preview coordinates enter this request.
  const editor = createEditor({ map_id: source.map_id, revision: source.revision, frame_id: source.frame_id, points: [] });
  editor.importVersion(JSON.stringify({ ...value, regions }));
  return Object.freeze({ ...editor.exportVersion(), version_id: value.version_id });
}

/** Build a save request from editor.exportVersion() and the server's full-source descriptor. */
export function buildFullSourceEditRequest(options) {
  exactKeys(options, OPTIONS_KEYS, 'Full-source save options');
  if (typeof options.name !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(options.name)) fail('Copy name must use 1 to 64 letters, digits, underscores or hyphens');
  if (!['visibility', 'localization'].includes(options.purpose)) fail('Copy purpose must be visibility or localization');
  const source = descriptor(options.source);
  return Object.freeze({ schema: FULL_SOURCE_EDIT_SCHEMA, name: options.name, purpose: options.purpose,
    source, annotation: annotationVersion(options.annotation, source) });
}

/** Save a new catalogue copy only. This function never switches or installs a map. */
export async function saveFullSourceCopy(options) {
  const keys = [...OPTIONS_KEYS];
  if (Object.hasOwn(options ?? {}, 'fetchImpl')) keys.push('fetchImpl');
  exactKeys(options, keys, 'Full-source save options');
  const { fetchImpl = globalThis.fetch, ...input } = options;
  const request = buildFullSourceEditRequest(input);
  if (typeof fetchImpl !== 'function') fail('A fetch implementation is required');
  let response;
  try {
    response = await fetchImpl(`/api/v1/saved-maps/${request.source.map_id}/pcd-edited-copy`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
    });
  } catch {
    throw new Error('Full-source copy could not be saved. Check the connection before trying again.');
  }
  if (!response?.ok) {
    if (response?.status === 409) throw new Error('The full source changed. Reload its descriptor and preview before saving again.');
    const status = Number.isInteger(response?.status) ? ` (HTTP ${response.status})` : '';
    throw new Error(`Full-source copy could not be saved${status}.`);
  }
  try { return await response.json(); } catch {
    throw new Error('The server returned an unreadable save result. Refresh the catalogue before retrying.');
  }
}

/** Wire an annotation-only editor save to the server without changing map selection. */
export function createFullSourceSaveHandler({ api, saveCopy = saveFullSourceCopy, updateCatalog, showToast }) {
  return async ({ name, purpose, annotation }) => {
    const source = await api(`/api/v1/saved-maps/${encodeURIComponent(annotation.source.map_id)}/pcd-edit-source`);
    const result = await saveCopy({ name, purpose, source, annotation });
    // The persisted ID remains available even if the catalogue refresh fails.
    try { updateCatalog(await api('/api/v1/saved-maps')); } catch {
      showToast(`PCD는 저장·등록되었습니다 (${result.map.id}). 지도 목록 새로고침에 실패했습니다.`, true);
    }
    return result;
  };
}
