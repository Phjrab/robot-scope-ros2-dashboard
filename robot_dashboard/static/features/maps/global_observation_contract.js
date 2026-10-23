// This controller owns historical job records only. It never exposes a current
// pose, transforms a live cloud, or changes the existing local-fit controller.
const ROOT = '/api/v1/observations/global-jobs';
const JOB_SCHEMA = 'robot-scope.raw-global-observation-job.v1';
const terminal = new Set(['succeeded', 'cancelled', 'failed', 'stale', 'timed_out']);
const idPattern = /^[a-f0-9]{24}$/;
const revisionPattern = /^[a-f0-9]{64}$/;
const stampPattern = /^[1-9][0-9]{0,19}$/;
const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));
const ambiguityOnly = reasons => Array.isArray(reasons) && reasons.length === 1
  && reasons[0] === 'AMBIGUOUS_ALTERNATIVES';
const finiteNonnegative = value => Number.isFinite(value) && value >= 0;
function ambiguityRigid(matrix) {
  if (!Array.isArray(matrix) || matrix.length !== 4 || matrix.some(row =>
    !Array.isArray(row) || row.length !== 4 || row.some(value => !Number.isFinite(value)))) return false;
  if (matrix[3].some((value, index) => Math.abs(value - (index === 3 ? 1 : 0)) > 1e-8)) return false;
  const axes = [0, 1, 2].map(index => [matrix[0][index], matrix[1][index], matrix[2][index]]);
  const dot = (a, b) => a.reduce((sum, value, index) => sum + value * b[index], 0);
  const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
  return axes.every((axis, index) => Math.abs(dot(axis, axis) - 1) <= 1e-5
    && axes.every((other, otherIndex) => index === otherIndex || Math.abs(dot(axis, other)) <= 1e-5))
    && Math.abs(dot(cross(axes[0], axes[1]), axes[2]) - 1) <= 1e-6;
}
function ambiguityEligible(candidate) {
  if (!ambiguityOnly(candidate?.gate_reasons) || candidate.refinement_stationary !== true
      || !Number.isSafeInteger(candidate.scan_count) || !Number.isSafeInteger(candidate.inlier_count)
      || !Number.isSafeInteger(candidate.distinct_inlier_voxel_count)
      || candidate.distinct_inlier_voxel_count < 60
      || candidate.distinct_inlier_voxel_count > candidate.inlier_count
      || candidate.inlier_count > candidate.scan_count
      || !['rmse_m', 'full_scan_rmse_m', 'capped_full_rmse_m', 'overlap',
        'geometry_min_max_eigen_ratio', 'inlier_geometry_min_max_eigen_ratio']
        .every(key => finiteNonnegative(candidate[key]))
      || candidate.overlap < .60 || candidate.overlap > 1
      || candidate.geometry_min_max_eigen_ratio < .002
      || candidate.inlier_geometry_min_max_eigen_ratio < .002) return false;
  return ambiguityRigid(candidate.map_from_scan);
}

export function validatedAmbiguityMetadata(override) {
  return override?.enabled === true && override.applied === true
    && Object.keys(override).sort().join(',')
      === 'applied,enabled,original_gate_reasons,original_selected_candidate,selection_rule'
    && override.selection_rule === 'LOWEST_RMSE_M_THEN_ORIGINAL_INDEX'
    && override.original_selected_candidate === null
    && ambiguityOnly(override.original_gate_reasons);
}

export function validatedAmbiguityOverride(observation) {
  const override = observation?.ambiguity_override, selected = observation?.selected_candidate;
  if (!validatedAmbiguityMetadata(override)
      || !ambiguityOnly(observation.gate_reasons)
      || observation.estimate_label !== 'AMBIGUOUS_UNVERIFIED_ESTIMATE'
      || !Array.isArray(observation.candidates)
      || !Number.isInteger(selected) || selected < 0 || selected >= observation.candidates.length) return false;
  const eligible = observation.candidates.map((candidate, index) => ({ candidate, index }))
    .filter(({ candidate }) => ambiguityEligible(candidate));
  if (!eligible.length) return false;
  eligible.sort((a, b) => a.candidate.rmse_m - b.candidate.rmse_m || a.index - b.index);
  return eligible[0].index === selected;
}
export function globalObservationRequestId() {
  // Robot dashboards are commonly served on a LAN HTTP address where
  // randomUUID is unavailable, while getRandomValues remains supported.
  const bytes = new Uint8Array(16); globalThis.crypto.getRandomValues(bytes);
  return `global-${Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')}`;
}
const restricted = value => value?.historical_only === true && value.current_result === null
  && value.body_pose === null && value.tracking_verified === false
  && value.body_pose_verified === false && value.body_extrinsic_verified === false
  && value.operational_application === 'NOT_RUN' && value.absolute_accuracy_m === null;

export function globalMapIdentity(meta, cloud) {
  if (!idPattern.test(meta?.id || '') || !revisionPattern.test(meta?.revision || '')
      || meta.kind !== 'pointcloud3d') return null;
  const frame = cloud?.frame_id || meta.frame_id;
  if (typeof frame !== 'string' || !frame || (cloud?.revision && cloud.revision !== meta.revision)
      || (meta.frame_id && cloud?.frame_id && meta.frame_id !== cloud.frame_id)) return null;
  return { map_id: meta.id, map_revision: meta.revision, map_frame: frame };
}

export function globalSourceIdentity(cloud) {
  const o = cloud?.observation;
  if (!cloud?.frame_id || !cloud?.topic || !o?.observer_id || !o?.publisher_epoch) return null;
  return { source_frame: cloud.frame_id, source_topic: cloud.topic,
    observer_id: o.observer_id, observer_epoch: o.publisher_epoch };
}

function validContext(context, map, source) {
  if (!context || !map || !Object.keys(map).every(key => context[key] === map[key])
      || !stampPattern.test(context.source_stamp_ns || '') || typeof context.source_stamp_ns !== 'string') return false;
  if (!['source_frame', 'observer_id', 'observer_epoch'].every(key => typeof context[key] === 'string' && context[key])) return false;
  // A UI stream may be absent: the server still owns all capture/completion
  // fences. When present it supplies an additional independent client fence.
  return !source || Object.keys(source).every(key => key === 'source_topic'
    ? !context.source_topic || context.source_topic === source[key] : context[key] === source[key]);
}

function sameJsonValue(left, right) {
  if (left === null || right === null || typeof left !== 'object' || typeof right !== 'object') return left === right;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right)
    && left.length === right.length && left.every((value, index) => sameJsonValue(value, right[index]));
  const keys = Object.keys(left);
  // JSON object key order is not part of the capture identity; every key,
  // nested value, primitive type and array position still has to match.
  return keys.length === Object.keys(right).length
    && keys.every(key => Object.hasOwn(right, key) && sameJsonValue(left[key], right[key]));
}

export function validateGlobalJob(job, map, source = null) {
  if (job?.schema !== JOB_SCHEMA || !idPattern.test(job.job_id || '') || !restricted(job)
      || !Number.isSafeInteger(job.generation) || !['capturing', 'running', ...terminal].includes(job.state)
      || typeof job.worker_active !== 'boolean' || typeof job.request_id !== 'string') return false;
  if (job.captured_context !== null && !validContext(job.captured_context, map, source)) return false;
  if (job.state !== 'succeeded') return job.result === null;
  const result = job.result;
  return restricted(result) && result.schema === 'robot-scope.raw-global-observation-result.v1'
    && result.job_id === job.job_id && result.generation === job.generation
    && validContext(result.captured_context, map, source)
    && sameJsonValue(result.captured_context, job.captured_context)
    && result.observation && typeof result.observation === 'object' && !Array.isArray(result.observation);
}

function validHistoricalJob(job, map, source) {
  return validateGlobalJob(job, map, source) && terminal.has(job.state) && job.worker_active === false
    && (!Object.hasOwn(job, 'map_id') || job.map_id === map?.map_id)
    && (!Object.hasOwn(job, 'map_revision') || job.map_revision === map?.map_revision)
    && (job.captured_context !== null || (job.map_id === map?.map_id && job.map_revision === map?.map_revision));
}

export class GlobalObservationController {
  constructor({ request = (...args) => fetch(...args), changed = () => {}, requestId = globalObservationRequestId,
    canChangeHistory = () => true } = {}) {
    this.request = request; this.changed = changed; this.requestId = requestId;
    this.canChangeHistory = canChangeHistory;
    this.map = null; this.source = null; this.provider = null; this.generation = 0;
    this.pending = null; this.job = null; this.record = null; this.error = '';
    this.busy = false; this.reading = false; this.cancelling = false; this.foreignBusy = false;
    this.history = []; this.historyJob = null; this.historyBusy = false;
    this.historicalSelection = null; this.historyReadToken = 0; this.serverGeneration = null;
    this.disposed = false;
  }
  setMap(meta, cloud) {
    const map = globalMapIdentity(meta, cloud);
    if (JSON.stringify(map) !== JSON.stringify(this.map)) { this.invalidate('MAP_CHANGED'); this.map = map; }
  }
  ingestCloud(cloud) {
    const source = globalSourceIdentity(cloud);
    if (this.source && JSON.stringify(source) !== JSON.stringify(this.source)) this.invalidate('SOURCE_CHANGED');
    this.source = source;
  }
  invalidate(reason = 'CONTEXT_CHANGED') {
    const hadHistorical = Boolean(this.historicalSelection || this.historyBusy);
    this.generation++; this.record = null;
    this.historyReadToken++; this.historyJob = null; this.historicalSelection = null; this.history = [];
    if (hadHistorical && !this.job?.worker_active) this.job = null;
    if (this.pending || this.job?.worker_active || hadHistorical) this.error = reason;
    if (this.pending) this.pending.invalidated = true;
    if (this.job?.worker_active) void this.cancel(false);
    this.changed();
  }
  snapshot() {
    const historyLocked = !this.historyChangeAllowed();
    return { map: this.map, provider: this.provider, job: this.job, record: this.record,
      history: clone(this.history), historyBusy: this.historyBusy, historyLocked, historicalSelection: this.historicalSelection,
      historicalCurrentGeneration: Boolean(this.historyJob && this.historyJob.generation === this.serverGeneration),
      historicalTrackingEligible: Boolean(this.historicalSelection && this.record),
      displayJob: this.historicalSelection ? this.historyJob : this.job,
      displayRecord: this.historicalSelection ? (this.historyJob?.state === 'succeeded' ? this.historyJob : null) : this.record,
      canOpenHistorical: !historyLocked && !this.disposed && Boolean(this.map) && !this.historyBusy && !this.reading
        && !this.busy && !this.foreignBusy && !this.job?.worker_active && !this.pending,
      error: this.error, busy: this.busy || this.historyBusy || this.foreignBusy || Boolean(this.job?.worker_active),
      canStart: !this.disposed && Boolean(this.map) && this.provider?.available === true
        && !this.busy && !this.historyBusy && !this.foreignBusy && !this.job?.worker_active && !this.pending,
      canRetry: Boolean(this.pending && !this.pending.invalidated && !this.job && !this.busy),
      canCancel: Boolean(this.job?.worker_active && !this.cancelling),
      uncertain: Boolean(this.pending && !this.job && !this.busy) };
  }
  async json(path, options = {}) {
    const response = await this.request(path, { ...options, signal: AbortSignal.timeout(10000) });
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `HTTP ${response.status}`);
    return value;
  }
  async start() {
    if (!this.snapshot().canStart && !this.snapshot().canRetry) return;
    this.historyReadToken++; this.historyJob = null; this.historicalSelection = null;
    if (!this.pending) this.pending = { request_id: this.requestId(), ...this.map,
      generation: this.generation, source: clone(this.source), invalidated: false };
    const pending = this.pending;
    this.busy = true; this.error = ''; this.record = null; this.changed();
    try {
      const job = await this.json(ROOT, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: pending.request_id, map_id: pending.map_id, map_revision: pending.map_revision }) });
      await this.accept(job, pending);
    } catch (error) { this.error = `요청 결과 미확인 · ${error.message} · 기존 request_id 조회 후 재확인`; }
    finally { this.busy = false; this.changed(); }
  }
  async accept(job, pending = this.pending) {
    if (!pending || job?.request_id !== pending.request_id) return;
    if (!idPattern.test(job.job_id || '')) { this.error = 'RESULT_CONTRACT_MISMATCH'; return; }
    if (pending.invalidated || pending.generation !== this.generation || this.disposed) {
      this.job = { ...clone(job), result: null }; this.record = null;
      if (job.worker_active) { if (!pending.cancelSent) await this.cancel(false); }
      else { this.pending = null; this.job = null; }
      return;
    }
    const map = { map_id: pending.map_id, map_revision: pending.map_revision, map_frame: pending.map_frame };
    if (!validateGlobalJob(job, map, pending.source)
        || (this.job?.job_id === job.job_id && this.job.generation !== job.generation)) {
        this.error = 'RESULT_CONTRACT_MISMATCH'; this.record = null;
        pending.invalidated = true;
        this.job = { ...clone(job), result: null };
        if (job.worker_active) await this.cancel(false);
        else this.pending = null;
        return;
    }
    this.job = clone(job); this.error = '';
    this.record = job.state === 'succeeded' ? clone(job) : null;
    if (!job.worker_active && terminal.has(job.state)) this.pending = null;
  }
  async poll() {
    if (this.reading || this.historyBusy || this.disposed) return;
    this.reading = true;
    const knownJob = this.job?.job_id;
    try {
      const status = await this.json(ROOT);
      if (status.schema !== 'robot-scope.raw-global-observations.v1' || !restricted(status)
          || typeof status.provider?.available !== 'boolean'
          || !Number.isSafeInteger(status.generation) || status.generation < 0) throw new Error('STATUS_CONTRACT_MISMATCH');
      this.provider = clone(status.provider);
      this.serverGeneration = status.generation;
      this.updateHistory(status.latest);
      if (knownJob && knownJob === this.record?.job_id && status.generation !== this.record.generation) this.record = null;
      if (knownJob && knownJob === this.job?.job_id && this.pending && status.generation !== this.job.generation
          && !this.pending.invalidated) this.invalidate('SERVER_GENERATION_CHANGED');
      this.foreignBusy = Boolean(status.active?.worker_active && status.active.request_id !== this.pending?.request_id
        && status.active.job_id !== this.job?.job_id);
      if (this.historicalSelection && (status.closed !== false || status.active !== null)) this.record = null;
      const match = [status.active, status.latest].find(job => job && job.request_id === this.pending?.request_id);
      if (match) await this.accept(match);
      else if (this.job?.worker_active && this.pending) await this.accept(await this.json(`${ROOT}/${this.job.job_id}`));
    } catch (error) { this.provider = null; this.history = [];
      if (this.historicalSelection) this.record = null;
      this.error = `조회 실패 · ${error.message}`; }
    finally { this.reading = false; this.changed(); }
  }
  updateHistory(latest = null) {
    const jobs = [latest, this.historyJob].filter((value, index, values) => value
      && values.findIndex(other => other?.job_id === value.job_id) === index
      && validHistoricalJob(value, this.map, this.source));
    this.history = jobs.map(value => ({ job_id: value.job_id, request_id: value.request_id,
      generation: value.generation, state: value.state, capture_age_s: value.capture_age_s,
      captured_context: clone(value.captured_context) }));
  }
  historyChangeAllowed() {
    // A composed sensor controller may still consume the current record. A
    // read-only history action must never invalidate that active/pending owner.
    try { return this.canChangeHistory() === true; } catch { return false; }
  }
  clearHistoricalSelection() {
    // This is local display invalidation only: never cancel an owned/uncertain job.
    if (!this.historyChangeAllowed() || this.pending || this.busy || this.job?.worker_active) return;
    this.historyReadToken++; this.historyJob = null; this.historicalSelection = null;
    this.record = null; this.job = null; this.error = ''; this.changed();
  }
  async openHistorical(jobId) {
    if (!this.snapshot().canOpenHistorical) return;
    const expected = clone(this.history.find(value => value.job_id === jobId));
    const token = ++this.historyReadToken, generation = this.generation;
    const map = clone(this.map), source = clone(this.source);
    this.historyBusy = true; this.historyJob = null; this.historicalSelection = null;
    this.record = null; this.job = null; this.error = ''; this.changed();
    const current = () => !this.disposed && token === this.historyReadToken && generation === this.generation;
    try {
      if (!idPattern.test(jobId || '')) throw new Error('HISTORY_JOB_ID_INVALID');
      const job = await this.json(`${ROOT}/${jobId}`);
      if (!current()) return;
      if (job?.job_id !== jobId || !validateGlobalJob(job, map, source)) throw new Error('RESULT_CONTRACT_MISMATCH');
      if (!terminal.has(job.state) || job.worker_active !== false) throw new Error('HISTORY_JOB_NOT_TERMINAL_OR_CLEAN');
      if (!validHistoricalJob(job, map, source)) throw new Error('HISTORY_MAP_MISMATCH');
      if (expected && (job.request_id !== expected.request_id || job.generation !== expected.generation
          || !sameJsonValue(job.captured_context, expected.captured_context))) throw new Error('HISTORY_IDENTITY_CHANGED');
      const status = await this.json(ROOT);
      if (!current()) return;
      if (!this.historyChangeAllowed()) throw new Error('HISTORY_SELECTION_IN_USE');
      if (status.schema !== 'robot-scope.raw-global-observations.v1' || !restricted(status)
          || typeof status.provider?.available !== 'boolean'
          || !Number.isSafeInteger(status.generation) || status.generation < 0) throw new Error('STATUS_CONTRACT_MISMATCH');
      const listed = [status.active, status.latest].find(value => value?.job_id === jobId);
      if (listed && (!validateGlobalJob(listed, map, source) || listed.request_id !== job.request_id
          || listed.generation !== job.generation || !sameJsonValue(listed.captured_context, job.captured_context)))
        throw new Error('HISTORY_IDENTITY_CHANGED');
      // The first live source can arrive while an initially source-less read is
      // in flight. Validate again instead of relying only on generation changes.
      if (!validHistoricalJob(job, this.map, this.source)) throw new Error('HISTORY_CURRENT_CONTEXT_MISMATCH');
      this.serverGeneration = status.generation; this.provider = clone(status.provider);
      this.foreignBusy = Boolean(status.active?.worker_active);
      this.historyJob = clone(job); this.historicalSelection = jobId; this.job = clone(job);
      // Keep the original server-generation fence on the tracking handoff.
      // A different generation is still viewable only through displayRecord.
      this.record = job.state === 'succeeded' && status.generation === job.generation
        && status.closed === false && status.active === null ? clone(job) : null;
      this.updateHistory(status.latest);
    } catch (error) {
      if (current()) { this.record = null; this.job = null; this.historyJob = null; this.historicalSelection = null;
        this.error = `과거 결과 조회 실패 · ${error.message}`; }
    } finally { this.historyBusy = false; this.changed(); }
  }
  async cancel(explicit = true) {
    if (explicit) { this.generation++; this.record = null; if (this.pending) this.pending.invalidated = true; }
    if (!this.job?.job_id || this.cancelling) { this.changed(); return; }
    const id = this.job.job_id; this.cancelling = true; this.changed();
    if (this.pending) this.pending.cancelSent = true;
    try {
      const job = await this.json(`${ROOT}/${id}/cancel`, { method: 'POST' });
      if (job.job_id !== id || !restricted(job)) throw new Error('CANCEL_CONTRACT_MISMATCH');
      this.job = { ...clone(job), result: null }; this.record = null;
      if (!job.worker_active) this.pending = null;
    } catch (error) { this.error = `취소 결과 미확인 · ${error.message} · 작업 조회 유지`; }
    finally { this.cancelling = false; this.changed(); }
  }
  destroy() { this.invalidate('VIEW_DISPOSED'); this.disposed = true; }
}
