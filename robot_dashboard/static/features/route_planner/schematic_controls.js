import { createCompetitionMapView } from './competition_map_view.js';

const MAX_VENUE_APPROACHES = 2;

function accessEdgePrefix(venueId) { return `ACCESS_${venueId}`; }

export function connectedApproachNodeIds(layout, binding) {
  const nodes = Array.isArray(layout?.nodes) ? layout.nodes : [];
  const edges = Array.isArray(layout?.edges) ? layout.edges : [];
  const venueNode = nodes.find((node) => node.venue_id === binding?.venue_id);
  const result = [];
  const add = (node) => {
    if (!node || node.id === venueNode?.id || node.venue_id || result.includes(node.id)) return;
    result.push(node.id);
  };
  const primary = nodes.find((node) => binding?.approach_point_px
    && node.x_px === binding.approach_point_px[0] && node.y_px === binding.approach_point_px[1]);
  add(primary);
  if (venueNode) {
    edges
      .filter((edge) => (edge.id === accessEdgePrefix(binding.venue_id) || edge.id.startsWith(`${accessEdgePrefix(binding.venue_id)}_`))
        && (edge.from === venueNode.id || edge.to === venueNode.id))
      .sort((left, right) => left.id.localeCompare(right.id))
      .forEach((edge) => add(nodes.find((node) => node.id === (edge.from === venueNode.id ? edge.to : edge.from))));
  }
  return result.slice(0, MAX_VENUE_APPROACHES);
}

// Shared by the dashboard and Cockpit panel; no timer, fetch, ROS or control owner.
export function createSchematicControls(host, client, doc = globalThis.document) {
  const el = (tag, text = '') => { const n = doc.createElement(tag); n.textContent = text; return n; };
  const select = (label, values) => { const n = el('select'); n.setAttribute('aria-label', label); for (const [v, t] of values) { const o = el('option', t); o.value = v; n.append(o); } return n; };
  const input = (label, value = '', type = 'text') => { const n = el('input'); n.setAttribute('aria-label', label); n.type = type; n.value = value ?? ''; if (type === 'number') n.step = 'any'; return n; };
  const field = (label, node) => { const n = el('label', label); n.append(node); return n; };
  const button = (label, fn) => { const n = el('button', label); n.type = 'button'; n.onclick = fn; return n; };
  const root = el('section'); root.className = 'schematic-controls';
  const context = select('지도 컨텍스트', [['SAVED_OCCUPANCY', '저장 지도 · 기존 검증 유지'], ['DEMO', 'DEMO · 예시 도식 / 현장 아님'], ['FIELD', 'FIELD · 현장 도식 / 승인 필요']]);
  const body = el('div'); body.hidden = true;
  const banner = el('strong'); banner.setAttribute('role', 'status');
  const error = el('p'); error.setAttribute('role', 'alert');
  const provenance = el('p', 'MANUAL_GUIDANCE · MANUAL_STEP · 거리 미보정 / ETA 미확인 · 실제 위치 미연결 / 자동추적 OFF · LIVE_POSE_NOT_CONFIGURED');
  const warning = el('p', '신호 UNKNOWN · 운영자 기록은 통과 허가가 아닙니다. 현장 신호·보행자를 직접 확인하세요. 원본 그림의 초록색은 현재 신호가 아닙니다. 안내 종료는 로봇 정지가 아닙니다.');
  const mapHost = el('div'); const click = el('p', '지도 클릭은 도식 좌표 확인만 합니다. 현장 측정값이 아닙니다.');
  const planning = el('section'); const start = select('도식 출발 장소', [['', '출발 장소를 선택하세요']]);
  const candidates = el('div'); const guide = el('div'); const steps = el('ol');
  const calculate = button('도식 추천 경로 계산', () => command('RECOMMEND'));
  planning.append(field('출발 장소', start), calculate, candidates, guide, steps);
  const setup = el('details'); setup.append(el('summary', '현장 배치·연결 설정 / 별도 승인'));
  const setupBody = el('div'); setup.append(setupBody);
  body.append(banner, error, provenance, warning, mapHost, click, planning, setup);
  const offline = el('details'); offline.append(el('summary', '읽기 전용 참고 지도 (서버 연결 없이 보기)'));
  const offlineHost = el('div'); offline.append(offlineHost);
  let referenceViewer = null;
  offline.ontoggle = () => { if (offline.open && !referenceViewer) { referenceViewer = createCompetitionMapView(offlineHost, { document: doc }); referenceViewer.render({}); } };
  root.append(field('지도 컨텍스트', context), offline, body); host.append(root);
  let current = null; let viewer = null; let layoutPin = ''; let lastContext = ''; let startPin = '';
  const command = (action, data = {}) => client.schematicCommand(action, data);
  context.onchange = () => command('CONTEXT', { context: context.value });
  start.onchange = () => command('START_POINT', { node_id: start.value });
  const numberOrNull = (v) => v.trim() === '' ? null : Number(v);

  function buildSetup(s) {
    setupBody.replaceChildren();
    setupBody.append(el('p', '좌표는 schematic_px (y↓), yaw는 라디안 −π~π입니다. 빈칸은 미확인입니다. DEMO 좌표는 FIELD로 복사되지 않습니다. 저장하면 기존 승인·추천이 해제됩니다.'));
    const zoneFields = {};
    const zones = el('div'); zones.className = 'schematic-grid';
    for (const corner of ['A', 'B', 'C', 'D']) {
      const n = select(`${corner} 공식 구역`, [['', '미확인'], ...[1, 2, 3, 4].map((i) => [`ZONE${i}`, `ZONE${i}`])]); n.value = s.layout.corner_zones[corner] || ''; zoneFields[corner] = n; zones.append(field(`코너 ${corner}`, n));
    }
    setupBody.append(zones);
    const rows = [];
    for (const b of s.layout.bindings) {
      const row = el('fieldset'); row.append(el('legend', b.venue_id)); row.className = 'schematic-grid';
      const corner = select(`${b.venue_id} 코너`, [['', '미확인'], ...['A', 'B', 'C', 'D'].map((c) => [c, c])]); corner.value = b.corner || '';
      const approachChoices = [['', '미확인'], ...s.layout.nodes.filter((n) => !n.venue_id).map((n) => [n.id, `${n.label} (${n.id})`])];
      const approachIds = connectedApproachNodeIds(s.layout, b);
      const approach = select(`${b.venue_id} 접근 노드`, approachChoices); approach.value = approachIds[0] || '';
      const alternateApproach = select(`${b.venue_id} 추가 접근 노드`, [['', '사용 안 함'], ...approachChoices.slice(1)]); alternateApproach.value = approachIds[1] || '';
      const x = input(`${b.venue_id} 정지 x_px`, b.dock_point_px?.[0], 'number'); const y = input(`${b.venue_id} 정지 y_px`, b.dock_point_px?.[1], 'number'); const yaw = input(`${b.venue_id} yaw_rad`, b.dock_yaw_rad, 'number');
      row.append(field('코너', corner), field('접근점 1 (연결 노드)', approach), field('접근점 2 (선택)', alternateApproach), field('정지 x_px', x), field('정지 y_px', y), field('yaw_rad', yaw)); rows.push({ b, corner, approach, alternateApproach, x, y, yaw }); setupBody.append(row);
    }
    const graph = el('textarea'); graph.setAttribute('aria-label', '도식 노드·통행 연결 JSON'); graph.rows = 12;
    graph.value = JSON.stringify({ nodes: s.layout.nodes, edges: s.layout.edges }, null, 2);
    const advanced = el('details'); advanced.append(el('summary', '통행 연결 상세 편집 (nodes / edges / polyline_px)'), el('p', 'enabled=false: 폐쇄, bidirectional=false: 단방향. 접근·정지 연결은 입력 좌표로 생성하고 서버가 차도 침범을 거부합니다. 경유 노드·우회선은 이 JSON에서 명시적으로 편집하세요.'), graph);
    const rules = input('조종 경기 음식별 사전준비 2개 규칙 확인', '', 'checkbox'); rules.checked = s.layout.rules_profile === 'MANUAL_PREPARED_2_CONFIRMED';
    const permission = input('주최 측 정적 참고 지도 사용 허용 확인', '', 'checkbox'); permission.checked = s.layout.static_reference_allowed;
    const underpass = input('지하보도 실제 연결 현장 확인', '', 'checkbox'); underpass.checked = s.layout.underpass_verified;
    const save = button('배치·연결 저장 (승인 해제)', async () => {
      try {
        const geometry = JSON.parse(graph.value);
        if (Object.keys(geometry).sort().join(',') !== 'edges,nodes') throw new Error('nodes / edges만 입력하세요');
        const layout = { ...s.layout, ...geometry, corner_zones: Object.fromEntries(Object.entries(zoneFields).map(([c, n]) => [c, n.value || null])),
          rules_profile: rules.checked ? 'MANUAL_PREPARED_2_CONFIRMED' : 'UNCONFIRMED', static_reference_allowed: permission.checked, underpass_verified: underpass.checked };
        layout.bindings = rows.map(({ b, corner, approach, alternateApproach, x, y, yaw }) => {
          if (!approach.value && alternateApproach.value) throw new Error(`${b.venue_id}: 접근점 1을 먼저 선택하세요`);
          if (approach.value && approach.value === alternateApproach.value) throw new Error(`${b.venue_id}: 서로 다른 접근 노드를 선택하세요`);
          const approachNodes = [approach.value, alternateApproach.value].filter(Boolean).map((id) => layout.nodes.find((n) => n.id === id));
          if (approachNodes.some((node) => !node || node.venue_id)) throw new Error(`${b.venue_id}: 접근점은 통행 노드여야 합니다`);
          const px = numberOrNull(x.value); const py = numberOrNull(y.value);
          if ((px === null) !== (py === null)) throw new Error(`${b.venue_id}: x와 y를 함께 입력하세요`);
          const dock = px === null ? null : [px, py];
          const prefix = accessEdgePrefix(b.venue_id);
          layout.edges = layout.edges.filter((e) => e.id !== prefix && !e.id.startsWith(`${prefix}_`));
          if (dock && approachNodes.length) {
            let n = layout.nodes.find((n) => n.venue_id === b.venue_id);
            if (!n) { n = { id: b.venue_id, label: b.venue_id, role: ['DOMINO', 'HANSOT', 'EDIYA'].includes(b.venue_id) ? 'RESTAURANT' : 'DESTINATION', venue_id: b.venue_id }; layout.nodes.push(n); }
            n.x_px = px; n.y_px = py;
            approachNodes.forEach((a, index) => layout.edges.push({ id: `${prefix}_${index + 1}`, from: a.id, to: n.id, type: 'WALKWAY', enabled: true, bidirectional: true, polyline_px: [[a.x_px, a.y_px], dock] }));
          }
          const primary = approachNodes[0];
          return { venue_id: b.venue_id, corner: corner.value || null, approach_point_px: primary ? [primary.x_px, primary.y_px] : null, dock_point_px: dock, dock_yaw_rad: numberOrNull(yaw.value) };
        });
        await command('LAYOUT', { layout });
      } catch (e) { error.textContent = e.message; }
    });
    const reviewer = input('현장 배치 확인자 이름'); reviewer.maxLength = 64;
    const approve = button('현재 FIELD revision 승인', () => command('APPROVE', { reviewer: reviewer.value, layout_revision: s.layout_revision }));
    approve.disabled = s.usage !== 'FIELD' || s.missing.length > 0;
    setupBody.append(advanced, field('음식별 사전준비 2개 규칙을 확인했습니다 (20초 추정 사용 안 함)', rules), field('주최 측 정적 참고 지도 사용 허용을 확인했습니다', permission), field('지하보도 실제 연결을 확인했습니다 (edge 활성화 별도)', underpass), save,
      el('p', s.missing.length ? `미확인: ${s.missing.join(' · ')}` : '필수 입력 완료 · 별도 확인자 승인 필요'), field('확인자', reviewer), approve);
  }

  function render(state) {
    current = state; const s = state.schematic; const active = s?.map_kind === 'SCHEMATIC_MANUAL';
    context.value = s?.context || 'SAVED_OCCUPANCY'; context.disabled = state.busy || s?.available !== true || Boolean(s?.guidance?.active);
    body.hidden = !active;
    if (!active) return;
    if (!viewer) viewer = createCompetitionMapView(mapHost, { document: doc, onPoint: (p) => { if (p) click.textContent = `도식 클릭 x_px=${p.x.toFixed(1)}, y_px=${p.y.toFixed(1)} · 선택 참고만 / 현장 측정 아님`; } });
    viewer.render(s);
    banner.textContent = `${s.usage === 'DEMO' ? 'DEMO — 예시 배치 · 현장 아님' : `FIELD — ${s.field_approved ? '승인됨' : '미승인 / 시작 차단'}`} · ${s.available ? '서버 연결됨' : '연결 끊김 · 마지막 참고 화면'} · ${s.state}`;
    error.textContent = state.error || '';
    const editPin = `${s.context}:${s.layout_revision}`;
    if (editPin !== layoutPin) { layoutPin = editPin; buildSetup(s); }
    if (s.context !== lastContext) { lastContext = s.context; viewer.fit(); }
    setupBody.inert = state.busy || s.guidance.active || !s.available;
    const newStartPin = `${editPin}:${s.start_node_id}`;
    if (startPin !== newStartPin) {
      startPin = newStartPin; start.replaceChildren();
      for (const [value, label] of [['', '출발 장소를 선택하세요'], ...s.layout.nodes.filter((n) => n.role === 'DESTINATION').map((n) => [n.id, n.label])]) { const o = el('option', label); o.value = value; start.append(o); }
      start.value = s.start_node_id || '';
    }
    const disabled = state.busy || !s.available;
    start.disabled = disabled || s.guidance.active;
    calculate.disabled = disabled || s.guidance.active || !s.order?.locked || !s.start_node_id || (s.usage === 'FIELD' && !s.field_approved);
    candidates.replaceChildren();
    for (const r of s.recommendations) {
      const card = el('article'); const selected = r.id === s.selected_route_id;
      card.append(el('strong', `${selected ? '선택됨 · ' : ''}${r.profiles.join(' / ')}`), el('p', `상대 비용 ${r.relative_cost} / 실측 아님 · 거리 미보정 · ETA 미확인`), el('p', r.stops.map((p) => `${p.label} ${p.kind === 'PICKUP' ? '픽업' : '배달'}`).join(' → ')));
      const pick = button('이 도식 경로 선택', () => command('SELECT', { route_id: r.id, route_revision: r.revision })); pick.disabled = disabled || s.guidance.active; card.append(pick); candidates.append(card);
    }
    guide.replaceChildren(); steps.replaceChildren();
    const r = s.recommendations.find((r) => r.id === s.selected_route_id); const g = s.guidance;
    guide.append(el('strong', `수동 기록 ${g.state} · 구간 ${g.current_segment_index}/${r?.segments.length || 0} · 적재 ${g.cargo}/5`), el('p', '운영자 체크 위치 / 센서 위치 아님 · 신호 UNKNOWN'));
    if (!r) return;
    const begin = button('수동 안내 시작 (로봇 동작 없음)', () => command('START', { route_id: r.id, route_revision: r.revision })); begin.disabled = disabled || g.active;
    const end = button('표시 안내 종료 (로봇 정지 아님)', () => command('END')); end.disabled = disabled || !g.active;
    const pending = r.stops.filter((p) => p.after_segment === g.current_segment_index && !(p.kind === 'PICKUP' ? g.completed_pickups : g.completed_dropoffs).includes(p.venue_id));
    const step = button('현재 구간 완료 기록 (통과 허가 아님)', () => client.schematicEvent('STEP')); step.disabled = disabled || !g.active || pending.length > 0 || g.current_segment_index >= r.segments.length;
    guide.append(begin, end, step);
    for (const p of pending) { const n = button(`${p.label} ${p.kind === 'PICKUP' ? '픽업' : '배달'} 확인`, () => client.schematicEvent(p.kind, p.venue_id)); n.disabled = disabled || !g.active; guide.append(n); }
    for (const seg of r.segments) steps.append(el('li', `${seg.index < g.current_segment_index ? '✓' : seg.index === g.current_segment_index ? '현재' : '대기'} · ${seg.label} · ${seg.type === 'CROSSWALK' ? '횡단 대기·현장 확인 필요 / UNKNOWN' : seg.type}`));
  }
  return { render, destroy() { viewer?.destroy(); referenceViewer?.destroy(); root.remove(); } };
}
