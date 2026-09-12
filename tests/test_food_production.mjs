import test from 'node:test';
import assert from 'node:assert/strict';
import { PROVIDED_ORDERS, productionSchedule, productionProgress, createFoodProduction } from '../robot_dashboard/static/features/route_planner/food_production.js';

test('provided eight sheets: restaurant-parallel completion and sequence', () => {
  const schedule = productionSchedule(PROVIDED_ORDERS);
  assert.equal(schedule.reduce((n, p) => n + p.quantity, 0), 31);
  const end = Object.fromEntries(['DOMINO', 'HANSOT', 'EDIYA'].map((id) => [id, Math.max(...schedule.filter((p) => p.restaurant_id === id).map((p) => p.readyAt))]));
  assert.deepEqual(end, { DOMINO: 160, HANSOT: 260, EDIYA: 200 });
  assert.equal(productionProgress(schedule, 19.999).reduce((n, p) => n + p.produced, 0), 0);
  assert.equal(productionProgress(schedule, 20).reduce((n, p) => n + p.produced, 0), 3);
  assert.equal(productionProgress(schedule, 260).reduce((n, p) => n + p.produced, 0), 31);
  assert.equal(productionProgress(schedule, 99999).reduce((n, p) => n + p.produced, 0), 31);
  assert.equal(schedule[0].readyAt, 40);
  assert.equal(schedule[1].readyAt, 20);
});
test('reject malformed clocks and food assignments', () => {
  for (const time of [-1, NaN, Infinity]) assert.throws(() => productionProgress([], time));
  assert.throws(() => productionSchedule([{ lines: [{ restaurant_id: 'DOMINO', menu_id: 'CAFE_LATTE', quantity: 1 }] }]));
  assert.deepEqual(productionProgress([], 0), []);
});

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.value = tag === 'select' ? 'provided' : ''; }
  set textContent(v) { this.text = v; this.children = []; }
  get textContent() { return (this.text || '') + this.children.map((x) => x.textContent).join(' '); }
  setAttribute(k, v) { this[k] = v; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  remove() { this.removed = true; }
}
const doc = { createElement: (tag) => new Element(tag) };
const find = (node, predicate) => predicate(node) ? node : node.children.map((n) => find(n, predicate)).find(Boolean);
test('local clock receipt persistence, reset, corrupt storage and timer disposal', () => {
  const host = new Element('main'); let now = 100000; let tick; let cleared = 0; let raw;
  const storage = { getItem: () => raw, setItem: (_, v) => { raw = v; }, removeItem: () => { raw = null; } };
  const options = { storage, now: () => now, setInterval: (fn) => { tick = fn; return 7; }, clearInterval: (id) => { assert.equal(id, 7); cleared++; } };
  let board = createFoodProduction(host, doc, options);
  let root = host.children.at(-1);
  const button = (text) => find(root, (n) => n.tag === 'button' && n.text === text);
  button('조리 시작').onclick(); now += 20000; tick();
  assert.match(root.textContent, /생성 예상 3\/31개/);
  button('1개 수령 확인').onclick();
  assert.match(root.textContent, /수령 확인 1개/);
  board.destroy(); board = createFoodProduction(host, doc, options); root = host.children.at(-1);
  assert.equal(button('조리 시작').disabled, true);
  assert.match(root.textContent, /수령 확인 1개/);
  now -= 40000; tick(); assert.match(root.textContent, /계산 중단/);
  const check = find(root, (n) => n.type === 'checkbox'); check.checked = true; check.onchange(); button('타이머 초기화 확인').onclick();
  assert.equal(raw, null); board.destroy(); assert.equal(cleared, 2);
  raw = '{bad'; board = createFoodProduction(host, doc, options); root = host.children.at(-1);
  assert.match(root.textContent, /복원하지 못했습니다/); assert.equal(button('조리 시작').disabled, false); board.destroy();
});
