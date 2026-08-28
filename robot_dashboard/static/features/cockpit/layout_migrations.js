export const COCKPIT_LAYOUT_SCHEMA_VERSION = 1;

function exactKeys(value, allowed) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).every((key) => allowed.includes(key));
}

export function migrateLayoutDocument(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('Layout document must be an object.');
  if (value.schema_version === COCKPIT_LAYOUT_SCHEMA_VERSION) return value;
  if (value.schema_version !== 0 || !exactKeys(value, ['schema_version', 'name', 'profile', 'scene', 'panels'])) {
    throw new RangeError('Unsupported layout schema version.');
  }
  return {
    schema_version: COCKPIT_LAYOUT_SCHEMA_VERSION,
    name: value.name,
    profile_id: value.profile,
    scene: value.scene,
    panels: value.panels,
  };
}
