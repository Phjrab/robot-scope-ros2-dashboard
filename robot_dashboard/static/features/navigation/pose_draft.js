// Pre-navigation placement is a local, non-sendable draft bound to its entire context.
export function preNavigationDraftBinding({ selected, pair, mapMeta, mapData, maps, selected2d, selected3d, navigation, available, epoch }) {
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
    source?.localization_generation ?? null, source?.runtime_instance_generation ?? null, epoch ?? null, pair.calibration_sha256 ?? null]);
}
export function createPreNavigationDraftController({ inputs, binding, clear, suspend = clear, archive = clear }) {
  return {
    current: () => preNavigationDraftBinding(inputs()),
    runtime: staged => historicalRuntimeBinding(staged, inputs()),
    suspend() { if (binding()) suspend(); },
    invalidate() {
      const previous = binding();
      if (!previous) return;
      const value = inputs(), current = preNavigationDraftBinding(value);
      if (current === previous) return;
      let old;
      try { old = JSON.parse(previous); } catch { clear(); return; }
      const [generation, locId, locRev, mapId, mapRev, pipeline, job, bundle, localization, runtime, epoch, calibration] = old;
      const knownMapChanged = value.selected2d !== mapId || value.selected3d !== locId
        || (value.mapMeta && (value.mapMeta.id !== mapId || value.mapMeta.revision !== mapRev))
        || (value.mapData && ((value.mapData.map_id || value.mapData.id) !== mapId || value.mapData.revision !== mapRev));
      const knownRuntimeChanged = value.navigationAvailable && (value.navigation?.pipeline?.state !== pipeline
        || (value.navigation?.pipeline?.job_id ?? null) !== job
        || (value.navigation?.operational_localization?.bundle_generation ?? null) !== bundle
        || (value.navigation?.operational_localization?.localization_generation ?? null) !== localization
        || (value.navigation?.operational_localization?.runtime_instance_generation ?? null) !== runtime);
      const selected = value.selected, pair = value.pair;
      const stopPending = pair?.valid === false && Array.isArray(pair.checks) && pair.checks.length === 1
        && ['HANDOFF_OBSERVATION_STOP_REQUIRED', 'HANDOFF_MONITOR_PENDING'].includes(pair.checks[0]?.code);
      const knownPairChanged = value.preparationAvailable && (selected?.generation !== generation
        || selected?.localization_3d?.map_id !== locId || selected?.localization_3d?.revision !== locRev
        || selected?.navigation_2d?.map_id !== mapId || selected?.navigation_2d?.revision !== mapRev
        || pair?.generation !== generation || (pair?.calibration_sha256 ?? null) !== (calibration ?? null)
        || (pair?.valid !== true && !stopPending)
        || pair?.localization_3d?.map_id !== locId || pair?.localization_3d?.revision !== locRev
        || pair?.navigation_2d?.map_id !== mapId || pair?.navigation_2d?.revision !== mapRev);
      if ((value.epoch ?? null) !== epoch || knownMapChanged || knownPairChanged) clear();
      else if (stopPending && value.preparationAvailable) suspend();
      else if (knownRuntimeChanged) archive();
      else if (value.observing && value.observationAction === 'start') return;
      else if (value.available) clear();
      else suspend();
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

// A draft is an operator assumption, never a sensor measurement or a command.
export function operatorDraftSnapshot({ staged, pointer, toolBinding, currentBinding, revision }) {
  if (!staged?.preBinding) return { status: pointer?.preBinding || toolBinding ? 'incomplete' : 'none' };
  if (staged.stale) return { status: 'stale' };
  if (pointer || !currentBinding || staged.preBinding !== currentBinding) return { status: 'pending', revision };
  let binding;
  try { binding = JSON.parse(staged.preBinding); } catch { return { status: 'stale' }; }
  const [generation, locId, locRev, mapId, mapRev] = binding;
  if (![staged.x, staged.y, staged.yaw].every(Number.isFinite) || Math.abs(staged.yaw) > Math.PI
      || !generation || !locId || !locRev || !mapId || !mapRev) return { status: 'stale' };
  return { status: 'ready', revision, pose: { x: staged.x, y: staged.y, yaw: staged.yaw },
    bundle_generation: generation, localization_map: { id: locId, revision: locRev }, navigation_map: { id: mapId, revision: mapRev } };
}

export function historicalRuntimeBinding(staged, value) {
  if (!staged?.historical || !staged.preBinding || !value.available || !value.navigationAvailable || !value.preparationAvailable) return null;
  let old; try { old = JSON.parse(staged.preBinding); } catch { return null; }
  const [generation, locId, locRev, mapId, mapRev, , , , , , epoch, calibration] = old;
  const nav = value.navigation, source = nav?.operational_localization, selected = value.selected, pair = value.pair;
  if (value.epoch !== epoch || value.selected2d !== mapId || value.selected3d !== locId
      || selected?.generation !== generation || selected?.localization_3d?.map_id !== locId || selected?.localization_3d?.revision !== locRev
      || selected?.navigation_2d?.map_id !== mapId || selected?.navigation_2d?.revision !== mapRev || pair?.valid !== true || pair?.generation !== generation || (pair?.calibration_sha256 ?? null) !== (calibration ?? null)
      || pair?.localization_3d?.map_id !== locId || pair?.localization_3d?.revision !== locRev
      || pair?.navigation_2d?.map_id !== mapId || pair?.navigation_2d?.revision !== mapRev
      || nav?.pipeline?.state !== 'running' || !nav.pipeline.job_id || nav.map?.id !== mapId || nav.map?.revision !== mapRev
      || source?.bundle_generation !== generation || source?.localization_map_id !== locId || source?.localization_map_revision !== locRev
      || source?.fresh !== true || !source?.runtime_instance_generation || !Number.isInteger(source.localization_generation) || source.localization_generation <= 0
      || value.mapMeta?.id !== mapId || value.mapMeta?.revision !== mapRev
      || (value.mapData?.map_id || value.mapData?.id) !== mapId || value.mapData?.revision !== mapRev) return null;
  return JSON.stringify([staged.preBinding, nav.pipeline.job_id, source.runtime_instance_generation, source.localization_generation]);
}

export function renderDraftControls({ ui, initialAllowed, goalAllowed, busy, tool, toolBinding, staged, sendAllowed }) {
  ui.navigationInitialPoseTool.disabled = busy || !initialAllowed;
  ui.navigationGoalPoseTool.disabled = busy || !goalAllowed;
  ui.navigationInitialPoseTool.classList.toggle('is-active', tool === 'initial');
  ui.navigationGoalPoseTool.classList.toggle('is-active', tool === 'goal');
  ui.navigationInitialPoseTool.setAttribute('aria-pressed', tool === 'initial' ? 'true' : 'false');
  ui.navigationGoalPoseTool.setAttribute('aria-pressed', tool === 'goal' ? 'true' : 'false');
  ui.navigationPoseMode.textContent = staged
    ? staged.preBinding ? staged.stale ? 'INITIAL · 이전 미전송 초안 · 미확인' : 'INITIAL · 미전송 로컬 초안' : staged.reconfirmBinding ? 'INITIAL · 이전 초안 재확인 · 미전송' : `${staged.mode === 'initial' ? 'INITIAL' : 'GOAL'} · STAGED`
    : toolBinding ? 'INITIAL · 미전송 로컬 초안 지정' : tool ? `${tool === 'initial' ? 'INITIAL' : 'GOAL'} · DRAW ON MAP` : 'NO TOOL';
  ui.navigationPoseCoordinates.textContent = staged
    ? `X ${staged.x.toFixed(3)} · Y ${staged.y.toFixed(3)} · YAW ${staged.yaw.toFixed(3)} · ${staged.preBinding ? staged.stale ? '보존된 이전 초안 · 현재 상태 미확인 · 실행 중 재확인 또는 다시 지정 필요' : '미전송 사용자 초안 · 실제 위치와 높이·기울기 확인 아님' : staged.mode === 'initial' ? '사용자 초기 위치 점·방향' : '목표 정지 자세 (URDF 또는 방향 마커)'}`
    : 'X — · Y — · YAW —';
  ui.navigationPoseDiscard.disabled = !staged || busy;
  ui.navigationPoseSend.disabled = !(staged && !staged.preBinding && sendAllowed(staged.mode)) || busy;
  ui.navigationPoseSend.textContent = staged?.mode === 'goal' ? 'SEND GOAL' : 'SEND POSE';
}
