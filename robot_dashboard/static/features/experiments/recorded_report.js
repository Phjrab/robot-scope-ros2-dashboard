// Local recorded diagnostics have their own contract; synthetic benchmark gates stay unchanged.
export const RECORDED_SCHEMA = 'robot-scope.recorded-se3-view.v1';
export const MAX_RECORDED_BYTES = 12_000_000;
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const text = (v) => typeof v === 'string' && v.length > 0 && v.length <= 240;
const hash = (v) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const vector = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => finite(x) && Math.abs(x) <= 1000);
const fail = (message) => { throw new Error(message); };
export const identity = () => [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
export function isRigidTransform(m) {
  if (!Array.isArray(m) || m.length !== 4 || !m.every((r) => Array.isArray(r) && r.length === 4 && r.every((x) => finite(x) && Math.abs(x) <= 1000))
      || !m[3].every((x, i) => Math.abs(x - (i === 3 ? 1 : 0)) < 1e-8)) return false;
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
    if (Math.abs(m[i].slice(0, 3).reduce((s, x, k) => s + x * m[j][k], 0) - Number(i === j)) > 1e-5) return false;
  }
  const det = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
    - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  return Math.abs(det - 1) < 1e-5;
}
export function multiply(a, b) {
  return a.map((r) => b[0].map((_, j) => r.reduce((s, x, k) => s + x * b[k][j], 0)));
}
export function transformPoints(points, m) {
  return points.map((p) => m.slice(0, 3).map((r) => r[0] * p[0] + r[1] * p[1] + r[2] * p[2] + r[3]));
}
export function matrixPose(m, frameId) {
  const pitch = Math.asin(Math.max(-1, Math.min(1, -m[2][0])));
  const singular = Math.abs(Math.cos(pitch)) < 1e-8;
  return { x: m[0][3], y: m[1][3], z: m[2][3],
    roll: singular ? 0 : Math.atan2(m[2][1], m[2][2]), pitch,
    yaw: singular ? Math.atan2(-m[0][1], m[1][1]) : Math.atan2(m[1][0], m[0][0]), frameId };
}
function cloud(c, maxPoints) {
  return c && text(c.frame_id) && text(c.session_id) && hash(c.sha256)
    && Number.isSafeInteger(c.original_count) && c.original_count > 0
    && Array.isArray(c.points) && c.points.length > 0 && c.points.length <= maxPoints
    && c.original_count >= c.points.length && c.points.every(vector);
}
function metrics(m) {
  return m && Number.isSafeInteger(m.reference_points) && m.reference_points > 0
    && Number.isSafeInteger(m.query_points) && m.query_points > 0
    && finite(m.correspondence_gate_m) && m.correspondence_gate_m > 0
    && finite(m.overlap_ratio) && m.overlap_ratio >= 0 && m.overlap_ratio <= 1
    && (m.rmse_m === null || (finite(m.rmse_m) && m.rmse_m >= 0))
    && m.direction === 'query_to_reference';
}
export function validateRecordedReport(r, now = Date.now()) {
  if (!r || r.schema !== RECORDED_SCHEMA || !['RECORDED_SENSOR', 'SYNTHETIC_FIXTURE'].includes(r.data_kind)
      || r.diagnostic_only !== true || r.operational_application !== 'NOT_RUN' || r.live_verification !== 'NOT_RUN'
      || r.absolute_accuracy_m !== null || !['BLOCKED', 'UNQUALIFIED'].includes(r.qualification)) fail('진단 전용 기록 형식이 아닙니다.');
  if (!text(r.generated_at) || !Number.isFinite(Date.parse(r.generated_at))
      || !text(r.captured_at) || !Number.isFinite(Date.parse(r.captured_at))
      || Date.parse(r.generated_at) > now + 300000 || Date.parse(r.captured_at) > now + 300000
      || !/^[a-f0-9]{40}$/.test(r.source_commit)) fail('출처 commit 또는 기록 시각이 올바르지 않습니다.');
  if (!cloud(r.target, 100000) || !cloud(r.source, 10000)
      || r.source.point_semantics !== 'REGISTERED_QUERY'
      || r.source.session_id === r.target.session_id
      || typeof r.source.stamp_ns !== 'string' || !/^[1-9][0-9]{0,19}$/.test(r.source.stamp_ns)
      || !text(r.source.clock_domain)) fail('점군·세션·frame·timestamp 계약 불일치입니다.');
  if (r.result !== null) {
    const q = r.result;
    if (!q || !['CANDIDATE', 'REJECTED', 'UNCERTAIN'].includes(q.status) || !text(q.reason)
        || typeof q.converged !== 'boolean' || !Number.isSafeInteger(q.iterations) || q.iterations < 0 || q.iterations > 40
        || !isRigidTransform(q.T_target_source) || !metrics(q.solver_metrics)
        || q.solver_metrics.query_points !== r.source.original_count
        || q.solver_metrics.reference_points > r.target.original_count
        || (q.full_reference_metrics !== null && (!metrics(q.full_reference_metrics)
          || q.full_reference_metrics.reference_points !== r.target.original_count
          || q.full_reference_metrics.query_points !== r.source.original_count))) fail('정합 결과·잔차의 대상 지도 계약 불일치입니다.');
    // Imported labels cannot upgrade rejection by substituting full-map postmetrics.
    if (q.status === 'CANDIDATE' && (!q.converged || q.reason !== 'CANDIDATE'
        || q.solver_metrics.overlap_ratio < .60 || q.solver_metrics.rmse_m === null || q.solver_metrics.rmse_m > .05
        || !finite(q.geometry_min_max_eigen_ratio) || q.geometry_min_max_eigen_ratio < .002)) fail('후보 판정과 solver 품질 gate가 일치하지 않습니다.');
  }
  if (r.body_relation !== null && (!r.body_relation || r.body_relation.verified !== false
      || r.body_relation.source_frame !== r.source.frame_id || r.body_relation.source_session !== r.source.session_id
      || r.body_relation.body_frame !== 'base_link' || !text(r.body_relation.provenance)
      || !isRigidTransform(r.body_relation.T_source_body))) fail('source→body 변환 출처가 일치하지 않습니다.');
  if (!r.trajectory || r.trajectory.frame_id !== r.source.frame_id || r.trajectory.session_id !== r.source.session_id
      || !text(r.trajectory.estimand) || !Array.isArray(r.trajectory.points)
      || r.trajectory.points.length > 400 || !r.trajectory.points.every(vector)) fail('궤적 frame 또는 세션이 일치하지 않습니다.');
  return r;
}
export function recordedState(r, now = Date.now()) {
  if (!r) return 'NO_DATA';
  if (!r.result) return 'NO_RESULT';
  return now - Date.parse(r.captured_at) > 30 * 86400000 ? 'STALE_RECORDING' : 'ARCHIVED_NOT_LIVE';
}
export function replayGeometry(r, aligned = true) {
  const transform = aligned && r.result ? r.result.T_target_source : identity();
  const body = r.body_relation;
  return {
    query: transformPoints(r.source.points, transform),
    trajectory: transformPoints(r.trajectory.points, transform),
    pose: matrixPose(multiply(transform, body?.T_source_body || identity()), r.target.frame_id),
    poseKind: body ? 'UNVERIFIED_BODY_CANDIDATE' : 'QUERY_ORIGIN_REFERENCE',
    // Same header string never implies the same session origin.
    coordinateMode: aligned && r.result ? 'T_target_source' : 'UNALIGNED_SESSION_COORDINATES',
  };
}
// All success AND failure completions use the same generation guard.
export function createRecordedLoader(onChange) {
  let generation = 0;
  return async (file) => {
    const mine = ++generation;
    onChange(null, file ? 'LOADING' : 'NO_DATA');
    try {
      if (!file) return;
      if (file.size <= 0 || file.size > MAX_RECORDED_BYTES) fail('기록 JSON 크기 제한은 12 MB입니다.');
      const report = validateRecordedReport(JSON.parse(await file.text()));
      if (generation === mine) onChange(report, recordedState(report));
    } catch (error) {
      if (generation === mine) onChange(null, 'INVALID', error.message);
    }
  };
}
