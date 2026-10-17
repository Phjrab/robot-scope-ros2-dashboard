/* Separate stationary depth capture. Never controls VSLAM, motion or TF. */
const controllers = new WeakMap();
const API = '/api/v1/slam';
const ENGINE = 'realsense_depth';
const ACTIVE_STATES = new Set(['PREFLIGHT', 'STARTING', 'WAITING_INPUT', 'CAPTURING', 'STOPPING', 'ERROR']);
export const DEPTH_POLL_MS = 2000;

export function depthRequestId(win) {
  // LAN HTTP has getRandomValues but may omit secure-context randomUUID.
  if (win.crypto?.randomUUID) return win.crypto.randomUUID();
  if (win.crypto?.getRandomValues) return 'depth-' + Array.from(win.crypto.getRandomValues(new Uint8Array(16)),
    value => value.toString(16).padStart(2, '0')).join('');
  return `depth-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function depthSession(value) {
  return Boolean(value?.engine_id === ENGINE && value.task === 'calibration' &&
    typeof value.session_id === 'string' && value.session_id.length > 0 &&
    Number.isInteger(value.generation) && value.generation >= 1);
}

export function sameDepthSession(left, right) {
  return depthSession(left) && depthSession(right) && left.session_id === right.session_id &&
    left.generation === right.generation && left.engine_id === right.engine_id;
}

export function depthConfirmation(value) {
  if (!['robot_seated', 'robot_stationary', 'camera_stationary'].every(key => value?.[key] === true)) {
    throw new Error('DEPTH_STATIONARY_CONFIRMATION_REQUIRED');
  }
  return { robot_seated: true, robot_stationary: true, camera_stationary: true };
}

export function depthActions(session, capability, confirmation, { busy = false, uncertain = false, known = true } = {}) {
  const confirmed = ['robot_seated', 'robot_stationary', 'camera_stationary'].every(key => confirmation?.[key] === true);
  const own = depthSession(session), idle = !session || session.state === 'IDLE';
  return {
    start: Boolean(known && !busy && !uncertain && idle && capability?.available_now === true &&
      capability.tasks?.includes('calibration') && confirmed),
    capture: known && !busy && !uncertain && own && ['WAITING_INPUT', 'CAPTURING'].includes(session.state) && confirmed,
    stop: known && !busy && own && ACTIVE_STATES.has(session.state) && session.state !== 'STOPPING',
  };
}

function errorMessage(error) {
  const detail = error?.detail;
  const resources = Array.isArray(detail?.resources) ? detail.resources.map(item => `${item.resource}: ${item.reason}`).join(', ') : '';
  return `${detail?.code || error.message || 'DEPTH_REQUEST_FAILED'}${resources ? ` · ${resources}` : ''}`;
}

export function mountDepthCapture(doc = document, options = {}) {
  if (controllers.has(doc)) return controllers.get(doc);
  const host = doc.querySelector('[data-page="mapping"]');
  if (!host) return null;
  const win = options.window || doc.defaultView || window;
  const fetcher = options.fetch || win.fetch.bind(win);
  const requestId = options.requestId || (() => depthRequestId(win));
  const listeners = [], requests = new Set();
  const state = { session: null, capability: null, known: false, busy: false, uncertain: null,
    activePage: doc.documentElement.dataset.activePage || win.location.hash.slice(1),
    disposed: false, timer: null, readSerial: 0, selected: null, imageSerial: 0, samples: [] };
  const el = (tag, attributes = {}, ...children) => {
    const node = doc.createElement(tag);
    for (const [key, value] of Object.entries(attributes)) {
      if (key === 'text') node.textContent = value;
      else if (['hidden', 'disabled', 'checked'].includes(key)) node[key] = value;
      else node.setAttribute(key, String(value));
    }
    node.append(...children); return node;
  };
  const on = (node, event, fn) => {
    node.addEventListener(event, fn); listeners.push(() => node.removeEventListener(event, fn));
  };
  const panel = el('section', { id: 'depthCaptureConsole', class: 'panel slam-console', 'aria-label': '정지 Depth 캡처' });
  const status = el('strong', { id: 'depthCaptureState', text: 'CHECKING', role: 'status' });
  const message = el('p', { id: 'depthCaptureMessage', class: 'slam-muted', role: 'status', 'aria-live': 'polite' });
  const checks = {};
  const labels = { robot_seated: '로봇이 앉아 있습니다.', robot_stationary: '로봇이 정지해 있습니다.',
    camera_stationary: '카메라가 움직이지 않습니다.' };
  const confirmations = el('div', { class: 'slam-control-row' });
  for (const [key, label] of Object.entries(labels)) {
    checks[key] = el('input', { type: 'checkbox', id: `depth_${key}` });
    confirmations.append(el('label', { class: 'slam-check' }, checks[key], el('span', { text: label })));
    on(checks[key], 'change', render);
  }
  const start = el('button', { id: 'depthCaptureStart', type: 'button', text: 'Depth 캡처 시작', disabled: true });
  const capture = el('button', { id: 'depthCaptureSample', type: 'button', text: '정지 샘플 저장', disabled: true });
  const stop = el('button', { id: 'depthCaptureStop', type: 'button', text: 'Depth 캡처 중지', disabled: true });
  const refresh = el('button', { id: 'depthCaptureRefresh', type: 'button', text: '상태·저장 목록 확인' });
  const list = el('div', { id: 'depthCaptureSamples', class: 'slam-package-list', 'aria-label': '저장된 Depth 샘플' });
  const detail = el('p', { id: 'depthCaptureSampleDetail', class: 'slam-detail', text: '저장된 샘플을 선택하면 원본 IR 영상과 내려받기를 확인할 수 있습니다.' });
  const image = el('img', { id: 'depthCaptureImage', alt: '저장된 무손실 IR 원본 영상', hidden: true,
    style: 'display:block;max-width:100%;height:auto;object-fit:contain' });
  const downloads = el('div', { class: 'slam-control-row' });
  panel.append(el('div', { class: 'slam-heading' }, el('h2', { text: '정지 Depth 캡처' }), status),
    el('p', { class: 'slam-muted', text: '별도 카메라 모드입니다. 먼저 실행 중인 VSLAM을 직접 중지하세요. VSLAM의 중지·지도 폐기·재시작은 자동 실행하지 않습니다.' }),
    el('p', { class: 'slam-muted', text: '매 시작·저장 직전에 세 조건을 다시 확인하세요. 앉은 본체가 수평이라고 가정하지 않으며, 본체 자세는 미측정으로 기록합니다. TF·SLAM 보정에 자동 적용하지 않습니다.' }),
    confirmations, el('div', { class: 'slam-control-row' }, start, capture, stop, refresh), message,
    el('h3', { text: '저장된 샘플' }), list, detail, downloads, image);
  const slamPanel = doc.getElementById('slamConsole');
  if (slamPanel?.parentNode === host) slamPanel.after(panel); else host.prepend(panel);

  const visible = () => !state.disposed && !doc.hidden && state.activePage === 'mapping';
  const confirmation = () => Object.fromEntries(Object.entries(checks).map(([key, node]) => [key, node.checked === true]));
  function resetChecks() { for (const node of Object.values(checks)) node.checked = false; }
  function render() {
    const actions = depthActions(state.session, state.capability, confirmation(), {
      busy: state.busy, uncertain: Boolean(state.uncertain), known: state.known && visible() });
    start.disabled = !actions.start; capture.disabled = !actions.capture; stop.disabled = !actions.stop;
    refresh.disabled = state.busy; panel.setAttribute('aria-busy', String(state.busy));
    for (const node of Object.values(checks)) node.disabled = state.busy;
    status.textContent = !state.known ? 'UNKNOWN' : depthSession(state.session) ? state.session.state :
      state.session && state.session.state !== 'IDLE' ? `${state.session.engine_id} · ${state.session.state}` : 'IDLE';
  }
  async function api(path, body) {
    const controller = new win.AbortController(); requests.add(controller);
    const timer = win.setTimeout(() => controller.abort(), 15_000);
    try {
      const response = await fetcher(API + path, { method: body === undefined ? 'GET' : 'POST',
        headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      const result = await response.json();
      if (!response.ok) throw Object.assign(new Error(result.detail?.code || `HTTP_${response.status}`),
        { detail: result.detail, definite: response.status >= 400 && response.status < 500 });
      return result;
    } finally { win.clearTimeout(timer); requests.delete(controller); }
  }
  function acceptSession(value) {
    const previous = state.session;
    state.session = value.active_session || null; state.known = true;
    if (!sameDepthSession(previous, state.session)) resetChecks();
    if (state.uncertain?.action === 'stop' && (!state.session || state.session.state === 'IDLE')) state.uncertain = null;
  }
  function schedule() {
    win.clearTimeout(state.timer); state.timer = null;
    if (visible() && depthSession(state.session) && state.session.state !== 'IDLE') {
      state.timer = win.setTimeout(() => refreshStatus(false), DEPTH_POLL_MS);
    }
  }
  async function refreshStatus(full = false) {
    if (!visible() || state.busy) return;
    const serial = ++state.readSerial;
    try {
      const values = await Promise.all([api('/session'), ...(full ? [api('/engines'), api('/depth/samples')] : [])]);
      if (serial !== state.readSerial || !visible()) return;
      acceptSession(values[0]);
      if (full) { state.capability = values[1].engines?.find(item => item.engine_id === ENGINE) || null; showSamples(values[2].samples || []); }
      if (!state.uncertain) message.textContent = state.session && state.session.state !== 'IDLE' && !depthSession(state.session)
        ? '다른 관측 세션이 실행 중입니다. 해당 세션 화면에서 직접 중지한 뒤 상태를 확인하세요.'
        : state.session?.reason || state.capability?.blocked_reason || '시작과 저장에는 현재 정지 상태 확인이 필요합니다.';
    } catch (error) { if (serial === state.readSerial && visible()) { state.known = false; message.textContent = `상태 확인 실패 · ${errorMessage(error)}`; } }
    finally { if (serial === state.readSerial) { render(); schedule(); } }
  }
  function showSamples(samples) {
    state.samples = samples.slice(0, 100);
    list.replaceChildren();
    for (const sample of state.samples) {
      if (!validSampleId(sample?.sample_id)) continue;
      const button = el('button', { type: 'button', text: sample.sample_id, 'data-sample-id': sample.sample_id });
      list.append(button);
    }
    if (!list.children.length) list.append(el('p', { class: 'slam-muted', text: '저장된 Depth 샘플이 없습니다.' }));
  }
  function showSample(sample) {
    const dimensions = sample.image;
    state.selected = sample.sample_id; const serial = ++state.imageSerial;
    image.hidden = true; image.removeAttribute('src'); downloads.replaceChildren();
    const compatibility = sample.compatibility;
    detail.textContent = `${sample.sample_id} · 호환성 ${compatibility?.available === true ? 'available' : 'unavailable'}${compatibility?.reason ? ` · ${compatibility.reason}` : ''} · 본체 수평 가정 없음 · 자동 적용 없음`;
    if (Number.isFinite(sample.valid_depth_ratio) && sample.valid_depth_ratio >= 0 && sample.valid_depth_ratio <= 1) {
      detail.textContent += ` · 유효 Depth ${(sample.valid_depth_ratio * 100).toFixed(1)}% (0이 아닌 raw 픽셀 비율)`;
    }
    if (Number.isFinite(sample.actual_source_skew_ms) && sample.actual_source_skew_ms >= 0) {
      detail.textContent += ` · IR–Depth timestamp 차이 ${sample.actual_source_skew_ms.toFixed(3)}ms`;
    }
    for (const [suffix, label] of [['export', '샘플 ZIP'], ['compatibility', '호환성 JSON'], ['image', '원본 IR PNG']]) {
      if (suffix === 'compatibility' && compatibility?.available !== true) continue;
      downloads.append(el('a', { href: `${API}/depth/samples/${encodeURIComponent(sample.sample_id)}/${suffix}`, download: '', text: label }));
    }
    if (dimensions?.available !== true || !Number.isInteger(dimensions?.width) || !Number.isInteger(dimensions?.height) ||
        dimensions.width < 1 || dimensions.height < 1 || dimensions.width > 4096 || dimensions.height > 4096) {
      detail.textContent += ' · IMAGE_DIMENSIONS_UNAVAILABLE'; return;
    }
    image.width = dimensions.width; image.height = dimensions.height;
    image.onload = () => {
      if (serial !== state.imageSerial || state.disposed) return;
      image.hidden = image.naturalWidth !== dimensions.width || image.naturalHeight !== dimensions.height;
      detail.textContent += image.hidden ? ' · IMAGE_DIMENSION_MISMATCH' : ` · 원본 ${dimensions.width} × ${dimensions.height}px (표시 크기만 조정)`;
    };
    image.onerror = () => { if (serial === state.imageSerial) { image.hidden = true; detail.textContent += ' · IMAGE_UNAVAILABLE'; } };
    image.src = `${API}/depth/samples/${encodeURIComponent(sample.sample_id)}/image`;
  }
  async function act(action) {
    const allowed = depthActions(state.session, state.capability, confirmation(), {
      busy: state.busy, uncertain: Boolean(state.uncertain), known: state.known && visible() });
    if (!allowed[action]) return;
    const context = state.session ? { ...state.session } : null;
    const flags = action === 'stop' ? null : depthConfirmation(confirmation());
    state.busy = true; state.readSerial += 1; win.clearTimeout(state.timer); render();
    let submitted = false;
    try {
      const fresh = await api('/session');
      acceptSession(fresh);
      if (action === 'start') {
        const caps = await api('/engines');
        state.capability = caps.engines?.find(item => item.engine_id === ENGINE) || null;
        if (state.session && state.session.state !== 'IDLE') throw new Error('SESSION_ACTIVE_STOP_IT_FIRST');
        if (state.capability?.available_now !== true || !state.capability.tasks?.includes('calibration')) throw new Error(state.capability?.blocked_reason || 'DEPTH_ENGINE_UNAVAILABLE');
      } else if (!sameDepthSession(context, state.session)) throw new Error('DEPTH_SESSION_CHANGED');
      else if (!depthActions(state.session, state.capability, flags || {}, { known: true })[action]) throw new Error('DEPTH_OPERATION_IN_PROGRESS');
      if (!visible()) throw new Error('DEPTH_PAGE_INACTIVE');
      const id = requestId();
      const path = action === 'start' ? '/depth/sessions' : `/sessions/${encodeURIComponent(context.session_id)}/${action === 'capture' ? 'depth-samples' : 'stop'}`;
      const body = action === 'start' ? { request_id: id, ...flags } : action === 'capture'
        ? { generation: context.generation, request_id: id, ...flags, body_attitude: null }
        : { generation: context.generation, request_id: id, discard_unsaved: false };
      resetChecks(); submitted = true;
      const result = await api(path, body);
      // Save responses may outlive a session. Re-read exact ownership before
      // presenting the response as this live session's capture.
      acceptSession(await api('/session'));
      if (action === 'capture') {
        if (!sameDepthSession(context, state.session)) throw Object.assign(new Error('DEPTH_SESSION_CHANGED_AFTER_CAPTURE'), { definite: true });
        if (!validSampleId(result.sample_id) || result.session_id !== context.session_id ||
            result.generation !== context.generation || result.engine_id !== context.engine_id) throw new Error('DEPTH_CAPTURE_RECEIPT_INVALID');
        showSample(result);
        const entries = await api('/depth/samples'); showSamples(entries.samples || []);
      }
      state.uncertain = null;
      message.textContent = action === 'capture' ? '샘플 저장 완료. 다음 저장 전에는 세 조건을 다시 확인하세요.' :
        action === 'start' ? 'Depth 시작 요청을 접수했습니다. 카메라 준비 후 다시 정지 상태를 확인해 샘플을 저장하세요.' : 'Depth 중지 요청을 접수했습니다. IDLE과 카메라 정리 상태를 확인하세요.';
    } catch (error) {
      if (submitted && !error.definite) state.uncertain = { action, context };
      message.textContent = `${errorMessage(error)}${state.uncertain ? ' · 요청 결과 미확정. 자동 재시도하지 않습니다. 상태·저장 목록을 확인하고 필요하면 Depth를 중지하세요.' : ''}`;
    } finally { state.busy = false; render(); schedule(); }
  }
  for (const [button, action] of [[start, 'start'], [capture, 'capture'], [stop, 'stop']]) on(button, 'click', () => act(action));
  on(refresh, 'click', () => refreshStatus(true));
  on(list, 'click', event => {
    const id = event.target.closest('[data-sample-id]')?.dataset.sampleId;
    const sample = state.samples.find(value => value.sample_id === id);
    if (sample) showSample(sample);
  });
  async function setActive(page) {
    state.activePage = page; state.readSerial += 1; win.clearTimeout(state.timer); state.timer = null;
    render(); if (visible()) await refreshStatus(true);
  }
  on(doc, 'robot-scope:page-change', event => setActive(event.detail?.activePage));
  on(doc, 'visibilitychange', () => setActive(state.activePage));
  const controller = { setActive, refresh: refreshStatus,
    dispose() {
      state.disposed = true; state.readSerial += 1; state.imageSerial += 1; win.clearTimeout(state.timer);
      for (const request of requests) request.abort();
      for (const dispose of listeners) dispose();
      image.onload = image.onerror = null; panel.remove(); controllers.delete(doc);
    },
  };
  on(win, 'pagehide', event => { if (!event.persisted) controller.dispose(); else setActive(null); });
  on(win, 'pageshow', event => { if (event.persisted) setActive(doc.documentElement.dataset.activePage || win.location.hash.slice(1)); });
  controllers.set(doc, controller); setActive(state.activePage); return controller;
}

function validSampleId(value) { return typeof value === 'string' && /^[A-Za-z0-9_-]{8,96}$/.test(value); }

if (typeof document !== 'undefined') mountDepthCapture(document);
