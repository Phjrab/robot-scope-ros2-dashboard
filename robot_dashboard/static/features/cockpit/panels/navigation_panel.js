import { createOccupancyRasterCache } from './map_panel.js';

function make(documentValue, name, className = '', text = '') {
  const element = documentValue.createElement(name); element.className = className; element.textContent = text; return element;
}

function createNavigationPanelView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const engine = options.navigationEngine;
  const root = make(documentValue, 'section', 'cockpit-navigation-panel');
  const header = make(documentValue, 'div', 'cockpit-navigation-header');
  const status = make(documentValue, 'strong', '', 'WAITING');
  const revisions = make(documentValue, 'span', '', 'MAP — · PARAM —'); header.append(status, revisions);
  const mapSelect = documentValue.createElement('select'); mapSelect.setAttribute('aria-label', 'Navigation static map');
  const actions = make(documentValue, 'div', 'cockpit-navigation-actions');
  const buttons = Object.fromEntries([
    ['start', 'START NAV2'], ['stop', 'STOP NAV2'], ['initial', 'INITIAL POSE'], ['goal', 'GOAL POSE'],
    ['send', 'SEND STAGED'], ['discard', 'DISCARD POSE'], ['cancel', 'CANCEL GOAL'], ['clear', 'CLEAR COSTMAPS'], ['takeover', 'MANUAL TAKEOVER'], ['retry', 'RETRY CLEANUP'],
  ].map(([key, label]) => { const button = make(documentValue, 'button', '', label); button.type = 'button'; button.dataset.navigationAction = key; actions.append(button); return [key, button]; }));
  const canvasWrap = make(documentValue, 'div', 'cockpit-navigation-map');
  const canvas = documentValue.createElement('canvas'); canvas.setAttribute('aria-label', 'Navigation pose selection map');
  const hint = make(documentValue, 'small', '', 'START NAV2 후 pose tool을 선택하세요.'); canvasWrap.append(canvas, hint);
  const takeover = make(documentValue, 'div', 'cockpit-navigation-takeover');
  const takeoverState = make(documentValue, 'strong', '', 'TAKEOVER IDLE');
  const takeoverNote = make(documentValue, 'small', '', '자동 ARM은 수행하지 않습니다.'); takeover.append(takeoverState, takeoverNote);
  const metrics = make(documentValue, 'div', 'cockpit-navigation-metrics');
  const annotations = make(documentValue, 'div', 'cockpit-navigation-annotations');
  const logs = make(documentValue, 'pre', 'cockpit-navigation-logs'); logs.setAttribute('aria-label', 'Sanitized Navigation progress log');
  root.append(header, mapSelect, actions, canvasWrap, takeover, metrics, annotations, logs); options.host.append(root);
  const rasterCache = createOccupancyRasterCache({ document: documentValue });
  let current = null; let tool = ''; let pointer = null; let staged = null;

  function canvasPoint(event) {
    const rect = canvas.getBoundingClientRect();
    return rect.width && rect.height ? { x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height } : null;
  }

  function mapLayout(state) {
    return state.map ? engine.mapLayout(state.map, canvas.width, canvas.height, 0.05) : null;
  }

  function drawMarker(context, layout, pose, color, label) {
    if (!pose) return; let point;
    try { point = engine.worldToCanvas(layout, pose); } catch (_) { return; }
    if (!point.inside) return;
    context.save(); context.strokeStyle = color; context.fillStyle = color; context.lineWidth = 2;
    context.beginPath(); context.arc(point.x, point.y, 6, 0, Math.PI * 2); context.stroke();
    context.beginPath(); context.moveTo(point.x, point.y); context.lineTo(point.x + Math.cos(point.heading) * 24, point.y + Math.sin(point.heading) * 24); context.stroke();
    context.font = '9px ui-monospace, monospace'; context.fillText(label, point.x + 8, point.y - 8); context.restore();
  }

  function draw(state) {
    const context = canvas.getContext('2d'); context.fillStyle = '#04100d'; context.fillRect(0, 0, canvas.width, canvas.height);
    if (!state.map) return;
    try {
      const normalized = { ...state.map, dataB64: state.map.data_b64 || state.map.dataB64 };
      const raster = rasterCache.get(normalized, engine); const layout = mapLayout(state);
      context.imageSmoothingEnabled = false; context.drawImage(raster.canvas, layout.left, layout.top, layout.drawWidth, layout.drawHeight);
      const path = Array.isArray(state.navigation?.path) ? state.navigation.path.slice(-512) : [];
      const points = path.map((pose) => { try { return engine.worldToCanvas(layout, pose); } catch (_) { return null; } }).filter((point) => point?.inside);
      if (points.length > 1) { context.save(); context.strokeStyle = '#a28bff'; context.setLineDash([6, 4]); context.beginPath(); points.forEach((point, i) => i ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y)); context.stroke(); context.restore(); }
      drawMarker(context, layout, state.navigation?.localization?.pose, '#7df0b6', 'ROBOT');
      drawMarker(context, layout, staged, tool === 'initial' ? '#5dded8' : '#ffc66d', `${tool.toUpperCase()} · STAGED`);
    } catch (error) { hint.textContent = `MAP RENDER ERROR · ${String(error?.message || error).slice(0, 120)}`; }
  }

  function poseAllowed(state, mode) {
    if (state.operationBusy || String(state.navigation?.pipeline?.state || '').toLowerCase() !== 'running' || !state.mapMeta || !state.map) return false;
    if (mode === 'initial') return state.navigation?.safety?.can_set_initial_pose === true;
    return state.navigation?.safety?.can_send_goal === true && String(state.navigation?.localization?.state || '').toLowerCase() === 'localized' && !state.canCancel;
  }

  function render(state) {
    current = state;
    const pipeline = String(state.navigation?.pipeline?.state || 'idle').toUpperCase();
    status.textContent = pipeline; status.dataset.state = pipeline.toLowerCase();
    revisions.textContent = `MAP ${state.mapMeta?.revision?.slice(0, 10) || '—'} · PARAM ${state.parameters?.revision?.slice(0, 10) || '—'}`;
    const selectedId = state.mapMeta?.id || '';
    mapSelect.replaceChildren(...state.maps.map((map) => { const option = documentValue.createElement('option'); option.value = map.id; option.textContent = `${map.name || 'Saved map'} · ${String(map.revision || '').slice(0, 8)}`; return option; }));
    mapSelect.value = selectedId; mapSelect.disabled = state.operationBusy || state.navigationActive;
    buttons.start.disabled = state.operationBusy || !state.canStart; buttons.stop.disabled = state.operationBusy || !state.canStop;
    buttons.cancel.disabled = state.operationBusy || !state.canCancel; buttons.clear.disabled = state.operationBusy || !state.canClear;
    buttons.initial.disabled = !poseAllowed(state, 'initial'); buttons.goal.disabled = !poseAllowed(state, 'goal');
    buttons.send.disabled = !staged || !poseAllowed(state, tool); buttons.discard.disabled = !staged;
    buttons.takeover.disabled = state.operationBusy || !state.navigationActive || ['CANCELING', 'STOPPING', 'VERIFYING'].includes(state.takeover.state);
    buttons.retry.hidden = state.takeover.state !== 'FAILED';
    takeoverState.textContent = `TAKEOVER ${state.takeover.state}`;
    takeoverNote.textContent = state.takeover.error || (state.takeover.readyToArm
      ? `NAV RELEASED · BRIDGE ${state.takeover.bridgeReady ? 'READY' : 'WAIT'} · XBOX ${state.takeover.controllerFresh ? 'FRESH' : 'WAIT'} · 별도로 ARM하세요.`
      : 'Cancel → stop → navigation lease release를 확인합니다. 자동 ARM은 수행하지 않습니다.');
    const rows = [
      ['LOCALIZATION', `${String(state.navigation?.localization?.state || 'unknown').toUpperCase()} / ${String(state.navigation?.localization_health?.state || 'UNAVAILABLE').toUpperCase()}`],
      ['GOAL', String(state.navigation?.goal?.state || 'idle').toUpperCase()],
      ['REMAINING', Number.isFinite(Number(state.navigation?.goal?.distance_remaining)) ? `${Number(state.navigation.goal.distance_remaining).toFixed(2)} m` : '—'],
      ['MANUAL', state.manualActive ? 'LEASE ACTIVE · BLOCKED' : state.commandZero ? 'RELEASED · ZERO' : 'COMMAND NOT ZERO'],
    ];
    metrics.replaceChildren(...rows.map(([label, value]) => { const item = make(documentValue, 'div'); item.append(make(documentValue, 'span', '', label), make(documentValue, 'strong', '', value)); return item; }));
    const pointsForGoals = Array.isArray(state.annotations?.points) ? state.annotations.points.filter((item) => ['HOME', 'DOCK', 'POI', 'INSPECTION_POINT'].includes(item?.type)).slice(0, 64) : [];
    annotations.replaceChildren(...pointsForGoals.map((point) => { const button = make(documentValue, 'button', '', `${point.type} · ${point.name}`); button.type = 'button'; button.dataset.annotationGoal = point.id; button.disabled = !poseAllowed(state, 'goal'); return button; }));
    const entries = Array.isArray(state.logs?.entries) ? state.logs.entries.slice(-80) : [];
    logs.textContent = entries.map((entry) => `[${String(entry.phase || '').toUpperCase()}] ${String(entry.message || '').slice(0, 320)}`).join('\n') || 'SANITIZED NAVIGATION LOG · WAITING';
    draw(state);
  }

  actions.addEventListener('click', (event) => {
    const action = event.target.closest?.('button[data-navigation-action]')?.dataset.navigationAction;
    if (!action || !current) return;
    if (action === 'initial' || action === 'goal') { tool = tool === action ? '' : action; staged = null; hint.textContent = tool ? 'Known-free 셀에서 진행 방향으로 드래그하세요.' : 'Pose tool이 해제되었습니다.'; render(current); return; }
    if (action === 'discard') { staged = null; hint.textContent = 'Staged pose를 버렸습니다.'; render(current); return; }
    if (action === 'send' && staged && tool) { const pose = staged; options.adapter.submitPose(tool, pose); staged = null; tool = ''; render(current); return; }
    if (action === 'start') options.adapter.start(); else if (action === 'stop') options.adapter.stop(); else if (action === 'cancel') options.adapter.cancel();
    else if (action === 'clear') options.adapter.clear(); else if (action === 'takeover') options.adapter.requestTakeover(); else if (action === 'retry') options.adapter.retryTakeover();
  });
  mapSelect.addEventListener('change', () => options.adapter.selectMap(mapSelect.value));
  annotations.addEventListener('click', (event) => { const id = event.target.closest?.('button[data-annotation-goal]')?.dataset.annotationGoal; if (id) options.adapter.submitAnnotationGoal(id); });
  canvas.addEventListener('pointerdown', (event) => {
    if (!tool || !current || !poseAllowed(current, tool)) return;
    const point = canvasPoint(event); const layout = mapLayout(current); let cell = null;
    try { cell = engine.occupancyCellAtCanvas(layout, current.mapCells, point); } catch (_) {}
    if (!cell?.inside || !cell.free) { hint.textContent = cell?.value < 0 ? 'UNKNOWN 셀은 선택할 수 없습니다.' : 'FREE 셀을 선택하세요.'; return; }
    pointer = { id: event.pointerId, start: point, end: point }; canvas.setPointerCapture?.(event.pointerId); event.preventDefault();
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!pointer || pointer.id !== event.pointerId) return; pointer.end = canvasPoint(event);
    staged = engine.poseFromDrag(mapLayout(current), pointer.start, pointer.end, Number(current.navigation?.localization?.pose?.yaw) || 0); draw(current);
  });
  const finish = (event) => {
    if (!pointer || pointer.id !== event.pointerId) return; pointer.end = canvasPoint(event) || pointer.end;
    staged = engine.poseFromDrag(mapLayout(current), pointer.start, pointer.end, Number(current.navigation?.localization?.pose?.yaw) || 0); pointer = null; canvas.releasePointerCapture?.(event.pointerId);
    if (staged) { const pose = staged; hint.textContent = `${tool.toUpperCase()} X ${pose.x.toFixed(2)} · Y ${pose.y.toFixed(2)} · YAW ${pose.yaw.toFixed(2)} · SEND STAGED로 확인하세요.`; }
    draw(current);
  };
  canvas.addEventListener('pointerup', finish); canvas.addEventListener('pointercancel', finish);
  return Object.freeze({ render, destroy() { rasterCache.reset(); root.remove(); }, clear() { pointer = null; }, resize() { draw(current || {}); } });
}

export function createNavigationPanel(options = {}) {
  if (!options.adapter) throw new TypeError('Navigation panel requires the shared application adapter.');
  let view = null; let release = null; let active = false; let destroyed = false;
  function mount(host) { if (!view && !destroyed) view = (options.viewFactory || createNavigationPanelView)({ ...options, host }); }
  function activate() { if (!active && view && !destroyed) { active = true; release = options.adapter.subscribe((state) => view?.render(state)); } }
  function deactivate() { if (active) { active = false; release?.(); release = null; view?.clear(); } }
  function destroy() { if (!destroyed) { deactivate(); destroyed = true; view?.destroy(); view = null; } }
  return Object.freeze({ mount, activate, deactivate, destroy, diagnostics: () => Object.freeze({ active, destroyed, subscribed: Boolean(release) }) });
}
