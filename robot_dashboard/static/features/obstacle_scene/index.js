import { createSceneConsumer, LIMITS } from './consumer.js';
import { createOverlayPainter } from './draw.js';

const DEFAULT_LAYERS = { reference: true, LIDAR: true, DEPTH: true, obstacles: true,
  costmap: true, path: true, local: true, robot: true, envelope: true };
const LABELS = { reference: '저장 지도', LIDAR: 'LiDAR', DEPTH: 'Depth', obstacles: '물체',
  costmap: 'Costmap · 평면', path: '제공된 global path', local: '제공된 local trajectory',
  robot: '공식 URDF · 시각화', envelope: '별도 collision envelope' };

export function mountObstacleScene(host, { scene, subscribe, getMap, theme = 'dark', clock = () => performance.now() }) {
  if (!host?.ownerDocument || !scene?.canvas || typeof scene.project !== 'function'
    || typeof scene.setRobot !== 'function' || typeof subscribe !== 'function') {
    throw new TypeError('host, scene {canvas,project,setRobot}, subscribe and getMap are required');
  }
  const doc = host.ownerDocument, win = doc.defaultView;
  const consumer = createSceneConsumer({ getMap, clock });
  const layers = { ...DEFAULT_LAYERS }, events = [];
  let destroyed = false, paused = false, pending = null, displayed = null, selected = '', dirty = true;
  let raf = 0, rendered = 0, dropped = 0, received = 0, maxPending = 0, lastRefresh = -Infinity;
  let lastViewKey = '', maxDrawMs = 0, robotKey = '', lastContext = '', lastValidity = '';
  const make = (tag, className, content) => { const el = doc.createElement(tag); if (className) el.className = className; if (content) el.textContent = content; return el; };
  const root = make('section', 'obstacle-scene'); root.dataset.theme = typeof theme === 'string' ? theme : theme();
  root.setAttribute('aria-label', '장애물 관측 · C3');
  const header = make('header', 'os-header');
  header.append(make('span', 'os-eyebrow', 'ROBOT SCOPE / C3 · OFFLINE REVIEW'), make('h1', '', '장애물 관측창'));
  header.append(make('p', 'os-note', '입력 geometry·경로만 표시합니다. 공식 URDF와 collision 모델은 별도입니다.'));
  const toolbar = make('div', 'os-toolbar');
  const pauseButton = make('button', '', '표시 일시정지'); pauseButton.type = 'button'; pauseButton.dataset.action = 'pause';
  const stepButton = make('button', '', '대기 패킷 1개 표시'); stepButton.type = 'button'; stepButton.dataset.action = 'step';
  toolbar.append(pauseButton, stepButton);
  const mode = make('strong', 'os-mode', 'WAITING'); mode.dataset.testid = 'mode'; toolbar.append(mode);
  const fieldset = make('fieldset', 'os-layers'); fieldset.append(make('legend', '', '표시 레이어'));
  for (const [name, label] of Object.entries(LABELS)) {
    const row = make('label'); const input = make('input'); input.type = 'checkbox'; input.checked = true; input.dataset.layer = name;
    row.append(input, doc.createTextNode(label)); fieldset.append(row);
    listen(input, 'change', () => { layers[name] = input.checked; dirty = true; });
  }
  const stage = make('div', 'os-stage');
  const canvas = make('canvas', 'os-overlay'); canvas.setAttribute('aria-label', '제공된 3D 장애물·경로·평면 costmap overlay');
  const sceneSlot = scene.canvas.parentElement;
  if (!sceneSlot) throw new TypeError('scene canvas must be mounted in a positioned viewport');
  // The existing host retains ownership of its scene/canvas/cache.
  sceneSlot.classList.add('os-viewport'); sceneSlot.append(canvas);
  const summary = make('div', 'os-summary'); summary.dataset.testid = 'summary'; summary.setAttribute('role','status');
  const sourceRows = make('div', 'os-sources'); sourceRows.dataset.testid = 'sources';
  const risk = make('div', 'os-risk'); risk.dataset.testid = 'risk';
  risk.setAttribute('role','button'); risk.tabIndex = 0; risk.setAttribute('aria-label','위험 평가 원본 확인');
  const paths = make('p', 'os-paths'); paths.dataset.testid = 'paths';
  const objects = make('div', 'os-objects'); objects.setAttribute('aria-label', '위험 객체 선택');
  const inspector = make('pre', 'os-inspector', '물체 또는 위험 상태를 선택하면 source·geometry·frame·time·provenance가 표시됩니다.');
  inspector.dataset.testid = 'inspector'; inspector.tabIndex = 0;
  const metrics = make('p', 'os-metrics'); metrics.dataset.testid = 'metrics';
  const note = make('p', 'os-note', '표시 일시정지는 이 브라우저에만 적용됩니다. 장비 제어 정지를 의미하지 않습니다.');
  stage.append(summary, sourceRows, risk, paths, objects, inspector, metrics, note);
  root.append(header, toolbar, fieldset, stage); host.append(root);
  const painter = createOverlayPainter(canvas, scene);
  function listen(el, event, fn) { el.addEventListener(event, fn); events.push(() => el.removeEventListener(event, fn)); }
  function inspect(value) { inspector.textContent = JSON.stringify(value, null, 2).slice(0, LIMITS.inspectorChars); }
  function applyPending() {
    if (!pending) return;
    consumer.ingest(pending); pending = null; displayed = consumer.snapshot(); dirty = true;
  }
  listen(pauseButton, 'click', () => { paused = !paused; if (!paused) applyPending(); dirty = true; });
  listen(stepButton, 'click', () => { paused = true; applyPending(); dirty = true; });
  listen(objects, 'click', event => {
    const button = event.target.closest('button[data-track]'); if (!button) return;
    selected = button.dataset.track; dirty = true;
  });
  listen(risk, 'click', () => { selected = '@risk'; dirty = true; });
  listen(risk, 'keydown', event => { if (['Enter',' '].includes(event.key)) { event.preventDefault(); selected = '@risk'; dirty = true; } });
  function renderPanel(view) {
    const kind = view.evidence_kind || 'WAITING';
    mode.textContent = `SOURCE MODE: ${view.source_mode || 'FIXTURE'} · ${kind} · ${paused ? '표시 PAUSED' : '표시 진행'} · ${kind === 'LIVE' ? 'LIVE 입력' : '실장비 관측 아님'}`;
    pauseButton.textContent = paused ? '표시 재개' : '표시 일시정지'; pauseButton.setAttribute('aria-pressed', String(paused));
    stepButton.disabled = !pending;
    root.dataset.ready = String(view.ready); root.dataset.sequence = String(view.sequence ?? '');
    if (!view.ready) {
      summary.textContent = `표시 차단 · ${view.reason}`; sourceRows.replaceChildren(); objects.replaceChildren();
      risk.textContent = '데이터 불충분 · UNKNOWN'; risk.dataset.severity = 'UNKNOWN'; paths.textContent = 'Global path 없음 · Local trajectory 없음';
      inspector.textContent = '현재 지도/epoch에 유효한 데이터가 없습니다.';
    } else {
      summary.textContent = `${kind} / ${view.map_identity.map_id} @ ${view.map_identity.revision} · ${view.map_identity.frame_id} · epoch ${view.source_epoch} · #${view.sequence} · ${view.stamp_ns} ns (${view.clock_domain}) · source ${view.map_identity.source_identity || 'identity 미제공'}${view.lastRejection ? ' · 차단: '+view.lastRejection : ''}`;
      sourceRows.replaceChildren();
      const knownSources = new Map(view.sources.map(s => [s.id,s]));
      for (const id of ['LIDAR','DEPTH']) {
        const s = knownSources.get(id); const row = make('p');
        const state = !layers[id] ? '표시 중단' : !s ? '미수신' : s.reason || s.value?.health || 'UNKNOWN';
        row.textContent = `${id} · ${state} · age ${s?.age_ms == null ? 'UNKNOWN' : Math.round(s.age_ms)+' ms'} · 취득 ${s?.value?.stamp_ns || '—'} ns`;
        row.dataset.source = id; sourceRows.append(row);
      }
      sourceRows.append(make('p', '', `Pose · ${view.pose.value ? 'FRESH' : view.pose.reason} / Joints · ${view.joints.value ? 'FRESH' : view.joints.reason} / URDF · ${layers.robot && view.pose.value && view.joints.value ? '시각화용' : '표시 차단'}`));
      if (view.obstacles.value?.suppressed) sourceRows.append(make('p', '', `${view.obstacles.value.suppressed}개 geometry 차단 · source stale / calibration / sensor time skew`));
      if (!view.obstacles.value) sourceRows.append(make('p', '', `ObstacleFrame · ${view.obstacles.reason}`));
      for (const c of view.costmaps) sourceRows.append(make('p', '', `Costmap · ${c.value ? `${c.value.id} · 2D ground-plane (실제 3D 표면 아님)` : c.reason}`));
      if (view.availability) sourceRows.append(make('p','',`Sensor clouds/origins · ${view.availability.sensor_clouds} / ${view.availability.sensor_origins} · Reference · ${view.availability.reference_cloud} · sensor age UNKNOWN (C1 미제공)`));
      const assessment = view.collision.value;
      risk.textContent = assessment ? `${assessment.severity} · ${assessment.contact_state} · ${assessment.reason} · clearance ${assessment.min_clearance_m ?? 'UNKNOWN'} m`
        : `데이터 불충분 · UNKNOWN · ${view.collision.reason}`;
      if (assessment?.canonical) risk.textContent += ` · coverage ${typeof assessment.coverage === 'string' ? assessment.coverage : `${assessment.coverage?.status || 'UNKNOWN'} / complete_for_motion=${assessment.coverage?.complete_for_motion ?? 'UNKNOWN'}`} · protection ${assessment.protection_mode} · ${assessment.recommendation} · envelope geometry ${assessment.envelope_geometry_status}`;
      if (view.source_mode==='ACTUAL_C1_SERVICE' && !assessment) risk.textContent += ` · last reported protection ${view.protection.mode} · ${view.protection.recommendation} · 현재 근거 UNAVAILABLE`;
      if (view.protection?.transition) risk.textContent += ' · '+view.protection.transition;
      if (view.availability?.errors.length) risk.textContent += ' · ' + view.availability.errors.join(', ');
      risk.dataset.severity = assessment?.severity || 'UNKNOWN';
      const path = view.path.value;
      paths.textContent = `Global path · ${path ? `${path.generation} / ${path.representation} / ${path.stamp_ns} ns / ${path.reason || 'replanning 이유 미제공'}` : view.path.reason} · history ${view.history.length}/${LIMITS.pathHistory} | Local trajectory · ${view.local.value ? `${view.local.value.generation} / ${view.local.value.representation}` : `없음 (${view.local.reason})`}`;
      objects.replaceChildren();
      for (const object of view.obstacles.value?.obstacles || []) {
        const button = make('button', '', `${object.track_id} · ${object.class_name} · ${object.state} · ${object.sensor_support.join('+')} · ${object.novelty}`);
        button.type = 'button'; button.dataset.track = object.track_id; button.setAttribute('aria-pressed', String(selected === object.track_id)); objects.append(button);
      }
      const object = view.obstacles.value?.obstacles.find(o => o.track_id === selected);
      if (selected === '@risk') inspect({ assessment: assessment || { severity:'UNKNOWN',reason:view.collision.reason },
        evidence_kind: kind, pose: view.pose.value, joints: view.joints.value, frame: view.map_identity,
        stamp_ns: view.stamp_ns, clock_domain: view.clock_domain });
      else if (object) inspect({ ...object, frame: view.obstacles.value.frame_key, stamp_ns: view.obstacles.value.stamp_ns,
        clock_domain: view.obstacles.value.clock_domain, calibration_id: view.obstacles.value.calibration_id,
        evidence_kind: kind, producer: view.obstacles.value.producer, sources: view.sources.map(s => s.value ? { id:s.id, stamp_ns:s.value.stamp_ns, provenance:s.value.provenance } : {id:s.id,reason:s.reason}),
        collision: assessment, ingestion: { published_to_nav2: view.obstacles.value.published_to_nav2,
          costmap_ingestion_observed: view.obstacles.value.costmap_ingestion_observed,
          controller_consumption_observed: view.obstacles.value.controller_consumption_observed } });
      else if (selected) { selected = ''; inspector.textContent = '선택 객체가 현재 frame에서 제거/차단되었습니다.'; }
      else inspector.textContent = '물체 또는 위험 상태를 선택하면 source·geometry·frame·time·provenance가 표시됩니다.';
    }
    metrics.textContent = `수신 ${received} · 표시 ${rendered} · coalesced/drop ${dropped} · 대기 ${pending ? 1 : 0}/1 · retained history ${consumer.diagnostics().history}/${LIMITS.pathHistory}`;
  }
  function render(view) {
    const currentTheme = typeof theme === 'function' ? theme() : theme; root.dataset.theme = currentTheme;
    const nextRobotKey = view.ready && layers.robot && view.pose.value && view.joints.value
      ? `${view.contextKey}|${view.sequence}|${view.pose.value.ref}|${view.joints.value.ref}` : '';
    if (nextRobotKey !== robotKey) {
      scene.setRobot(nextRobotKey ? { pose: view.pose.value, joints: view.joints.value, evidence_kind: view.evidence_kind } : null);
      robotKey = nextRobotKey;
    }
    scene.setReferenceVisible?.(layers.reference);
    painter.draw(view, layers, selected, currentTheme); rendered++; renderPanel(view);
  }
  function tick() {
    if (destroyed) return;
    const now = clock();
    const current = consumer.snapshot(); // invalidation also runs while paused/idle
    if (current.contextKey !== lastContext) {
      lastContext = current.contextKey; displayed = current; selected = ''; dirty = true;
    }
    if (!paused && pending) applyPending();
    if (!paused || !displayed?.ready) displayed = consumer.snapshot();
    const v = displayed;
    const validity = v?.ready ? [v.pose.reason,v.joints.reason,v.obstacles.reason,
      v.obstacles.value?.obstacles.length,v.collision.reason,v.path.reason,v.local.reason,
      ...v.sources.map(s => s.reason),...v.costmaps.map(c => c.reason)].join('|') : 'EMPTY';
    if (validity !== lastValidity) { lastValidity = validity; dirty = true; }
    const cameraKey = scene.viewKey?.() || '';
    const themeKey = typeof theme === 'function' ? theme() : theme;
    const nextViewKey = `${cameraKey}|${themeKey}`;
    if (nextViewKey !== lastViewKey) { dirty = true; lastViewKey = nextViewKey; }
    if (dirty || now - lastRefresh >= 100) {
      const started = performance.now(); render(displayed || current);
      maxDrawMs = Math.max(maxDrawMs, performance.now()-started); dirty = false; lastRefresh = now;
    }
    raf = win.requestAnimationFrame(tick);
  }
  const unsubscribe = subscribe(packet => {
    if (destroyed) return;
    received++; if (pending) dropped++; pending = packet; maxPending = 1; dirty = true;
  });
  if (typeof unsubscribe !== 'function') { canvas.remove(); root.remove(); throw new TypeError('subscribe must return unsubscribe'); }
  raf = win.requestAnimationFrame(tick);
  return {
    diagnostics: () => ({ ...consumer.diagnostics(), received, rendered, dropped, pending: pending ? 1 : 0,
      maxPending, maxDrawMs, paused, destroyed, ...painter.diagnostics() }),
    snapshot: () => displayed,
    destroy() {
      if (destroyed) return; destroyed = true; win.cancelAnimationFrame(raf); unsubscribe();
      events.splice(0).forEach(dispose => dispose()); consumer.destroy(); pending = null; displayed = null;
      scene.setRobot(null); scene.setReferenceVisible?.(true); painter.clear(); canvas.remove(); root.remove();
    },
  };
}
