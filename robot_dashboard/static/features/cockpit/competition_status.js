const COMPETITION_STALE_MS = 3000;
const TASKS = Object.freeze(['lane', 'object', 'depth_summary']);

function finite(value) {
  if (value == null || value === '' || typeof value === 'boolean') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function text(value, fallback = '—') {
  const normalized = String(value ?? '').trim();
  return normalized || fallback;
}

function positiveInteger(value) {
  const number = finite(value);
  return Number.isSafeInteger(number) && number > 0 ? number : 0;
}

function shortHash(value) {
  const normalized = String(value || '').toLowerCase();
  return /^[0-9a-f]{64}$/.test(normalized) ? normalized.slice(0, 12) : '—';
}

export function reduceCompetitionState(state = {}, action = {}) {
  const current = {
    generation: Number(state.generation) || 0,
    updatedAt: Number(state.updatedAt) || 0,
    competition: state.competition || null,
    models: state.models || null,
    error: String(state.error || ''),
  };
  const generation = Number(action.generation);
  if (Number.isFinite(generation) && generation < current.generation) return Object.freeze(current);
  if (action.type === 'RESET') return Object.freeze({ generation: current.generation + 1, updatedAt: 0, competition: null, models: null, error: '' });
  if (action.type === 'SUCCESS') return Object.freeze({ generation, updatedAt: Number(action.updatedAt) || 0, competition: action.competition || null, models: action.models || null, error: '' });
  if (action.type === 'ERROR') return Object.freeze({ ...current, generation, error: text(action.error, 'UNAVAILABLE') });
  return Object.freeze(current);
}

function taskProjection(snapshot, task, localAgeMs) {
  const result = (Array.isArray(snapshot?.results) ? snapshot.results : []).find((entry) => entry?.task === task);
  const receiveAge = finite(result?.last_receive_age);
  const sourceSequence = positiveInteger(result?.source_sequence);
  const sourceEpoch = positiveInteger(result?.source_epoch);
  const inputAge = finite(result?.input_age_s);
  const currentInputAge = inputAge == null ? null : inputAge + Math.max(0, localAgeMs) / 1000;
  const stale = !result || localAgeMs > 2000 || receiveAge == null || receiveAge > 2
    || sourceSequence === 0 || sourceEpoch === 0 || currentInputAge == null
    || currentInputAge > 2 || result.result_status !== 'LIVE';
  const transport = text(snapshot?.transport_state, 'OFFLINE').toUpperCase();
  const state = !result ? (transport === 'WAITING' ? 'WAITING' : 'OFFLINE') : stale ? 'STALE' : 'LIVE';
  const confidence = finite(result?.confidence);
  const fps = finite(result?.inference_fps);
  const p95 = finite(result?.inference_p95_ms);
  return Object.freeze({
    task,
    state,
    model: `${text(result?.model_id)} · ${shortHash(result?.model_sha256)}`,
    resultSequence: result ? String(positiveInteger(result.sequence) || '—') : '—',
    sourceSequence: sourceSequence ? String(sourceSequence) : '—',
    sourceEpoch: sourceEpoch ? String(sourceEpoch) : '—',
    age: receiveAge == null ? '—' : `${receiveAge.toFixed(2)} s`,
    inputAge: currentInputAge == null ? '—' : `${currentInputAge.toFixed(2)} s`,
    inputClock: result?.clock_domain_verified === true ? 'VERIFIED' : 'UNVERIFIED CLOCK',
    performance: `${fps == null ? '—' : `${fps.toFixed(1)} FPS`} · P95 ${p95 == null ? '—' : `${p95.toFixed(1)} ms`}`,
    confidence: confidence == null ? '—' : `${(confidence * 100).toFixed(0)}%`,
  });
}

export function projectCompetitionStatus(input = {}, now = Date.now()) {
  const backend = input.state || {};
  const fresh = Number(backend.updatedAt) > 0 && now - Number(backend.updatedAt) <= COMPETITION_STALE_MS;
  const competition = fresh ? backend.competition : null;
  const catalog = input.cameraCatalog || {};
  const sources = Array.isArray(catalog.sources) ? catalog.sources : [];
  const realsense = sources.find((entry) => entry.id === 'realsense_color') || {};
  const go2 = sources.find((entry) => entry.id === 'go2_front') || {};
  const relayWifi = realsense.metadata?.relay_health?.wifi || realsense.relay_health?.wifi || {};
  const rssi = finite(relayWifi.rssi_dbm);
  const link = finite(relayWifi.link_mbps);
  const receiveMbps = finite(realsense.metadata?.receive_bitrate_mbps ?? realsense.receive_bitrate_mbps);
  const receiveFps = finite(realsense.metadata?.receive_fps ?? realsense.receive_fps);
  const sourceFps = finite(realsense.metadata?.fps ?? realsense.fps);
  const sourceAge = finite(realsense.metadata?.age_s ?? realsense.age_s);
  const reconnects = finite(realsense.metadata?.browser_reconnects ?? realsense.restart_count) || 0;
  const queue = realsense.metadata?.browser_decode || {};
  const perceptionSnapshot = input.perception?.snapshot || {};
  const perceptionAge = input.perception?.updatedAt ? Math.max(0, now - input.perception.updatedAt) : Number.POSITIVE_INFINITY;
  const tasks = Object.freeze(Object.fromEntries(TASKS.map((task) => [task, taskProjection(perceptionSnapshot, task, perceptionAge)])));
  const active = backend.models?.active || {};
  const previous = backend.models?.previous || {};
  const activeText = TASKS.map((task) => active[task]?.model_id ? `${task}:${active[task].model_id}` : '').filter(Boolean).join(' · ') || 'NONE';
  const previousText = TASKS.map((task) => previous[task] ? `${task}:${previous[task]}` : '').filter(Boolean).join(' · ') || 'NONE';
  const transition = TASKS.some((task) => {
    const result = tasks[task];
    const expected = active[task]?.model_id;
    return expected && result.model !== '— · —' && !result.model.startsWith(`${expected} ·`);
  });
  const capture = input.dataset?.capture;
  return Object.freeze({
    operationMode: competition ? text(competition.operation_mode, 'SAFE_STOP') : 'SAFE_STOP · STALE',
    requestedMode: competition ? text(competition.requested_mode, 'MANUAL') : 'UNKNOWN',
    lock: competition ? (competition.locked ? 'LOCKED' : 'UNLOCKED') : 'UNKNOWN · BLOCKED',
    locked: competition?.locked !== false,
    authority: competition ? text(competition.motion_authority, 'NONE') : 'NONE',
    perceptionMode: 'SHADOW',
    dataset: capture?.active ? `CAPTURING · ${text(capture.sessionId, 'SESSION')}` : 'IDLE',
    robotWifi: `${text(relayWifi.state, 'UNAVAILABLE').toUpperCase()} · RSSI ${rssi == null ? '—' : `${rssi.toFixed(0)} dBm`} · LINK ${link == null ? '—' : `${link.toFixed(1)} Mbps`}`,
    rtt: 'UNAVAILABLE · P50 — · P95 — · P99 — · LOSS — · MEASURED —',
    go2Camera: `${text(go2.connection, 'WAITING').toUpperCase()} · ${finite(go2.fps) == null ? '—' : `${finite(go2.fps).toFixed(1)} FPS`}`,
    realsense: `${text(realsense.connection, 'WAITING').toUpperCase()} · ${sourceFps == null ? '—' : `${sourceFps.toFixed(1)} FPS`} · AGE ${sourceAge == null ? '—' : `${sourceAge.toFixed(2)} s`}`,
    transport: `${receiveMbps == null ? '—' : `${receiveMbps.toFixed(3)} Mbps`} · ${receiveFps == null ? '—' : `${receiveFps.toFixed(1)} FPS`}`,
    decode: `OK ${Number(queue.decodedFrames) || 0} · FAIL ${Number(queue.decodeFailures) || 0} · DROP ${Number(queue.supersededFrames) || 0}`,
    reconnect: realsense.reconnecting ? 'RECONNECTING' : `COUNT ${reconnects}`,
    clock: text(realsense.cross_host_latency_state || realsense.metadata?.cross_host_latency_state, 'UNVERIFIED_CLOCK_DOMAIN'),
    tasks,
    depthMode: tasks.depth_summary.state === 'LIVE' ? 'SUMMARY' : 'OFF',
    pointcloudMode: tasks.depth_summary.state === 'LIVE' ? 'SUMMARY' : 'OFF',
    activeModel: transition ? `TRANSITION · ${activeText}` : activeText,
    previousModel: previousText,
    fresh,
  });
}

function appendMetric(documentValue, root, label, value = '—') {
  const item = documentValue.createElement('div');
  const name = documentValue.createElement('span');
  const output = documentValue.createElement('strong');
  name.textContent = label;
  output.textContent = value;
  item.append(name, output);
  root.append(item);
  return output;
}

export function createCompetitionStatus(options = {}) {
  const documentValue = options.document || globalThis.document;
  const root = options.root;
  if (!documentValue || !root) throw new TypeError('CompetitionStatus requires document and root.');
  const api = options.api;
  const now = options.now || Date.now;
  const setIntervalValue = options.setInterval || globalThis.setInterval?.bind(globalThis);
  const clearIntervalValue = options.clearInterval || globalThis.clearInterval?.bind(globalThis);
  let state = reduceCompetitionState();
  let active = false;
  let timer = 0;
  let generation = 0;
  let cameraCatalog = options.cameraDemand?.snapshot?.() || { sources: [] };
  let perception = { snapshot: {}, updatedAt: 0 };
  let releaseCamera = null;
  let releasePerception = null;
  let expanded = false;

  root.replaceChildren();
  root.className = 'cockpit-competition-status';
  root.setAttribute('aria-label', 'Competition network perception and operation status');
  const header = documentValue.createElement('div');
  header.className = 'cockpit-competition-header';
  const title = documentValue.createElement('strong');
  title.textContent = 'COMPETITION STATUS';
  const shadow = documentValue.createElement('span');
  shadow.textContent = 'SHADOW · AUTHORITY NONE';
  const toggle = documentValue.createElement('button');
  toggle.type = 'button';
  toggle.className = 'cockpit-competition-toggle';
  toggle.textContent = '상세 펼치기';
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', 'cockpitCompetitionDetails');
  header.append(title, shadow, toggle);
  const metrics = documentValue.createElement('div');
  metrics.id = 'cockpitCompetitionDetails';
  metrics.className = 'cockpit-competition-metrics';
  metrics.hidden = true;
  const fields = new Map();
  for (const [label, key] of [
    ['MODE', 'mode'], ['LOCK', 'lock'], ['DATASET', 'dataset'], ['ROBOT WI-FI', 'wifi'], ['RTT / LOSS', 'rtt'],
    ['GO2 CAMERA', 'go2'], ['REALSENSE', 'realsense'], ['TRANSPORT RX', 'transport'], ['DECODE', 'decode'], ['RECONNECT', 'reconnect'], ['CLOCK', 'clock'],
    ['LANE', 'lane'], ['OBJECT / YOLO', 'object'], ['DEPTH', 'depth'], ['POINTCLOUD', 'pointcloud'], ['ACTIVE MODEL', 'active-model'], ['PREVIOUS MODEL', 'previous-model'],
  ]) fields.set(key, appendMetric(documentValue, metrics, label));
  const controls = documentValue.createElement('div');
  controls.className = 'cockpit-competition-controls';
  controls.hidden = true;
  const modeButtons = new Map();
  for (const mode of ['MANUAL', 'SHADOW', 'ASSISTED', 'AUTO']) {
    const button = documentValue.createElement('button');
    button.type = 'button';
    button.textContent = mode;
    button.dataset.competitionMode = mode;
    if (['ASSISTED', 'AUTO'].includes(mode)) {
      button.disabled = true;
      button.dataset.blockedReason = 'hardware acceptance and competition-rule review required';
      button.title = '하드웨어 수락과 대회 규정 확인 전에는 사용할 수 없습니다.';
    }
    modeButtons.set(mode, button);
    controls.append(button);
  }
  const lockButton = documentValue.createElement('button');
  lockButton.type = 'button';
  lockButton.textContent = 'ENABLE LOCK';
  const stationary = documentValue.createElement('label');
  const check = documentValue.createElement('input');
  check.type = 'checkbox';
  stationary.append(check, documentValue.createTextNode(' STATIONARY + DISARMED 확인'));
  const note = documentValue.createElement('small');
  note.textContent = 'Competition Lock은 설정 변경 잠금이며 물리 E-STOP이 아닙니다.';
  controls.append(lockButton, stationary, note);
  root.append(header, metrics, controls);

  function setExpanded(value) {
    expanded = Boolean(value);
    root.dataset.expanded = String(expanded);
    metrics.hidden = !expanded;
    controls.hidden = !expanded;
    toggle.textContent = expanded ? '상세 접기' : '상세 펼치기';
    toggle.setAttribute('aria-expanded', String(expanded));
  }

  function render() {
    const projected = projectCompetitionStatus({ state, cameraCatalog, perception, dataset: options.getDatasetSnapshot?.() }, now());
    fields.get('mode').textContent = `${projected.operationMode} · REQUESTED ${projected.requestedMode}`;
    fields.get('lock').textContent = `${projected.lock} · PHYSICAL SAFETY: NO`;
    fields.get('dataset').textContent = projected.dataset;
    fields.get('wifi').textContent = projected.robotWifi;
    fields.get('rtt').textContent = projected.rtt;
    fields.get('go2').textContent = projected.go2Camera;
    fields.get('realsense').textContent = projected.realsense;
    fields.get('transport').textContent = projected.transport;
    fields.get('decode').textContent = projected.decode;
    fields.get('reconnect').textContent = projected.reconnect;
    fields.get('clock').textContent = projected.clock;
    for (const [task, key] of [['lane', 'lane'], ['object', 'object'], ['depth_summary', 'depth']]) {
      const item = projected.tasks[task];
      fields.get(key).textContent = `${item.state} · ${item.model} · SRC ${item.sourceSequence} · EPOCH ${item.sourceEpoch} · INPUT AGE ${item.inputAge} · ${item.inputClock} · RX AGE ${item.age} · ${item.performance} · CONF ${item.confidence}`;
    }
    fields.get('pointcloud').textContent = `${projected.pointcloudMode} · DEPTH ${projected.depthMode}`;
    fields.get('active-model').textContent = projected.activeModel;
    fields.get('previous-model').textContent = projected.previousModel;
    shadow.textContent = `${projected.operationMode} · ${projected.lock} · AUTHORITY ${projected.authority}`;
    root.dataset.state = projected.fresh ? 'live' : 'stale';
    root.dataset.locked = String(projected.locked);
    lockButton.textContent = projected.locked ? 'UNLOCK' : 'ENABLE LOCK';
    lockButton.disabled = !projected.fresh;
    for (const [mode, button] of modeButtons) {
      button.setAttribute('aria-pressed', String(projected.requestedMode === mode));
      if (!['ASSISTED', 'AUTO'].includes(mode)) button.disabled = !projected.fresh || projected.locked;
    }
    options.onProjection?.(projected);
    return projected;
  }

  async function refresh() {
    if (!active) return render();
    const requestGeneration = ++generation;
    try {
      const [competition, models] = await Promise.all([api('/api/v1/competition'), api('/api/v1/models/active')]);
      if (!active || requestGeneration !== generation) return render();
      state = reduceCompetitionState(state, { type: 'SUCCESS', generation: requestGeneration, updatedAt: now(), competition, models });
    } catch (error) {
      if (!active || requestGeneration !== generation) return render();
      state = reduceCompetitionState(state, { type: 'ERROR', generation: requestGeneration, error: error?.message });
    }
    return render();
  }

  async function mutate(path, body) {
    if (!active) return;
    try {
      await api(path, { method: 'POST', body: JSON.stringify(body) });
      await refresh();
    } catch (error) {
      options.onError?.(error);
      render();
    }
  }

  for (const [mode, button] of modeButtons) button.addEventListener('click', () => mutate('/api/v1/competition/mode', { mode, confirmation: mode }));
  toggle.addEventListener('click', () => setExpanded(!expanded));
  lockButton.addEventListener('click', () => {
    const locked = state.competition?.locked !== false;
    if (locked) mutate('/api/v1/competition/unlock', { confirmation: 'UNLOCK', stationary_confirmed: check.checked === true });
    else mutate('/api/v1/competition/lock', { confirmation: 'LOCK' });
  });

  function activate() {
    if (active) return;
    active = true;
    releaseCamera = options.cameraDemand?.subscribe?.((value) => { if (active) { cameraCatalog = value; render(); } }) || null;
    releasePerception = options.perception?.subscribe?.((snapshot, localAgeMs) => { if (active) { perception = { snapshot, updatedAt: now() - localAgeMs }; render(); } }) || null;
    refresh();
    timer = setIntervalValue?.(refresh, 1000) || 0;
  }

  function deactivate() {
    if (!active) return;
    active = false;
    generation += 1;
    if (timer) clearIntervalValue?.(timer);
    timer = 0;
    releaseCamera?.(); releaseCamera = null;
    releasePerception?.(); releasePerception = null;
    state = reduceCompetitionState(state, { type: 'RESET' });
    render();
  }

  function destroy() { deactivate(); root.replaceChildren(); }
  setExpanded(false);
  render();
  return Object.freeze({ activate, deactivate, refresh, setExpanded, snapshot: () => Object.freeze({ active, expanded, state, projected: projectCompetitionStatus({ state, cameraCatalog, perception, dataset: options.getDatasetSnapshot?.() }, now()) }), destroy });
}

export { COMPETITION_STALE_MS };
