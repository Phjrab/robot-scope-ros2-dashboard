// Pre-navigation placement is a local, non-sendable draft bound to its entire context.
export function preNavigationDraftBinding({ selected, pair, mapMeta, mapData, maps, selected2d, selected3d, navigation, available }) {
  const pipeline = navigation?.pipeline, source = navigation?.operational_localization;
  const loc = selected?.localization_3d, nav = selected?.navigation_2d;
  if (!available || pipeline?.state !== 'idle' || pipeline.job_id || selected?.workflow !== 'staged_navigation_pair'
      || !selected.generation || pair?.valid !== true || pair.generation !== selected.generation
      || !loc?.map_id || !loc.revision || !nav?.map_id || !nav.revision
      || pair.localization_3d?.map_id !== loc.map_id || pair.localization_3d?.revision !== loc.revision
      || pair.navigation_2d?.map_id !== nav.map_id || pair.navigation_2d?.revision !== nav.revision
      || selected3d !== loc.map_id || selected2d !== nav.map_id
      || mapMeta?.id !== nav.map_id || mapMeta?.revision !== nav.revision
      || (mapData?.map_id || mapData?.id) !== nav.map_id || mapData?.revision !== nav.revision
      || !maps?.some(item => item.id === nav.map_id && item.revision === nav.revision && item.kind === 'occupancy2d' && item.format === 'map-server-pgm')
      || !maps?.some(item => item.id === loc.map_id && item.revision === loc.revision && item.kind === 'pointcloud3d')) return null;
  return JSON.stringify([selected.generation, loc.map_id, loc.revision, nav.map_id, nav.revision,
    pipeline.state, pipeline.job_id ?? null, source?.bundle_generation ?? null,
    source?.localization_generation ?? null, source?.runtime_instance_generation ?? null]);
}
export function createPreNavigationDraftController({ inputs, binding, clear }) {
  return {
    current: () => preNavigationDraftBinding(inputs()),
    invalidate() {
      const previous = binding();
      if (previous && previous !== preNavigationDraftBinding(inputs())) clear();
    },
  };
}

export function navigationMapCandidatesFrom(maps) {
  return maps.filter(entry => entry.kind === 'occupancy2d' && entry.format === 'map-server-pgm'
    && typeof entry.revision === 'string' && entry.revision.length > 0);
}

export function navigationCanvasPointFrom(canvas, event) {
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return null;
  return { x: (event.clientX - bounds.left) * (canvas.width / bounds.width),
    y: (event.clientY - bounds.top) * (canvas.height / bounds.height) };
}

export function navigationActiveMapMatches(pipelineActive, active, selected, snapshot, candidates) {
  if (!pipelineActive) return true;
  const id = String(active?.id || ''), revision = String(active?.revision || '');
  return Boolean(id && revision && selected?.id === id && String(selected?.revision || '') === revision
    && String(snapshot?.revision || '') === revision
    && candidates.some(entry => entry.id === id && String(entry.revision || '') === revision));
}
