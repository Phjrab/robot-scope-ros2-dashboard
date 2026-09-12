// Spatial authoring only: no Mission, Navigation, or Control mutation surface.
const NS = 'http://www.w3.org/2000/svg';
const LIMIT = 4096;
export function gridToWorld(map, x, y) {
  const [ox, oy, yaw] = map.origin; const dx = x * map.resolution; const dy = (map.height - y) * map.resolution;
  return { x: ox + dx * Math.cos(yaw) - dy * Math.sin(yaw), y: oy + dx * Math.sin(yaw) + dy * Math.cos(yaw) };
}
export function worldToGrid(map, point) {
  const [ox, oy, yaw] = map.origin; const dx = point.x - ox; const dy = point.y - oy;
  return { x: (dx * Math.cos(yaw) + dy * Math.sin(yaw)) / map.resolution, y: map.height - (-dx * Math.sin(yaw) + dy * Math.cos(yaw)) / map.resolution };
}
export function familyPins(map, document) {
  const matches = (document.families || []).filter((family) => family.occupancy?.map_id === map.map_id && family.occupancy?.map_revision === map.revision);
  if (document.map_id !== map.map_id || document.map_revision !== map.revision || matches.length !== 1) throw new Error('이 지도와 일치하는 3D/2D 지도 연결 정보가 필요합니다. Saved Maps에서 확인하세요.');
  const f = matches[0];
  return { family_id: f.family_id, family_revision: f.family_revision, pcd_map_id: f.source.pcd_map_id, pcd_revision: f.source.pcd_revision, occupancy_map_id: map.map_id, occupancy_revision: map.revision };
}
export function pathPoses(points, finalYawDegrees) {
  if (!points.length || points.length > LIMIT || !Number.isFinite(finalYawDegrees) || Math.abs(finalYawDegrees) > 180) throw new Error('경로 점 수 또는 마지막 방향이 올바르지 않습니다.');
  return points.map((point, index) => {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) throw new Error('확인되지 않은 좌표입니다.');
    const next = points[index + 1];
    return { ...point, yaw: next ? Math.atan2(next.y - point.y, next.x - point.x) : finalYawDegrees * Math.PI / 180 };
  });
}
export function createSpatialEditor(host, client, doc = globalThis.document) {
  const make = (tag, text = '') => { const node = doc.createElement(tag); node.textContent = text; return node; };
  const svgNode = (tag, attrs = {}) => { const node = doc.createElementNS(NS, tag); for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value)); return node; };
  const root = make('details'); root.className = 'spatial-route-editor';
  root.append(make('summary', '세부 경로 편집 · 실제 저장 지도'));
  const note = make('p', '지도를 클릭해 연결하거나 누른 채 선을 그리세요. 제약 모드는 저장·미리보기 단계이며 아직 주행에 적용되지 않습니다.');
  const toolbar = make('div'); toolbar.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;align-items:center';
  const select = (label, entries) => { const wrapper = make('label', label + ' '); const node = make('select'); node.setAttribute('aria-label', label); for (const [value, text] of entries) { const option = make('option', text); option.value = value; node.append(option); } wrapper.append(node); toolbar.append(wrapper); return node; };
  const button = (label, action) => { const node = make('button', label); node.type = 'button'; node.addEventListener('click', () => run(action)); toolbar.append(node); return node; };
  const input = (label, type, value, min, max, step) => { const wrapper = make('label', label + ' '); const node = make('input'); node.type = type; node.value = value; node.setAttribute('aria-label', label); if (min != null) { node.min = min; node.max = max; node.step = step; } node.style.width = type === 'text' ? '160px' : '85px'; wrapper.append(node); toolbar.append(wrapper); return node; };
  const mapSelect = select('편집 지도', []);
  button('지도 목록 새로고침', async () => {
    const payload = await client.spatialMaps(); if (destroyed) return;
    const previous = mapSelect.value; mapSelect.replaceChildren();
    for (const map of payload.maps || []) if (map.kind === 'occupancy2d') { const o = make('option', map.name); o.value = map.id; mapSelect.append(o); }
    if ([...mapSelect.options].some((o) => o.value === previous)) mapSelect.value = previous;
    message.textContent = '지도를 선택한 뒤 불러오세요.';
  });
  button('지도 불러오기', async () => { if (!discard()) return; await loadMap(mapSelect.value); reset(); });
  const name = input('경로 이름', 'text', '새 세부 경로'); name.maxLength = 64;
  const mode = select('경로 제약', [['FLEXIBLE', '경유점 중심'], ['CORRIDOR', '경로 폭 제한 · 편집용'], ['STRICT', '선 추종 · 편집용']]);
  const width = input('통로 전체 폭(m)', 'number', '0.8', '0.1', '5', '0.1');
  const blocked = select('막혔을 때', [['STOP', '정지'], ['REQUIRE_OPERATOR', '운영자 확인'], ['REPLAN', '재계획 · 경유점 모드']]);
  const tool = select('편집 도구', [['DRAW', '클릭 / 이어 그리기'], ['EDIT', '점 이동'], ['DELETE', '점 삭제'], ['PAN', '지도 이동']]);
  const yaw = input('마지막 방향(°)', 'number', '0', '-180', '180', '0.1');
  button('되돌리기', () => { if (history.length) { points = history.pop(); dirty = true; invalidate(); draw(); } });
  button('경로 비우기', () => { remember(); points = []; invalidate(); draw(); });
  button('전체 보기', () => { if (map) { view = [0, 0, map.width, map.height]; draw(); } });
  button('선택한 추천 경로 가져오기', () => {
    const route = state?.selectedRoute;
    if (!map || !route || route.map_id !== map.map_id || route.map_revision !== map.revision) throw new Error('같은 저장 지도에서 추천 경로를 먼저 선택하세요.');
    if (!discard()) return;
    const imported = [];
    for (const segment of route.segments) for (const point of segment.polyline) {
      const last = imported.at(-1); if (!last || Math.hypot(last.x - point.x, last.y - point.y) > 0.001) imported.push({ x: point.x, y: point.y });
    }
    if (!imported.length || imported.length > LIMIT) throw new Error('가져올 경로 점은 1~4096개여야 합니다.');
    reset(); points = imported; dirty = true; draw(); message.textContent = '추천 경로의 선을 가져왔습니다. 주문·방문 의미는 기존 Planner에 유지되며 미션 변환은 후속 단계입니다.';
  });
  const routeSelect = select('저장 경로', []);
  async function listRoutes() {
    const payload = await client.spatialRoutes(); if (destroyed) return;
    routeSelect.replaceChildren();
    for (const route of payload.routes || []) { const o = make('option', route.label); o.value = route.route_id; routeSelect.append(o); }
  }
  button('경로 목록', listRoutes);
  button('경로 불러오기', async () => {
    if (!discard()) return;
    const result = await client.spatialRoute(routeSelect.value); if (destroyed) return;
    await loadMap(result.route.map_family.occupancy_map_id);
    if (Object.keys(pins).some((key) => pins[key] !== result.route.map_family[key])) throw new Error('저장 경로의 지도 버전이 달라 불러올 수 없습니다.');
    saved = result.route; points = saved.poses.map((p) => ({ ...p })); history = []; dirty = false;
    name.value = saved.label; mode.value = saved.policy.mode; width.value = saved.policy.corridor_width_m; blocked.value = saved.policy.blocked_behavior;
    yaw.value = String(saved.poses.at(-1).yaw * 180 / Math.PI); validation = result.validation; draw();
    message.textContent = '저장 경로를 불러왔습니다. 검사 결과는 저장 당시 기준입니다. 수정 후 저장하면 다시 검사합니다.';
  });
  async function save(copy) {
    if (!map || !pins) throw new Error('연결 정보가 있는 저장 지도를 먼저 불러오세요.');
    const corridor = Number(width.value);
    if (!Number.isFinite(corridor) || corridor < 0.1 || corridor > 5) throw new Error('통로 폭은 0.1~5m입니다.');
    if (mode.value !== 'FLEXIBLE' && blocked.value === 'REPLAN') throw new Error('폭 제한·선 추종 모드에서는 정지 또는 운영자 확인을 선택하세요.');
    const payload = { label: name.value.trim(), map_family: pins, authoring_source: 'POINT_CLICK', policy: { mode: mode.value, corridor_width_m: corridor, blocked_behavior: blocked.value }, poses: pathPoses(points, Number(yaw.value)) };
    if (!payload.label) throw new Error('경로 이름을 입력하세요.');
    const result = await client.saveSpatialRoute(payload, !copy ? saved : null); if (destroyed) return;
    saved = result.route; validation = result.validation; dirty = false; draw();
    message.textContent = validation.valid ? '경로 저장 및 지도 검사 통과. 실행 기능은 아직 연결되지 않았습니다.' : `초안 저장됨 · 지도 검사 실패 ${validation.violation_count}건. 빨간 표시를 수정하세요. 실행할 수 없습니다.`;
  }
  button('검사 후 저장', () => save(false)); button('새 경로로 저장', () => save(true));
  const canvas = svgNode('svg', { viewBox: '0 0 640 400', role: 'img', 'aria-label': '저장 지도 경로 편집' }); canvas.style.cssText = 'width:100%;height:420px;background:#18212d;touch-action:none;display:block';
  const message = make('p', '지도 목록을 불러와 시작하세요.'); message.setAttribute('role', 'status');
  const count = make('p'); root.append(note, toolbar, canvas, count, message); host.append(root);
  let state = null, map = null, pins = null, background = '', annotations = null, points = [], history = [], view = [0, 0, 640, 400], saved = null, validation = null, dirty = false, busy = false, destroyed = false, gesture = null, contextEpoch = 0;
  const allowed = () => !destroyed && state?.context === 'SAVED_OCCUPANCY';
  const discard = () => !dirty || globalThis.confirm?.('편집 중인 경로를 버리고 불러올까요?') === true;
  function invalidate() { validation = null; dirty = true; message.textContent = '수정됨 · 저장 시 전체 경로와 지도·주석 버전을 다시 검사합니다.'; }
  function remember() { history.push(points.map((p) => ({ ...p }))); if (history.length > 30) history.shift(); dirty = true; }
  function reset() { points = []; history = []; saved = null; validation = null; dirty = false; draw(); }
  async function run(action) {
    if (busy || !allowed()) return; busy = true; refreshDisabled();
    try { await action(); } catch (error) { if (!destroyed) message.textContent = error.message; }
    finally { busy = false; refreshDisabled(); }
  }
  function refreshDisabled() { for (const node of toolbar.querySelectorAll('button,input,select')) node.disabled = busy || !allowed(); }
  async function loadMap(id) {
    if (!/^[0-9a-f]{24}$/.test(id)) throw new Error('저장 지도를 선택하세요.');
    const epoch = contextEpoch;
    const result = await client.spatialMap(id);
    if (destroyed || epoch !== contextEpoch || !allowed()) throw new Error('지도 컨텍스트가 변경되었습니다. 다시 불러오세요.');
    const data = result.data; const family = familyPins(data, result.family);
    if (data.kind !== 'occupancy2d' || data.frame_id !== 'map' || !Number.isInteger(data.width) || !Number.isInteger(data.height) || data.width < 1 || data.height < 1 || data.width * data.height > 16000000 || !Number.isFinite(data.resolution) || data.resolution <= 0 || !Array.isArray(data.origin) || data.origin.length !== 3 || !data.origin.every(Number.isFinite)) throw new Error('지원하지 않는 지도 형식 또는 크기입니다.');
    if (result.annotations.map_id !== data.map_id || result.annotations.map_revision !== data.revision) throw new Error('지도와 주석 버전이 다릅니다.');
    const bytes = atob(data.data_b64); if (bytes.length !== data.width * data.height) throw new Error('지도 셀 수가 일치하지 않습니다.');
    const imageCanvas = doc.createElement('canvas'); imageCanvas.width = data.width; imageCanvas.height = data.height;
    const ctx = imageCanvas.getContext('2d'); const image = ctx.createImageData(data.width, data.height);
    for (let y = 0; y < data.height; y++) for (let x = 0; x < data.width; x++) {
      const cell = bytes.charCodeAt(y * data.width + x); const offset = ((data.height - y - 1) * data.width + x) * 4; const shade = cell === 255 ? 110 : cell === 0 ? 235 : 25;
      image.data.set([shade, shade, shade, 255], offset);
    }
    ctx.putImageData(image, 0, 0); const nextBackground = imageCanvas.toDataURL();
    map = data; pins = family; annotations = result.annotations; background = nextBackground; view = [0, 0, map.width, map.height]; reset();
    message.textContent = `지도 ${data.name || data.map_id} · 클릭 또는 드래그로 경로를 그리세요. 휠 확대, 지도 이동 도구를 사용할 수 있습니다.`;
  }
  function draw() {
    canvas.setAttribute('viewBox', view.join(' ')); canvas.replaceChildren();
    count.textContent = `${points.length} / ${LIMIT}점${dirty ? ' · 저장 전' : ''}`;
    if (!map) return;
    canvas.append(svgNode('image', { href: background, width: map.width, height: map.height, 'pointer-events': 'none' }));
    const scale = Math.max(view[2], view[3]) / 500;
    for (const polygon of annotations?.polygons || []) {
      const shape = (polygon.vertices || []).map((p) => { const c = worldToGrid(map, p); return `${c.x},${c.y}`; }).join(' ');
      const color = polygon.type === 'KEEP_OUT' ? '#fa4455' : '#ffb938'; canvas.append(svgNode('polygon', { points: shape, fill: color, 'fill-opacity': 0.2, stroke: color, 'stroke-width': scale }));
    }
    for (const p of annotations?.points || []) {
      const c = worldToGrid(map, p.pose || p); canvas.append(svgNode('circle', { cx: c.x, cy: c.y, r: 3 * scale, fill: '#9b55ef' }));
      const label = svgNode('text', { x: c.x + 4 * scale, y: c.y, 'font-size': 10 * scale, fill: '#672cb6' }); label.textContent = p.name; canvas.append(label);
    }
    const coordinates = points.map((p) => worldToGrid(map, p)); const line = coordinates.map((p) => `${p.x},${p.y}`).join(' ');
    if (mode.value === 'CORRIDOR') canvas.append(svgNode('polyline', { points: line, fill: 'none', stroke: '#00b6e6', 'stroke-opacity': 0.2, 'stroke-width': Math.max(0.1, Math.min(5, Number(width.value) || 0.8)) / map.resolution, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    canvas.append(svgNode('polyline', { points: line, fill: 'none', stroke: '#008eeb', 'stroke-width': 2 * scale }));
    coordinates.forEach((p, index) => canvas.append(svgNode('circle', { cx: p.x, cy: p.y, r: 3 * scale, fill: '#008eeb', 'data-point-index': index })));
    if (points.length) {
      const p = coordinates.at(-1); const theta = Number(yaw.value) * Math.PI / 180 - map.origin[2];
      canvas.append(svgNode('line', { x1: p.x, y1: p.y, x2: p.x + 18 * scale * Math.cos(theta), y2: p.y - 18 * scale * Math.sin(theta), stroke: '#13a450', 'stroke-width': 4 * scale }));
    }
    for (const violation of validation?.violations || []) { const c = worldToGrid(map, violation); const marker = svgNode('circle', { cx: c.x, cy: c.y, r: 5 * scale, fill: 'none', stroke: '#f22', 'stroke-width': 2 * scale }); const title = svgNode('title'); title.textContent = violation.kind; marker.append(title); canvas.append(marker); }
  }
  function location(event) { const matrix = canvas.getScreenCTM(); if (!matrix) return null; const p = canvas.createSVGPoint(); p.x = event.clientX; p.y = event.clientY; return p.matrixTransform(matrix.inverse()); }
  function appendPoint(p) {
    if (p.x < 0 || p.y < 0 || p.x >= map.width || p.y >= map.height) return;
    const world = gridToWorld(map, p.x, p.y); const last = points.at(-1);
    if (last && Math.hypot(last.x - world.x, last.y - world.y) < Math.max(map.resolution, 0.03)) return;
    if (points.length >= LIMIT) { message.textContent = '최대 4096점입니다. 점을 삭제하거나 경로를 나누세요.'; return; }
    points.push(world); invalidate(); draw();
  }
  canvas.addEventListener('pointerdown', (event) => {
    if (busy || !allowed() || !map || event.button !== 0) return;
    const p = location(event); if (!p) return;
    const index = event.target.getAttribute('data-point-index');
    gesture = { id: event.pointerId, tool: tool.value, index: index == null ? -1 : Number(index), start: p, view: [...view], before: points.map((point) => ({ ...point })) };
    canvas.setPointerCapture(event.pointerId);
    if (tool.value === 'PAN') return;
    remember();
    if (tool.value === 'DRAW') appendPoint(p);
    if (tool.value === 'DELETE' && gesture.index >= 0) { points.splice(gesture.index, 1); invalidate(); draw(); }
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!gesture || gesture.id !== event.pointerId || busy || !allowed()) return;
    const p = location(event); if (!p) return;
    if (gesture.tool === 'DRAW') appendPoint(p);
    if (gesture.tool === 'EDIT' && gesture.index >= 0 && p.x >= 0 && p.y >= 0 && p.x < map.width && p.y < map.height) { points[gesture.index] = { ...points[gesture.index], ...gridToWorld(map, p.x, p.y) }; invalidate(); draw(); }
    if (gesture.tool === 'PAN') { view[0] += gesture.start.x - p.x; view[1] += gesture.start.y - p.y; draw(); }
  });
  canvas.addEventListener('pointerup', () => { gesture = null; });
  canvas.addEventListener('pointercancel', () => { if (gesture) { points = gesture.before; gesture = null; invalidate(); draw(); } });
  canvas.addEventListener('wheel', (event) => {
    if (!map || busy || !allowed() || gesture) return; event.preventDefault(); const p = location(event); if (!p) return;
    const factor = event.deltaY > 0 ? 1.15 : 1 / 1.15; const next = view[2] * factor;
    if (next < map.width / 50 || next > map.width * 3) return;
    view = [p.x + (view[0] - p.x) * factor, p.y + (view[1] - p.y) * factor, next, view[3] * factor]; draw();
  }, { passive: false });
  for (const node of [name, mode, width, blocked, yaw]) node.addEventListener('input', () => { invalidate(); draw(); });
  return Object.freeze({
    render(next) {
      const changed = state && state.context !== next.context; state = next;
      if (changed) { contextEpoch++; gesture = null; }
      root.hidden = !allowed(); refreshDisabled();
    },
    destroy() { destroyed = true; contextEpoch++; root.remove(); },
  });
}
