// A separate manual experiment: all mutations go through the navigation owner.
export function initializeManual2dExperiment({ host, api, engine, context, mutate, stop = mutate, emergencyStop, refresh }) {
  if (!host || !engine) return;
  const el = (name) => host.querySelector(`[data-manual="${name}"]`);
  const canvas = el('canvas');
  let meta = null, map = null, source = null, annotations = null, layout = null;
  let draft = null, tool = 'initial', pointer = null, generation = 0, pending = false;
  let message = '', binding = '', stopping = false;
  const sessionBinding = nav => `${nav?.mode || ''}:${jobId(nav)}:${nav?.map?.id || ''}:${nav?.map?.revision || ''}:${nav?.manual_seed?.source_epoch ?? ''}:${nav?.manual_seed?.seed_generation ?? ''}`;
  const active = () => !host.closest('[data-page]').hidden;
  const point = (event) => { const rect = canvas.getBoundingClientRect(); return { x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height }; };
  const sameMap = (nav) => Boolean(meta && map && (context().maps || []).some(item => item.id === meta.id && item.revision === meta.revision) && nav?.map?.id === meta.id && nav?.map?.revision === meta.revision);
  const manual = (nav) => nav?.mode === 'manual_seeded_2d';
  const jobId = (nav) => String(nav?.pipeline?.job_id || '');
  const isActive = (nav) => engine.pipelineActive(nav);
  const goalActive = (nav) => engine.goalActive(nav);
  function canPose(nav, mode) {
    const seed = nav?.manual_seed;
    if (!manual(nav) || !sameMap(nav) || !jobId(nav) || nav.robot_online !== true ||
        goalActive(nav) || !Number.isInteger(seed?.seed_generation)) return false;
    return mode === 'initial'
      ? nav.safety?.can_set_initial_pose === true && Number.isInteger(seed.source_epoch)
      : nav.safety?.can_send_goal === true && seed.state === 'ready_manual';
  }
  const clear = () => { draft = null; pointer = null; el('annotation').value = ''; };
  async function load(selected) {
    const gen = ++generation;
    el('site').checked = false;
    meta = selected; map = null; source = null; annotations = null; clear();
    if (!selected) { render(); return; }
    try {
      const data = await api(selected.data_url || `/api/v1/saved-maps/${encodeURIComponent(selected.id)}/data`);
      if (gen !== generation) return;
      if (data.revision !== selected.revision) throw new Error('지도 revision 불일치');
      source = engine.buildMapSource(data).source;
      map = data;
      try {
        const doc = await api(selected.annotations_url || `/api/v1/saved-maps/${encodeURIComponent(selected.id)}/annotations`);
        if (gen !== generation) return;
        if (doc.map_id === selected.id && doc.map_revision === selected.revision && doc.annotation_revision) annotations = doc;
      } catch (_) { message = '저장 위치를 불러오지 못했습니다.'; }
    } catch (error) { if (gen === generation) message = `지도 로드 실패: ${error.message}`; }
    render();
  }
  function draw(nav, scene) {
    const rect = canvas.getBoundingClientRect(); if (!rect.width || !rect.height) return;
    const ratio = window.devicePixelRatio || 1; canvas.width = Math.max(1, Math.round(rect.width * ratio)); canvas.height = Math.max(1, Math.round(rect.height * ratio));
    const ctx = canvas.getContext('2d'); ctx.fillStyle = '#04100d'; ctx.fillRect(0, 0, canvas.width, canvas.height); layout = null;
    if (!map || !source) return;
    layout = engine.mapLayout(map, canvas.width, canvas.height, .055); ctx.imageSmoothingEnabled = false;
    ctx.drawImage(source, layout.left, layout.top, layout.drawWidth, layout.drawHeight);
    const marker = (pose, state) => { if (!pose || !engine.worldToCanvas(layout, pose).inside) return; const preview = engine.navigationPosePreview(scene, ctx, layout, pose, state); engine.drawPoseMarker(ctx, layout, pose, preview.color, preview.label, ratio, false, preview.drawn); };
    if (sameMap(nav) && manual(nav)) {
      const path = Array.isArray(nav.path) ? nav.path : []; ctx.beginPath(); let started = false;
      for (const pose of path) { const p = engine.worldToCanvas(layout, pose); if (!p.inside) continue; if (!started) ctx.moveTo(p.x,p.y); else ctx.lineTo(p.x,p.y); started = true; }
      ctx.strokeStyle = '#a28bff'; ctx.lineWidth = 2 * ratio; ctx.stroke();
      marker(engine.goalPoseOverlay(nav, map)?.pose, 'accepted');
      marker(engine.currentRobotOverlay(nav, map), 'current');
    }
    marker(draft, 'staged');
  }
  function render() {
    if (!active()) return;
    const { maps, navigation: nav, parameters, available, busy, scene } = context();
    const nextBinding = sessionBinding(nav); if (binding && binding !== nextBinding) clear(); binding = nextBinding;
    const candidates = maps || [], selected = candidates.find(item => item.id === meta?.id && item.revision === meta?.revision);
    const pinned = manual(nav) && isActive(nav)
      ? candidates.find(item => item.id === nav.map?.id && item.revision === nav.map?.revision)
      : null;
    const target = pinned || (!selected && !isActive(nav) ? candidates[0] : null);
    if (target && target !== selected && !pending) {
      pending = true;
      void load(target).finally(() => { pending = false; });
    }
    const optionsKey = candidates.map(m => `${m.id}:${m.revision}`).join('|');
    if (el('map').dataset.key !== optionsKey) {
      el('map').replaceChildren(); for (const item of candidates) { const option = document.createElement('option'); option.value = item.id; option.textContent = `${item.name || item.id} · ${item.revision || 'revision 없음'}`; el('map').append(option); }
      if (!candidates.length) el('map').add(new Option('저장된 2D 지도 없음', '')); el('map').dataset.key = optionsKey;
    }
    el('map').value = selected?.id || ''; el('map').disabled = !!busy || isActive(nav);
    const geometry = map ? engine.mapGeometry(map) : null;
    el('map-info').textContent = meta && geometry ? `ID ${meta.id} · revision ${meta.revision} · resolution ${geometry.resolution} · origin (${geometry.originX}, ${geometry.originY}, ${geometry.originYaw})` : '2D 지도 필요';
    const generated = nav?.parameter_evidence?.saved_and_generated?.generated_job_yaml;
    const revision = generated?.job_id === jobId(nav) && isActive(nav)
      ? generated.parameters_revision : parameters?.revision;
    el('parameters').textContent = `현재 설정 revision ${revision || '확인 중'} · profile ${nav?.bindings?.navigation_profile || '확인 중'}`;
    el('prepare').disabled = !!busy || !available || nav?.available !== true || nav?.robot_online !== true || nav?.safety?.can_start !== true || isActive(nav) || !map || !parameters?.revision || !el('site').checked;
    el('stop').disabled = stopping || nav?.session_mode === 'localization_only' || !(nav?.safety?.can_stop || isActive(nav));
    el('cancel').disabled = stopping || !goalActive(nav);
    el('send').disabled = stopping || !!busy || !draft || !canPose(nav, draft.mode); el('send').textContent = draft?.mode === 'goal' ? '이동 시작' : '초기 위치 적용';
    el('pose').textContent = draft ? `${draft.mode.toUpperCase()} · X ${draft.x.toFixed(2)} · Y ${draft.y.toFixed(2)} · YAW ${draft.yaw.toFixed(2)}` : '위치 초안 없음';
    const blockers = Array.isArray(nav?.safety?.blockers) ? nav.safety.blockers.join(', ') : '';
    el('stop-notice').hidden = !nav?.safety?.blockers?.includes('software_stop_latched');
    const modeLabel = manual(nav) ? 'MANUAL_SEEDED_ODOMETRY'
      : isActive(nav) ? '기존 주행 또는 위치추정 세션 사용 중' : '실험 대기';
    const stopped = manual(nav) && nav?.deactivation_reason;
    const stopReason = stopped === 'navigation localization inputs are stale'
      ? `LiDAR 또는 상대 위치 입력이 제때 들어오지 않아 주행 제어가 중단됐습니다. (${stopped})`
      : stopped;
    el('status').textContent = [modeLabel, nav?.manual_seed?.state || nav?.pipeline?.state || 'IDLE',
      stopReason && `중단 사유: ${stopReason}`, nav?.pipeline?.error, blockers, message].filter(Boolean).join(' · ');
    const seed = nav?.manual_seed;
    const readiness = nav?.readiness || {};
    const quality = key => readiness[key] === true ? '확인' : '대기';
    const seconds = value => Number.isFinite(value) ? `${value.toFixed(2)}초` : '—';
    const acceptedMs = Number(seed?.receipt?.accepted_ros_ns) / 1e6;
    const acceptedAt = Number.isFinite(acceptedMs) && acceptedMs > 0
      ? new Date(acceptedMs).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'}) : '—';
    const distance = Number.isFinite(seed?.odometry_distance_m) ? `${seed.odometry_distance_m.toFixed(2)} m` : '—';
    el('details').textContent = [
      `목표 상태 ${nav?.goal?.state || 'idle'}${nav?.goal?.error ? ` · ${nav.goal.error}` : ''}`,
      `센서 상태 · scan ${quality('scan')} · 속도 odom ${quality('odometry')} · TF ${quality('tf')}`,
      `상대 위치 ${nav?.bindings?.localization_odometry || '/Odometry'} · 속도 입력 ${nav?.bindings?.controller_odometry || '확인 중'} · 장애물 ${nav?.bindings?.scan || '/scan'}`,
      `세션 ${jobId(nav) || '—'} · odometry epoch ${seed?.source_epoch ?? '—'} · seed 세대 ${seed?.seed_generation ?? '—'}`,
      `초기 위치 수락 기록 ${acceptedAt} · 경과 ${seconds(seed?.seed_age_s)} · 상대 odometry 이동 거리 ${distance} · 정지 관측 ${seconds(seed?.stopped_seconds)}`,
      `TF 확인 ${seed?.tf_readback ? '확인' : '대기'}${seed?.reason ? ` · ${seed.reason}` : ''}`,
    ].join('\n');
    const list = (annotations?.points || []).filter(p => p?.id && p?.pose && ['x','y','yaw'].every(k => Number.isFinite(p.pose[k])));
    const old = el('annotation').value; el('annotation').replaceChildren(new Option('저장 위치 선택', ''));
    for (const item of list) el('annotation').add(new Option(item.name, item.id)); el('annotation').value = old;
    el('annotation').disabled = !list.length || !!busy; draw(nav, scene);
  }
  el('map').addEventListener('change', () => { message = ''; el('site').checked = false; void load((context().maps || []).find(m => m.id === el('map').value)); });
  el('site').addEventListener('change', render);
  async function request(path, body) {
    message = '요청 처리 중'; render();
    try {
      const result = await mutate(path, body, error => { message = `요청 실패: ${error.message}`; });
      if (message === '요청 처리 중') message = result ? '' : '요청을 완료하지 못했습니다. 현재 상태를 확인하세요.';
      return result;
    } catch (error) {
      message = `요청 실패: ${error.message}`;
      return null;
    } finally { render(); }
  }
  el('prepare').addEventListener('click', async () => { if (el('prepare').disabled) return; await request('/api/v1/navigation/start', { map_id: meta.id, map_revision: meta.revision, parameters_revision: context().parameters.revision, mode: 'manual_seeded_2d' }); });
  async function safetyCommand(path, body) {
    if (stopping) return;
    stopping = true;
    clear();
    render();
    try {
      if (await stop(path, body)) message = '정지 요청 접수 · 목표 결과와 정지 상태를 확인하세요.';
    } finally {
      stopping = false;
      render();
    }
  }
  el('stop').addEventListener('click', () => safetyCommand('/api/v1/navigation/stop', {}));
  el('cancel').addEventListener('click', () => {
    const id = context().navigation?.goal?.goal_id;
    if (id) void safetyCommand('/api/v1/navigation/cancel', { goal_id: id });
  });
  el('estop').addEventListener('click', () => emergencyStop?.());
  for (const mode of ['initial','goal']) el(mode).addEventListener('click', () => { tool = mode; clear(); render(); });
  el('discard').addEventListener('click', () => { clear(); render(); });
  canvas.addEventListener('pointerdown', event => { if (!layout || !engine.canvasToWorld(layout, point(event))) return; pointer = { id: event.pointerId, start: point(event) }; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener('pointerup', event => { if (!pointer || pointer.id !== event.pointerId || !layout) return; const end = point(event); if (Math.hypot(end.x - pointer.start.x, end.y - pointer.start.y) < 4 * (window.devicePixelRatio || 1)) { message = '방향을 지정하려면 위치에서 드래그하세요.'; } else { draft = { ...engine.poseFromDrag(layout, pointer.start, end), mode: tool }; el('annotation').value = ''; message = ''; } pointer = null; render(); });
  canvas.addEventListener('pointercancel', () => { pointer = null; });
  el('annotation').addEventListener('change', () => { const item = annotations?.points?.find(p => p.id === el('annotation').value); if (item) { tool = 'goal'; draft = { ...item.pose, mode: 'goal', annotationId: item.id, annotationRevision: annotations.annotation_revision }; } else draft = null; render(); });
  el('send').addEventListener('click', async () => { const nav = context().navigation; if (stopping || !draft || !canPose(nav, draft.mode)) return; if (draft.mode === 'goal' && !window.confirm('주변을 비우고 물리 리모컨을 즉시 사용할 수 있나요? 확인하면 이동을 시작할 수 있습니다.')) return;
    const body = { map_id: meta.id, map_revision: meta.revision, job_id: jobId(nav) };
    body.seed_generation = nav.manual_seed.seed_generation;
    let endpoint = '/api/v1/navigation/initial-pose';
    if (draft.mode === 'goal') {
      endpoint = draft.annotationId ? '/api/v1/navigation/goal/annotation' : '/api/v1/navigation/goal';
      body.confirmed = true;
    } else {
      body.source_epoch = nav.manual_seed.source_epoch;
    }
    if (draft.annotationId) { body.annotation_id = draft.annotationId; body.annotation_revision = draft.annotationRevision; } else body.pose = { x: draft.x, y: draft.y, yaw: draft.yaw };
    const wasGoal = draft.mode === 'goal'; const result = await request(endpoint, body); if (result) { clear(); message = wasGoal ? '목표 접수됨' : '초기 위치 요청 처리됨 · seed 및 TF 수락 상태를 확인하세요.'; } render(); });
  document.addEventListener('robot-scope:page-change', () => { if (active()) { void refresh(); render(); } else { clear(); } });
  setInterval(render, 1000);
}
