const NS = 'http://www.w3.org/2000/svg';
const BASE = '/static/assets/competition/gangnam2026/';
export function schematicPoint(svg, clientX, clientY) {
  const p = svg.createSVGPoint(); p.x = clientX; p.y = clientY;
  const matrix = svg.getScreenCTM();
  if (!matrix) return null;
  const value = p.matrixTransform(matrix.inverse());
  return { x: value.x, y: value.y };
}
export function createCompetitionMapView(host, { onPoint = () => {}, document: doc = globalThis.document } = {}) {
  const root = doc.createElement('section'); root.className = 'competition-map-view';
  const toolbar = doc.createElement('div');
  const badge = doc.createElement('span'); badge.className = 'competition-map-badge'; toolbar.append(badge);
  const tabs = doc.createElement('select'); tabs.setAttribute('aria-label', '참고 지도 보기');
  for (const [value, label] of [['arena_schematic.svg', '도식 · 실측 아님'], ['arena_p11_original.png', 'p11 원본 조감도'], ['arena_p13_top_original.png', 'p13 원본 평면 참고']]) {
    const opt = doc.createElement('option'); opt.value = value; opt.textContent = label; tabs.append(opt);
  }
  const svg = doc.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 1135 812'); svg.setAttribute('aria-label', '도식 수동 안내 지도'); svg.setAttribute('role', 'img');
  // The supplied asset's geometry is translated (30, 88) inside 1200×960.
  const background = doc.createElementNS(NS, 'image'); background.setAttribute('href', BASE + 'arena_background.svg'); background.setAttribute('x', '-30'); background.setAttribute('y', '-88'); background.setAttribute('width', '1200'); background.setAttribute('height', '960'); svg.append(background);
  const routeLayer = doc.createElementNS(NS, 'g'); const nodeLayer = doc.createElementNS(NS, 'g'); const signalLayer = doc.createElementNS(NS, 'g');
  svg.append(routeLayer, nodeLayer, signalLayer);
  const reference = doc.createElement('img'); reference.alt = '원본 참고 그림 — 그림의 신호는 현재 신호가 아닙니다'; reference.hidden = true;
  const note = doc.createElement('p'); note.textContent = 'schematic_px · y↓ · 중앙 차도 경로 금지 · 신호 UNKNOWN ×8 · 지하보도 참고 OFF · 실제 위치 미연결';
  const legend = doc.createElement('p');
  let box = [0, 0, 1135, 812]; let drag = null; let state = null;
  const fit = () => { box = [0, 0, 1135, 812]; svg.setAttribute('viewBox', box.join(' ')); };
  toolbar.append(tabs);
  for (const [label, factor] of [['확대', 0.8], ['축소', 1.25], ['맞춤 / 초기화', 0]]) {
    const button = doc.createElement('button'); button.type = 'button'; button.textContent = label;
    button.onclick = () => { if (!factor) return fit(); const w = Math.max(100, Math.min(4540, box[2] * factor)); const h = w * 812 / 1135; box = [box[0] + (box[2] - w) / 2, box[1] + (box[3] - h) / 2, w, h]; svg.setAttribute('viewBox', box.join(' ')); }; toolbar.append(button);
  }
  for (const [label, layer] of [['경로', routeLayer], ['장소', nodeLayer], ['신호', signalLayer]]) {
    const field = doc.createElement('label'); const check = doc.createElement('input'); check.type = 'checkbox'; check.checked = true;
    check.onchange = () => { layer.style.display = check.checked ? '' : 'none'; }; field.append(check, label); toolbar.append(field);
  }
  tabs.onchange = () => { const schematic = tabs.value === 'arena_schematic.svg'; svg.hidden = !schematic; svg.style.display = schematic ? '' : 'none'; reference.hidden = schematic; if (!schematic) reference.src = BASE + tabs.value; };
  svg.onpointerdown = (event) => { drag = { x: event.clientX, y: event.clientY, box: [...box] }; svg.setPointerCapture(event.pointerId); };
  svg.onpointermove = (event) => { if (!drag) return; const rect = svg.getBoundingClientRect(); const scale = Math.min(rect.width / drag.box[2], rect.height / drag.box[3]); box = [drag.box[0] - (event.clientX - drag.x) / scale, drag.box[1] - (event.clientY - drag.y) / scale, ...drag.box.slice(2)]; svg.setAttribute('viewBox', box.join(' ')); };
  svg.onpointerup = (event) => { if (drag && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 4) onPoint(schematicPoint(svg, event.clientX, event.clientY)); drag = null; };
  svg.onpointercancel = () => { drag = null; };
  function render(next) {
    state = next; routeLayer.replaceChildren(); nodeLayer.replaceChildren(); signalLayer.replaceChildren();
    badge.textContent = state?.usage === 'DEMO' ? 'DEMO · 예시 배치 / 현장 아님' : state?.usage === 'FIELD' ? `FIELD · ${state.field_approved ? '배치 승인됨' : '미승인'} / 수동 기록 전용` : '참고 그림 · 현장 상태 아님';
    const route = state?.recommendations?.find((r) => r.id === state.selected_route_id);
    for (const segment of route?.segments || []) {
      const line = doc.createElementNS(NS, 'polyline'); line.setAttribute('points', segment.polyline_px.map((p) => p.join(',')).join(' ')); line.setAttribute('fill', 'none'); line.setAttribute('stroke', segment.index === state.guidance?.current_segment_index ? '#ffca62' : '#5adfd5'); line.setAttribute('stroke-width', '7'); routeLayer.append(line);
    }
    let venueIndex = 0; const venueLabels = [];
    for (const n of state?.layout?.nodes || []) {
      const dot = doc.createElementNS(NS, 'circle'); dot.setAttribute('cx', n.x_px); dot.setAttribute('cy', n.y_px); dot.setAttribute('r', '6'); dot.setAttribute('fill', '#65e3db');
      const title = doc.createElementNS(NS, 'title'); title.textContent = n.label; dot.append(title); nodeLayer.append(dot);
      if (n.venue_id) {
        venueIndex += 1; venueLabels.push(`${venueIndex}: ${n.label}`);
        const label = doc.createElementNS(NS, 'text'); label.setAttribute('x', n.x_px + 9); label.setAttribute('y', n.y_px - 8); label.setAttribute('fill', 'white'); label.setAttribute('font-size', '24'); label.textContent = String(venueIndex); nodeLayer.append(label);
      }
    }
    legend.textContent = `${Object.entries(state?.layout?.corner_zones || {}).map(([c,z]) => `${c} ↔ ${z || '미확인'}`).join(' · ')}${venueLabels.length ? ' | ' + venueLabels.join(' · ') : ' · 장소 위치 미확인'}`;
    note.textContent = `schematic_px · y↓ · 중앙 차도 경로 금지 · 신호 UNKNOWN ×8 · 지하보도 ${state?.layout?.edges?.some((e) => e.type === 'UNDERPASS' && e.enabled) ? '설정 연결 (신호 허가 아님)' : '참고 OFF'} · 실제 위치 미연결`;
    for (const [x,y] of [[209,192],[835,192],[932,214],[932,595],[834,617],[209,617],[107,594],[107,214]]) { const dot = doc.createElementNS(NS,'circle'); dot.setAttribute('cx',x); dot.setAttribute('cy',y); dot.setAttribute('r','11'); dot.setAttribute('fill','#697586'); const title=doc.createElementNS(NS,'title'); title.textContent='신호 UNKNOWN · 통과 허가 아님'; dot.append(title); signalLayer.append(dot); }
    const marker = state?.guidance?.operator_point;
    if (marker) { const dot=doc.createElementNS(NS,'circle'); dot.setAttribute('cx',marker[0]); dot.setAttribute('cy',marker[1]); dot.setAttribute('r','13'); dot.setAttribute('fill','#ffca62'); const title=doc.createElementNS(NS,'title'); title.textContent='운영자 체크 위치 / 센서 위치 아님'; dot.append(title); nodeLayer.append(dot); }
  }
  root.append(toolbar, svg, reference, note, legend); host.append(root);
  return { render, fit, destroy() { root.remove(); } };
}
