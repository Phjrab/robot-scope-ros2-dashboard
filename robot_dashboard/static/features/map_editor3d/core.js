/**
 * Annotation-only point-cloud editor. The source cloud is never changed.
 * Visibility regions affect this editor's preview; localization and keepout
 * regions are proposals only and are never installed in a robot runtime.
 */
export const EDITOR_LIMITS = Object.freeze({ points: 1_000_000, regions: 100, vertices: 256, history: 100, importBytes: 2 * 1024 * 1024 });
export const VERSION_SCHEMA = 'robot-dashboard.map-editor3d';
export const VERSION_SCHEMA_VERSION = 1;

const KINDS = Object.freeze(['visibility', 'localization', 'keepout']);
const EPSILON = 1e-12;
const compiledRegions = new WeakMap();
let versionSequence = 0;

function fail(message) {
  throw new TypeError(message);
}

function record(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)) {
    fail(`${label} must be an object`);
  }
}

function exactKeys(value, expected, label) {
  record(value, label);
  const actual = Object.keys(value);
  if (actual.length !== expected.length || actual.some((key) => !expected.includes(key))) {
    fail(`${label} must contain only ${expected.join(', ')}`);
  }
}

function identity(value) {
  exactKeys(value, ['map_id', 'revision', 'frame_id'], 'Source identity');
  for (const key of ['map_id', 'frame_id']) {
    if (typeof value[key] !== 'string' || !value[key].trim() || value[key].length > 512) {
      fail(`${key} must be a nonempty string of at most 512 characters`);
    }
  }
  const revision = value.revision;
  if (!(typeof revision === 'string' && revision.trim() && revision.length <= 512)
    && !(Number.isSafeInteger(revision) && revision >= 0)) {
    fail('revision must be a nonempty string or a nonnegative safe integer');
  }
  return Object.freeze({ map_id: value.map_id, revision, frame_id: value.frame_id });
}

function finite(value, label) {
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(`${label} must be finite`);
  return value;
}

function cross(ax, ay, bx, by, cx, cy) {
  return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

function onSegment(x, y, a, b) {
  return Math.abs(cross(a[0], a[1], b[0], b[1], x, y)) <= EPSILON
    && x >= Math.min(a[0], b[0]) - EPSILON && x <= Math.max(a[0], b[0]) + EPSILON
    && y >= Math.min(a[1], b[1]) - EPSILON && y <= Math.max(a[1], b[1]) + EPSILON;
}

function intersects(a, b, c, d) {
  const abC = cross(...a, ...b, ...c);
  const abD = cross(...a, ...b, ...d);
  const cdA = cross(...c, ...d, ...a);
  const cdB = cross(...c, ...d, ...b);
  if (((abC > EPSILON && abD < -EPSILON) || (abC < -EPSILON && abD > EPSILON))
    && ((cdA > EPSILON && cdB < -EPSILON) || (cdA < -EPSILON && cdB > EPSILON))) return true;
  return onSegment(...c, a, b) || onSegment(...d, a, b)
    || onSegment(...a, c, d) || onSegment(...b, c, d);
}

function compilePolygon(polygon) {
  // Normalize before geometric arithmetic to avoid overflow for finite inputs.
  let coordinateScale = 0;
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const [x, y] of polygon) {
    coordinateScale = Math.max(coordinateScale, Math.abs(x), Math.abs(y));
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  coordinateScale ||= 1;
  const originX = polygon[0][0] / coordinateScale;
  const originY = polygon[0][1] / coordinateScale;
  const relative = polygon.map(([x, y]) => [x / coordinateScale - originX, y / coordinateScale - originY]);
  const extent = Math.max(...relative.flat().map(Math.abs));
  if (!extent) fail('Polygon is degenerate');
  const normalized = relative.map(([x, y]) => [x / extent, y / extent]);
  const count = normalized.length;
  for (let i = 0; i < count; i += 1) {
    const a = normalized[i];
    for (let j = i + 1; j < count; j += 1) {
      const b = normalized[j];
      if (Math.abs(a[0] - b[0]) <= EPSILON && Math.abs(a[1] - b[1]) <= EPSILON) {
        fail('Polygon has repeated or numerically indistinguishable vertices; do not repeat the closing vertex');
      }
    }
    const previous = normalized[(i + count - 1) % count];
    const next = normalized[(i + 1) % count];
    if (Math.abs(cross(...previous, ...a, ...next)) <= EPSILON
      && (a[0] - previous[0]) * (next[0] - a[0]) + (a[1] - previous[1]) * (next[1] - a[1]) < 0) {
      fail('Polygon edges must not overlap');
    }
    for (let j = i + 2; j < count; j += 1) {
      if (i === 0 && j === count - 1) continue;
      if (intersects(a, next, normalized[j], normalized[(j + 1) % count])) {
        fail('Polygon must not self-intersect or touch itself');
      }
    }
  }
  let twiceArea = 0;
  for (let i = 0; i < count; i += 1) {
    const a = normalized[i]; const b = normalized[(i + 1) % count];
    twiceArea += a[0] * b[1] - b[0] * a[1];
  }
  if (Math.abs(twiceArea) <= EPSILON) fail('Polygon is degenerate or numerically too thin');
  return { polygon: normalized, coordinateScale, originX, originY, extent, minX, minY, maxX, maxY };
}

/** Validate and defensively copy one unclosed XY polygon with inclusive Z bounds. */
export function validateRegion(value) {
  record(value, 'Region');
  const keys = ['kind', 'polygon', 'z_min', 'z_max'];
  if (Object.hasOwn(value, 'selection')) keys.push('selection');
  exactKeys(value, keys, 'Region');
  const selection = Object.hasOwn(value, 'selection') ? value.selection : 'inside';
  if (!['inside', 'outside'].includes(selection)) fail('Region selection must be inside or outside');
  if (!KINDS.includes(value.kind)) fail(`Region kind must be ${KINDS.join(', ')}`);
  finite(value.z_min, 'z_min'); finite(value.z_max, 'z_max');
  if (value.z_min > value.z_max) fail('z_min must be less than or equal to z_max');
  if (!Array.isArray(value.polygon) || value.polygon.length < 3 || value.polygon.length > EDITOR_LIMITS.vertices) {
    fail(`Polygon requires 3 to ${EDITOR_LIMITS.vertices} vertices`);
  }
  const polygon = value.polygon.map((vertex) => {
    if (!Array.isArray(vertex) || vertex.length !== 2) fail('Polygon vertices must be [x, y] pairs');
    return Object.freeze([finite(vertex[0], 'Polygon x'), finite(vertex[1], 'Polygon y')]);
  });
  const geometry = compilePolygon(polygon);
  const region = Object.freeze({ kind: value.kind, selection, polygon: Object.freeze(polygon), z_min: value.z_min, z_max: value.z_max });
  compiledRegions.set(region, geometry);
  return region;
}

function containsXY(x, y, region) {
  const geometry = compiledRegions.get(region);
  if (x < geometry.minX || x > geometry.maxX || y < geometry.minY || y > geometry.maxY) return false;
  const px = (x / geometry.coordinateScale - geometry.originX) / geometry.extent;
  const py = (y / geometry.coordinateScale - geometry.originY) / geometry.extent;
  const polygon = geometry.polygon;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[j]; const b = polygon[i];
    if (onSegment(px, py, a, b)) return true;
    if ((a[1] > py) !== (b[1] > py)
      && px < (b[0] - a[0]) * (py - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}

function contains(x, y, z, region) {
  // An outside selection complements XY membership only, never the Z slab.
  if (z < region.z_min || z > region.z_max) return false;
  const inside = containsXY(x, y, region);
  return region.selection === 'outside' ? !inside : inside;
}

/** Test selected points. Polygon edges are inside; Z planes are inclusive. */
export function pointInRegion(point, region) {
  if ((!Array.isArray(point) && !ArrayBuffer.isView(point)) || point.length !== 3) fail('Point must be [x, y, z]');
  const [x, y, z] = point;
  finite(x, 'Point x'); finite(y, 'Point y'); finite(z, 'Point z');
  return contains(x, y, z, compiledRegions.has(region) ? region : validateRegion(region));
}

function newVersionId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return `edit-${globalThis.crypto.randomUUID()}`;
  versionSequence += 1;
  return `edit-${Date.now().toString(36)}-${versionSequence.toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** Create a local, annotation-only editing session for an identified source. */
export function createEditor(source) {
  record(source, 'Source');
  const sourceIdentity = identity({ map_id: source.map_id, revision: source.revision, frame_id: source.frame_id });
  const input = source.points;
  if ((!Array.isArray(input) && !ArrayBuffer.isView(input)) || !Number.isSafeInteger(input.length)
    || input.length % 3 !== 0 || input.length > EDITOR_LIMITS.points * 3) {
    fail(`Source points must be flat XYZ coordinates, at most ${EDITOR_LIMITS.points} points`);
  }
  const original = Object.freeze(Array.from(input, (value) => finite(value, 'Source point coordinate')));
  let regions = Object.freeze([]);
  let past = [];
  let future = [];
  let previewCache = null;

  function commit(next) {
    if (JSON.stringify(next) === JSON.stringify(regions)) return false;
    past.push(regions);
    if (past.length > EDITOR_LIMITS.history) past.shift();
    regions = Object.freeze(next);
    future = [];
    previewCache = null;
    return true;
  }

  function preview() {
    if (!previewCache) {
      const groups = KINDS.map((kind) => regions.filter((region) => region.kind === kind));
      const counts = { total: original.length / 3, visible: 0, hidden: 0, visibility: 0, localization: 0, keepout: 0 };
      const points = [];
      for (let i = 0; i < original.length; i += 3) {
        const x = original[i]; const y = original[i + 1]; const z = original[i + 2];
        let hidden = false;
        for (let kind = 0; kind < KINDS.length; kind += 1) {
          for (const region of groups[kind]) {
            if (contains(x, y, z, region)) {
              counts[KINDS[kind]] += 1;
              if (kind === 0) hidden = true;
              break;
            }
          }
        }
        if (!hidden) points.push(x, y, z);
      }
      counts.visible = points.length / 3;
      counts.hidden = counts.total - counts.visible;
      previewCache = { points, counts: Object.freeze(counts) };
    }
    return { points: previewCache.points.slice(), counts: previewCache.counts };
  }

  /**
   * Return a separate point-cloud copy for exactly one annotation purpose.
   * This does not replace the source, change the preview, or install anything.
   * Keepout proposals cannot be used to remove cloud points.
   */
  function editedCopy(purpose = 'visibility') {
    if (!['visibility', 'localization'].includes(purpose)) fail('Edited copy purpose must be visibility or localization');
    if (purpose === 'visibility') {
      const { points } = preview();
      return { points, purpose, removed_count: (original.length - points.length) / 3 };
    }
    const selected = regions.filter((region) => region.kind === purpose);
    const points = [];
    pointLoop: for (let i = 0; i < original.length; i += 3) {
      const x = original[i]; const y = original[i + 1]; const z = original[i + 2];
      for (const region of selected) {
        if (contains(x, y, z, region)) continue pointLoop;
      }
      points.push(x, y, z);
    }
    return { points, purpose, removed_count: (original.length - points.length) / 3 };
  }

  function exportVersion() {
    return Object.freeze({
      schema: VERSION_SCHEMA,
      schema_version: VERSION_SCHEMA_VERSION,
      version_id: newVersionId(),
      source: sourceIdentity,
      runtime_installed: false,
      regions,
    });
  }

  function importVersion(json) {
    if (typeof json !== 'string') fail('Version import must be a JSON string');
    if (json.length > EDITOR_LIMITS.importBytes || new TextEncoder().encode(json).byteLength > EDITOR_LIMITS.importBytes) {
      fail('Version import exceeds the 2 MiB limit');
    }
    let value;
    try { value = JSON.parse(json); } catch { fail('Version import is not valid JSON'); }
    exactKeys(value, ['schema', 'schema_version', 'version_id', 'source', 'runtime_installed', 'regions'], 'Version');
    if (value.schema !== VERSION_SCHEMA || value.schema_version !== VERSION_SCHEMA_VERSION) fail('Unsupported annotation version schema');
    if (typeof value.version_id !== 'string' || !value.version_id.trim() || value.version_id.length > 128) fail('Invalid version_id');
    if (value.runtime_installed !== false) fail('Annotation versions must have runtime_installed: false');
    const importedSource = identity(value.source);
    for (const key of ['map_id', 'revision', 'frame_id']) {
      if (importedSource[key] !== sourceIdentity[key]) fail(`Version source ${key} does not match this map`);
    }
    if (!Array.isArray(value.regions) || value.regions.length > EDITOR_LIMITS.regions) fail(`Version allows at most ${EDITOR_LIMITS.regions} regions`);
    const next = value.regions.map(validateRegion);
    return commit(next);
  }

  return Object.freeze({
    get original() { return original.slice(); },
    get regions() { return regions; },
    get canUndo() { return past.length > 0; },
    get canRedo() { return future.length > 0; },
    addRegion(value) {
      if (regions.length >= EDITOR_LIMITS.regions) fail(`At most ${EDITOR_LIMITS.regions} regions are allowed`);
      return commit([...regions, validateRegion(value)]);
    },
    undo() {
      if (!past.length) return false;
      future.push(regions); regions = past.pop(); previewCache = null;
      return true;
    },
    redo() {
      if (!future.length) return false;
      past.push(regions); regions = future.pop(); previewCache = null;
      return true;
    },
    reset() { return commit([]); },
    preview,
    editedCopy,
    exportVersion,
    importVersion,
  });
}
