// Read-only local experiment report contract. No API or robot-control imports.
export const EXPERIMENT_REPORT_SCHEMA = 'robot-scope.experimental-se3-benchmark.v1';
export const MAX_REPORT_BYTES = 5_000_000;
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
const HEX64 = /^[0-9a-f]{64}$/;
const COMMIT = /^[0-9a-f]{40}$/;

const finite = (value) => typeof value === 'number' && Number.isFinite(value);
const fail = (reason) => { throw new Error(reason); };
const vector3 = (point) => Array.isArray(point) && point.length === 3
  && point.every((value) => finite(value) && Math.abs(value) <= 1000);

function matrix4(value) {
  if (!(Array.isArray(value) && value.length === 4
    && value.every((row) => Array.isArray(row) && row.length === 4
      && row.every((entry) => finite(entry) && Math.abs(entry) <= 1000))
    && value[3].every((entry, index) => Math.abs(entry - (index === 3 ? 1 : 0)) < 1e-8))) return false;
  const rows = value.slice(0, 3).map((row) => row.slice(0, 3));
  for (let i = 0; i < 3; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      const dot = rows[i].reduce((sum, entry, axis) => sum + entry * rows[j][axis], 0);
      if (Math.abs(dot - (i === j ? 1 : 0)) > 1e-5) return false;
    }
  }
  const determinant = rows[0][0] * (rows[1][1] * rows[2][2] - rows[1][2] * rows[2][1])
    - rows[0][1] * (rows[1][0] * rows[2][2] - rows[1][2] * rows[2][0])
    + rows[0][2] * (rows[1][0] * rows[2][1] - rows[1][1] * rows[2][0]);
  return Math.abs(determinant - 1) <= 1e-5;
}

function preview(value) {
  return Array.isArray(value) && value.length > 0 && value.length <= 256
    && value.every(vector3);
}

function validCase(item) {
  if (!item || typeof item !== 'object' || !/^[a-z0-9-]{1,64}$/.test(item.id)
      || item.data_kind !== 'SYNTHETIC' || !['CANDIDATE', 'REJECTED'].includes(item.expected_status)
      || !HEX64.test(item.target_sha256)
      || !HEX64.test(item.source_sha256) || !matrix4(item.initial_t_target_source)
      || !preview(item.target_preview_points) || !preview(item.source_preview_points)) return false;
  if (item.truth_t_target_source != null && !matrix4(item.truth_t_target_source)) return false;
  const result = item.se3;
  const pose = result?.pose;
  const metrics = result?.metrics;
  const hasTruth = item.truth_t_target_source != null;
  if (hasTruth !== (item.se3_position_error_m != null && item.se3_rotation_error_deg != null)) return false;
  if (item.se2 != null && (!['ACCEPTED', 'REJECTED', 'PROCESS_ERROR'].includes(item.se2.status)
      || item.se2.z_roll_pitch !== 'UNAVAILABLE_BY_CONTRACT'
      || (item.se2.runtime_ms != null && (!finite(item.se2.runtime_ms) || item.se2.runtime_ms < 0)))) return false;
  return result?.schema === 'robot-scope.experimental-se3-result.v1'
    && result.experimental === true && result.transform_convention === 'T_target_source'
    && result.method === 'bounded-point-to-point-se3-icp'
    && result.target_frame === 'map' && result.source_frame === 'camera_init'
    && Number.isSafeInteger(result.query_stamp_ns) && result.query_stamp_ns > 0
    && ['CANDIDATE', 'REJECTED'].includes(result.status)
    && typeof result.reason === 'string' && result.reason.length > 0 && result.reason.length <= 80
    && (result.status === 'CANDIDATE') === (result.reason === 'CANDIDATE')
    && pose && ['x', 'y', 'z', 'roll_rad', 'pitch_rad', 'yaw_rad'].every((key) => finite(pose[key]))
    && Array.isArray(pose.quaternion_xyzw) && pose.quaternion_xyzw.length === 4
    && pose.quaternion_xyzw.every(finite)
    && Math.abs(Math.hypot(...pose.quaternion_xyzw) - 1) <= 1e-5
    && metrics && typeof metrics.converged === 'boolean'
    && Number.isSafeInteger(metrics.iterations) && metrics.iterations >= 1 && metrics.iterations <= 40
    && finite(metrics.runtime_ms) && metrics.runtime_ms >= 0 && metrics.runtime_ms <= 60_000
    && finite(metrics.overlap_ratio) && metrics.overlap_ratio >= 0 && metrics.overlap_ratio <= 1
    && finite(metrics.geometry_min_max_eigen_ratio)
    && metrics.geometry_min_max_eigen_ratio >= 0 && metrics.geometry_min_max_eigen_ratio <= 1
    && vector3(metrics.weak_geometry_direction_target)
    && Math.abs(Math.hypot(...metrics.weak_geometry_direction_target) - 1) <= 1e-5
    && (metrics.rmse_m === null || (finite(metrics.rmse_m) && metrics.rmse_m >= 0))
    && (result.status !== 'CANDIDATE' || (metrics.converged && metrics.overlap_ratio >= 0.60
      && metrics.rmse_m != null && metrics.rmse_m <= 0.05
      && metrics.geometry_min_max_eigen_ratio >= 0.002))
    && (item.se3_position_error_m == null || (finite(item.se3_position_error_m) && item.se3_position_error_m >= 0))
    && (item.se3_rotation_error_deg == null || (finite(item.se3_rotation_error_deg) && item.se3_rotation_error_deg >= 0));
}

export function validateExperimentReport(report, nowMs = Date.now()) {
  if (!report || typeof report !== 'object' || Array.isArray(report)
      || report.schema !== EXPERIMENT_REPORT_SCHEMA || report.experimental !== true
      || report.data_kind !== 'SYNTHETIC') fail('지원되지 않는 실험 형식 또는 데이터 출처입니다. LIVE 결과로 변환하지 않습니다.');
  const stamp = typeof report.generated_at === 'string' ? Date.parse(report.generated_at) : NaN;
  if (!Number.isFinite(stamp) || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(report.generated_at)
      || stamp > nowMs + 5 * 60_000 || nowMs - stamp > MAX_AGE_MS) {
    fail('생성 시각이 없거나 오래된 실험 결과입니다. 동일 입력으로 다시 실행하세요.');
  }
  if (!COMMIT.test(report.source_commit) || !HEX64.test(report.manifest_sha256)
      || !HEX64.test(report.module_sha256) || !HEX64.test(report.benchmark_sha256)
      || typeof report.source_tree_dirty !== 'boolean'
      || !Number.isSafeInteger(report.peak_rss_platform_units) || report.peak_rss_platform_units < 0
      || typeof report.platform !== 'string' || report.platform.length > 120
      || !Array.isArray(report.cases) || report.cases.length < 1 || report.cases.length > 64
      || report.case_count !== report.cases.length) fail('출처 또는 사례 목록이 잘못되었습니다.');
  const ids = new Set();
  for (const item of report.cases) {
    if (!validCase(item) || ids.has(item.id)) fail('사례의 지도·점군·결과 필드가 잘못되었습니다.');
    ids.add(item.id);
  }
  if (report.candidate_count !== report.cases.filter((item) => item.se3.status === 'CANDIDATE').length
      || report.false_candidate_count !== report.cases.filter((item) => item.se3.status === 'CANDIDATE'
        && item.expected_status === 'REJECTED').length
      || report.expected_status_mismatch_count !== report.cases.filter((item) => item.se3.status !== item.expected_status).length) {
    fail('후보 또는 실패 집계가 사례와 일치하지 않습니다.');
  }
  return report;
}

export function compareExperimentReports(baseline, candidate) {
  if (baseline.manifest_sha256 !== candidate.manifest_sha256
      || baseline.cases.length !== candidate.cases.length) {
    fail('입력 manifest가 달라 기준선과 비교할 수 없습니다.');
  }
  const baselineCases = new Map(baseline.cases.map((item) => [item.id, item]));
  for (const item of candidate.cases) {
    const before = baselineCases.get(item.id);
    if (!before || before.target_sha256 !== item.target_sha256
        || before.source_sha256 !== item.source_sha256
        || JSON.stringify(before.initial_t_target_source) !== JSON.stringify(item.initial_t_target_source)) {
      fail('지도 revision, query 또는 초기값이 달라 비교할 수 없습니다.');
    }
  }
  return true;
}

export function transformPreview(points, matrix) {
  if (!preview(points) || !matrix4(matrix)) fail('시각화 변환이 잘못되었습니다.');
  return points.map(([x, y, z]) => [
    matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
    matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
    matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
  ]);
}

export function poseMatrix(pose) {
  const [x, y, z, w] = pose.quaternion_xyzw;
  return [
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), pose.x],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), pose.y],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), pose.z],
    [0, 0, 0, 1],
  ];
}
