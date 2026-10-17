import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('../robot_dashboard/static/features/slam/depth_capture.js', import.meta.url), 'utf8');
const { depthSession, sameDepthSession, depthConfirmation, depthActions, depthRequestId, mountDepthCapture, DEPTH_POLL_MS } =
  await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const ready = { session_id: 'depth-session-a', generation: 3, engine_id: 'realsense_depth',
  task: 'calibration', state: 'CAPTURING' };
const flags = { robot_seated: true, robot_stationary: true, camera_stationary: true };
const capability = { engine_id: 'realsense_depth', available_now: true, tasks: ['calibration'] };
const receipt = { sample_id: 'a'.repeat(32), ...ready, compatibility: { available: true, reason: null },
  image: { available: true, width: 640, height: 480 } };

class Node {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.listeners = new Map(); this.attributes = {};
    this.dataset = {}; this.hidden = false; this.checked = false; this.disabled = false;
    this.textContent = ''; this.parentNode = null;
  }
  append(...children) { for (const child of children) { child.parentNode = this; this.children.push(child); } }
  prepend(child) { child.parentNode = this; this.children.unshift(child); }
  after(child) { const siblings = this.parentNode.children; child.parentNode = this.parentNode; siblings.splice(siblings.indexOf(this) + 1, 0, child); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); }
  setAttribute(key, value) {
    this.attributes[key] = value;
    if (key === 'id') this.id = value;
    if (key === 'data-sample-id') this.dataset.sampleId = value;
  }
  removeAttribute(key) { delete this.attributes[key]; if (key === 'src') this.src = ''; }
  addEventListener(event, fn) { if (!this.listeners.has(event)) this.listeners.set(event, new Set()); this.listeners.get(event).add(fn); }
  removeEventListener(event, fn) { this.listeners.get(event)?.delete(fn); }
  async emit(event, detail = {}) { await Promise.all([...this.listeners.get(event) || []].map(fn => fn({ target: this, ...detail }))); }
  closest(selector) { return selector === '[data-sample-id]' && this.dataset.sampleId ? this : this.parentNode?.closest(selector); }
}

async function fixture({ session = null, cap = capability, samples = [], page = 'mapping', post = null } = {}) {
  const host = new Node('section'), doc = new Node('document'), win = new Node('window');
  const slam = new Node(); slam.id = 'slamConsole'; host.append(slam);
  const walk = node => [node, ...node.children.flatMap(walk)];
  doc.querySelector = selector => selector === '[data-page="mapping"]' ? host : null;
  doc.createElement = tag => new Node(tag);
  doc.getElementById = id => walk(host).find(node => node.id === id);
  doc.documentElement = { dataset: { activePage: page } }; doc.hidden = false; doc.defaultView = win;
  win.location = { hash: '#' + page }; win.AbortController = AbortController;
  const timers = new Map(); let timerId = 0, id = 0;
  win.setTimeout = (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId; };
  win.clearTimeout = key => timers.delete(key);
  const data = { session, cap, samples, calls: [], getHook: null, postHook: post };
  const fetcher = async (url, init) => {
    const path = url.replace('/api/v1/slam', '');
    const body = init.body && JSON.parse(init.body);
    data.calls.push({ path, method: init.method, body });
    let value;
    if (init.method === 'POST') {
      if (data.postHook) value = await data.postHook(path, body, data);
      else if (path === '/depth/sessions') { data.session = { ...ready, state: 'STARTING' }; value = ready; }
      else if (path.endsWith('/depth-samples')) { data.samples = [receipt]; value = receipt; }
      else if (path.endsWith('/stop')) { data.session = { ...data.session, state: 'IDLE' }; value = data.session; }
      else throw new Error('Unexpected mutation ' + path);
    } else {
      if (data.getHook) await data.getHook(path, data);
      if (path === '/session') value = { active_session: data.session };
      else if (path === '/engines') value = { engines: data.cap ? [data.cap] : [] };
      else if (path === '/depth/samples') value = { samples: data.samples };
      else throw new Error('Unexpected GET ' + path);
    }
    if (value?.httpError) return { ok: false, status: value.status, json: async () => value.body };
    return { ok: true, status: 200, json: async () => value };
  };
  const controller = mountDepthCapture(doc, { window: win, fetch: fetcher, requestId: () => `depth-request-${++id}` });
  const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
  await flush();
  const get = id => doc.getElementById(id);
  const confirm = async () => { for (const key of Object.keys(flags)) { const node = get('depth_' + key); node.checked = true; await node.emit('change'); } };
  const posts = () => data.calls.filter(call => call.method === 'POST');
  return { host, doc, win, data, timers, controller, get, confirm, posts, flush };
}

test('only explicit true attestations are accepted; body attitude is never inferred', () => {
  assert.deepEqual(depthConfirmation(flags), flags);
  for (const key of Object.keys(flags)) for (const value of [false, undefined, 1, 'true']) {
    assert.throws(() => depthConfirmation({ ...flags, [key]: value }), /CONFIRMATION_REQUIRED/);
  }
});

test('request ids work on LAN HTTP without secure-context randomUUID', () => {
  const id = depthRequestId({ crypto: { getRandomValues: array => array.fill(123) } });
  assert.equal(id, 'depth-' + '7b'.repeat(16));
  assert.match(depthRequestId({}), /^[A-Za-z0-9_-]{8,96}$/);
});

test('exact depth identity includes engine, task, id and generation', () => {
  assert.equal(depthSession(ready), true); assert.equal(sameDepthSession(ready, { ...ready }), true);
  for (const change of [{ engine_id: 'visual_stereo' }, { task: 'mapping' }, { session_id: 'other' }, { generation: 4 }]) {
    assert.equal(sameDepthSession(ready, { ...ready, ...change }), false);
  }
  assert.equal(depthSession({ ...ready, generation: '3' }), false);
});

test('start requires idle known shared session, capability, task and all confirmations', () => {
  assert.equal(depthActions(null, capability, flags).start, true);
  for (const [session, cap, confirm, options] of [
    [ready, capability, flags, {}], [null, { ...capability, available_now: false }, flags, {}],
    [null, { ...capability, tasks: ['mapping'] }, flags, {}], [null, null, flags, {}],
    [null, capability, {}, {}], [null, capability, flags, { known: false }],
    [null, capability, flags, { busy: true }], [null, capability, flags, { uncertain: true }],
  ]) assert.equal(depthActions(session, cap, confirm, options).start, false);
});

test('ready depth capture allows WAITING_INPUT/CAPTURING and stop but no foreign operation', () => {
  for (const state of ['WAITING_INPUT', 'CAPTURING']) {
    assert.equal(depthActions({ ...ready, state }, capability, flags).capture, true);
    assert.equal(depthActions({ ...ready, state }, capability, flags).stop, true);
  }
  for (const state of ['STARTING', 'STOPPING', 'IDLE', 'ERROR']) assert.equal(depthActions({ ...ready, state }, capability, flags).capture, false);
  const foreign = { ...ready, engine_id: 'visual_stereo', task: 'mapping', state: 'MAPPING' };
  assert.deepEqual(depthActions(foreign, capability, flags), { start: false, capture: false, stop: false });
  assert.equal(depthActions(ready, capability, flags, { uncertain: true }).stop, true);
});

test('mount is unique and only mapping activation reads; idle does not poll', async () => {
  const f = await fixture({ page: 'maps' });
  assert.equal(f.data.calls.length, 0);
  assert.equal(mountDepthCapture(f.doc), f.controller);
  assert.equal(f.host.children[1].id, 'depthCaptureConsole');
  await f.controller.setActive('mapping');
  assert.deepEqual(f.data.calls.map(call => call.path).sort(), ['/depth/samples', '/engines', '/session']);
  assert.equal(f.timers.size, 0); f.controller.dispose();
});

test('start sends only strict new mode confirmation, resets checks and never stops VSLAM', async () => {
  const f = await fixture(); await f.confirm();
  assert.equal(f.get('depthCaptureStart').disabled, false);
  await f.get('depthCaptureStart').emit('click');
  assert.deepEqual(f.posts(), [{ path: '/depth/sessions', method: 'POST',
    body: { request_id: 'depth-request-1', ...flags } }]);
  for (const key of Object.keys(flags)) assert.equal(f.get('depth_' + key).checked, false);
  assert.equal(f.get('depthCaptureSample').disabled, true);
  f.controller.dispose();
});

test('fresh shared-session or capability conflict blocks start without mutation', async () => {
  for (const kind of ['session', 'capability']) {
    const f = await fixture(); await f.confirm();
    if (kind === 'session') f.data.session = { ...ready, engine_id: 'visual_stereo', state: 'MAPPING' };
    else f.data.cap = { ...capability, available_now: false, blocked_reason: 'CAMERA_BUSY' };
    await f.get('depthCaptureStart').emit('click');
    assert.equal(f.posts().length, 0); f.controller.dispose();
  }
});

test('capture rechecks exact generation before submitting', async () => {
  const f = await fixture({ session: ready }); await f.confirm();
  f.data.session = { ...ready, generation: 4 };
  await f.get('depthCaptureSample').emit('click');
  assert.equal(f.posts().length, 0);
  assert.match(f.get('depthCaptureMessage').textContent, /SESSION_CHANGED/); f.controller.dispose();
});

test('saved sample retains original IR dimensions and becomes visible only after lossless image loads', async () => {
  const f = await fixture({ session: ready }); await f.confirm();
  await f.get('depthCaptureSample').emit('click');
  assert.deepEqual(f.posts()[0], { path: '/sessions/depth-session-a/depth-samples', method: 'POST',
    body: { generation: 3, request_id: 'depth-request-1', ...flags, body_attitude: null } });
  for (const key of Object.keys(flags)) assert.equal(f.get('depth_' + key).checked, false);
  assert.equal(f.get('depthCaptureSample').disabled, true);
  const image = f.get('depthCaptureImage');
  assert.equal(image.hidden, true); assert.equal(image.width, 640); assert.equal(image.height, 480);
  assert.equal(image.src, `/api/v1/slam/depth/samples/${receipt.sample_id}/image`);
  image.naturalWidth = 640; image.naturalHeight = 480; image.onload();
  assert.equal(image.hidden, false); assert.match(f.get('depthCaptureSampleDetail').textContent, /640 × 480/);
  f.controller.dispose();
});

test('image mismatch or unavailable source remains hidden without suppressing downloads', async () => {
  for (const available of [true, false]) {
    const f = await fixture({ session: ready, post: async () => ({ ...receipt, image: { ...receipt.image, available } }) });
    await f.confirm(); await f.get('depthCaptureSample').emit('click');
    const image = f.get('depthCaptureImage');
    if (available) { image.naturalWidth = 320; image.naturalHeight = 240; image.onload(); }
    assert.equal(image.hidden, true);
    assert.match(f.get('depthCaptureSampleDetail').textContent, available ? /IMAGE_DIMENSION_MISMATCH/ : /IMAGE_DIMENSIONS_UNAVAILABLE/);
    f.controller.dispose();
  }
});

test('capture receipt and post-save shared context must match exactly', async () => {
  for (const change of ['receipt', 'session']) {
    const f = await fixture({ session: ready, post: async (_path, _body, data) => {
      if (change === 'session') data.session = { ...ready, generation: 4 };
      return change === 'receipt' ? { ...receipt, generation: 99 } : receipt;
    } });
    await f.confirm(); await f.get('depthCaptureSample').emit('click');
    assert.equal(f.get('depthCaptureImage').src, undefined);
    assert.match(f.get('depthCaptureMessage').textContent, change === 'receipt' ? /RECEIPT_INVALID/ : /CHANGED_AFTER_CAPTURE/);
    f.controller.dispose();
  }
});

test('uncertain capture is not retried under a new request id; exact depth stop remains available', async () => {
  const f = await fixture({ session: ready, post: async () => { throw new TypeError('Network failure'); } });
  await f.confirm(); await f.get('depthCaptureSample').emit('click');
  await f.confirm(); await f.get('depthCaptureSample').emit('click');
  await f.controller.refresh(true); await f.confirm();
  assert.equal(f.posts().length, 1); assert.equal(f.get('depthCaptureSample').disabled, true);
  assert.equal(f.get('depthCaptureStop').disabled, false);
  assert.match(f.get('depthCaptureMessage').textContent, /요청 결과 미확정/); f.controller.dispose();
});

test('server conflict gives exact resource and requires fresh confirmations', async () => {
  const f = await fixture({ session: ready, post: async () => ({ httpError: true, status: 409,
    body: { detail: { code: 'RESOURCE_CONFLICT', resources: [{ resource: 'camera', reason: 'camera_busy' }] } } }) });
  await f.confirm(); await f.get('depthCaptureSample').emit('click');
  assert.match(f.get('depthCaptureMessage').textContent, /camera: camera_busy/);
  assert.equal(f.get('depthCaptureSample').disabled, true);
  await f.confirm(); assert.equal(f.get('depthCaptureSample').disabled, false); f.controller.dispose();
});

test('stop uses exact context without discard and never touches existing VSLAM', async () => {
  const f = await fixture({ session: ready });
  await f.get('depthCaptureStop').emit('click');
  assert.deepEqual(f.posts(), [{ path: '/sessions/depth-session-a/stop', method: 'POST',
    body: { generation: 3, request_id: 'depth-request-1', discard_unsaved: false } }]);
  assert.equal(f.timers.size, 0); f.controller.dispose();
});

test('PREFLIGHT depth session remains stoppable while sample capture stays disabled', async () => {
  const f = await fixture({ session: { ...ready, state: 'PREFLIGHT' } });
  await f.confirm();
  assert.equal(f.get('depthCaptureSample').disabled, true);
  assert.equal(f.get('depthCaptureStop').disabled, false);
  await f.get('depthCaptureStop').emit('click');
  assert.equal(f.posts().length, 1);
  assert.equal(f.posts()[0].path, '/sessions/depth-session-a/stop');
  assert.equal(f.posts()[0].body.discard_unsaved, false); f.controller.dispose();
});

test('unavailable compatibility hides only its JSON link and preserves reason, raw ZIP and IR', async () => {
  for (const available of [false, undefined, 'true']) {
    const f = await fixture({ session: ready, post: async () => ({ ...receipt,
      compatibility: { available, reason: 'DISTORTION_MODEL_UNSUPPORTED' } }) });
    await f.confirm(); await f.get('depthCaptureSample').emit('click');
    const walk = node => [node, ...node.children.flatMap(walk)];
    const links = walk(f.get('depthCaptureConsole')).filter(node => node.tagName === 'a');
    assert.deepEqual(links.map(node => node.textContent), ['샘플 ZIP', '원본 IR PNG']);
    assert.match(f.get('depthCaptureSampleDetail').textContent, /DISTORTION_MODEL_UNSUPPORTED/);
    assert.equal(f.get('depthCaptureImage').src, `/api/v1/slam/depth/samples/${receipt.sample_id}/image`);
    f.controller.dispose();
  }
});

test('finite source metrics are shown without treating raw nonzero fraction as accuracy', async () => {
  for (const valid of [true, false]) {
    const f = await fixture({ session: ready, post: async () => ({ ...receipt,
      valid_depth_ratio: valid ? .75 : null, actual_source_skew_ms: valid ? 2.5 : null }) });
    await f.confirm(); await f.get('depthCaptureSample').emit('click');
    const detail = f.get('depthCaptureSampleDetail').textContent;
    assert.equal(detail.includes('유효 Depth 75.0% (0이 아닌 raw 픽셀 비율)'), valid);
    assert.equal(detail.includes('IR–Depth timestamp 차이 2.500ms'), valid);
    f.controller.dispose();
  }
});

test('depth polling is bounded at two seconds and stops when hidden or inactive', async () => {
  const f = await fixture({ session: ready });
  assert.equal(DEPTH_POLL_MS, 2000); assert.deepEqual([...f.timers.values()].map(timer => timer.ms), [2000]);
  const before = f.data.calls.length; f.doc.hidden = true; await f.doc.emit('visibilitychange');
  assert.equal(f.timers.size, 0); assert.equal(f.data.calls.length, before);
  f.doc.hidden = false; await f.controller.setActive('maps');
  assert.equal(f.timers.size, 0); assert.equal(f.data.calls.length, before);
  await f.controller.setActive('mapping');
  assert.deepEqual([...f.timers.values()].map(timer => timer.ms), [2000]); f.controller.dispose();
});

test('failed status read disables actions rather than trusting stale depth state', async () => {
  const f = await fixture({ session: ready }); await f.confirm();
  f.data.getHook = async () => { throw new TypeError('offline'); };
  await f.controller.refresh(false);
  assert.equal(f.get('depthCaptureStart').disabled, true);
  assert.equal(f.get('depthCaptureSample').disabled, true);
  assert.equal(f.get('depthCaptureStop').disabled, true); f.controller.dispose();
});

test('hidden page cannot submit capture after a delayed preflight completes', async () => {
  const f = await fixture({ session: ready }); await f.confirm();
  f.data.getHook = async () => { f.doc.hidden = true; };
  await f.get('depthCaptureSample').emit('click');
  assert.equal(f.posts().length, 0); f.controller.dispose();
});

test('index adds depth module once and module has no point selection or operational mutation path', () => {
  const html = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
  assert.equal(html.split('/static/features/slam/depth_capture.js').length - 1, 1);
  for (const path of ['/control/', '/navigation/', '/initialpose', '/localize', '/save', '/mapping/start']) assert.equal(source.includes(path), false);
  assert.equal(source.includes('getContext('), false);
});
