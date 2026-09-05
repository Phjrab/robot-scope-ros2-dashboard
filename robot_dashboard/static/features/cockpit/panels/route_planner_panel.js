const DESTINATIONS = Object.freeze([
  ['COEX', '코엑스'], ['WHIMOON', '휘문고등학교'], ['GANGNAM_POLICE', '강남경찰서'], ['GTX_SITE', 'GTX 공사현장'],
]);
const RESTAURANTS = Object.freeze([
  ['DOMINO', '도미노피자'], ['HANSOT', '한솥도시락'], ['EDIYA', '이디야커피'],
]);
const MENUS = Object.freeze({
  DOMINO: Object.freeze([['SUPER_SUPREME', '슈퍼슈프림피자'], ['CHEESE_PIZZA', '치즈피자']]),
  HANSOT: Object.freeze([['SPAM_KIMCHI', '스팸김치도시락'], ['CHICKEN_MAYO', '치킨마요도시락']]),
  EDIYA: Object.freeze([['AMERICANO', '아메리카노'], ['CAFE_LATTE', '카페라떼']]),
});

function make(documentValue, name, className = '', text = '') {
  const element = documentValue.createElement(name); element.className = className; element.textContent = text; return element;
}

function option(documentValue, value, label) {
  const item = documentValue.createElement('option'); item.value = value; item.textContent = label; return item;
}

function createRoutePlannerPanelView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const root = make(documentValue, 'section', 'cockpit-route-planner');
  const header = make(documentValue, 'div', 'route-planner-header');
  const status = make(documentValue, 'strong', '', 'ROUTE PLANNER WAITING');
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const pins = make(documentValue, 'span', '', 'MAP — · GRAPH —'); header.append(status, pins);

  const orderSection = make(documentValue, 'section', 'route-planner-order');
  orderSection.append(make(documentValue, 'h3', '', '주문 정보'));
  const labelInput = documentValue.createElement('input'); labelInput.maxLength = 64; labelInput.value = 'Competition order'; labelInput.setAttribute('aria-label', '주문 이름');
  const destination = documentValue.createElement('select'); destination.setAttribute('aria-label', '배송지');
  destination.append(...DESTINATIONS.map(([value, label]) => option(documentValue, value, label)));
  const lines = make(documentValue, 'div', 'route-planner-order-lines');
  const addLine = make(documentValue, 'button', '', '+ 주문 항목'); addLine.type = 'button'; addLine.dataset.routeAction = 'add-line';
  const saveOrder = make(documentValue, 'button', '', '주문 저장'); saveOrder.type = 'button'; saveOrder.dataset.routeAction = 'save-order';
  const lockOrder = make(documentValue, 'button', '', '주문 잠금'); lockOrder.type = 'button'; lockOrder.dataset.routeAction = 'lock-order';
  const orderSummary = make(documentValue, 'small', 'route-planner-order-summary', '총 0개 / 적재 한도 5');
  orderSection.append(labelInput, destination, lines, addLine, orderSummary, saveOrder, lockOrder);

  const planningSection = make(documentValue, 'section', 'route-planner-planning');
  planningSection.append(make(documentValue, 'h3', '', '추천 경로'));
  const startNode = documentValue.createElement('select'); startNode.setAttribute('aria-label', 'Route start node');
  const operationMode = documentValue.createElement('select'); operationMode.setAttribute('aria-label', 'Route operation mode');
  operationMode.append(option(documentValue, 'AUTO_NAV2', '수동 안내 + Mission 호환'), option(documentValue, 'MANUAL_GUIDANCE', '수동 안내 전용'));
  const calculate = make(documentValue, 'button', '', '추천 경로 계산'); calculate.type = 'button'; calculate.dataset.routeAction = 'calculate';
  const cards = make(documentValue, 'div', 'route-planner-cards');
  planningSection.append(startNode, operationMode, calculate, cards);

  const guidance = make(documentValue, 'section', 'route-planner-guidance');
  guidance.setAttribute('aria-label', 'Manual route guidance');
  const guidanceAction = make(documentValue, 'strong', 'route-guidance-action', 'GUIDANCE OFF');
  const guidanceMetrics = make(documentValue, 'div', 'route-guidance-metrics', '선택 경로 없음');
  const requirementState = make(documentValue, 'div', 'route-guidance-requirements', '신호 — · 사람 — · 정렬 — · 도킹 —');
  const confirmations = make(documentValue, 'div', 'route-guidance-confirmations');
  const guidanceButtons = make(documentValue, 'div', 'route-guidance-buttons');
  for (const [action, label] of [['start-guidance', '수동 안내 시작'], ['stop-guidance', '안내 종료'], ['preview', 'NAV2 PREVIEW'], ['export', 'MISSION DRAFT EXPORT']]) {
    const button = make(documentValue, 'button', '', label); button.type = 'button'; button.dataset.routeAction = action; guidanceButtons.append(button);
  }
  const segmentList = make(documentValue, 'ol', 'route-planner-segments');
  const message = make(documentValue, 'small', 'route-planner-message', 'SERVER-AUTHORITATIVE · NO MOTION AUTHORITY');
  guidance.append(guidanceAction, guidanceMetrics, requirementState, confirmations, guidanceButtons, segmentList, message);

  const rehearsalSection = make(documentValue, 'section', 'route-planner-rehearsal'); rehearsalSection.hidden = true;
  const rehearsalBanner = make(documentValue, 'strong', 'route-rehearsal-banner', 'REHEARSAL — VIRTUAL DATA — ROBOT WILL NOT MOVE');
  const scenarioSelect = documentValue.createElement('select'); scenarioSelect.setAttribute('aria-label', 'Rehearsal scenario');
  const rehearsalStart = make(documentValue, 'button', '', 'REHEARSAL 시작'); rehearsalStart.type = 'button'; rehearsalStart.dataset.routeRehearsalAction = 'START';
  const rehearsalControls = make(documentValue, 'div', 'route-rehearsal-controls');
  for (const [action, label] of [['RESET', 'RESET'], ['PLAY', 'PLAY'], ['PAUSE', 'PAUSE'], ['STEP', 'STEP'], ['OFF_ROUTE', 'OFF-ROUTE'], ['EXIT', 'EXIT']]) {
    const button = make(documentValue, 'button', '', label); button.type = 'button'; button.dataset.routeRehearsalAction = action; rehearsalControls.append(button);
  }
  const speed = documentValue.createElement('select'); speed.setAttribute('aria-label', 'Rehearsal speed');
  for (const value of [0.5, 1, 2, 5]) speed.append(option(documentValue, String(value), `${value}x`));
  const timeline = documentValue.createElement('input'); timeline.type = 'range'; timeline.min = '0'; timeline.max = '1'; timeline.step = '1'; timeline.value = '0'; timeline.setAttribute('aria-label', 'Rehearsal timeline');
  const playback = make(documentValue, 'small', 'route-rehearsal-playback', 'PAUSED · 0 / 0 ms');
  const virtualPose = make(documentValue, 'div', 'route-rehearsal-virtual-pose', 'VIRTUAL ROBOT —');
  const advisoryState = make(documentValue, 'div', 'route-rehearsal-advisory', 'ADVISORY —');
  const expectedActual = make(documentValue, 'small', 'route-rehearsal-expected', 'EXPECTED / ACTUAL —');
  const eventList = make(documentValue, 'ol', 'route-rehearsal-events');
  const cargo = make(documentValue, 'div', 'route-rehearsal-cargo');
  const missionDryRun = make(documentValue, 'div', 'route-rehearsal-mission', 'MISSION DRY-RUN —');
  const rehearsalReport = make(documentValue, 'pre', 'route-rehearsal-report');
  const dryRunButton = make(documentValue, 'button', '', 'MISSION DRY-RUN'); dryRunButton.type = 'button'; dryRunButton.dataset.routeRehearsalAction = 'DRY_RUN';
  const reportButton = make(documentValue, 'button', '', 'REPORT JSON / MARKDOWN'); reportButton.type = 'button'; reportButton.dataset.routeRehearsalAction = 'REPORT';
  rehearsalSection.append(make(documentValue, 'h3', '', 'Development / Rehearsal'), rehearsalBanner, scenarioSelect, rehearsalStart, rehearsalControls, speed, timeline, playback, virtualPose, advisoryState, expectedActual, eventList, cargo, missionDryRun, dryRunButton, reportButton, rehearsalReport);
  root.append(header, orderSection, planningSection, guidance, rehearsalSection); options.host.append(root);

  let current = null;
  const lineRows = [];
  let scenarioSignature = '';

  function syncMenus(row) {
    const prior = row.menu.value;
    row.menu.replaceChildren(...(MENUS[row.restaurant.value] || []).map(([value, label]) => option(documentValue, value, label)));
    if ([...row.menu.children].some((item) => item.value === prior)) row.menu.value = prior;
  }

  function addOrderLine(restaurantId = 'HANSOT', menuId = '', quantity = 1) {
    if (lineRows.length >= 5) return;
    const rowRoot = make(documentValue, 'div', 'route-planner-order-line');
    const sequence = make(documentValue, 'span', '', String(lineRows.length + 1));
    const restaurant = documentValue.createElement('select'); restaurant.setAttribute('aria-label', `음식점 ${lineRows.length + 1}`);
    restaurant.append(...RESTAURANTS.map(([value, label]) => option(documentValue, value, label))); restaurant.value = restaurantId;
    const menu = documentValue.createElement('select'); menu.setAttribute('aria-label', `메뉴 ${lineRows.length + 1}`);
    const quantityInput = documentValue.createElement('input'); quantityInput.type = 'number'; quantityInput.min = '1'; quantityInput.max = '5'; quantityInput.value = String(quantity); quantityInput.setAttribute('aria-label', `수량 ${lineRows.length + 1}`);
    const remove = make(documentValue, 'button', '', '×'); remove.type = 'button'; remove.dataset.routeRemoveLine = 'true';
    const row = { root: rowRoot, sequence, restaurant, menu, quantity: quantityInput };
    lineRows.push(row); syncMenus(row); if (menuId) menu.value = menuId;
    restaurant.addEventListener('change', () => { syncMenus(row); renderOrderSummary(); });
    quantityInput.addEventListener('input', renderOrderSummary);
    remove.addEventListener('click', () => { if (lineRows.length <= 2) return; const index = lineRows.indexOf(row); if (index >= 0) lineRows.splice(index, 1); rowRoot.remove(); lineRows.forEach((item, rowIndex) => { item.sequence.textContent = String(rowIndex + 1); }); renderOrderSummary(); });
    rowRoot.append(sequence, restaurant, menu, quantityInput, remove); lines.append(rowRoot); renderOrderSummary();
  }

  function draftPayload(locked = false) {
    return {
      label: labelInput.value.trim() || 'Competition order', destination_id: destination.value, order_started_at: null, locked,
      lines: lineRows.map((row, index) => ({ sequence: index + 1, restaurant_id: row.restaurant.value, menu_id: row.menu.value, quantity: Math.max(1, Math.min(5, Number(row.quantity.value) || 1)) })),
    };
  }

  function renderOrderSummary() {
    const total = lineRows.reduce((sum, row) => sum + Math.max(1, Math.min(5, Number(row.quantity.value) || 1)), 0);
    const restaurantCount = new Set(lineRows.map((row) => row.restaurant.value)).size;
    orderSummary.textContent = `총 ${total}개 / 적재 한도 5 · 음식점 ${restaurantCount}곳 · 20초 순차 생성`;
    orderSummary.dataset.valid = String(total >= 3 && total <= 5 && restaurantCount >= 2);
  }

  function loadOrder(order) {
    if (!order) return;
    labelInput.value = order.label; destination.value = order.destination_id;
    while (lineRows.length) lineRows.pop().root.remove();
    for (const line of order.lines) addOrderLine(line.restaurant_id, line.menu_id, line.quantity);
  }

  function renderCards(state) {
    cards.replaceChildren(...state.recommendations.map((route) => {
      const card = make(documentValue, 'article', 'route-planner-card'); card.dataset.routeId = route.id;
      if (state.selectedRoute?.id === route.id) card.dataset.selected = 'true';
      const title = make(documentValue, 'strong', '', route.profiles.join(' · ') || route.profile);
      const metrics = make(documentValue, 'p', '', `${route.metrics.distance_m.toFixed(1)} m · ${route.metrics.eta_s.toFixed(0)}초 · 준비 대기 ${route.metrics.food_wait_s.toFixed(0)}초 · Risk ${route.metrics.risk_score.toFixed(1)}`);
      const detail = make(documentValue, 'small', '', `주행 ${route.metrics.travel_time_s.toFixed(0)}초 · 음식 ${route.metrics.food_wait_s.toFixed(0)}초 · 신호 ${route.metrics.signal_wait_s.toFixed(0)}초 · 거리 ${route.metrics.distance_m.toFixed(1)}m · 위험 ${route.metrics.risk_score.toFixed(1)}`);
      const counts = make(documentValue, 'small', '', `횡단보도 ${route.metrics.crosswalk_count} · UNDERPASS ${route.metrics.underpass_count} · 회전 ${route.metrics.turn_count} · 특수 ${route.metrics.special_behavior_count} · ${route.executable ? 'READY' : route.reason || 'ADVISORY'}`);
      const select = make(documentValue, 'button', '', '선택'); select.type = 'button'; select.dataset.routeSelect = route.id;
      card.append(title, metrics, detail, counts, select); return card;
    }));
  }

  function renderRehearsal(state) {
    const value = state.rehearsal;
    rehearsalSection.hidden = !value.enabled;
    if (!value.enabled) return;
    const signature = value.scenarios.map((item) => item.id).join('|');
    if (signature !== scenarioSignature) {
      const selected = scenarioSelect.value;
      scenarioSelect.replaceChildren(...value.scenarios.map((item) => option(documentValue, item.id, `${item.id} · ${item.description}`)));
      if ([...scenarioSelect.children].some((item) => item.value === selected)) scenarioSelect.value = selected;
      scenarioSignature = signature;
    }
    rehearsalBanner.textContent = value.banner || 'REHEARSAL — VIRTUAL DATA — ROBOT WILL NOT MOVE';
    rehearsalStart.disabled = state.busy || !state.selectedRoute || value.active || !scenarioSelect.value;
    for (const button of rehearsalControls.children) button.disabled = state.busy || !value.active;
    speed.disabled = state.busy || !value.active; speed.value = String(value.playback.speed);
    timeline.disabled = state.busy || !value.active; timeline.max = String(Math.max(1, value.playback.durationMs)); timeline.value = String(Math.min(value.playback.durationMs, value.playback.positionMs));
    playback.textContent = `${value.playback.state} · ${value.playback.positionMs} / ${value.playback.durationMs} ms · ${value.playback.speed}x · EVENT ${value.playback.eventIndex}/${value.playback.eventCount}`;
    const pose = value.virtualRobot;
    virtualPose.textContent = pose ? `${pose.label} · x ${pose.x.toFixed(2)} · y ${pose.y.toFixed(2)} · yaw ${pose.yaw.toFixed(2)} · SEG ${pose.segmentIndex + 1} ${(pose.segmentProgress * 100).toFixed(0)}%${pose.offRoute ? ' · OFF-ROUTE INJECTED' : ''}` : 'VIRTUAL ROBOT —';
    advisoryState.textContent = value.active ? `ADVISORY ${value.advisory.behavior} · ${value.advisory.state} · ${value.advisory.advisory}${value.advisory.reasons.length ? ` · ${value.advisory.reasons.join('/')}` : ''}` : 'ADVISORY —';
    expectedActual.textContent = value.active ? `EXPECTED / ACTUAL ${value.expectedActual.match ? 'MATCH' : 'DIFF'} · ${value.explainability.reason || 'DETERMINISTIC METRICS'}` : 'EXPECTED / ACTUAL —';
    eventList.replaceChildren(...value.events.map((item) => {
      const row = make(documentValue, 'li', '', `${item.atMs} ms · ${item.kind} · ${item.status}`); if (item.status === 'APPLIED') row.dataset.applied = 'true'; return row;
    }));
    cargo.replaceChildren(make(documentValue, 'strong', '', `CARGO ${value.delivery.cargoCount} / ${value.delivery.cargoCapacity} · ${value.delivery.state || 'WAITING'}`), ...value.delivery.items.map((item) => {
      const row = make(documentValue, 'div', 'route-rehearsal-cargo-item', `${item.sequence}. ${item.venueId}/${item.menuId} ×${item.quantity} · READY ${item.estimatedReadyS.toFixed(0)}s · ARRIVAL ${item.arrivalEstimateS.toFixed(0)}s · WAIT ${item.waitEstimateS.toFixed(0)}s · ${item.pickupState}`);
      if (value.active && item.venueId === value.delivery.nextVenueId) { const button = make(documentValue, 'button', '', 'PICKUP CONFIRM'); button.type = 'button'; button.dataset.routeRehearsalPickup = item.venueId; row.append(button); }
      return row;
    }));
    if (value.active && !value.delivery.nextVenueId && value.delivery.destinationState !== 'COMPLETE') { const button = make(documentValue, 'button', '', `${value.delivery.destinationId} DROPOFF CONFIRM`); button.type = 'button'; button.dataset.routeRehearsalDropoff = value.delivery.destinationId; cargo.append(button); }
    missionDryRun.textContent = value.active ? `MISSION DRY-RUN ${value.missionDryRun.eligibility ? 'ELIGIBLE' : value.missionDryRun.rejectionReason || 'REJECTED'} · WAYPOINTS ${value.missionDryRun.waypointCount} · MISSION CREATE ${value.missionDryRun.missionCreated ? '1' : '0'} · GOAL ${value.missionDryRun.navigationGoalSubmitted ? '1' : '0'} · NAV2 PATH ${value.overlay.actualNav2PathStatus || 'UNAVAILABLE'}` : 'MISSION DRY-RUN —';
    dryRunButton.disabled = state.busy || !state.selectedRoute;
    reportButton.disabled = state.busy || !value.active || !value.reportAvailable;
  }

  function render(state) {
    const previousOrderId = current?.order?.id; current = state;
    status.textContent = `ROUTE PLANNER ${state.state}`;
    pins.textContent = `MAP ${state.graph?.map_revision?.slice(0, 8) || '—'} · GRAPH ${state.graph?.graph_revision?.slice(0, 8) || '—'}`;
    if (state.order && state.order.id !== previousOrderId) loadOrder(state.order);
    const rehearsalActive = state.rehearsal.active;
    startNode.replaceChildren(...(state.graph?.nodes || []).filter((node) => node.role === 'START').map((node) => option(documentValue, node.id, node.label)));
    saveOrder.disabled = state.busy || rehearsalActive || state.order?.locked === true; lockOrder.disabled = state.busy || rehearsalActive || !state.order || state.order.locked;
    addLine.disabled = state.busy || rehearsalActive || lineRows.length >= 5 || state.order?.locked === true;
    calculate.disabled = state.busy || rehearsalActive || !state.order || !state.graph || !startNode.value;
    renderCards(state);
    const route = state.selectedRoute; const guide = state.guidance;
    guidanceAction.textContent = guide.active ? `${guide.instruction_type || 'GUIDANCE'} · ${guide.instruction || ''}` : 'GUIDANCE OFF';
    guidanceAction.dataset.warning = String(guide.off_route || guide.paused);
    guidanceMetrics.textContent = route ? `${guide.remaining_distance_m || route.metrics.distance_m} m 남음 · ETA ${(guide.eta_remaining_s || route.metrics.eta_s).toFixed(0)}초 · 이탈 ${(guide.cross_track_error_m || 0).toFixed(2)} m` : '선택 경로 없음';
    const requirements = guide.requirements || {};
    requirementState.textContent = `신호 ${requirements.TRAFFIC_GREEN || '—'} · 사람 ${requirements.PEDESTRIAN_CLEAR || '—'} · 정렬 ${requirements.CROSSWALK_ALIGNMENT || '—'} · 도킹 ${requirements.ARUCO_DOCKING || '—'}`;
    const pickupStops = (route?.stops || []).filter((stop) => ['RESTAURANT_APPROACH', 'RESTAURANT_DOCK'].includes(stop.role));
    const uniquePickups = [...new Map(pickupStops.map((stop) => [stop.venue_id, stop])).values()];
    const destinationStop = (route?.stops || []).find((stop) => ['DESTINATION_APPROACH', 'DESTINATION_DOCK'].includes(stop.role));
    confirmations.replaceChildren(
      ...uniquePickups.map((stop) => {
        const completed = guide.completed_pickups?.includes(stop.venue_id);
        const button = make(documentValue, 'button', '', completed ? `${stop.label} 픽업 완료` : `${stop.label} 픽업 확인`);
        button.type = 'button'; button.dataset.routePickup = stop.venue_id; button.disabled = state.busy || rehearsalActive || !guide.active || completed; return button;
      }),
      ...(destinationStop ? (() => {
        const button = make(documentValue, 'button', '', guide.dropoff_complete ? `${destinationStop.label} 배송 완료` : `${destinationStop.label} 배송 확인`);
        button.type = 'button'; button.dataset.routeDropoff = destinationStop.venue_id; button.disabled = state.busy || rehearsalActive || !guide.active || guide.dropoff_complete; return [button];
      })() : []),
    );
    const buttons = Object.fromEntries([...guidanceButtons.children].map((button) => [button.dataset.routeAction, button]));
    buttons['start-guidance'].disabled = state.busy || rehearsalActive || !route || guide.active;
    buttons['stop-guidance'].disabled = state.busy || rehearsalActive || !guide.active;
    buttons.preview.disabled = state.busy || !route;
    buttons.export.disabled = state.busy || rehearsalActive || !route;
    segmentList.replaceChildren(...(route?.segments || []).map((segment, index) => {
      const item = make(documentValue, 'li', '', `${index + 1}. ${segment.label} · ${segment.distance_m.toFixed(1)}m${segment.requirements.length ? ` · ${segment.requirements.map((entry) => entry.id).join('/')}` : ''}`);
      if (guide.active && guide.current_segment_index === index) item.dataset.current = 'true'; return item;
    }));
    message.textContent = state.error || state.staleReason || (state.perception.fresh ? 'PERCEPTION FRESH · GUIDANCE ONLY' : 'PERCEPTION UNKNOWN/STALE · AUTO EDGE NOT READY');
    message.dataset.error = String(Boolean(state.error || state.staleReason));
    renderRehearsal(state);
    renderOrderSummary();
  }

  root.addEventListener('click', async (event) => {
    const rehearsalPickup = event.target.closest?.('[data-route-rehearsal-pickup]')?.dataset.routeRehearsalPickup;
    if (rehearsalPickup) { await options.client.controlRehearsal('CONFIRM_PICKUP', { venue_id: rehearsalPickup }); return; }
    const rehearsalDropoff = event.target.closest?.('[data-route-rehearsal-dropoff]')?.dataset.routeRehearsalDropoff;
    if (rehearsalDropoff) { await options.client.controlRehearsal('CONFIRM_DROPOFF', { destination_id: rehearsalDropoff }); return; }
    const rehearsalAction = event.target.closest?.('[data-route-rehearsal-action]')?.dataset.routeRehearsalAction;
    if (rehearsalAction && current) {
      const route = current.selectedRoute;
      if (rehearsalAction === 'START' && route) await options.client.beginRehearsal(route, scenarioSelect.value);
      else if (rehearsalAction === 'DRY_RUN' && route) { const value = await options.client.missionDryRun(route); rehearsalReport.textContent = value ? JSON.stringify(value, null, 2).slice(0, 16000) : ''; }
      else if (rehearsalAction === 'REPORT') { const value = await options.client.rehearsalReport(); rehearsalReport.textContent = String(value?.markdown || '').slice(0, 16000); }
      else if (rehearsalAction === 'OFF_ROUTE') await options.client.controlRehearsal('OFF_ROUTE', { enabled: !current.rehearsal.virtualRobot?.offRoute });
      else await options.client.controlRehearsal(rehearsalAction);
      return;
    }
    const pickupId = event.target.closest?.('[data-route-pickup]')?.dataset.routePickup;
    if (pickupId) { await options.client.markPickup(pickupId); return; }
    const dropoffId = event.target.closest?.('[data-route-dropoff]')?.dataset.routeDropoff;
    if (dropoffId) { await options.client.markDropoff(dropoffId); return; }
    const selectId = event.target.closest?.('[data-route-select]')?.dataset.routeSelect;
    if (selectId && current) { const route = current.recommendations.find((item) => item.id === selectId); if (route) await options.client.select(route); return; }
    const action = event.target.closest?.('[data-route-action]')?.dataset.routeAction;
    if (!action || !current) return;
    if (action === 'add-line') { addOrderLine('EDIYA'); return; }
    if (action === 'save-order') {
      if (current.order) await options.client.updateOrder(current.order.id, { ...draftPayload(false), base_revision: current.order.revision });
      else await options.client.createOrder(draftPayload(false));
      return;
    }
    if (action === 'lock-order' && current.order) { await options.client.updateOrder(current.order.id, { ...draftPayload(true), base_revision: current.order.revision }); return; }
    if (action === 'calculate' && current.order && current.graph) {
      await options.client.calculate({ order_id: current.order.id, order_revision: current.order.revision, graph_revision: current.graph.graph_revision, start_node_id: startNode.value, operation_mode: operationMode.value }); return;
    }
    const route = current.selectedRoute; if (!route) return;
    if (action === 'start-guidance') await options.client.startGuidance(route);
    else if (action === 'stop-guidance') await options.client.stopGuidance();
    else if (action === 'preview') await options.client.preview(route);
    else if (action === 'export') await options.client.exportMission(route);
  });

  speed.addEventListener('change', async () => { if (current?.rehearsal.active) await options.client.controlRehearsal('SET_SPEED', { speed: Number(speed.value) }); });
  timeline.addEventListener('change', async () => { if (current?.rehearsal.active) await options.client.controlRehearsal('SCRUB', { position_ms: Math.max(0, Number(timeline.value) || 0) }); });

  addOrderLine('HANSOT', 'CHICKEN_MAYO', 2); addOrderLine('EDIYA', 'AMERICANO', 1);
  return Object.freeze({ render, destroy() { root.remove(); } });
}

export function createRoutePlannerPanel(options = {}) {
  if (!options.client) throw new TypeError('Route Planner panel requires its shared server client.');
  let view = null; let release = null; let active = false; let destroyed = false;
  function mount(host) { if (!view && !destroyed) view = (options.viewFactory || createRoutePlannerPanelView)({ ...options, host }); }
  function activate() { if (!active && view && !destroyed) { active = true; release = options.client.subscribe((state) => view?.render(state)); } }
  function deactivate() { if (active) { active = false; release?.(); release = null; } }
  function destroy() { if (!destroyed) { deactivate(); destroyed = true; view?.destroy(); view = null; } }
  return Object.freeze({ mount, activate, deactivate, destroy, diagnostics: () => Object.freeze({ active, destroyed, subscribed: Boolean(release) }) });
}

export { createRoutePlannerPanelView };
