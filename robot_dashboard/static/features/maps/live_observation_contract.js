// Display estimates only. No registration solver, ROS writes, or motion controls.
import { identity, isRigidTransform, multiply, matrixPose, transformPoints } from '../experiments/recorded_report.js';

const finite = v => typeof v === 'number' && Number.isFinite(v);
const fastlioImu = p => p?.topic === '/Odometry' && p.frame_id === 'camera_init' && p.child_frame_id === 'body';
const exactStamp = v => typeof v === 'string' && /^[1-9][0-9]{0,19}$/.test(v);
const ORIGINAL_POLICY_ID = 'robot-scope.residual-policy.original-0.05m.v1';
const PROVISIONAL_POLICY_ID = 'robot-scope.residual-policy.provisional-0.10m.v1';
const policyFields = Object.freeze({ source_policy_id: ORIGINAL_POLICY_ID, original_max_rmse_m: .05,
  unit: 'm', evaluation_scope: 'STORED_RMSE_ONLY', observation_only: true, no_accuracy_claim: true, accuracy_verified: false });
const qualificationFields = ['residual_evaluation', 'original_assessment', 'gate_reasons', 'provisional', 'candidate_kind', 'body_pose', 'tracking_verified'];
function exactFields(value, expected) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, item]) => value[key] === item);
}
function validPolicy(value, provisional) {
  return exactFields(value, { ...policyFields, policy_id: provisional ? PROVISIONAL_POLICY_ID : ORIGINAL_POLICY_ID,
    max_rmse_m: provisional ? .10 : .05, provisional,
    qualifier: provisional ? 'PROVISIONAL_RESIDUAL_ONLY' : 'ORIGINAL_RESIDUAL_ONLY' });
}
// Residual metadata cannot grant candidate acceptance. The independent numeric
// gates and every source/lifecycle fence below still apply to the live wrapper.
function observationQualification(value, candidate) {
  if (!qualificationFields.some(key => Object.hasOwn(value, key))) return { valid: true, provisional: false };
  const m = value.metrics, e = value.residual_evaluation, original = value.original_assessment;
  const activeCandidate = value.status === candidate;
  if (!qualificationFields.every(key => Object.hasOwn(value, key)) || value.provisional !== true
      || value.candidate_kind !== 'PROVISIONAL_OBSERVATION_HYPOTHESIS' || value.body_pose !== null
      || value.tracking_verified !== false || value.body_pose_verified !== false || value.body_extrinsic_verified !== false
      || value.absolute_accuracy_m !== null || !['CANDIDATE', 'REJECTED'].includes(original?.status)
      || typeof original.reason !== 'string' || !original.reason || original.max_rmse_m !== .05
      || (original.status === 'CANDIDATE') !== (original.reason === 'CANDIDATE')
      || !Array.isArray(value.gate_reasons) || !value.gate_reasons.every(reason => typeof reason === 'string' && /^[A-Z][A-Z0-9_]{0,99}$/.test(reason))
      || new Set(value.gate_reasons).size !== value.gate_reasons.length
      || ![candidate, 'REJECTED'].includes(value.status) || activeCandidate !== (value.gate_reasons.length === 0)) return { valid: false };
  if (e === null) return { valid: !activeCandidate && m?.rmse_m === null && original.status === 'REJECTED', provisional: true };
  if (!e || typeof e !== 'object' || Array.isArray(e) || Object.keys(e).length !== 7
      || !finite(m?.rmse_m) || m.rmse_m < 0 || e.rmse_m !== m.rmse_m
      || !validPolicy(e.policy, true) || !validPolicy(e.original_policy, false)
      || e.residual_passed !== (m.rmse_m <= .10) || e.original_residual_passed !== (m.rmse_m <= .05)
      || e.overall_candidate_acceptance_evaluated !== false || e.overall_candidate_accepted !== null
      || (original.status === 'CANDIDATE' && !e.original_residual_passed)) return { valid: false };
  if (activeCandidate && (original.status !== (e.original_residual_passed ? 'CANDIDATE' : 'REJECTED')
      || original.reason !== (e.original_residual_passed ? 'CANDIDATE' : 'HIGH_RESIDUAL'))) return { valid: false };
  return { valid: true, provisional: true };
}
export const OBSERVATION_LIMITS = Object.freeze({ staleMs: 1000, pairSeconds: .15, maxPoints: 10000, jumpMetres: 1, jumpRadians: Math.PI / 3 });
export function inverseRigid(m) {
  if (!isRigidTransform(m)) throw new Error('INVALID_TRANSFORM');
  const r = identity();
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) r[i][j] = m[j][i];
    r[i][3] = -r[i].slice(0, 3).reduce((sum, x, j) => sum + x * m[j][3], 0);
  }
  return r;
}
export function rpyMatrix(p) {
  if (!['x', 'y', 'z', 'roll', 'pitch', 'yaw'].every(k => finite(p?.[k]))) throw new Error('INVALID_POSE');
  const [sr, cr, sp, cp, sy, cy] = [Math.sin(p.roll), Math.cos(p.roll), Math.sin(p.pitch), Math.cos(p.pitch), Math.sin(p.yaw), Math.cos(p.yaw)];
  const m = [[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, p.x],
    [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, p.y],
    [-sp, cp * sr, cp * cr, p.z], [0, 0, 0, 1]];
  if (!isRigidTransform(m)) throw new Error('INVALID_POSE');
  return m;
}
export function odometryMatrix(p) {
  const q = p?.orientation, t = p?.position;
  if (!q || !t || !['x', 'y', 'z', 'w'].every(k => finite(q[k])) || !['x', 'y', 'z'].every(k => finite(t[k]))) throw new Error('INVALID_ODOMETRY');
  const n = Math.hypot(q.x, q.y, q.z, q.w);
  if (Math.abs(n - 1) > .01) throw new Error('INVALID_QUATERNION');
  const [x, y, z, w] = [q.x / n, q.y / n, q.z / n, q.w / n];
  const m = [[1 - 2 * (y*y + z*z), 2*(x*y-z*w), 2*(x*z+y*w), t.x],
    [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w), t.y],
    [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y), t.z], [0,0,0,1]];
  if (!isRigidTransform(m)) throw new Error('INVALID_ODOMETRY');
  return m;
}
function subscriptionGraphAge(value) {
  return (value?.observation?.received_monotonic_s - value?.observation?.subscription_evidence?.graph?.observed_monotonic_s) * 1000;
}
function subscriptionKey(s, kind) {
  const o = s?.observation, e = o?.subscription_evidence, g = e?.graph, endpoint = g?.endpoints?.[0];
  const type = kind === 'pose' ? 'nav_msgs/msg/Odometry' : 'sensor_msgs/msg/PointCloud2';
  const qos = value => value && ['RELIABLE', 'BEST_EFFORT'].includes(value.reliability)
    && ['VOLATILE', 'TRANSIENT_LOCAL'].includes(value.durability) && ['KEEP_LAST', 'KEEP_ALL'].includes(value.history)
    && Number.isSafeInteger(value.depth) && value.depth >= 0;
  const graphAge = subscriptionGraphAge(s);
  if (!o?.observer_id || !o.publisher_epoch || !exactStamp(o.source_stamp_ns)
      || !finite(o.received_monotonic_s) || o.receipt_clock !== 'OBSERVER_HOST_MONOTONIC'
      || !Number.isSafeInteger(s.seq) || s.seq <= 0 || !s.topic || !s.frame_id || o.invalidated || o.reset_reason === 'SOURCE_STAMP_STALLED'
      || e?.schema !== 'robot-scope.subscription-observation.v1' || !/^[0-9a-f]{32}$/.test(e.session_id || '')
      || e.topic !== s.topic || !e.topic.startsWith('/') || e.type_name !== type || !qos(e.subscription_qos)
      || e.per_message_publisher_verified !== false || e.identity_basis !== 'LOCAL_SUBSCRIPTION_AND_ROS_GRAPH_ONLY'
      || g?.state !== 'ok' || !finite(g.observed_monotonic_s) || !finite(graphAge) || graphAge < 0 || graphAge > 3000
      || g.endpoint_count !== 1 || g.reported_publisher_count !== 1 || !Array.isArray(g.endpoints) || g.endpoints.length !== 1
      || !/^[0-9a-f]{64}$/.test(g.fingerprint || '') || typeof endpoint?.node_name !== 'string' || !endpoint.node_name
      || typeof endpoint.node_namespace !== 'string' || !endpoint.node_namespace
      || endpoint.topic_type !== type || !/^(?:[0-9a-f]{32}|[0-9a-f]{48})$/.test(endpoint.endpoint_gid || '') || /^0+$/.test(endpoint.endpoint_gid)
      || !qos(endpoint.qos)) throw new Error('SOURCE_IDENTITY_UNAVAILABLE');
  return JSON.stringify([o.observer_id, o.publisher_epoch, e.session_id, e.topic, s.frame_id, s.child_frame_id || '',
    e.type_name, e.subscription_qos, g.fingerprint]);
}
function sourceKey(s, mode = 'native_publisher', kind) {
  if (mode === 'subscription_observation') return subscriptionKey(s, kind);
  const o = s?.observation;
  if (o?.identity_status !== 'OBSERVED_PUBLISHER' || o.publisher_count !== 1 || !o.publisher_gid
      || !o.observer_id || !o.publisher_epoch || !exactStamp(o.source_stamp_ns)
      || !finite(o.received_monotonic_s) || o.receipt_clock !== 'OBSERVER_HOST_MONOTONIC'
      || !Number.isSafeInteger(s.seq) || s.seq <= 0
      || !s.topic || !s.frame_id || o.invalidated) throw new Error('SOURCE_IDENTITY_UNAVAILABLE');
  return JSON.stringify([o.observer_id, o.publisher_epoch, o.publisher_gid, s.topic, s.frame_id, s.child_frame_id || '']);
}
function jump(a, b) {
  const d = multiply(inverseRigid(a), b);
  const angle = Math.acos(Math.max(-1, Math.min(1, (d[0][0]+d[1][1]+d[2][2]-1)/2)));
  return Math.hypot(d[0][3], d[1][3], d[2][3]) > OBSERVATION_LIMITS.jumpMetres || angle > OBSERVATION_LIMITS.jumpRadians;
}

// Metadata for explaining receipt is separate from inputs accepted for geometry.
// Never keep points, transforms or native position/orientation in this summary.
function telemetryMetadata(value, kind, arrived) {
  const o = value?.observation || {}, e = o.subscription_evidence, text = v => typeof v === 'string' ? v.slice(0, 160) : '';
  return {
    topic: text(value?.topic), frame_id: text(value?.frame_id), child_frame_id: text(value?.child_frame_id),
    seq: Number.isSafeInteger(value?.seq) && value.seq > 0 ? value.seq : null,
    state: kind === 'pose' ? text(value?.state) : value?.points?.length ? 'received' : 'waiting',
    point_count: kind === 'cloud' ? Math.max(0, Math.floor((value?.points?.length || 0) / 3)) : null,
    source_stamp_ns: exactStamp(o.source_stamp_ns) ? o.source_stamp_ns : null,
    identity_status: text(o.identity_status) || 'UNAVAILABLE', publisher_gid_present: Boolean(o.publisher_gid),
    publisher_count: Number.isSafeInteger(o.publisher_count) ? o.publisher_count : null,
    observer_id: text(o.observer_id), publisher_epoch: text(o.publisher_epoch), invalidated: o.invalidated === true,
    subscription_session_id: text(e?.session_id), graph_fingerprint: text(e?.graph?.fingerprint),
    graph_state: text(e?.graph?.state), graph_endpoint_count: Number.isSafeInteger(e?.graph?.endpoint_count) ? e.graph.endpoint_count : null,
    age_s: kind === 'pose' && finite(value?.age_s) && value.age_s >= 0 ? value.age_s : 0,
    arrived_ms: arrived,
  };
}
function telemetrySource(summary) {
  return JSON.stringify([summary.topic, summary.frame_id, summary.child_frame_id,
    summary.observer_id, summary.publisher_epoch, summary.publisher_count, summary.subscription_session_id, summary.graph_fingerprint]);
}

export class LiveMapObservation {
  constructor(now = () => performance.now()) {
    this.now = now; this.map = null; this.enabled = false; this.anchor = null;
    this.pose = null; this.cloud = null; this.history = []; this.trail = [];
    this.reason = 'OFF'; this.generation = 0; this.geometryCache = null; this.samples = [];
    this.registration = null; this.registrationEnabled = false;
    this.provenanceMode = 'native_publisher';
    this.continuousEstimate = false;
    this.alignmentRevision = 0;
    this.telemetrySummary = { pose: null, cloud: null };
    this.telemetryReceipt = { pose: null, cloud: null };
  }
  enable(value) {
    this.enabled = Boolean(value); this.invalidate(value ? 'NO_ANCHOR' : 'OFF');
    this.pose = null; this.cloud = null; this.history = [];
  }
  setProvenanceMode(mode) {
    if (!['native_publisher', 'subscription_observation'].includes(mode)) throw new Error('INVALID_PROVENANCE_MODE');
    if (mode === this.provenanceMode) return;
    this.provenanceMode = mode; this.registrationEnabled = false; this.resetInputs('PROVENANCE_MODE_CHANGED');
  }
  setContinuousEstimate(value) {
    this.continuousEstimate = Boolean(value);
    this.invalidate('NO_ANCHOR');
  }
  invalidate(reason, keepTelemetry = false) {
    this.anchor = null; this.reason = reason; this.trail = []; this.samples = []; this.geometryCache = null; this.registration = null; this.generation++;
    if (!keepTelemetry) this.telemetrySummary = { pose: null, cloud: null };
  }
  resetInputs(reason) { this.invalidate(reason); this.pose = null; this.cloud = null; this.history = []; }
  rememberTelemetry(kind, value) {
    const next = telemetryMetadata(value, kind, this.now()), previous = this.telemetrySummary[kind];
    const source = telemetrySource(next), receipt = this.telemetryReceipt[kind];
    if (receipt?.source === source && next.seq !== null && receipt.seq !== null && next.seq <= receipt.seq) {
      // Keep the receipt fence after clear/disable so cached snapshots cannot
      // revive hidden diagnostics or become a new freshness window.
      if (previous && next.seq === receipt.seq) {
        if (next.state === 'stale') previous.state = 'stale';
        if (next.invalidated) previous.invalidated = true;
      }
      return;
    }
    if (previous && telemetrySource(previous) !== source) this.telemetrySummary = { pose: null, cloud: null };
    this.telemetryReceipt[kind] = { source, seq: next.seq };
    this.telemetrySummary[kind] = next;
  }
  telemetrySnapshot() {
    return Object.fromEntries(['pose', 'cloud'].map(kind => {
      const value = this.telemetrySummary[kind];
      if (!value) return [kind, null];
      const { arrived_ms, age_s, ...metadata } = value;
      const age_ms = age_s * 1000 + Math.max(0, this.now() - arrived_ms);
      const freshness = value.invalidated ? 'INVALIDATED' : value.state === 'stale' || age_ms > OBSERVATION_LIMITS.staleMs
        ? 'STALE' : ['ok', 'received'].includes(value.state) ? 'RECEIVED' : 'WAITING';
      return [kind, { ...metadata, age_ms, freshness }];
    }));
  }
  setMap(meta, loaded) {
    const next = meta?.kind === 'pointcloud3d' && meta.id && meta.revision && loaded?.points?.length
      && !loaded.demo_snapshot && loaded.revision === meta.revision
      ? { id: meta.id, revision: meta.revision, frame: loaded.frame_id,
        name: meta.name, point_count: meta.point_count, saved_at: meta.modified_at } : null;
    if (JSON.stringify(next) !== JSON.stringify(this.map)) this.invalidate('MAP_CHANGED');
    this.map = next;
  }
  ingestPose(value) {
    if (!this.enabled) return;
    try {
      const key = sourceKey(value, this.provenanceMode, 'pose'), matrix = odometryMatrix(value);
      if (value.child_frame_id !== 'base_link' && !fastlioImu(value)) throw new Error('BODY_FRAME_UNAVAILABLE');
      if (value.state !== 'ok' || !finite(value.age_s) || value.age_s < 0 || value.age_s > 1) throw new Error('POSE_STALE');
      const last = this.pose;
      if (last?.key === key && value.seq <= last.value.seq) return; // late snapshot cannot renew freshness
      if (last && last.key !== key) { this.invalidate('POSE_SOURCE_CHANGED'); this.history = []; }
      if (last?.key === key && BigInt(value.observation.source_stamp_ns) < BigInt(last.value.observation.source_stamp_ns)) this.invalidate('POSE_TIME_REVERSED');
      if (last?.key === key && jump(last.matrix, matrix)) this.invalidate('POSE_JUMP');
      this.pose = { value, key, matrix, arrived: this.now() };
      this.history.push(this.pose); this.history = this.history.slice(-80);
    } catch (error) { this.pose = null; this.history = []; this.invalidate(error.message, true); }
    finally { this.rememberTelemetry('pose', value); }
  }
  ingestCloud(value) {
    if (!this.enabled) return;
    try {
      const key = sourceKey(value, this.provenanceMode, 'cloud');
      if (!value.points?.length || value.points.length % 3 || value.units !== 'm') throw new Error('CLOUD_INVALID');
      if (this.cloud?.key === key && value.seq <= this.cloud.value.seq) return;
      if (this.cloud && this.cloud.key !== key) this.invalidate('CLOUD_SOURCE_CHANGED');
      if (this.cloud?.key === key && BigInt(value.observation.source_stamp_ns) < BigInt(this.cloud.value.observation.source_stamp_ns)) this.invalidate('CLOUD_TIME_REVERSED');
      this.cloud = { value, key, arrived: this.now() }; this.geometryCache = null;
    } catch (error) { this.cloud = null; this.invalidate(error.message, true); }
    finally { this.rememberTelemetry('cloud', value); }
  }
  pair() {
    const cloud = this.cloud?.value;
    if (!cloud) throw new Error('WAITING_CLOUD');
    const imu = fastlioImu(this.pose?.value);
    // Registered points already live in O. Continuous display needs T_M_O
    // for them and a fresh independent pose for T_M_O * T_O_F(now), not a
    // scan-time pose that may have been skipped by browser stream sampling.
    // The backend still requires exact FAST-LIO stamps for every correction.
    if (this.continuousEstimate && imu && cloud.topic === '/cloud_registered'
        && cloud.pipeline_stage === 'registered' && cloud.frame_id === this.pose.value.frame_id
        && cloud.observation.observer_id === this.pose.value.observation.observer_id) {
      return { paired: this.pose, pointsToOdom: identity(), kind: 'REGISTERED_CLOUD_FIXED_FRAME_UNVERIFIED',
        extrinsic: null, pair_method: 'REGISTERED_FRAME_INDEPENDENT_CURRENT_POSE',
        receipt_delta_s: this.pose.value.observation.received_monotonic_s - cloud.observation.received_monotonic_s,
        source_delta_ns: String(BigInt(this.pose.value.observation.source_stamp_ns) - BigInt(cloud.observation.source_stamp_ns)) };
    }
    const candidates = this.history.filter(p => p.value.observation.observer_id === cloud.observation.observer_id
      && p.key === this.pose?.key && (!imu || p.value.observation.source_stamp_ns === cloud.observation.source_stamp_ns));
    const paired = candidates.reduce((best, p) => !best || Math.abs(p.value.observation.received_monotonic_s - cloud.observation.received_monotonic_s)
      < Math.abs(best.value.observation.received_monotonic_s - cloud.observation.received_monotonic_s) ? p : best, null);
    if (!paired) throw new Error('WAITING_PAIRED_POSE');
    const delta = paired.value.observation.received_monotonic_s - cloud.observation.received_monotonic_s;
    if (Math.abs(delta) > OBSERVATION_LIMITS.pairSeconds) throw new Error('RECEIPT_TIME_MISMATCH');
    let pointsToOdom, kind, extrinsic = null;
    if (cloud.topic === '/cloud_registered' && cloud.pipeline_stage === 'registered' && cloud.frame_id === paired.value.frame_id) {
      pointsToOdom = identity(); kind = 'REGISTERED_CLOUD_FIXED_FRAME_UNVERIFIED';
    } else if ((cloud.topic === '/lidar_points' && cloud.pipeline_stage === 'raw' || cloud.topic === '/velodyne_points' && cloud.pipeline_stage === 'converted')
        && paired.value.child_frame_id === 'base_link' && cloud.robot_pose_in_frame?.source === 'configured_sensor_extrinsic'
        && cloud.robot_pose_in_frame.frame_id === cloud.frame_id) {
      extrinsic = rpyMatrix(cloud.robot_pose_in_frame);
      pointsToOdom = multiply(paired.matrix, inverseRigid(extrinsic)); kind = 'RAW_CLOUD_CONFIGURED_EXTRINSIC_UNVERIFIED';
    } else throw new Error('CLOUD_POSE_FRAME_RELATION_UNAVAILABLE');
    return { paired, pointsToOdom, kind, extrinsic, receipt_delta_s: delta,
      pair_method: imu ? 'FASTLIO_OUTPUT_STAMP_EXACT' : 'HOST_RECEIPT_NEAREST',
      source_delta_ns: String(BigInt(paired.value.observation.source_stamp_ns) - BigInt(cloud.observation.source_stamp_ns)) };
  }
  ready() {
    if (!this.enabled) throw new Error('OFF');
    if (!this.map) throw new Error('SELECT_SAVED_3D_MAP');
    if (!this.pose || !this.cloud) throw new Error(this.reason === 'OFF' ? 'WAITING_INPUTS' : this.reason);
    if (this.pose.value.age_s * 1000 + this.now() - this.pose.arrived > 1000 || this.now() - this.cloud.arrived > 1000) throw new Error('STALE');
    if (this.provenanceMode === 'subscription_observation' && [this.pose, this.cloud].some(input =>
      subscriptionGraphAge(input.value) + this.now() - input.arrived > 3000)) throw new Error('SUBSCRIPTION_GRAPH_STALE');
    const pair = this.pair(), paired = pair.paired;
    if (!finite(paired.value.age_s) || paired.value.age_s < 0
        || paired.value.age_s * 1000 + this.now() - paired.arrived > 1000) throw new Error('STALE');
    return pair;
  }
  setAnchor(target, confirmed) {
    if (confirmed !== true) throw new Error('OPERATOR_ESTIMATE_CONFIRMATION_REQUIRED');
    const pair = this.ready(), targetMatrix = rpyMatrix(target);
    this.generation++;
    this.anchor = { generation: this.generation, map: { ...this.map }, poseKey: this.pose.key, cloudKey: this.cloud.key,
      T_map_odom: multiply(targetMatrix, inverseRigid(this.pose.matrix)), target_pose: { ...target },
      pose_stamp_ns: this.pose.value.observation.source_stamp_ns, kind: pair.kind, extrinsic: pair.extrinsic,
      basis: 'OPERATOR_APPROXIMATE_DISPLAY_ANCHOR', accepted_registration: false, body_calibration_verified: false,
      tracked_frame: this.pose.value.child_frame_id, pose_topic: this.pose.value.topic,
      pose_reference: fastlioImu(this.pose.value) ? 'FASTLIO_IMU' : 'UNVERIFIED_BODY',
      continuous_estimate: this.continuousEstimate,
      provenance_mode: this.provenanceMode, per_message_publisher_verified: this.provenanceMode === 'native_publisher', body_extrinsic_verified: false };
    this.reason = this.provenanceMode === 'subscription_observation' ? 'ODOMETRY_PROPAGATED_SOURCE_UNVERIFIED' : 'ODOMETRY_PROPAGATED_UNVERIFIED'; this.trail = []; this.samples = []; this.geometryCache = null;
    this.registration = null;
  }
  snapshot() {
    const base = { enabled: this.enabled, status: this.reason, map: this.map, anchor: this.anchor,
      pose: null, points: null, trail: [], absolute_accuracy_m: null, map_registration: this.registration?.status || 'NOT_RUN',
      source_to_display_latency_ms: null, body_pose_verified: false, body_extrinsic_verified: false, body_pose: null, tracking_verified: false,
      provenance_mode: this.provenanceMode, per_message_publisher_verified: Boolean(this.provenanceMode === 'native_publisher' && this.pose && this.cloud), telemetry: this.telemetrySnapshot() };
    if (!this.enabled) return base;
    let pair;
    try { pair = this.ready(); } catch (e) {
      if (this.anchor && ['STALE', 'POSE_STALE', 'SUBSCRIPTION_GRAPH_STALE'].includes(e.message)) this.invalidate(e.message, true);
      return { ...base, anchor: this.anchor, status: e.message };
    }
    if (!this.anchor) return { ...base, canAnchor: true, status: this.reason === 'SOURCE_IDENTITY_UNAVAILABLE' ? 'NO_ANCHOR' : this.reason, pairing: pair.kind };
    if (this.anchor.poseKey !== this.pose.key || this.anchor.cloudKey !== this.cloud.key
        || this.anchor.kind !== pair.kind || JSON.stringify(this.anchor.extrinsic) !== JSON.stringify(pair.extrinsic)) {
      this.invalidate('SOURCE_CONTRACT_CHANGED'); return { ...base, anchor: null, status: this.reason };
    }
    const registrationStale = this.registration && (this.now() - this.registration.received > 2000
      || this.cloud.value.observation.received_monotonic_s - (this.registration.source?.received_monotonic_s ?? -Infinity) > 1);
    const candidate = this.provenanceMode === 'subscription_observation' ? 'CANDIDATE_SOURCE_UNVERIFIED' : 'CANDIDATE';
    const correctionUnavailable = this.registrationEnabled && (!this.registration || this.registration.status !== candidate || registrationStale);
    if (correctionUnavailable && !this.continuousEstimate) {
      return { ...base, canAnchor: true, status: this.registration
        ? `SCAN_TO_MAP_${registrationStale && this.registration.status === candidate ? 'STALE' : this.registration.status} · ${this.registration.reason}`
        : 'SCAN_TO_MAP_WAITING', registration: this.registration };
    }
    const pose = matrixPose(multiply(this.anchor.T_map_odom, this.pose.matrix), this.map.frame);
    const cacheKey = `${this.generation}:${this.alignmentRevision}:${this.cloud.value.seq}:${pair.paired.value.seq}`;
    if (this.geometryCache?.key !== cacheKey) {
      const flat = this.cloud.value.points, points = [];
      const stride = Math.max(1, Math.ceil(flat.length / 3 / OBSERVATION_LIMITS.maxPoints));
      for (let i = 0; i < flat.length; i += 3 * stride) points.push([flat[i], flat[i+1], flat[i+2]]);
      const transformed = transformPoints(points, multiply(this.anchor.T_map_odom, pair.pointsToOdom));
      if (!transformed.every(p => p.every(v => finite(v) && Math.abs(v) <= 1000))) {
        this.invalidate('OVERLAY_COORDINATE_LIMIT'); return { ...base, anchor: null, status: this.reason };
      }
      this.geometryCache = { key: cacheKey, points: transformed };
    }
    const last = this.trail.at(-1);
    if (!last || this.now() - last.received_ms >= 250) {
      this.trail.push({ ...pose, received_ms: this.now() }); this.trail = this.trail.slice(-400);
      this.samples.push({ pose, alignment_revision: this.alignmentRevision, source_stamp_ns: this.pose.value.observation.source_stamp_ns,
        cloud_stamp_ns: this.cloud.value.observation.source_stamp_ns, receipt_pair_delta_s: pair.receipt_delta_s,
        source_delta_ns: pair.source_delta_ns, clock_relation: 'UNVERIFIED', observed_browser_ms: this.now() });
      this.samples = this.samples.slice(-400);
    }
    const estimateStatus = this.anchor.accepted_registration
      ? (correctionUnavailable ? 'MAP_CORRECTION_UNAVAILABLE_ODOMETRY_CONTINUING' : 'MAP_CORRECTED_ESTIMATE_ACCURACY_UNVERIFIED')
      : 'SAME_START_ODOMETRY_ESTIMATE';
    return { ...base, status: this.continuousEstimate ? estimateStatus : this.provenanceMode === 'subscription_observation'
      ? (this.registrationEnabled ? 'SCAN_TO_MAP_CANDIDATE_SOURCE_UNVERIFIED' : 'ODOMETRY_PROPAGATED_SOURCE_UNVERIFIED')
      : (this.registrationEnabled ? 'SCAN_TO_MAP_CANDIDATE_UNVERIFIED' : 'ODOMETRY_PROPAGATED_UNVERIFIED'), canAnchor: true, pose,
      registration: this.registration,
      tracked_frame: this.anchor.tracked_frame, pose_reference: this.anchor.pose_reference,
      pair_method: pair.pair_method, pose_topic: this.pose.value.topic, odometry_frame: this.pose.value.frame_id,
      source_stamp_ns: this.pose.value.observation.source_stamp_ns,
      points: this.geometryCache.points, geometryKey: cacheKey, trail: this.trail,
      pairing: pair.kind, receipt_pair_delta_s: pair.receipt_delta_s, source_delta_ns: pair.source_delta_ns,
      pose_age_ms: this.now()-this.pose.arrived, cloud_age_ms: this.now()-this.cloud.arrived,
      cloud_receive_to_prepare_ms: this.now()-this.cloud.arrived };
  }
  alignmentRequest() {
    this.ready();
    if (!this.anchor) throw new Error('NO_ANCHOR');
    return { map_id: this.map.id, map_revision: this.map.revision, T_map_odom_seed: this.anchor.T_map_odom, provenance_mode: this.provenanceMode,
      observer_id: this.cloud.value.observation.observer_id,
      cloud_epoch: this.cloud.value.observation.publisher_epoch, pose_epoch: this.pose.value.observation.publisher_epoch };
  }
  applyAlignment(value, generation, requestedAt = this.now()) {
    if (generation !== this.generation || !this.anchor || !this.registrationEnabled) return false;
    const expected = this.alignmentRequest();
    const subscription = this.provenanceMode === 'subscription_observation', candidate = subscription ? 'CANDIDATE_SOURCE_UNVERIFIED' : 'CANDIDATE';
    if (value.schema !== 'robot-scope.observation-alignment.v1' || value.experimental !== true
        || value.operational_application !== 'NOT_RUN' || value.map_id !== expected.map_id
        || value.map_revision !== expected.map_revision || value.target_frame !== this.map.frame
        || ['observer_id', 'cloud_epoch', 'pose_epoch'].some(k => value.source?.[k] !== expected[k])
        || (value.provenance_mode != null && value.provenance_mode !== expected.provenance_mode)
        || (value.source?.provenance_mode != null && value.source.provenance_mode !== expected.provenance_mode)
        || (subscription && (value.provenance_mode !== expected.provenance_mode || value.source?.provenance_mode !== expected.provenance_mode
          || value.per_message_publisher_verified !== false || value.source?.per_message_publisher_verified !== false
          || value.body_pose_verified !== false || value.body_extrinsic_verified !== false || value.source?.body_extrinsic_verified !== false))) {
      this.alignmentFailed('RESULT_IDENTITY_MISMATCH', generation); return false;
    }
    if (!finite(requestedAt) || this.now() - requestedAt > 1000 || this.now() < requestedAt
        || !finite(value.source.received_monotonic_s)
        || Math.abs(this.cloud.value.observation.received_monotonic_s - value.source.received_monotonic_s) > 1) {
      this.alignmentFailed('RESULT_STALE', generation); return false;
    }
    const qualification = observationQualification(value, candidate);
    if (!qualification.valid) {
      this.alignmentFailed('RESULT_POLICY_MISMATCH', generation); return false;
    }
    this.registration = { ...value, received: requestedAt };
    if (value.status !== candidate) return false;
    const m = value.metrics;
    if (value.reason !== candidate || !isRigidTransform(value.T_map_odom) || m?.converged !== true
        || !finite(m.rmse_m) || m.rmse_m < 0 || m.rmse_m > (qualification.provisional ? .10 : .05) || !finite(m.overlap_ratio) || m.overlap_ratio < .60 || m.overlap_ratio > 1
        || !finite(m.geometry_min_max_eigen_ratio) || m.geometry_min_max_eigen_ratio < .002
        || !finite(m.matched_geometry_min_max_eigen_ratio) || m.matched_geometry_min_max_eigen_ratio < .002 || value.correspondence_gate_m !== .75
        || (qualification.provisional && (m.geometry_min_max_eigen_ratio > 1 || m.matched_geometry_min_max_eigen_ratio > 1
          || !Number.isSafeInteger(value.query_points) || value.query_points < 60 || value.query_points > 512
          || !Number.isSafeInteger(m.inlier_count) || m.inlier_count < 60 || m.inlier_count > value.query_points))) {
      this.alignmentFailed('RESULT_GATE_MISMATCH', generation); return false;
    }
    if (jump(multiply(this.anchor.T_map_odom, this.pose.matrix), multiply(value.T_map_odom, this.pose.matrix))) { this.invalidate('ALIGNMENT_JUMP'); return false; }
    this.anchor.T_map_odom = value.T_map_odom;
    this.anchor.accepted_registration = true;
    this.anchor.correction_source_stamp_ns = value.source.source_stamp_ns;
    this.alignmentRevision++;
    // Each correction defines a new display segment; do not join different map estimates.
    this.trail = []; this.samples = []; this.geometryCache = null;
    return true;
  }
  alignmentFailed(reason, generation) {
    if (generation === this.generation) this.registration = { status: 'UNAVAILABLE', reason, received: this.now() };
  }
  exportRecord() {
    const state = this.snapshot();
    return { schema: 'robot-scope.live-map-observation.v1', data_kind: 'OBSERVATION_ESTIMATE',
      generated_at: new Date().toISOString(), limits: OBSERVATION_LIMITS, map: state.map,
      anchor: state.anchor, status: state.status, map_registration: this.registration || 'NOT_RUN', absolute_accuracy_m: null,
      operational_application: 'NOT_RUN', body_pose_verified: false, body_pose: null, tracking_verified: false, samples: this.samples,
      provenance_mode: this.provenanceMode, per_message_publisher_verified: Boolean(this.provenanceMode === 'native_publisher' && this.pose && this.cloud), body_extrinsic_verified: false,
      source: { pose: this.pose?.value.observation || null, cloud: this.cloud?.value.observation || null } };
  }
}
