function make(documentValue, name, className = '', text = '') {
  const element = documentValue.createElement(name); element.className = className; element.textContent = text; return element;
}

function createMissionPanelView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const root = make(documentValue, 'section', 'cockpit-mission-panel');
  const header = make(documentValue, 'div', 'cockpit-mission-header');
  const stateLabel = make(documentValue, 'strong', '', 'MISSION WAITING');
  const pins = make(documentValue, 'span', '', 'MAP — · ANN —'); header.append(stateLabel, pins);
  const missionSelect = documentValue.createElement('select'); missionSelect.setAttribute('aria-label', 'Server mission selection');
  const draft = make(documentValue, 'div', 'cockpit-mission-draft');
  const labelInput = documentValue.createElement('input'); labelInput.maxLength = 64; labelInput.placeholder = 'Mission label'; labelInput.setAttribute('aria-label', 'Mission label');
  const annotationChoices = make(documentValue, 'div', 'cockpit-mission-choices');
  const draftOrder = make(documentValue, 'ol', 'cockpit-mission-order');
  const createButton = make(documentValue, 'button', '', 'CREATE PINNED MISSION'); createButton.type = 'button'; createButton.dataset.missionAction = 'create';
  draft.append(labelInput, annotationChoices, draftOrder, createButton);
  const actions = make(documentValue, 'div', 'cockpit-mission-actions');
  const buttons = Object.fromEntries([
    ['start', 'START'], ['pause', 'PAUSE'], ['resume', 'RESUME'], ['skip', 'SKIP'], ['retry', 'RETRY'], ['abort', 'ABORT'], ['takeover', 'MANUAL TAKEOVER'],
  ].map(([key, label]) => { const button = make(documentValue, 'button', '', label); button.type = 'button'; button.dataset.missionAction = key; actions.append(button); return [key, button]; }));
  const metrics = make(documentValue, 'div', 'cockpit-mission-metrics');
  const route = make(documentValue, 'ol', 'cockpit-mission-route');
  const logs = make(documentValue, 'pre', 'cockpit-mission-logs'); logs.setAttribute('aria-label', 'Bounded mission progress log');
  const error = make(documentValue, 'small', 'cockpit-mission-error');
  root.append(header, missionSelect, draft, actions, metrics, route, logs, error); options.host.append(root);
  let current = null; let draftIds = [];

  function context() { return options.getContext?.() || {}; }
  function annotationPoints() {
    const points = context().annotations?.points;
    return (Array.isArray(points) ? points : []).filter((point) => ['HOME', 'POI', 'DOCK', 'INSPECTION_POINT'].includes(point?.type)).slice(0, 32);
  }
  function draftPoint(id) { return annotationPoints().find((point) => point.id === id); }

  function renderDraft() {
    const points = annotationPoints(); draftIds = draftIds.filter((id) => points.some((point) => point.id === id)).slice(0, 32);
    annotationChoices.replaceChildren(...points.map((point) => {
      const button = make(documentValue, 'button', '', `${draftIds.includes(point.id) ? '✓ ' : '+ '}${point.type} · ${point.name}`);
      button.type = 'button'; button.dataset.missionDraftId = point.id; button.setAttribute('aria-pressed', String(draftIds.includes(point.id))); return button;
    }));
    draftOrder.replaceChildren(...draftIds.map((id, index) => {
      const point = draftPoint(id); const item = make(documentValue, 'li', '', `${index + 1}. ${point?.name || id}`);
      const controls = make(documentValue, 'span');
      for (const [move, label] of [['up', '↑'], ['down', '↓'], ['remove', '×']]) { const button = make(documentValue, 'button', '', label); button.type = 'button'; button.dataset.missionDraftMove = move; button.dataset.missionDraftIndex = String(index); controls.append(button); }
      item.append(controls); return item;
    }));
    const value = context(); createButton.disabled = current?.busy || !draftIds.length || !value.mapMeta?.id || !value.mapMeta?.revision || !value.annotations?.annotation_revision;
  }

  function render(state) {
    current = state; const mission = state.selected;
    stateLabel.textContent = `MISSION ${String(mission?.state || (state.available === false ? 'UNAVAILABLE' : 'IDLE')).toUpperCase()}`;
    pins.textContent = `MAP ${mission?.map_revision?.slice(0, 8) || '—'} · ANN ${mission?.annotation_revision?.slice(0, 8) || '—'}`;
    missionSelect.replaceChildren(...state.missions.map((item) => { const option = documentValue.createElement('option'); option.value = item.id; option.textContent = `${item.label} · ${item.state.toUpperCase()}`; return option; }));
    missionSelect.value = state.selectedMissionId || ''; missionSelect.disabled = state.busy || !state.missions.length;
    const active = mission?.ownership_active === true;
    buttons.start.disabled = state.busy || mission?.state !== 'ready'; buttons.pause.disabled = state.busy || mission?.state !== 'running';
    buttons.resume.disabled = state.busy || mission?.state !== 'paused'; buttons.skip.disabled = state.busy || !['running', 'paused', 'failed'].includes(mission?.state);
    buttons.retry.disabled = state.busy || mission?.state !== 'failed' || mission?.outcome === 'aborted'; buttons.abort.disabled = state.busy || !active;
    buttons.takeover.disabled = state.busy || !(active || context().navigationActive);
    const rows = [
      ['CURRENT', mission ? `${Math.min(mission.current_index + 1, mission.waypoints.length)} / ${mission.waypoints.length}` : '—'],
      ['DONE', mission ? `${mission.completed_count} / ${mission.waypoints.length}` : '—'], ['REMAINING', mission?.remaining_count ?? '—'],
      ['ELAPSED', mission ? `${mission.elapsed_seconds.toFixed(1)} s` : '—'],
    ];
    metrics.replaceChildren(...rows.map(([label, value]) => { const item = make(documentValue, 'div'); item.append(make(documentValue, 'span', '', label), make(documentValue, 'strong', '', String(value))); return item; }));
    route.replaceChildren(...(mission?.waypoints || []).map((waypoint, index) => { const item = make(documentValue, 'li', '', `${index + 1}. ${waypoint.label} · ${waypoint.status.toUpperCase()}${waypoint.hold_seconds ? ` · HOLD ${waypoint.hold_seconds}s` : ''}${waypoint.requires_operator_confirmation ? ' · CONFIRM' : ''}`); if (index === mission.current_index) item.dataset.current = 'true'; return item; }));
    logs.textContent = (mission?.logs || []).map((entry) => `[${entry.seq}] ${entry.event}${entry.waypoint_index == null ? '' : ` · WP ${entry.waypoint_index + 1}`}`).join('\n') || 'BOUNDED SERVER MISSION LOG · WAITING';
    error.textContent = state.error || mission?.error || (mission?.pause_reason ? `PAUSED · ${mission.pause_reason}` : 'SERVER-AUTHORITATIVE · NO AUTO ARM · NO SCRIPT ACTIONS');
    error.dataset.error = String(Boolean(state.error || mission?.error)); renderDraft();
  }

  missionSelect.addEventListener('change', () => options.client.select(missionSelect.value));
  annotationChoices.addEventListener('click', (event) => { const id = event.target.closest?.('[data-mission-draft-id]')?.dataset.missionDraftId; if (!id) return; draftIds = draftIds.includes(id) ? draftIds.filter((item) => item !== id) : [...draftIds, id].slice(0, 32); renderDraft(); });
  draftOrder.addEventListener('click', (event) => {
    const button = event.target.closest?.('[data-mission-draft-move]'); if (!button) return; const index = Number(button.dataset.missionDraftIndex); const move = button.dataset.missionDraftMove;
    if (move === 'remove') draftIds.splice(index, 1); else { const target = move === 'up' ? index - 1 : index + 1; if (target >= 0 && target < draftIds.length) [draftIds[index], draftIds[target]] = [draftIds[target], draftIds[index]]; } renderDraft();
  });
  root.addEventListener('click', async (event) => {
    const action = event.target.closest?.('[data-mission-action]')?.dataset.missionAction; if (!action || !current) return;
    if (action === 'create') {
      const value = context(); const points = new Map(annotationPoints().map((point) => [point.id, point]));
      await options.client.create({ label: labelInput.value.trim() || 'Competition route', map_id: value.mapMeta.id, map_revision: value.mapMeta.revision, annotation_revision: value.annotations.annotation_revision,
        waypoints: draftIds.map((id) => ({ annotation_id: id, arrival_tolerance: null, hold_seconds: 0.0, requires_operator_confirmation: false, label: String(points.get(id)?.name || 'Waypoint').slice(0, 64) })) });
      return;
    }
    if (action === 'takeover') { options.navigationAdapter.requestTakeover(); return; }
    const mission = current.selected; if (!mission) return;
    if (['start', 'skip', 'abort'].includes(action) && globalThis.confirm?.(`${action.toUpperCase()} mission ${mission.label}?`) !== true) return;
    options.client[action]?.(mission.id);
  });
  return Object.freeze({ render, destroy() { root.remove(); } });
}

export function createMissionPanel(options = {}) {
  if (!options.client || !options.navigationAdapter) throw new TypeError('Mission panel requires shared mission and navigation owners.');
  let view = null; let release = null; let active = false; let destroyed = false;
  function mount(host) { if (!view && !destroyed) view = (options.viewFactory || createMissionPanelView)({ ...options, host }); }
  function activate() { if (!active && view && !destroyed) { active = true; release = options.client.subscribe((state) => view?.render(state)); } }
  function deactivate() { if (active) { active = false; release?.(); release = null; } }
  function destroy() { if (!destroyed) { deactivate(); destroyed = true; view?.destroy(); view = null; } }
  return Object.freeze({ mount, activate, deactivate, destroy, diagnostics: () => Object.freeze({ active, destroyed, subscribed: Boolean(release) }) });
}
