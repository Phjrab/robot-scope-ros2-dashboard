// Advisory-only local clock. No fetch, navigation, mission or control commands.
export const FOOD_NAMES = Object.freeze({ CHEESE_PIZZA: '치즈피자', SUPER_SUPREME: '슈퍼슈프림피자', CHICKEN_MAYO: '치킨마요도시락', SPAM_KIMCHI: '스팸김치도시락', AMERICANO: '아메리카노', CAFE_LATTE: '카페라떼' });
const RESTAURANTS = { DOMINO: '도미노피자', HANSOT: '한솥도시락', EDIYA: '이디야커피' };
const DESTINATIONS = { GANGNAM_POLICE: '강남경찰서', GTX_SITE: 'GTX 공사현장', COEX: '코엑스', WHIMOON: '휘문고등학교' };
const restaurantFor = (menu) => ['CHEESE_PIZZA', 'SUPER_SUPREME'].includes(menu) ? 'DOMINO' : ['CHICKEN_MAYO', 'SPAM_KIMCHI'].includes(menu) ? 'HANSOT' : 'EDIYA';
export const PROVIDED_ORDERS = Object.freeze([
  ['24', 'GANGNAM_POLICE', [['CHEESE_PIZZA', 2], ['CHICKEN_MAYO', 1]]],
  ['61', 'GTX_SITE', [['AMERICANO', 1], ['SPAM_KIMCHI', 1], ['CHICKEN_MAYO', 1]]],
  ['8', 'COEX', [['AMERICANO', 1], ['CAFE_LATTE', 1], ['CHICKEN_MAYO', 1]]],
  ['148', 'GTX_SITE', [['CHEESE_PIZZA', 1], ['AMERICANO', 1], ['SPAM_KIMCHI', 2]]],
  ['145', 'GTX_SITE', [['SUPER_SUPREME', 1], ['CAFE_LATTE', 2], ['SPAM_KIMCHI', 1]]],
  ['121', 'GTX_SITE', [['SUPER_SUPREME', 2], ['SPAM_KIMCHI', 2]]],
  ['185', 'GTX_SITE', [['CHEESE_PIZZA', 1], ['AMERICANO', 2], ['CHICKEN_MAYO', 2]]],
  ['184', 'GTX_SITE', [['CHEESE_PIZZA', 1], ['AMERICANO', 2], ['SPAM_KIMCHI', 2]]],
].map(([number, destination_id, items]) => Object.freeze({ number, destination_id, lines: Object.freeze(items.map(([menu_id, quantity]) => Object.freeze({ menu_id, quantity, restaurant_id: restaurantFor(menu_id) }))) })));

export function productionSchedule(sheets) {
  const counts = {}; const result = [];
  for (const [index, sheet] of (sheets || []).slice(0, 8).entries()) {
    for (const [lineIndex, line] of (sheet.lines || []).slice(0, 5).entries()) {
      if (!RESTAURANTS[line.restaurant_id] || !FOOD_NAMES[line.menu_id] || !Number.isInteger(line.quantity) || line.quantity < 1 || line.quantity > 5 || restaurantFor(line.menu_id) !== line.restaurant_id) throw new TypeError('음식·수량을 확인하세요');
      const before = counts[line.restaurant_id] || 0;
      counts[line.restaurant_id] = before + line.quantity;
      result.push({ ...line, key: `${index}:${lineIndex}`, order: index + 1, number: sheet.number || String(index + 1), destination: sheet.destination_id, startsAt: before * 20, readyAt: (before + line.quantity) * 20 });
    }
  }
  return result;
}

export function productionProgress(schedule, elapsedSeconds) {
  if (!Number.isFinite(elapsedSeconds) || elapsedSeconds < 0) throw new TypeError('invalid elapsed time');
  return schedule.map((line) => {
    const produced = Math.min(line.quantity, Math.max(0, Math.floor((elapsedSeconds - line.startsAt) / 20)));
    return { ...line, produced, nextIn: produced === line.quantity ? null : Math.max(0, Math.ceil(line.startsAt + (produced + 1) * 20 - elapsedSeconds)) };
  });
}

export function createFoodProduction(host, doc = globalThis.document, options = {}) {
  const make = (tag, text = '') => { const el = doc.createElement(tag); el.textContent = text; return el; };
  const root = make('section'); root.className = 'food-production'; root.setAttribute('aria-label', '음식 생성 예상 현황');
  const title = make('h3', '음식 생성 예상 현황 · 조종용');
  const note = make('p', '음식점별 동시 조리 · 각 음식점에서 주문서/메뉴 순서대로 20초에 1개. 실제 생성·수령을 감지하지 않습니다.');
  const source = make('select'); source.setAttribute('aria-label', '조리 주문 선택');
  for (const [value, label] of [['provided', '제공한 8개 주문서'], ['current', '현재 저장 주문']]) { const item = make('option', label); item.value = value; source.append(item); }
  const start = make('button', '조리 시작'); start.type = 'button';
  const reset = make('button', '타이머 초기화 확인'); reset.type = 'button';
  const confirm = make('input'); confirm.type = 'checkbox'; confirm.setAttribute('aria-label', '타이머 초기화 동의');
  const confirmLabel = make('label', '시작 시각·수령 기록 초기화 동의 '); confirmLabel.append(confirm);
  const status = make('p'); status.setAttribute('role', 'status');
  const summary = make('p'); const inventory = make('p'); const rows = make('div'); rows.className = 'food-production-rows';
  root.append(title, note, source, start, confirmLabel, reset, status, summary, inventory, rows); host.append(root);
  const now = options.now || Date.now;
  const storageKey = 'robot-scope.food-production.restaurant-parallel.v1';
  let storage; let storageError = ''; let currentOrder = null; let session = null; let lastSecond = -1;
  try { storage = options.storage || globalThis.localStorage; const raw = storage?.getItem(storageKey); if (raw) {
    const value = JSON.parse(raw);
    if (value.version !== 1 || !['provided', 'current'].includes(value.source) || !Number.isFinite(value.startedAt) || value.startedAt < 0 || !Array.isArray(value.sheets) || value.sheets.length < 1 || value.sheets.length > 8) throw new Error('invalid session');
    const restored = productionSchedule(value.sheets);
    if (!restored.length || !value.received || typeof value.received !== 'object' || Array.isArray(value.received)
      || Object.entries(value.received).some(([key, count]) => !Number.isInteger(count) || count < 0 || count > (restored.find((p) => p.key === key)?.quantity ?? -1))) throw new Error('invalid receipts');
    session = value; source.value = session.source;
  } } catch { storageError = '저장 기록을 복원하지 못했습니다. 자동 시작하지 않습니다.'; }
  const sheets = () => source.value === 'provided' ? PROVIDED_ORDERS : currentOrder?.orders || (currentOrder?.lines?.length ? [{ destination_id: currentOrder.destination_id, lines: currentOrder.lines }] : []);
  function save() { try { storage?.setItem(storageKey, JSON.stringify(session)); storageError = ''; } catch { storageError = '이 브라우저에 저장할 수 없습니다. 새로고침하면 기록이 사라질 수 있습니다.'; } }
  function draw() {
    const elapsed = session ? (now() - session.startedAt) / 1000 : 0;
    const clockInvalid = !Number.isFinite(elapsed) || elapsed < 0;
    const changed = session?.source === 'current' && currentOrder?.revision !== session.orderRevision;
    const invalid = clockInvalid || changed;
    let schedule = []; try { schedule = productionSchedule(session?.sheets || sheets()); } catch { storageError = '주문 형식이 잘못되었습니다.'; }
    start.disabled = Boolean(session) || !schedule.length; source.disabled = Boolean(session); reset.disabled = !confirm.checked;
    status.textContent = `${session ? invalid ? '계산 중단 · 주문 변경/시계 이상. 확인 후 초기화하세요.' : `시작 후 ${Math.floor(elapsed)}초 · 이 브라우저에만 저장` : '시작 대기 · 첫 음식은 시작 20초 후'} ${storageError}`;
    if (invalid) { rows.replaceChildren(); summary.textContent = '예상 수량 미확인'; inventory.textContent = ''; return; }
    const progress = productionProgress(schedule, elapsed);
    const produced = progress.reduce((n, p) => n + p.produced, 0); const total = progress.reduce((n, p) => n + p.quantity, 0);
    summary.textContent = `생성 예상 ${produced}/${total}개 · 전체 준비 ${Math.max(0, ...schedule.map((p) => p.readyAt))}초`;
    inventory.textContent = '미수령 예상: ' + Object.entries(FOOD_NAMES).map(([menu, name]) => {
      const available = progress.filter((p) => p.menu_id === menu).reduce((n, p) => n + p.produced - Math.min(p.produced, Math.max(0, Number(session?.received?.[p.key]) || 0)), 0);
      return `${name} ${available}개`;
    }).join(' · ');
    rows.replaceChildren(...progress.map((p) => {
      const row = make('div'); row.className = 'food-production-row';
      const received = Math.min(p.produced, Math.max(0, Number(session?.received?.[p.key]) || 0));
      const text = make('span', `${p.order}번 (주문 ${p.number}) · ${DESTINATIONS[p.destination] || p.destination || '도착지 미확인'} · ${RESTAURANTS[p.restaurant_id]} · ${FOOD_NAMES[p.menu_id]} ${p.produced}/${p.quantity}개 · ${p.nextIn === null ? '준비 예상 완료' : `다음 생성 ${p.nextIn}초 후`} · 수령 확인 ${received}개`);
      const take = make('button', '1개 수령 확인'); take.type = 'button'; take.disabled = !session || received >= p.produced;
      take.onclick = () => { session.received ||= {}; session.received[p.key] = received + 1; save(); draw(); };
      const undo = make('button', '수령 1개 취소'); undo.type = 'button'; undo.disabled = !session || received < 1;
      undo.onclick = () => { session.received[p.key] = received - 1; save(); draw(); };
      row.append(text, take, undo); return row;
    }));
  }
  start.onclick = () => { if (session || !sheets().length) return; session = { version: 1, source: source.value, orderRevision: currentOrder?.revision || null, sheets: JSON.parse(JSON.stringify(sheets())), startedAt: now(), received: {} }; save(); draw(); };
  reset.onclick = () => { if (!confirm.checked) return; session = null; confirm.checked = false; try { storage?.removeItem(storageKey); } catch { storageError = '저장 기록 초기화 실패'; } draw(); };
  source.onchange = draw; confirm.onchange = draw;
  const timer = (options.setInterval || globalThis.setInterval)(() => { const second = Math.floor(now() / 1000); if (second !== lastSecond) { lastSecond = second; draw(); } }, 250);
  draw();
  return { render(state) { currentOrder = state.order; draw(); }, destroy() { (options.clearInterval || globalThis.clearInterval)(timer); root.remove(); } };
}
