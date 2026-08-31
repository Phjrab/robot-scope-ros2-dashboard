import { createSafetyHudView } from './safety_hud_view.js';

export const SAFETY_HUD_STALE_MS = 2500;

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function ageFresh(updatedAt, now, staleMs = SAFETY_HUD_STALE_MS) {
  const age = Number(now) - Number(updatedAt);
  return Number(updatedAt) > 0 && Number.isFinite(age) && age >= 0 && age <= staleMs;
}

function navigationActive(snapshot) {
  const pipeline = String(snapshot?.pipeline?.state || '').toLowerCase();
  const goal = String(snapshot?.goal?.state || '').toLowerCase();
  return ['starting', 'running', 'active', 'stopping', 'canceling'].includes(pipeline)
    || ['pending', 'accepted', 'executing', 'active', 'canceling'].includes(goal);
}

function formatAxis(value) {
  const number = finite(value);
  return number == null ? 'UNKNOWN' : `${number >= 0 ? '+' : ''}${number.toFixed(3)}`;
}

export function projectSafetyHud(input = {}, now = Date.now()) {
  const state = input.state || null;
  const control = input.control || null;
  const stateFresh = Boolean(state) && ageFresh(input.stateUpdatedAt, now);
  const controlFresh = Boolean(control) && ageFresh(input.controlUpdatedAt, now);
  const health = state?.health || {};
  const targetConnected = health.robot_target_connected == null ? Boolean(health.robot_ip) : health.robot_target_connected === true;
  const telemetryLinkLive = stateFresh && health.agent_ready === true && targetConnected && health.robot_online === true;
  const navActive = input.navigationAvailable === true && navigationActive(input.navigation);
  const cachedLeaseActive = Boolean(input.locallyArmed || control?.lease?.active);
  const manualActive = controlFresh && cachedLeaseActive;
  const conflict = manualActive && navActive;
  const source = navActive ? 'NAVIGATION' : manualActive ? 'MANUAL' : 'NONE';
  const command = controlFresh ? (input.command || control?.command || {}) : {};
  const stopLatched = controlFresh ? Boolean(control?.estop_latched ?? control?.estop?.latched) : null;
  const bridge = controlFresh ? control?.bridge : null;
  const bridgeState = bridge && typeof bridge === 'object'
    ? (bridge.ready === true && bridge.authenticated !== false ? 'READY' : String(bridge.state || 'NOT READY').toUpperCase())
    : 'UNKNOWN';
  const bridgeLowstateAgeMs = finite(bridge?.lowstate_age_ms);
  const bridgeLowstateFresh = Boolean(bridge)
    && bridge.ready === true
    && bridge.authenticated !== false
    && bridge.connected !== false
    && bridgeLowstateAgeMs != null
    && bridgeLowstateAgeMs >= 0
    && bridgeLowstateAgeMs <= 1500;
  const controlLinkLive = controlFresh && bridgeLowstateFresh;
  const linkLive = telemetryLinkLive || controlLinkLive;
  const competition = input.competition || null;
  const capture = input.dataset?.capture || null;
  const sensors = stateFresh && Array.isArray(state?.sensors) ? state.sensors : [];
  const lowstate = sensors.find((sensor) => sensor?.category === 'robot_state' || /(^|\/)lowstate$/i.test(String(sensor?.topic || '')));
  const lowstateAge = finite(lowstate?.age_s);
  const telemetryLowstateFresh = Boolean(lowstate) && lowstate?.state === 'ok' && lowstateAge != null && lowstateAge >= 0 && lowstateAge <= 1.5;
  const lowstateFresh = bridgeLowstateFresh || telemetryLowstateFresh;
  const battery = sensors.find((sensor) => sensor?.category === 'battery' || sensor?.values?.battery_soc != null);
  const batteryAge = finite(battery?.age_s);
  const batterySoc = finite(battery?.values?.battery_soc ?? (battery?.values?.percentage == null ? null : battery.values.percentage * 100));
  const batteryFresh = Boolean(battery) && battery?.state === 'ok' && batteryAge != null && batteryAge >= 0 && batteryAge <= 3 && batterySoc != null;
  const reportedScale = finite(command.speed_scale ?? input.speedScale ?? control?.limits?.default_speed_scale);
  const controlUnknownWhileOwned = cachedLeaseActive && !controlFresh;
  const danger = stopLatched === true || conflict || controlUnknownWhileOwned || ((manualActive || navActive) && (!linkLive || !lowstateFresh));
  return Object.freeze({
    'control-source': source,
    armed: controlFresh ? (cachedLeaseActive ? 'ARMED' : 'DISARMED') : cachedLeaseActive ? 'UNKNOWN · LOCKED' : 'UNKNOWN',
    deadman: controlFresh ? (command.deadman ? 'HELD' : 'RELEASED') : 'UNKNOWN',
    'software-stop': stopLatched == null ? 'UNKNOWN' : stopLatched ? 'LATCHED' : 'CLEAR',
    'control-bridge': bridgeState,
    'operation-mode': competition ? String(competition.operationMode || 'SAFE_STOP') : 'SAFE_STOP · UNKNOWN',
    'competition-lock': competition ? String(competition.lock || 'UNKNOWN') : 'UNKNOWN · BLOCKED',
    'perception-authority': competition ? String(competition.authority || 'NONE') : 'NONE',
    dataset: capture?.active ? 'CAPTURING' : 'IDLE',
    lease: controlFresh ? (control?.lease?.active ? 'ACTIVE' : 'NONE') : cachedLeaseActive ? 'UNKNOWN · LOCKED' : 'UNKNOWN',
    'go2-link': telemetryLinkLive ? 'LIVE' : controlLinkLive ? 'CONTROL LIVE' : stateFresh ? 'OFFLINE' : 'STALE',
    lowstate: bridgeLowstateFresh
      ? `${Math.round(bridgeLowstateAgeMs)} ms`
      : telemetryLowstateFresh
        ? `${Math.round(lowstateAge * 1000)} ms`
        : lowstate ? 'STALE' : 'WAITING',
    battery: batteryFresh ? `${Math.round(batterySoc)}%` : battery ? 'STALE' : 'WAITING',
    vx: controlFresh ? formatAxis(command.linear_x) : 'UNKNOWN',
    vy: controlFresh ? formatAxis(command.linear_y) : 'UNKNOWN',
    wz: controlFresh ? formatAxis(command.angular_z) : 'UNKNOWN',
    'speed-scale': reportedScale == null || !controlFresh ? 'UNKNOWN' : `${Math.round(reportedScale * 100)}%`,
    layoutArmed: cachedLeaseActive || navActive,
    tone: danger || (Object.hasOwn(input, 'competition') && !competition) ? 'danger' : linkLive && controlFresh ? 'normal' : 'waiting',
  });
}

export function createSafetyHud(options = {}) {
  const now = options.now || Date.now;
  const setIntervalValue = options.setInterval || globalThis.setInterval?.bind(globalThis);
  const clearIntervalValue = options.clearInterval || globalThis.clearInterval?.bind(globalThis);
  const view = (options.viewFactory || createSafetyHudView)({
    root: options.root,
    document: options.document,
    onRequestEdit: options.onRequestEdit,
    onApply: options.onApply,
    onStop: options.onStop,
  });
  let active = false;
  let timer = 0;
  let layoutState = options.layoutState;
  let projected = projectSafetyHud({}, now());

  function refresh() {
    const input = options.getSnapshot?.() || {};
    projected = projectSafetyHud(input, now());
    options.onProjection?.(projected, input);
    view.render(projected, layoutState);
    return projected;
  }

  function setLayoutState(next) {
    layoutState = next;
    view.render(projected, layoutState);
  }

  function activate() {
    if (active) return;
    active = true;
    refresh();
    timer = setIntervalValue?.(refresh, 250) || 0;
  }

  function deactivate() {
    if (!active) return;
    active = false;
    if (timer) clearIntervalValue?.(timer);
    timer = 0;
  }

  function destroy() {
    deactivate();
    view.destroy();
  }

  return Object.freeze({ activate, deactivate, refresh, setLayoutState, diagnostics: () => Object.freeze({ active, projected, layoutState }), destroy });
}
