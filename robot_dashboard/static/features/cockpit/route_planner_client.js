const HEX24 = /^[0-9a-f]{24}$/;
const HEX32 = /^[0-9a-f]{32}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const STATES = new Set(['EMPTY', 'DRAFT', 'VALIDATING_ORDER', 'ORDER_READY', 'PLANNING', 'RECOMMENDATIONS_READY', 'ROUTE_SELECTED', 'GUIDANCE_ACTIVE', 'MISSION_EXPORTED', 'STALE', 'INVALID', 'FAILED']);

function text(value, maximum = 96) { return String(value || '').slice(0, maximum); }
function finite(value, fallback = 0) { const number = Number(value); return Number.isFinite(number) ? number : fallback; }

function point(value) {
  const x = Number(value?.x); const y = Number(value?.y); const z = Number(value?.z ?? 0.035);
  return Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z) ? Object.freeze({ x, y, z }) : null;
}

function projectSegment(value, index) {
  const polyline = (Array.isArray(value?.polyline) ? value.polyline : []).slice(0, 128).map(point).filter(Boolean);
  return Object.freeze({
    index: Number.isInteger(value?.index) ? value.index : index,
    edge_id: text(value?.edge_id, 64), from_node_id: text(value?.from_node_id, 64), to_node_id: text(value?.to_node_id, 64),
    type: text(value?.type, 32), label: text(value?.label, 160), polyline: Object.freeze(polyline),
    distance_m: Math.max(0, finite(value?.distance_m)), travel_time_s: Math.max(0, finite(value?.travel_time_s)),
    expected_wait_s: Math.max(0, finite(value?.expected_wait_s)), risk: Math.max(0, finite(value?.risk)),
    requirements: Object.freeze((Array.isArray(value?.requirements) ? value.requirements : []).slice(0, 7).map((item) => Object.freeze({ id: text(item?.id, 32), state: text(item?.state, 16) }))),
  });
}

function projectRoute(value) {
  if (!value || !HEX32.test(String(value.id || '')) || !HEX64.test(String(value.revision || ''))) return null;
  const segments = (Array.isArray(value.segments) ? value.segments : []).slice(0, 512).map(projectSegment);
  return Object.freeze({
    id: String(value.id), revision: String(value.revision), profile: text(value.profile, 16),
    profiles: Object.freeze((Array.isArray(value.profiles) ? value.profiles : []).slice(0, 3).map((item) => text(item, 16))),
    operation_mode: text(value.operation_mode, 24), map_id: text(value.map_id, 24), map_revision: text(value.map_revision, 64),
    annotation_revision: text(value.annotation_revision, 64), graph_revision: text(value.graph_revision, 64),
    start_node_id: text(value.start_node_id, 64), executable: value.executable === true, reason: text(value.reason, 64),
    stops: Object.freeze((Array.isArray(value.stops) ? value.stops : []).slice(0, 5).map((stop) => Object.freeze({
      index: Number(stop?.index) || 0, node_id: text(stop?.node_id, 64), annotation_id: text(stop?.annotation_id, 24),
      role: text(stop?.role, 32), venue_id: text(stop?.venue_id, 64), label: text(stop?.label, 64),
    }))),
    segments: Object.freeze(segments), metrics: Object.freeze({
      distance_m: Math.max(0, finite(value.metrics?.distance_m)), travel_time_s: Math.max(0, finite(value.metrics?.travel_time_s)),
      food_wait_s: Math.max(0, finite(value.metrics?.food_wait_s)), signal_wait_s: Math.max(0, finite(value.metrics?.signal_wait_s)),
      risk_score: Math.max(0, finite(value.metrics?.risk_score)), eta_s: Math.max(0, finite(value.metrics?.eta_s)),
      crosswalk_count: Math.max(0, finite(value.metrics?.crosswalk_count)), underpass_count: Math.max(0, finite(value.metrics?.underpass_count)),
      turn_count: Math.max(0, finite(value.metrics?.turn_count)), special_behavior_count: Math.max(0, finite(value.metrics?.special_behavior_count)),
    }),
  });
}

function projectOrder(value) {
  if (!value || !HEX32.test(String(value.id || '')) || !HEX64.test(String(value.revision || ''))) return null;
  return Object.freeze({
    id: String(value.id), revision: String(value.revision), label: text(value.label, 64), destination_id: text(value.destination_id, 32),
    total_quantity: Math.max(0, Number(value.total_quantity) || 0), restaurant_count: Math.max(0, Number(value.restaurant_count) || 0),
    difficulty: text(value.difficulty, 16), locked: value.locked === true, order_started_at: text(value.order_started_at, 32) || null,
    lines: Object.freeze((Array.isArray(value.lines) ? value.lines : []).slice(0, 5).map((line) => Object.freeze({
      sequence: Number(line?.sequence) || 0, restaurant_id: text(line?.restaurant_id, 32), menu_id: text(line?.menu_id, 32),
      quantity: Math.max(0, Number(line?.quantity) || 0), ready_at_s: Math.max(0, Number(line?.ready_at_s) || 0),
    }))),
  });
}

function routePoints(route, limit = 2048) {
  const values = [];
  for (const segment of route?.segments || []) for (const value of segment.polyline) {
    if (!values.length || values.at(-1).x !== value.x || values.at(-1).y !== value.y) values.push(value);
    if (values.length >= limit) return Object.freeze(values);
  }
  return Object.freeze(values);
}

function overlayFor(state) {
  const selected = state.selectedRoute;
  const alternatives = state.recommendations.filter((route) => route.id !== selected?.id).slice(0, 2);
  if (!selected && !alternatives.length) return null;
  return Object.freeze({
    mapId: selected?.map_id || alternatives[0]?.map_id || '', revision: selected?.map_revision || alternatives[0]?.map_revision || '', frameId: 'map',
    selectedRoute: routePoints(selected, 2048),
    alternatives: Object.freeze(alternatives.map((route) => Object.freeze({ id: route.id, profile: route.profile, points: routePoints(route, 1024) }))),
    routeStops: Object.freeze((selected?.stops || []).map((stop) => Object.freeze({ id: stop.annotation_id, type: stop.role, name: stop.label }))),
    currentSegment: selected && Number.isInteger(state.guidance?.current_segment_index) ? selected.segments[state.guidance.current_segment_index]?.polyline || Object.freeze([]) : Object.freeze([]),
    actualNav2Path: Object.freeze([]),
  });
}

function projectState(payload, busy = false, error = '') {
  const recommendations = (Array.isArray(payload?.recommendations) ? payload.recommendations : []).slice(0, 3).map(projectRoute).filter(Boolean);
  const selectedId = text(payload?.selected_route_id, 32);
  const selectedRoute = recommendations.find((route) => route.id === selectedId) || null;
  const guidance = payload?.guidance && typeof payload.guidance === 'object' ? Object.freeze({
    active: payload.guidance.active === true, paused: payload.guidance.paused === true,
    instruction_type: text(payload.guidance.instruction_type, 32), instruction: text(payload.guidance.instruction, 160),
    current_segment_index: Math.max(0, Number(payload.guidance.current_segment_index) || 0),
    segment_progress: Math.max(0, Math.min(1, finite(payload.guidance.segment_progress))),
    cross_track_error_m: Math.max(0, finite(payload.guidance.cross_track_error_m)),
    remaining_distance_m: Math.max(0, finite(payload.guidance.remaining_distance_m)), eta_remaining_s: Math.max(0, finite(payload.guidance.eta_remaining_s)),
    off_route: payload.guidance.off_route === true, replan_available: payload.guidance.replan_available === true,
    requirements: Object.freeze({ ...(payload.guidance.requirements || {}) }),
    completed_pickups: Object.freeze((Array.isArray(payload.guidance.completed_pickups) ? payload.guidance.completed_pickups : []).slice(0, 5).map((item) => text(item, 32))),
    dropoff_complete: payload.guidance.dropoff_complete === true,
  }) : Object.freeze({ active: false, paused: false, completed_pickups: Object.freeze([]), dropoff_complete: false });
  const state = {
    available: payload?.available === true, busy, error: text(error || payload?.error, 200),
    state: STATES.has(String(payload?.state || '')) ? String(payload.state) : 'FAILED',
    staleReason: text(payload?.stale_reason, 96), order: projectOrder(payload?.order), graph: payload?.graph && HEX64.test(String(payload.graph.graph_revision || '')) ? Object.freeze({
      graph_revision: String(payload.graph.graph_revision), map_id: text(payload.graph.map_id, 24), map_revision: text(payload.graph.map_revision, 64),
      annotation_revision: text(payload.graph.annotation_revision, 64), nodes: Object.freeze((payload.graph.nodes || []).slice(0, 128)), edges: Object.freeze((payload.graph.edges || []).slice(0, 512)),
    }) : null,
    recommendations: Object.freeze(recommendations), selectedRoute, guidance,
    perception: Object.freeze({ fresh: payload?.perception?.fresh === true, state: text(payload?.perception?.state, 16), age_s: finite(payload?.perception?.age_s) }),
  };
  state.overlay = overlayFor(state);
  return Object.freeze(state);
}

export function createRoutePlannerClient(options = {}) {
  const api = options.api;
  if (typeof api !== 'function') throw new TypeError('Route Planner client requires the shared API function.');
  const setIntervalValue = options.setInterval || globalThis.setInterval?.bind(globalThis);
  const clearIntervalValue = options.clearInterval || globalThis.clearInterval?.bind(globalThis);
  const subscribers = new Set();
  let lastPayload = { available: null, state: 'EMPTY' };
  let state = projectState(lastPayload);
  let generation = 0; let timer = 0; let busy = false; let destroyed = false;

  function publish(payload = null, error = '') {
    if (payload) lastPayload = payload;
    state = projectState(lastPayload, busy, error);
    for (const subscriber of subscribers) subscriber(state);
    return state;
  }

  async function refresh(force = false) {
    if (destroyed || busy && !force) return state;
    const requestGeneration = ++generation;
    try {
      const payload = await api('/api/v1/route-planner');
      if (!destroyed && requestGeneration === generation) publish(payload);
    } catch (error) {
      if (!destroyed && requestGeneration === generation) publish({ available: false, state: 'FAILED' }, error?.message || error);
    }
    return state;
  }

  async function mutate(path, body, method = 'POST') {
    if (destroyed || busy) return null;
    busy = true; const requestGeneration = ++generation; publish();
    try {
      const response = await api(path, { method, body: JSON.stringify(body || {}) });
      if (destroyed || requestGeneration !== generation) return null;
      await refresh(true);
      return response;
    } catch (error) {
      if (!destroyed && requestGeneration === generation) publish(null, error?.message || error);
      return null;
    } finally {
      if (!destroyed) { busy = false; publish(); }
    }
  }

  function subscribe(callback) {
    if (typeof callback !== 'function') throw new TypeError('Route Planner subscriber callback is required.');
    subscribers.add(callback); callback(state);
    if (subscribers.size === 1) { void refresh(); timer = setIntervalValue?.(refresh, 750) || 0; }
    return () => { subscribers.delete(callback); if (!subscribers.size && timer) { clearIntervalValue?.(timer); timer = 0; generation += 1; } };
  }

  return Object.freeze({
    subscribe, refresh, snapshot: () => state,
    createOrder: (payload) => mutate('/api/v1/route-planner/orders', payload),
    updateOrder: (id, payload) => mutate(`/api/v1/route-planner/orders/${encodeURIComponent(id)}`, payload, 'PATCH'),
    calculate: (payload) => mutate('/api/v1/route-planner/recommendations', payload),
    select: (route) => mutate(`/api/v1/route-planner/recommendations/${encodeURIComponent(route.id)}/select`, { route_revision: route.revision }),
    startGuidance: (route) => mutate('/api/v1/route-planner/guidance/start', { route_id: route.id, route_revision: route.revision }),
    stopGuidance: () => mutate('/api/v1/route-planner/guidance/stop', {}),
    markPickup: (venueId) => mutate('/api/v1/route-planner/guidance/pickup', { venue_id: venueId }),
    markDropoff: (destinationId) => mutate('/api/v1/route-planner/guidance/dropoff', { destination_id: destinationId }),
    preview: (route) => mutate(`/api/v1/route-planner/routes/${encodeURIComponent(route.id)}/preview`, { route_revision: route.revision }),
    exportMission: (route) => mutate(`/api/v1/route-planner/routes/${encodeURIComponent(route.id)}/export-mission`, { route_revision: route.revision }),
    diagnostics: () => Object.freeze({ destroyed, busy, subscribers: subscribers.size, polling: Boolean(timer), rendererCount: 0 }),
    destroy() { destroyed = true; generation += 1; subscribers.clear(); if (timer) clearIntervalValue?.(timer); timer = 0; },
  });
}

export { projectRoute, projectState };
