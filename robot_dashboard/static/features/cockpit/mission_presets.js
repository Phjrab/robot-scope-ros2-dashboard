import { parseLayoutDocument } from './layout_schema.js';
import { COCKPIT_LAYOUT_SCHEMA_VERSION } from './layout_migrations.js';

export const MISSION_PRESETS = Object.freeze([
  { id: 'observation', label: 'Observation', panels: ['camera.go2-front'] },
  { id: 'mapping', label: 'Mapping', panels: ['placeholder.map', 'camera.go2-front'] },
  { id: 'navigation', label: 'Navigation', panels: ['navigation.main', 'placeholder.map'] },
  { id: 'capture', label: 'Dataset Capture', panels: ['camera.go2-front', 'camera.realsense-color'] },
]);

// Builtins use the same validated schema and singleton registry as user layouts.
// They contain UI preferences only and never write storage or invoke an API.
export function missionPresetDocument(id, profileId, registry, viewport = {}) {
  const preset = MISSION_PRESETS.find((entry) => entry.id === id);
  if (!preset) throw new RangeError('Unknown mission workspace preset.');
  const descriptors = registry.list();
  const narrow = viewport.width < 600;
  const panels = preset.panels.map((type, index) => {
    const descriptor = registry.get(type);
    const camera = descriptor.kind === 'camera';
    const geometry = preset.id === 'observation'
      ? { x: 0.52, y: 0.25, width: 0.38, height: 0.32 }
      : camera ? { x: index ? 0.51 : 0.01, y: 0.53, width: 0.48, height: 0.46 }
        : { x: index ? 0.55 : 0.01, y: 0.16, width: index ? 0.44 : 0.52, height: 0.83 };
    return { id: descriptor.id, panel_type: type, mode: narrow ? 'compact' : 'floating', dock: null,
      ...geometry, z_index: index + 1, pinned: false, locked: false, restore_geometry: null };
  });
  return parseLayoutDocument({ schema_version: COCKPIT_LAYOUT_SCHEMA_VERSION, name: preset.label, profile_id: profileId,
    scene: { view: 'robot-follow', follow_robot: true, point_size: 2, range_m: 150 }, panels },
  { allowedPanelTypes: descriptors.map((entry) => entry.panelType), panelIdsByType: Object.fromEntries(descriptors.map((entry) => [entry.panelType, entry.id])) });
}
