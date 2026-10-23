import { globalMapIdentity, validatedAmbiguityMetadata, validatedAmbiguityOverride } from './global_observation_contract.js';

const ROOT = '/api/v1/observations/sensor-tracking';
const SCHEMA = 'robot-scope.sensor-tracking.v1';
const STATES = new Set(['WAITING_GLOBAL', 'INITIALIZING', 'ACQUIRING_FRESH_SCAN', 'SENSOR_CANDIDATE', 'LOST', 'STALE', 'STOPPED']);
const ACTIVE = new Set(['INITIALIZING', 'ACQUIRING_FRESH_SCAN', 'SENSOR_CANDIDATE', 'LOST', 'STALE']);
const ID = /^[a-f0-9]{24}$/;
const STAMP = /^[1-9][0-9]{0,19}$/;

const sameMap = (left, right) => left && right && left.map_id === right.map_id
  && left.map_revision === right.map_revision && left.map_frame === right.map_frame;

function validMatrix(matrix) {
  if (!Array.isArray(matrix) || matrix.length !== 4 || matrix.some(row =>
    !Array.isArray(row) || row.length !== 4 || row.some(value => !Number.isFinite(value)))) return false;
  if (matrix[3].some((value, index) => Math.abs(value - (index === 3 ? 1 : 0)) > 1e-6)) return false;
  const axes = [0, 1, 2].map(index => [matrix[0][index], matrix[1][index], matrix[2][index]]);
  const dot = (a, b) => a.reduce((sum, value, index) => sum + value * b[index], 0);
  const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
  return matrix.slice(0, 3).every(row => Math.abs(row[3]) <= 1_000_000)
    && axes.every(axis => Math.abs(Math.sqrt(dot(axis, axis)) - 1) < .05)
    && Math.abs(dot(axes[0], axes[1])) < .05 && Math.abs(dot(axes[0], axes[2])) < .05
    && Math.abs(dot(axes[1], axes[2])) < .05 && dot(cross(axes[0], axes[1]), axes[2]) > .9;
}

export function sensorTrackingRequestId() {
  const bytes = new Uint8Array(16); globalThis.crypto.getRandomValues(bytes);
  return `sensor-${Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')}`;
}

export function selectedGlobalObservation(record, map) {
  const observation = record?.result?.observation, policy = observation?.selection_policy;
  const selected = observation?.selected_candidate;
  const candidate = Number.isInteger(selected) && selected >= 0 ? observation?.candidates?.[selected] : null;
  const capture = record?.captured_context;
  const ambiguous = validatedAmbiguityOverride(observation);
  const ambiguityClaimed = observation?.ambiguity_override?.applied === true
    || observation?.estimate_label === 'AMBIGUOUS_UNVERIFIED_ESTIMATE';
  const gateFree = Array.isArray(observation?.gate_reasons) && observation.gate_reasons.length === 0
    && Array.isArray(candidate?.gate_reasons) && candidate.gate_reasons.length === 0;
  if (record?.state !== 'succeeded' || record.worker_active !== false || !ID.test(record.job_id || '') || !Number.isSafeInteger(record.generation)
      || !sameMap(capture, map) || record?.historical_only !== true || record?.tracking_verified !== false
      || observation?.status !== 'OBSERVATION_ONLY_UNVERIFIED'
      || !candidate || (ambiguityClaimed && !ambiguous) || (!gateFree && !ambiguous)
      || candidate.refinement_stationary !== true || !Number.isFinite(candidate.rmse_m) || candidate.rmse_m < 0
      || !Number.isFinite(candidate.overlap) || candidate.overlap < .60 || candidate.overlap > 1
      || !validMatrix(candidate.map_from_scan)
      || policy?.schema !== 'robot-scope.global-provisional-selection.v2'
      || policy?.adapter !== 'dashboard-v031-observation-no-rmse-gate-v1'
      || policy?.scope !== 'PROVISIONAL_OBSERVATION_ONLY'
      || policy?.scoring !== 'UNCHANGED_ORIGINAL_REFERENCE_POPULATION'
      || policy?.rmse_selection_gate_enabled !== false
      || policy?.rmse_thresholds_purpose !== 'COMPARISON_ONLY'
      || policy?.original_selection_replayed !== false
      || policy?.original_max_rmse_m !== .05 || policy?.provisional_max_rmse_m !== .10) return null;
  return { job_id: record.job_id, generation: record.generation, selected_candidate: selected,
    map_id: map.map_id, map_revision: map.map_revision, map_frame: map.map_frame,
    ambiguity_override_applied: ambiguous };
}

export function validateSensorTrackingSnapshot(value, map) {
  if (value?.schema !== SCHEMA || !STATES.has(value.state) || !Number.isSafeInteger(value.generation)
      || value.generation < 0 || value.globally_verified !== false || value.body_pose !== null
      || value.tracking_verified !== false || value.source_clock_verified !== false
      || value.body_extrinsic_verified !== false || value.operational_application !== 'NOT_RUN'
      || typeof value.temporal_consistency_confirmed !== 'boolean'
      || !Array.isArray(value.trail) || value.trail.length > 40) return false;
  const ambiguous = value.ambiguity_override?.applied === true;
  if (ambiguous && (!validatedAmbiguityMetadata(value.ambiguity_override)
      || value.estimate_label !== 'AMBIGUOUS_UNVERIFIED_ESTIMATE'
      || !['GLOBAL', 'LOCAL'].includes(value.ambiguity_source))) return false;
  if (!ambiguous && (value.estimate_label === 'AMBIGUOUS_UNVERIFIED_ESTIMATE'
      || value.ambiguity_source != null)) return false;
  const serverMap = value.map;
  if (serverMap != null && (typeof serverMap.map_id !== 'string' || typeof serverMap.map_revision !== 'string'
      || typeof serverMap.frame_id !== 'string')) return false;
  if (ACTIVE.has(value.state) && (!map || !serverMap || serverMap.map_id !== map.map_id
      || serverMap.map_revision !== map.map_revision || serverMap.frame_id !== map.map_frame)) return false;
  if (ACTIVE.has(value.state) && (!ID.test(value.source_global_job?.job_id || '')
      || !Number.isSafeInteger(value.source_global_job?.generation)
      || !Number.isSafeInteger(value.source_global_job?.selected_candidate))) return false;
  if (value.state !== 'SENSOR_CANDIDATE') return value.sensor_pose === null && value.trail.length === 0;
  const pose = value.sensor_pose, source = value.source;
  if (!pose || !source || !value.temporal_consistency_confirmed || !validMatrix(pose.T_map_sensor)
      || pose.map_frame !== map?.map_frame || pose.source_frame !== source.frame_id
      || !STAMP.test(pose.source_stamp_ns || '') || pose.source_stamp_ns !== source.source_stamp_ns
      || !Number.isFinite(pose.received_monotonic_s) || pose.received_monotonic_s !== source.received_monotonic_s
      || !Number.isFinite(source.age_s) || source.age_s < 0 || source.age_s > 1
      || typeof source.observer_id !== 'string' || !source.observer_id
      || typeof source.observer_epoch !== 'string' || !source.observer_epoch
      || typeof source.topic !== 'string' || !source.topic
      || !Number.isFinite(pose.rmse_m) || pose.rmse_m < 0
      || !Number.isFinite(pose.overlap) || pose.overlap < 0 || pose.overlap > 1) return false;
  return value.trail.every(item => STAMP.test(item?.source_stamp_ns || '')
    && Number.isFinite(item.received_monotonic_s) && validMatrix(item.T_map_sensor));
}

export class SensorTrackingController {
  constructor({ request = (...args) => fetch(...args), changed = () => {}, requestId = sensorTrackingRequestId,
    now = () => performance.now() / 1000 } = {}) {
    this.request = request; this.changed = changed; this.requestId = requestId; this.now = now;
    this.map = null; this.global = null; this.value = null; this.error = '';
    this.pending = null; this.startedJobId = null; this.localGeneration = 0;
    this.serverGeneration = -1; this.lastStamp = null; this.sourceFence = null;
    this.acceptedAt = null; this.ageAtAcceptance = null; this.freshnessTimer = null;
    this.reading = false; this.writing = false; this.writeCount = 0;
    this.disposed = false; this.stopRequested = false; this.previewSuppressed = false;
    this.explicitStopFence = false;
  }
  setMap(meta, cloud) {
    const map = globalMapIdentity(meta, cloud);
    if (JSON.stringify(map) === JSON.stringify(this.map)) return;
    const hadStarted = Boolean(this.startedJobId);
    this.localGeneration++; this.map = map; this.global = null; this.value = null;
    this.serverGeneration = -1; this.lastStamp = null; this.sourceFence = null;
    this.clearFreshness();
    this.pending = null; this.startedJobId = null; this.stopRequested = hadStarted;
    this.previewSuppressed = false;
    this.explicitStopFence = false;
    this.error = hadStarted ? 'MAP_CHANGED' : '';
    this.changed();
    if (hadStarted) void this.stop(false);
  }
  setGlobalRecord(record) {
    const selected = selectedGlobalObservation(record, this.map);
    if (JSON.stringify(selected) === JSON.stringify(this.global)) return;
    const previous = this.global, activeJobId = this.startedJobId || this.pending?.job_id;
    this.global = selected;
    if (activeJobId && (!selected || selected.job_id !== activeJobId
        || selected.generation !== previous?.generation
        || selected.selected_candidate !== previous?.selected_candidate
        || selected.ambiguity_override_applied !== previous?.ambiguity_override_applied)) {
      this.invalidate('GLOBAL_SELECTION_CHANGED');
      return;
    }
    if (this.value?.state === 'SENSOR_CANDIDATE'
        && (!selected || this.value.source_global_job?.job_id !== selected.job_id
          || this.value.source_global_job?.generation !== selected.generation
          || this.value.source_global_job?.selected_candidate !== selected.selected_candidate)) {
      this.value = null; this.clearFreshness(); this.error = 'GLOBAL_SELECTION_CHANGED';
    }
    this.changed();
  }
  snapshot() {
    const expired = this.value?.state === 'SENSOR_CANDIDATE' && Number.isFinite(this.acceptedAt)
      && this.ageAtAcceptance + Math.max(0, this.now() - this.acceptedAt) >= 1;
    const value = expired ? { ...this.value, state: 'STALE', reason: 'CLIENT_RECEIPT_STALE',
      sensor_pose: null, trail: [], source: null, temporal_consistency_confirmed: false } : this.value;
    const state = value?.state || 'WAITING_GLOBAL';
    return { map: this.map, global: this.global, value, state, error: this.error,
      stopRequested: this.stopRequested, previewSuppressed: this.previewSuppressed,
      active: ACTIVE.has(state), canStart: !this.disposed && Boolean(this.map && this.global)
        && !this.writing && !this.stopRequested && !this.pending && !ACTIVE.has(state),
      canStop: !this.disposed && !this.writing && (ACTIVE.has(state) || Boolean(this.pending)
        || this.stopRequested || this.previewSuppressed),
      canRetry: Boolean(this.pending && !this.writing) };
  }
  async json(path, options = {}) {
    const response = await this.request(path, { ...options, signal: AbortSignal.timeout(4000) });
    const value = await response.json();
    if (!response.ok) {
      const reason = typeof value?.detail === 'string' && /^[A-Z0-9_]{1,64}$/.test(value.detail)
        ? `_${value.detail}` : '';
      const error = new Error(`HTTP_${response.status}${reason}`);
      error.httpStatus = response.status;
      throw error;
    }
    return value;
  }
  clearFreshness() { if (this.freshnessTimer != null) clearTimeout(this.freshnessTimer); this.freshnessTimer = null;
    this.acceptedAt = null; this.ageAtAcceptance = null; }
  beginWrite() { this.writeCount++; this.writing = true; }
  endWrite() { this.writeCount = Math.max(0, this.writeCount - 1); this.writing = this.writeCount > 0; }
  accept(value, localGeneration, requestStartedAt = this.now()) {
    if (this.disposed || localGeneration !== this.localGeneration) return false;
    if (this.explicitStopFence && value?.schema === SCHEMA && ACTIVE.has(value.state)) return false;
    // An active server session must keep the map's generic GO2 preview hidden,
    // even if this response is rejected by a later source or time fence.
    if (value?.schema === SCHEMA && ACTIVE.has(value.state)) this.previewSuppressed = true;
    if (!validateSensorTrackingSnapshot(value, this.map)) {
      this.value = null; this.clearFreshness(); this.error = 'TRACKING_CONTRACT_MISMATCH'; this.changed(); return false;
    }
    if (value.generation < this.serverGeneration) {
      this.value = null; this.clearFreshness(); this.error = 'TRACKING_GENERATION_REVERSED'; this.changed(); return false;
    }
    if (value.generation > this.serverGeneration) {
      this.serverGeneration = value.generation; this.lastStamp = null; this.sourceFence = null;
    }
    if (this.stopRequested && ACTIVE.has(value.state)) {
      this.value = null; this.clearFreshness(); this.error = 'STOP_PENDING'; this.changed(); return false;
    }
    if (value.state === 'SENSOR_CANDIDATE') {
      const stamp = BigInt(value.sensor_pose.source_stamp_ns);
      const sourceFence = `${value.source.observer_id}:${value.source.observer_epoch}`;
      if ((this.lastStamp !== null && stamp < this.lastStamp)
          || (this.sourceFence !== null && sourceFence !== this.sourceFence)) {
        this.value = null; this.clearFreshness(); this.error = 'TRACKING_SOURCE_OR_TIME_REVERSED'; this.changed(); return false;
      }
      const age = value.source.age_s + Math.max(0, this.now() - requestStartedAt);
      if (age >= 1) { this.value = null; this.clearFreshness(); this.error = 'CLIENT_RECEIPT_STALE'; this.changed(); return false; }
      this.lastStamp = stamp; this.sourceFence = sourceFence;
      this.clearFreshness(); this.acceptedAt = this.now(); this.ageAtAcceptance = age;
      this.freshnessTimer = setTimeout(() => this.changed(), Math.max(0, (1 - age) * 1000));
      this.freshnessTimer?.unref?.();
    } else this.clearFreshness();
    if (this.startedJobId && ACTIVE.has(value.state) && value.source_global_job?.job_id !== this.startedJobId) {
      this.value = null; this.clearFreshness(); this.error = 'TRACKING_SESSION_CHANGED'; this.changed(); return false;
    }
    if (value.state === 'SENSOR_CANDIDATE' && (!this.global
        || value.source_global_job?.job_id !== this.global.job_id
        || value.source_global_job?.generation !== this.global.generation
        || value.source_global_job?.selected_candidate !== this.global.selected_candidate)) {
      this.value = null; this.clearFreshness(); this.error = 'GLOBAL_SELECTION_CHANGED'; this.changed(); return false;
    }
    if (ACTIVE.has(value.state) && this.global?.ambiguity_override_applied
        && (!validatedAmbiguityMetadata(value.ambiguity_override)
          || value.ambiguity_source !== 'GLOBAL')) {
      this.value = null; this.clearFreshness(); this.error = 'TRACKING_AMBIGUITY_CONTRACT_MISMATCH';
      this.changed(); return false;
    }
    this.value = value; this.error = '';
    if (this.pending && value.source_global_job?.job_id === this.pending.job_id) {
      this.startedJobId = this.pending.job_id; this.pending = null;
    }
    if (value.state === 'STOPPED' || value.state === 'WAITING_GLOBAL') this.startedJobId = null;
    if (value.state === 'STOPPED') this.stopRequested = false;
    this.changed(); return true;
  }
  async poll() {
    if (this.reading || this.disposed || !this.map) return;
    this.reading = true; const generation = this.localGeneration, startedAt = this.now();
    try { this.accept(await this.json(ROOT), generation, startedAt); }
    catch (_) { if (generation === this.localGeneration) { this.value = null; this.clearFreshness(); this.error = 'TRACKING_STATUS_UNAVAILABLE'; this.changed(); } }
    finally { this.reading = false; }
  }
  async start() {
    if (!this.snapshot().canStart && !this.snapshot().canRetry) return;
    if (!this.pending) this.pending = { job_id: this.global.job_id, request_id: this.requestId() };
    this.explicitStopFence = false;
    this.previewSuppressed = true;
    const pending = this.pending, generation = this.localGeneration;
    const startedAt = this.now();
    this.beginWrite(); this.error = ''; this.changed();
    try {
      const value = await this.json(ROOT, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ global_job_id: pending.job_id, request_id: pending.request_id }) });
      if (generation !== this.localGeneration) { void this.stop(false); return; }
      this.accept(value, generation, startedAt);
    } catch (error) { if (generation === this.localGeneration)
      this.error = error.httpStatus ? `START_REJECTED_${error.message}` : 'START_RESULT_UNCERTAIN'; }
    finally { this.endWrite(); this.changed(); }
  }
  async stop(explicit = true) {
    if (explicit) { this.localGeneration++; this.value = null; this.pending = null; this.startedJobId = null; this.changed(); }
    this.stopRequested = true; this.clearFreshness();
    const generation = this.localGeneration;
    const startedAt = this.now();
    this.beginWrite(); this.changed();
    try {
      const value = await this.json(`${ROOT}/stop`, { method: 'POST' });
      if (this.accept(value, generation, startedAt) && explicit && value.state === 'STOPPED') {
        this.previewSuppressed = false;
        this.explicitStopFence = true;
        this.localGeneration++;
      }
    }
    catch (_) { if (generation === this.localGeneration) this.error = 'STOP_RESULT_UNCERTAIN'; }
    finally { this.endWrite(); this.changed(); }
  }
  invalidate(reason) {
    const hadStarted = Boolean(this.startedJobId || this.pending);
    this.localGeneration++; this.value = null; this.pending = null; this.startedJobId = null;
    this.stopRequested = hadStarted;
    this.lastStamp = null; this.sourceFence = null; this.clearFreshness(); this.error = reason;
    this.changed(); if (hadStarted) void this.stop(false);
  }
  destroy() {
    const hadStarted = Boolean(this.startedJobId || this.pending);
    this.disposed = true; this.localGeneration++; this.value = null; this.clearFreshness(); this.changed();
    if (hadStarted) void this.json(`${ROOT}/stop`, { method: 'POST' }).catch(() => {});
  }
}
