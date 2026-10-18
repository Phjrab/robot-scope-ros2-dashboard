// Display estimates only. No registration solver, ROS writes, or motion controls.
import { identity, isRigidTransform, multiply, matrixPose, transformPoints } from '../experiments/recorded_report.js';

const finite = v => typeof v === 'number' && Number.isFinite(v);
const exactStamp = v => typeof v === 'string' && /^[1-9][0-9]{0,19}$/.test(v);
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
function sourceKey(s) {
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

export class LiveMapObservation {
  constructor(now = () => performance.now()) {
    this.now = now; this.map = null; this.enabled = false; this.anchor = null;
    this.pose = null; this.cloud = null; this.history = []; this.trail = [];
    this.reason = 'OFF'; this.generation = 0; this.geometryCache = null; this.samples = [];
    this.registration = null; this.registrationEnabled = false;
    this.alignmentRevision = 0;
  }
  enable(value) {
    this.enabled = Boolean(value); this.invalidate(value ? 'NO_ANCHOR' : 'OFF');
    this.pose = null; this.cloud = null; this.history = [];
  }
  invalidate(reason) { this.anchor = null; this.reason = reason; this.trail = []; this.samples = []; this.geometryCache = null; this.registration = null; this.generation++; }
  resetInputs(reason) { this.invalidate(reason); this.pose = null; this.cloud = null; this.history = []; }
  setMap(meta, loaded) {
    const next = meta?.kind === 'pointcloud3d' && meta.id && meta.revision && loaded?.points?.length
      && !loaded.demo_snapshot && loaded.revision === meta.revision
      ? { id: meta.id, revision: meta.revision, frame: loaded.frame_id } : null;
    if (JSON.stringify(next) !== JSON.stringify(this.map)) this.invalidate('MAP_CHANGED');
    this.map = next;
  }
  ingestPose(value) {
    if (!this.enabled) return;
    try {
      const key = sourceKey(value), matrix = odometryMatrix(value);
      if (value.child_frame_id !== 'base_link') throw new Error('BODY_FRAME_UNAVAILABLE');
      if (value.state !== 'ok' || !finite(value.age_s) || value.age_s < 0 || value.age_s > 1) throw new Error('POSE_STALE');
      const last = this.pose;
      if (last?.key === key && value.seq <= last.value.seq) return; // late snapshot cannot renew freshness
      if (last && last.key !== key) { this.invalidate('POSE_SOURCE_CHANGED'); this.history = []; }
      if (last?.key === key && BigInt(value.observation.source_stamp_ns) < BigInt(last.value.observation.source_stamp_ns)) this.invalidate('POSE_TIME_REVERSED');
      if (last?.key === key && jump(last.matrix, matrix)) this.invalidate('POSE_JUMP');
      this.pose = { value, key, matrix, arrived: this.now() };
      this.history.push(this.pose); this.history = this.history.slice(-80);
    } catch (error) { this.pose = null; this.history = []; this.invalidate(error.message); }
  }
  ingestCloud(value) {
    if (!this.enabled) return;
    try {
      const key = sourceKey(value);
      if (!value.points?.length || value.points.length % 3 || value.units !== 'm') throw new Error('CLOUD_INVALID');
      if (this.cloud?.key === key && value.seq <= this.cloud.value.seq) return;
      if (this.cloud && this.cloud.key !== key) this.invalidate('CLOUD_SOURCE_CHANGED');
      if (this.cloud?.key === key && BigInt(value.observation.source_stamp_ns) < BigInt(this.cloud.value.observation.source_stamp_ns)) this.invalidate('CLOUD_TIME_REVERSED');
      this.cloud = { value, key, arrived: this.now() }; this.geometryCache = null;
    } catch (error) { this.cloud = null; this.invalidate(error.message); }
  }
  pair() {
    const cloud = this.cloud?.value;
    if (!cloud) throw new Error('WAITING_CLOUD');
    const candidates = this.history.filter(p => p.value.observation.observer_id === cloud.observation.observer_id
      && p.key === this.pose?.key);
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
      source_delta_ns: String(BigInt(paired.value.observation.source_stamp_ns) - BigInt(cloud.observation.source_stamp_ns)) };
  }
  ready() {
    if (!this.enabled) throw new Error('OFF');
    if (!this.map) throw new Error('SELECT_SAVED_3D_MAP');
    if (!this.pose || !this.cloud) throw new Error(this.reason === 'OFF' ? 'WAITING_INPUTS' : this.reason);
    if (this.pose.value.age_s * 1000 + this.now() - this.pose.arrived > 1000 || this.now() - this.cloud.arrived > 1000) throw new Error('STALE');
    return this.pair();
  }
  setAnchor(target, confirmed) {
    if (confirmed !== true) throw new Error('OPERATOR_ESTIMATE_CONFIRMATION_REQUIRED');
    const pair = this.ready(), targetMatrix = rpyMatrix(target);
    this.generation++;
    this.anchor = { generation: this.generation, map: { ...this.map }, poseKey: this.pose.key, cloudKey: this.cloud.key,
      T_map_odom: multiply(targetMatrix, inverseRigid(this.pose.matrix)), target_pose: { ...target },
      pose_stamp_ns: this.pose.value.observation.source_stamp_ns, kind: pair.kind, extrinsic: pair.extrinsic,
      basis: 'OPERATOR_APPROXIMATE_DISPLAY_ANCHOR', accepted_registration: false, body_calibration_verified: false };
    this.reason = 'ODOMETRY_PROPAGATED_UNVERIFIED'; this.trail = []; this.samples = []; this.geometryCache = null;
    this.registration = null;
  }
  snapshot() {
    const base = { enabled: this.enabled, status: this.reason, map: this.map, anchor: this.anchor,
      pose: null, points: null, trail: [], absolute_accuracy_m: null, map_registration: this.registration?.status || 'NOT_RUN',
      source_to_display_latency_ms: null, body_pose_verified: false };
    if (!this.enabled) return base;
    let pair;
    try { pair = this.ready(); } catch (e) {
      if (this.anchor && ['STALE', 'POSE_STALE'].includes(e.message)) this.invalidate(e.message);
      return { ...base, anchor: this.anchor, status: e.message };
    }
    if (!this.anchor) return { ...base, canAnchor: true, status: this.reason, pairing: pair.kind };
    if (this.anchor.poseKey !== this.pose.key || this.anchor.cloudKey !== this.cloud.key
        || this.anchor.kind !== pair.kind || JSON.stringify(this.anchor.extrinsic) !== JSON.stringify(pair.extrinsic)) {
      this.invalidate('SOURCE_CONTRACT_CHANGED'); return { ...base, anchor: null, status: this.reason };
    }
    const registrationStale = this.registration && (this.now() - this.registration.received > 2000
      || this.cloud.value.observation.received_monotonic_s - (this.registration.source?.received_monotonic_s ?? -Infinity) > 1);
    if (this.registrationEnabled && (!this.registration || this.registration.status !== 'CANDIDATE' || registrationStale)) {
      return { ...base, canAnchor: true, status: this.registration
        ? `SCAN_TO_MAP_${registrationStale && this.registration.status === 'CANDIDATE' ? 'STALE' : this.registration.status} · ${this.registration.reason}`
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
    return { ...base, status: this.registrationEnabled ? 'SCAN_TO_MAP_CANDIDATE_UNVERIFIED' : 'ODOMETRY_PROPAGATED_UNVERIFIED', canAnchor: true, pose,
      registration: this.registration,
      points: this.geometryCache.points, geometryKey: cacheKey, trail: this.trail,
      pairing: pair.kind, receipt_pair_delta_s: pair.receipt_delta_s, source_delta_ns: pair.source_delta_ns,
      pose_age_ms: this.now()-this.pose.arrived, cloud_age_ms: this.now()-this.cloud.arrived,
      cloud_receive_to_prepare_ms: this.now()-this.cloud.arrived };
  }
  alignmentRequest() {
    this.ready();
    if (!this.anchor) throw new Error('NO_ANCHOR');
    return { map_id: this.map.id, map_revision: this.map.revision, T_map_odom_seed: this.anchor.T_map_odom,
      observer_id: this.cloud.value.observation.observer_id,
      cloud_epoch: this.cloud.value.observation.publisher_epoch, pose_epoch: this.pose.value.observation.publisher_epoch };
  }
  applyAlignment(value, generation, requestedAt = this.now()) {
    if (generation !== this.generation || !this.anchor || !this.registrationEnabled) return false;
    const expected = this.alignmentRequest();
    if (value.schema !== 'robot-scope.observation-alignment.v1' || value.experimental !== true
        || value.operational_application !== 'NOT_RUN' || value.map_id !== expected.map_id
        || value.map_revision !== expected.map_revision || value.target_frame !== this.map.frame
        || ['observer_id', 'cloud_epoch', 'pose_epoch'].some(k => value.source?.[k] !== expected[k])) {
      this.alignmentFailed('RESULT_IDENTITY_MISMATCH', generation); return false;
    }
    if (!finite(requestedAt) || this.now() - requestedAt > 1000 || this.now() < requestedAt
        || !finite(value.source.received_monotonic_s)
        || Math.abs(this.cloud.value.observation.received_monotonic_s - value.source.received_monotonic_s) > 1) {
      this.alignmentFailed('RESULT_STALE', generation); return false;
    }
    this.registration = { ...value, received: requestedAt };
    if (value.status !== 'CANDIDATE') return false;
    const m = value.metrics;
    if (value.reason !== 'CANDIDATE' || !isRigidTransform(value.T_map_odom) || m?.converged !== true
        || !finite(m.rmse_m) || m.rmse_m < 0 || m.rmse_m > .05 || !finite(m.overlap_ratio) || m.overlap_ratio < .60 || m.overlap_ratio > 1
        || !finite(m.geometry_min_max_eigen_ratio) || m.geometry_min_max_eigen_ratio < .002
        || !finite(m.matched_geometry_min_max_eigen_ratio) || m.matched_geometry_min_max_eigen_ratio < .002 || value.correspondence_gate_m !== .75) {
      this.alignmentFailed('RESULT_GATE_MISMATCH', generation); return false;
    }
    if (jump(multiply(this.anchor.T_map_odom, this.pose.matrix), multiply(value.T_map_odom, this.pose.matrix))) { this.invalidate('ALIGNMENT_JUMP'); return false; }
    this.anchor.T_map_odom = value.T_map_odom;
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
      operational_application: 'NOT_RUN', body_pose_verified: false, samples: this.samples,
      source: { pose: this.pose?.value.observation || null, cloud: this.cloud?.value.observation || null } };
  }
}
