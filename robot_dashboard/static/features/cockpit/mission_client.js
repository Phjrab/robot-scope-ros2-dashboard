const MISSION_STATES = new Set(['idle', 'ready', 'starting', 'running', 'pausing', 'paused', 'retrying', 'skipping', 'canceling', 'completed', 'failed']);
const ACTIVE_STATES = new Set(['starting', 'running', 'pausing', 'paused', 'retrying', 'skipping', 'canceling']);

function text(value, maximum = 96) { return String(value || '').slice(0, maximum); }

function projectMission(value) {
  if (!value || typeof value !== 'object' || !/^[0-9a-f]{32}$/.test(String(value.id || ''))) return null;
  const state = MISSION_STATES.has(String(value.state || '')) ? String(value.state) : 'failed';
  const waypoints = (Array.isArray(value.waypoints) ? value.waypoints : []).slice(0, 32).map((item) => Object.freeze({
    annotation_id: text(item?.annotation_id, 24), label: text(item?.label, 64), status: text(item?.status, 16),
    hold_seconds: Number(item?.hold_seconds) || 0, requires_operator_confirmation: item?.requires_operator_confirmation === true,
    goal_id: text(item?.goal_id, 128) || null, attempts: Math.max(0, Number(item?.attempts) || 0),
  }));
  const logs = (Array.isArray(value.logs) ? value.logs : []).slice(-200).map((entry) => Object.freeze({
    seq: Number(entry?.seq) || 0, timestamp: text(entry?.timestamp, 32), event: text(entry?.event, 48), waypoint_index: Number.isInteger(entry?.waypoint_index) ? entry.waypoint_index : null,
  }));
  return Object.freeze({
    id: String(value.id), label: text(value.label, 64), state, outcome: text(value.outcome, 32) || null, error: text(value.error, 96) || null,
    map_id: text(value.map_id, 24), map_revision: text(value.map_revision, 64), annotation_revision: text(value.annotation_revision, 64),
    current_index: Math.max(0, Number(value.current_index) || 0), completed_count: Math.max(0, Number(value.completed_count) || 0),
    remaining_count: Math.max(0, Number(value.remaining_count) || 0), elapsed_seconds: Math.max(0, Number(value.elapsed_seconds) || 0),
    hold_remaining: Math.max(0, Number(value.hold_remaining) || 0), pause_reason: text(value.pause_reason, 48) || null,
    ownership_active: value.ownership_active === true || ACTIVE_STATES.has(state) && value.ownership_active !== false,
    waypoints: Object.freeze(waypoints), current_waypoint: waypoints[Math.max(0, Number(value.current_index) || 0)] || null, logs: Object.freeze(logs),
  });
}

export function createMissionClient(options = {}) {
  const api = options.api;
  if (typeof api !== 'function') throw new TypeError('Mission client requires the shared API function.');
  const setIntervalValue = options.setInterval || globalThis.setInterval?.bind(globalThis);
  const clearIntervalValue = options.clearInterval || globalThis.clearInterval?.bind(globalThis);
  const subscribers = new Set();
  let generation = 0; let busy = false; let destroyed = false; let timer = 0; let selectedId = '';
  let state = Object.freeze({ available: null, busy: false, error: '', activeMissionId: null, active: null, selectedMissionId: null, selected: null, missions: Object.freeze([]) });

  function publish(payload = null, error = '') {
    const missions = payload ? (Array.isArray(payload.missions) ? payload.missions : []).map(projectMission).filter(Boolean).slice(0, 32) : state.missions;
    const activeMissionId = payload ? text(payload.active_mission_id, 32) || null : state.activeMissionId;
    if (!selectedId || !missions.some((mission) => mission.id === selectedId)) selectedId = activeMissionId || missions[0]?.id || '';
    state = Object.freeze({ available: payload ? payload.available === true : state.available, busy, error: text(error || payload?.error, 160), activeMissionId, active: missions.find((mission) => mission.id === activeMissionId) || null, selectedMissionId: selectedId || null, selected: missions.find((mission) => mission.id === selectedId) || null, missions: Object.freeze([...missions]) });
    for (const subscriber of subscribers) subscriber(state);
    return state;
  }

  async function refresh(force = false) {
    if (destroyed || busy && !force) return state;
    const requestGeneration = ++generation;
    try {
      const payload = await api('/api/v1/missions');
      if (destroyed || requestGeneration !== generation) return state;
      return publish(payload);
    } catch (error) {
      if (!destroyed && requestGeneration === generation) publish({ missions: [], active_mission_id: null, available: false }, error?.message || error);
      return state;
    }
  }

  async function mutate(path, body = {}) {
    if (destroyed || busy) return null;
    const requestGeneration = ++generation; busy = true; publish();
    try {
      const response = await api(path, { method: 'POST', body: JSON.stringify(body) });
      if (destroyed || requestGeneration !== generation) return null;
      if (response?.mission?.id) selectedId = response.mission.id;
      await refresh(true);
      return destroyed ? null : response;
    } catch (error) {
      if (!destroyed && requestGeneration === generation) publish(null, error?.message || error);
      return null;
    } finally {
      if (!destroyed) { busy = false; publish(); }
    }
  }

  function subscribe(callback) {
    if (typeof callback !== 'function') throw new TypeError('Mission subscriber callback is required.');
    subscribers.add(callback); callback(state);
    if (subscribers.size === 1) { refresh(); timer = setIntervalValue?.(refresh, 500) || 0; }
    return () => { subscribers.delete(callback); if (!subscribers.size && timer) { clearIntervalValue?.(timer); timer = 0; generation += 1; } };
  }

  function select(id) { selectedId = text(id, 32); publish(); }
  const action = (name, id = selectedId) => id ? mutate(`/api/v1/missions/${encodeURIComponent(id)}/${name}`) : Promise.resolve(null);
  return Object.freeze({
    subscribe, refresh, snapshot: () => state, select,
    create: (payload) => mutate('/api/v1/missions', payload), start: (id) => action('start', id), pause: (id) => action('pause', id),
    resume: (id) => action('resume', id), skip: (id) => action('skip', id), retry: (id) => action('retry', id), abort: (id) => action('abort', id),
    abortActive: () => state.activeMissionId ? action('abort', state.activeMissionId) : Promise.resolve({ mission: null }),
    diagnostics: () => Object.freeze({ destroyed, subscribers: subscribers.size, generation, busy, polling: Boolean(timer) }),
    destroy() { destroyed = true; generation += 1; subscribers.clear(); if (timer) clearIntervalValue?.(timer); timer = 0; },
  });
}
