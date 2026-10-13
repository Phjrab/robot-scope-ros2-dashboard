import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const modelSource = fs.readFileSync(new URL('../robot_dashboard/static/features/resources/model.js', import.meta.url), 'utf8');
const model = await import('data:text/javascript;base64,' + Buffer.from(modelSource).toString('base64'));
const view = fs.readFileSync(new URL('../robot_dashboard/static/features/resources/view.js', import.meta.url), 'utf8').replace(/^import[^\n]*\n/, '');

class Element {
  constructor() { this.children = []; this.attributes = {}; this.listeners = {}; this.dataset = {}; this.style = {}; this.value = ''; this.rawText = ''; this.disabled = false; }
  set textContent(value) { this.rawText = String(value); this.children = []; }
  get textContent() { return this.rawText + this.children.map((node) => node.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.rawText = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  click() { this.listeners.click?.(); }
  closest() { return null; }
  getBoundingClientRect() { return { width: 0, height: 230 }; }
}

function harness() {
  const nodes = new Map();
  const document = {
    hidden: false, listeners: {}, documentElement: new Element(), body: new Element(),
    getElementById(id) { if (!nodes.has(id)) { const node = new Element(); if (id.endsWith('Bar')) node.parentElement = new Element(); nodes.set(id, node); } return nodes.get(id); },
    createElement: () => new Element(),
    createTextNode(text) { const node = new Element(); node.textContent = text; return node; },
    addEventListener(name, listener) { this.listeners[name] = listener; },
  };
  document.getElementById('loadThreshold').value = '80'; document.getElementById('historyWindow').value = '120';
  const h = { document, nodes, fail: false, calls: 0 };
  const fetch = async () => {
    h.calls++;
    if (h.fail) throw Error('offline');
    return { ok: true, json: async () => ({
      schema: 'robot-scope.resources.v1', seq: h.calls, timestamp_ms: 60000 + h.calls * 1200, sample_interval_s: 1.2,
      host: { model: 'Jetson fixture', hostname: 'fixture' },
      cpu: { percent: 20, max_core_percent: 95, cores: [{ name: 'cpu0', online: true, percent: 95, frequency_mhz: 1200 }] },
      gpu: { percent: 30, frequency_mhz: 612, source: 'sysfs fixture' }, memory: { percent: 40 },
      sensors: { cameras: [{ id: 'camera', label: 'Camera', state: 'ok', live: true, age_s: .1, receive_fps: 15, width: 1280, height: 720 }], topics: [] },
    }) };
  };
  class Observer { observe() {} }
  const factory = new Function('document', 'window', 'Node', 'ResizeObserver', 'MutationObserver', 'fetch', 'AbortController', 'setTimeout', 'clearTimeout', ...Object.keys(model), `${view}\nreturn { poll, history, events };`);
  h.api = factory(document, { addEventListener() {} }, Element, Observer, Observer, fetch, class { constructor() { this.signal = {}; } abort() {} }, () => 1, () => {}, ...Object.values(model));
  return h;
}

async function flush() { for (let i = 0; i < 8; i++) await Promise.resolve(); }

test('lost connection and pause clear current metrics while keeping recorded history', async () => {
  const h = harness(); await flush();
  assert.equal(h.nodes.get('connectionState').dataset.state, 'live');
  assert.match(h.nodes.get('cpuValue').textContent, /20.0/);
  assert.equal(h.api.history.length, 1);
  h.nodes.get('pauseButton').click();
  assert.equal(h.nodes.get('cpuValue').textContent, '—');
  assert.equal(h.nodes.get('markButton').disabled, true);
  assert.equal(h.api.history.length, 1);
  h.nodes.get('pauseButton').click(); await flush();
  assert.equal(h.nodes.get('connectionState').dataset.state, 'live');
  h.fail = true; await h.api.poll();
  assert.equal(h.nodes.get('cpuValue').textContent, '—');
  assert.equal(h.nodes.get('sensorRows').textContent, '연결 끊김');
  assert.equal(h.nodes.get('exportButton').disabled, false);
  assert.equal(h.api.history.length, 2);
});

test('saving a baseline waits for later samples and handles settings text literally', async () => {
  const h = harness(); await flush();
  for (let i = 0; i < 10; i++) await h.api.poll();
  assert.equal(h.nodes.get('baselineButton').disabled, false);
  h.document.getElementById('experimentNote').value = '<img onerror=alert(1)> 720p';
  h.nodes.get('baselineButton').click();
  assert.equal(h.api.events.length, 1);
  assert.match(h.nodes.get('baselineLabel').textContent, /<img onerror=alert\(1\)>/);
  assert.match(h.nodes.get('comparisonStatus').textContent, /기다리는 중/);
  for (let i = 0; i < 10; i++) await h.api.poll();
  assert.match(h.nodes.get('comparisonStatus').textContent, /서로 겹치지 않는/);
  h.document.hidden = true; h.document.listeners.visibilitychange();
  assert.equal(h.nodes.get('gpuValue').textContent, '—');
  const calls = h.calls; await h.api.poll(); assert.equal(h.calls, calls);
});
