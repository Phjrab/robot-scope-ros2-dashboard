/** Presentation only. Runtime admission remains authoritative for every command. */
export const PREPARATION_STEPS = [
  ['지도 선택·연결 확인', '3D·2D 지도 ID/revision, 변환 계보와 좌표 관계를 서버에서 확인'],
  ['센서·교정·초기값 준비', '센서 관측과 출처·좌표 기준을 확인하고 지도 기준 초기 높이·기울기 준비'],
  ['Nav2 시작·노드와 TF 확인', '실행 source, 현재 점군·자세, Nav2 노드와 TF 입력 확인'],
  ['INITIAL POSE 지정·전송', '지도에서 지정한 현재 위치·방향의 실제 런타임 접수 확인'],
  ['현재 LiDAR와 저장 지도 정합', '명시적으로 정합을 시작하고 실제 보정 갱신·품질 확인'],
  ['추정 위치·주행 준비 확인', '신선한 추정 위치, TF 반영과 기존 주행 안전 조건 충족'],
  ['목표 전송·경로 진행', '사용자가 별도로 목표를 전송하고 실제 Nav2 종료 확인'],
];

const REASONS = {
  WAITING_EXPLICIT_INITIAL_POSE: ['초기 위치·방향 미지정', '실제 정지 상태에서 INITIAL POSE를 지정·전송하세요.'],
  WAITING_EXPLICIT_MAP_MATCH: ['정합 시작 입력 필요', '초기 위치 접수 후 ⑤ 정합 시작을 누르세요.'],
  WAITING_EXPLICIT_MATCH: ['정합 시작 입력 필요', '초기 위치 접수 후 ⑤ 정합 시작을 누르세요.'],
  WAITING_EXACT_STAMP_PAIR: ['동일 시각 점군·자세 입력 부족', '센서 입력·시각과 TF 상태를 확인한 뒤 해당 단계에서 다시 확인하세요.'],
  INITIAL_REFINEMENT_LOW_OVERLAP: ['지도와 겹치는 관측 부족', '실제 위치·방향과 현재 관측 가능한 구조를 확인하세요.'],
  INITIAL_REFINEMENT_REQUIRES_STOP: ['실제 정지·대기 미충족', '로봇을 정지하고 관측된 정지 시간이 충족된 뒤 다시 확인하세요.'],
  INITIAL_REFINEMENT_OUT_OF_BOUNDS: ['초기값 주변 정합 범위 초과', '현재 위치·방향을 다시 지정하세요.'],
  CORRECTION_JUMP_RESEED_REQUIRED: ['지도 보정 불연속', '안전하게 정지한 뒤 초기 위치를 다시 지정하세요.'],
  MAP_CORRECTION_STALE: ['지도 보정 결과 오래됨', '현재 점군·자세와 지도 정합의 갱신 상태를 확인하세요.'],
  INSUFFICIENT_STRUCTURE: ['관측 가능한 구조 부족', '서로 다른 방향의 안정적인 구조가 관측되는지 확인하세요.'],
  HIGH_RESIDUAL: ['현재 정합 품질 기준 미달', '현재 잔차·겹침·구조 검사 결과를 확인하세요.'],
};
const INPUT_REASONS = {
  MAP_PAIR_REQUIRED: '지도 조합이 없습니다 → ①에서 3D·2D 지도를 연결하세요.',
  MAP_PAIR_INVALID: '지도 또는 교정 검증이 맞지 않습니다 → ①의 연결 상태를 다시 확인하세요.',
  OBSERVATION_INACTIVE: '센서 관측이 실행 중이 아닙니다 → 시작 조건을 확인하고 관측을 시작하세요.',
  OBSERVATION_INPUTS_UNAVAILABLE: '센서 입력을 확인하지 못했습니다 → 점군·자세 수신 상태를 확인하세요.',
  OBSERVATION_STALE_OR_SOURCE_INVALID: '센서 입력이 오래됐거나 출처가 일치하지 않습니다 → 현재 입력과 실행 상태를 확인하세요.',
  POSE_PAIR_UNAVAILABLE: '같은 시각의 점군·자세가 없습니다 → 새 센서 입력을 확인하세요.',
  CALIBRATION_UNAVAILABLE: '본체·센서 교정 근거가 없습니다 → 검증된 교정 상태를 확인하세요.',
  MAP_ABSOLUTE_Z_UNVERIFIED: '지도 기준 본체 높이가 확인되지 않았습니다 → 현재 높이의 지도 기준 근거가 필요합니다.',
  MAP_GRAVITY_ALIGNMENT_UNVERIFIED: '지도 기준 기울기가 확인되지 않았습니다 → 지도와 중력 방향의 관계를 확인해야 합니다.',
  MAP_ESTIMATE_UNAVAILABLE_OR_STALE: '현재 지도 추정이 없거나 오래됐습니다 → 현재 실행의 신선한 추정과 품질을 확인하세요.',
  MAP_ESTIMATE_INVALID: '지도 추정값을 사용할 수 없습니다 → 현재 추정과 품질 검사를 확인하세요.',
  NAVIGATION_JOB_NOT_RUNNING: '현재 주행 실행이 없습니다 → 지도 추정이 필요한 조건을 확인하세요.',
  CONTEXT_CHANGED: '조회 중 지도 또는 관측 실행이 바뀌었습니다 → 현재 상태를 다시 확인하세요.',
  SOURCE_CHANGED: '조회 중 센서 출처가 바뀌었습니다 → 현재 입력을 다시 확인하세요.',
  STALE_INPUT: '검사 당시 센서 입력이 오래됐습니다 → 현재 입력을 확인하세요.',
  FASTLIO_REGISTERED_IMU_REQUIRED: '검사 당시 필요한 FAST-LIO 입력 출처가 확인되지 않았습니다 → 센서 출처를 확인하세요.',
  RECEIPT_TIME_MISMATCH: '검사 당시 수신 시각이 맞지 않았습니다 → 센서 수신 상태를 확인하세요.',
  SUBSCRIPTION_TYPE_MISMATCH: '검사 당시 구독 입력 유형이 맞지 않았습니다 → 센서 출처를 확인하세요.',
  INVALID_QUATERNION: '검사 당시 자세 회전값을 사용할 수 없었습니다 → 자세 입력을 확인하세요.',
  INVALID_INPUT: '검사 당시 입력 형식이 유효하지 않았습니다 → 센서 입력을 확인하세요.',
  STAMP_REGRESSION: '조회 중 센서 시각이 역행했습니다 → 센서 출처와 시각을 확인하세요.',
  EXACT_STAMP_MISMATCH: '검사 당시 점군과 자세 시각이 맞지 않았습니다 → 같은 시각의 입력을 확인하세요.',
  INPUT_UNAVAILABLE: '검사 당시 입력을 확인하지 못했습니다 → 센서와 서버 상태를 확인하세요.',
  FASTLIO_SOURCE_TIME_MISMATCH: '검사 당시 FAST-LIO 점군과 자세 시각이 맞지 않았습니다 → 같은 시각의 입력을 확인하세요.',
  NO_PAIRED_POSE: '검사 당시 점군과 짝을 이루는 자세가 없었습니다 → 같은 시각의 자세 수신을 확인하세요.',
  POSE_SOURCE_CHANGED: '검사 중 자세 출처가 바뀌었습니다 → 현재 센서 출처를 확인하세요.',
  SOURCE_IDENTITY_UNAVAILABLE: '검사 당시 센서 출처 식별 근거가 없었습니다 → 출처 정보를 확인하세요.',
  SUBSCRIPTION_EVIDENCE_CHANGED: '검사 중 구독 출처 근거가 바뀌었습니다 → 현재 구독 상태를 확인하세요.',
  SUBSCRIPTION_EVIDENCE_UNAVAILABLE: '검사 당시 구독 출처 근거를 확인하지 못했습니다 → 현재 구독 상태를 확인하세요.',
  OBSERVATION_SESSION_NOT_STARTABLE: '관측 세션을 시작할 수 없는 상태입니다 → 현재 관측 상태를 확인하세요.',
  CONTROL_BRIDGE_NOT_INACTIVE: '제어 bridge가 비활성 상태가 아닙니다 → 기존 안전 절차로 상태를 확인하세요.',
  CONTROL_BRIDGE_STATE_UNKNOWN: '제어 bridge 상태를 확인하지 못했습니다 → 연결과 상태를 확인하세요.',
  START_BLOCKERS_UNAVAILABLE: '시작 조건을 확인하지 못했습니다 → 연결과 상태를 다시 확인하세요.',
  OBSERVATION_STATUS_UNAVAILABLE: '관측 상태를 확인하지 못했습니다 → 연결과 상태를 다시 확인하세요.',
  MAP_PAIR_CHANGED: '지도 구성이 바뀌었습니다 → 현재 지도와 관측을 다시 확인하세요.',
  OBSERVATION_SESSION_CHANGED: '관측 실행이 바뀌었습니다 → 새 관측에서 다시 계산하세요.',
  GLOBAL_BACKEND_UNAVAILABLE: '전역 위치 제안 기능을 사용할 수 없습니다 → 서버 구성을 확인하세요.',
  GLOBAL_JOB_NOT_READY: '위치 제안 계산이 아직 준비되지 않았습니다 → 현재 상태를 확인하세요.',
  GLOBAL_AMBIGUOUS: '서로 구분되지 않는 위치 후보가 있습니다 → 관측과 지도 단서를 확인하세요.',
  GLOBAL_CANDIDATE_REJECTED: '위치 제안이 품질 검사를 통과하지 못했습니다 → 현재 관측을 확인하세요.',
  CALIBRATION_CHANGED: '교정이 변경됐습니다 → 지도와 교정 상태를 다시 확인하세요.',
  OWNERSHIP_BUSY_OR_UNKNOWN: '다른 작업이 점유 중이거나 점유 상태를 확인하지 못했습니다 → 현재 작업 상태를 확인하세요.',
  HANDOFF_EXPIRED: '확인한 가설의 사용 시간이 지났습니다 → 새 제안을 계산하고 확인하세요.',
  HANDOFF_ALREADY_USED: '이 가설은 이미 사용됐습니다 → 새 제안을 확인하세요.',
  HANDOFF_OBSERVATION_STOP_REQUIRED: '관측 종료 확인이 필요합니다 → 센서 관측 종료를 별도로 누르세요.',
  HANDOFF_STOP_OUTCOME_UNKNOWN: '관측 종료 결과가 불확실합니다 → 현재 관측 상태와 정상 종료를 확인하세요.',
  HANDOFF_WORKER_NOT_SETTLED: '전역 관측 작업 종료가 확인되지 않았습니다 → 정리 완료를 기다리세요.',
  HANDOFF_CONTINUITY_UNVERIFIED: '감독 확인 또는 전환 근거가 부족합니다 → 현재 확인 내용을 점검하세요.',
  HANDOFF_RUNTIME_CHANGED: '실행 세대가 바뀌었습니다 → 현재 상태를 확인하세요.',
  HANDOFF_MONITOR_PENDING: '관측 종료 경계를 가설 감시기가 확인 중입니다 → 확인이 끝날 때까지 기다리세요.',
  HANDOFF_MONITOR_UNAVAILABLE: '가설 감시 상태가 유실됐거나 확인되지 않습니다 → 가설을 다시 확인하세요.',
  HANDOFF_JOB_CONTEXT_UNCONFIRMED: '현재 실행 또는 지도 증거가 부족합니다 → 서버 상태를 다시 확인하세요.',
  HANDOFF_JOB_STARTING: '새 실행이 시작 중입니다 → 실행과 지도 확인을 기다리세요.',
  HANDOFF_JOB_STOPPING: '실행이 종료 중입니다 → 종료 결과를 확인하세요.',
  HANDOFF_JOB_NOT_RUNNING: '이 가설에 연결된 실행이 종료됐습니다 → 현재 준비 상태를 확인하세요.',
  HANDOFF_MATCH_CURRENT_UNCONFIRMED: '이전 정합 수락은 있으나 현재 실행의 수락 상태를 확인하지 못했습니다.',
  INITIAL_POSE_CANDIDATE_MISMATCH: '입력 위치가 제안의 사용 범위를 벗어났습니다 → 새 제안을 확인하세요.',
  PROPOSAL_NOT_READY: '현재 제안이 확인 가능한 상태가 아닙니다 → 관측과 제안을 다시 확인하세요.',
  SOURCE_OR_CONTEXT_CHANGED: '센서 출처 또는 실행 문맥이 바뀌었습니다 → 현재 상태를 확인하세요.',
};
function inputReason(code) {
  if (INPUT_REASONS[code]) return INPUT_REASONS[code];
  const owners = { mapping: '지도 작성', navigation: '주행', slam: 'SLAM', control: '수동 제어', raw_capture: '센서 원본 기록', dataset: '데이터 기록', mission: '미션', mission_routes: '미션 경로', route_planner: '경로 계획', lifecycle: '실행 전환', global_observation: '전역 관측', relocalization: '위치 재추정', sensor_tracking: '센서 추적' };
  if (typeof code === 'string' && code.startsWith('OWNER_BUSY:')) return `${owners[code.slice(11)] || '다른 작업'}이 센서를 사용 중입니다 → 해당 작업의 종료 상태를 확인하세요.`;
  if (typeof code === 'string' && code.startsWith('OWNER_UNKNOWN:')) return `${owners[code.slice(14)] || '다른 작업'}의 점유 상태를 확인하지 못했습니다 → 현재 작업 상태를 확인하세요.`;
  return '상세 원인을 확인하지 못했습니다 → 기술 상세에서 서버의 검사 결과를 확인하세요.';
}
const finite = value => typeof value === 'number' && Number.isFinite(value);
const DIAGNOSTIC_STAGES = {
  session: '관측 세션 확인', initial_latest: '최초 최신 점군·자세 검사', initial_pairing: '최초 동일 시각 자세 확보',
  initial_paired: '최초 동일 시각 입력 검사', pair_validation: '지도 구성 검증', context_fence: '지도·관측 문맥 확인',
  health_and_handoff: '실행 상태·가설 확인', final_latest: '최종 최신 점군·자세 검사', final_pairing: '최종 동일 시각 자세 확보',
  final_paired: '최종 동일 시각 입력 검사', calibration_fence: '교정 최종 확인', response_fence: '응답 전 문맥 확인', response_pair: '응답 직전 입력 검사',
};
const DIAGNOSTIC_FAILURES = {
  POSE_STATE: '자세 입력 상태 미충족', POSE_TOPIC: '자세 topic 불일치', POSE_FRAME: '자세 좌표계 불일치', POSE_CHILD_FRAME: '자세 본체 좌표계 불일치',
  CLOUD_TOPIC: '점군 topic 불일치', CLOUD_FRAME: '점군 좌표계 불일치', CLOUD_UNITS: '점군 단위 불일치', CLOUD_POINTS: '점군 포인트 부족',
  SESSION_START: '관측 시작 시각 미확인', POSE_RECEIPT: '자세 수신 시각 조건 미충족', CLOUD_RECEIPT: '점군 수신 시각 조건 미충족',
  POSE_GRAPH: '자세 graph 출처 조건 미충족', CLOUD_GRAPH: '점군 graph 출처 조건 미충족', INPUT_MISSING_OR_INVALID: '검사 입력 누락 또는 형식 오류',
};
const DIAGNOSTIC_CODES = new Set(['OBSERVATION_INACTIVE', 'OBSERVATION_INPUTS_UNAVAILABLE', 'MAP_PAIR_REQUIRED', 'MAP_PAIR_INVALID', 'CONTEXT_CHANGED',
  'OBSERVATION_STALE_OR_SOURCE_INVALID', 'POSE_PAIR_UNAVAILABLE', 'SOURCE_CHANGED', 'STALE_INPUT', 'FASTLIO_REGISTERED_IMU_REQUIRED',
  'RECEIPT_TIME_MISMATCH', 'SUBSCRIPTION_TYPE_MISMATCH', 'INVALID_QUATERNION', 'INVALID_INPUT', 'CALIBRATION_CHANGED', 'STAMP_REGRESSION', 'EXACT_STAMP_MISMATCH', 'INPUT_UNAVAILABLE',
  'FASTLIO_SOURCE_TIME_MISMATCH', 'NO_PAIRED_POSE', 'POSE_SOURCE_CHANGED', 'SOURCE_IDENTITY_UNAVAILABLE', 'SUBSCRIPTION_EVIDENCE_CHANGED', 'SUBSCRIPTION_EVIDENCE_UNAVAILABLE']);
const DIAGNOSTIC_CHECK_STAGES = new Set(['initial_latest', 'initial_paired', 'final_latest', 'final_paired', 'response_pair']);
const DIAGNOSTIC_PHASES = ['initial_snapshot', 'initial_capture', 'pair_validation', 'health_and_handoff', 'final_capture', 'calibration_fence', 'response_fence', 'total'];
// Keep the optional server snapshot bounded; it never participates in admission decisions.
function preparationDiagnostics(value) {
  if (!value || typeof value !== 'object' || value.schema !== 'robot-scope.preparation-diagnostics.v1') return null;
  const text = item => typeof item === 'string' && item.length > 0 && item.length <= 128 && !/[\u0000-\u001f\u007f]/.test(item) ? item : null;
  const metadata = source => {
    if (!source || typeof source !== 'object' || Array.isArray(source)) return null;
    const result = {};
    for (const key of ['topic', 'frame_id', 'child_frame_id', 'observer_id', 'publisher_epoch', 'subscription_session_id', 'graph_fingerprint']) result[key] = text(source[key]);
    result.state = ['ok', 'waiting', 'stale', 'unavailable', 'error'].includes(source.state) ? source.state : null;
    result.units = source.units === 'm' ? source.units : null;
    result.sent_points = Number.isInteger(source.sent_points) && source.sent_points >= 0 && source.sent_points <= 2147483647 ? source.sent_points : null;
    result.receipt_after_session_start = typeof source.receipt_after_session_start === 'boolean' ? source.receipt_after_session_start : null;
    result.source_stamp_ns = typeof source.source_stamp_ns === 'string' && /^\d{1,20}$/.test(source.source_stamp_ns) ? source.source_stamp_ns : null;
    for (const key of ['receipt_age_s', 'graph_age_s']) result[key] = finite(source[key]) && Math.abs(source[key]) <= 1e9 ? source[key] : null;
    result.graph_state = ['ok', 'unavailable'].includes(source.graph_state) ? source.graph_state : null;
    for (const key of ['graph_endpoint_count', 'graph_publisher_count']) result[key] = Number.isInteger(source[key]) && source[key] >= 0 && source[key] <= 2147483647 ? source[key] : null;
    return result;
  };
  const checks = Array.isArray(value.checks) ? value.checks.slice(0, 5).flatMap(check => {
    if (!check || !DIAGNOSTIC_CHECK_STAGES.has(check.stage) || !['initial', 'final', 'response'].includes(check.sample)) return [];
    return [{ stage: check.stage, sample: check.sample, ready: typeof check.ready === 'boolean' ? check.ready : null,
      failures: Array.isArray(check.failures) ? check.failures.slice(0, 14).filter(code => typeof code === 'string' && Object.hasOwn(DIAGNOSTIC_FAILURES, code)) : [],
      pose: metadata(check.pose), cloud: metadata(check.cloud) }];
  }) : [];
  const phase_ms = {};
  for (const key of DIAGNOSTIC_PHASES) phase_ms[key] = finite(value.phase_ms?.[key]) && value.phase_ms[key] >= 0 && value.phase_ms[key] <= 86400000 ? value.phase_ms[key] : null;
  const failure_stage = typeof value.failure_stage === 'string' && Object.hasOwn(DIAGNOSTIC_STAGES, value.failure_stage) ? value.failure_stage : null;
  const sample = value.failure_sample;
  // A failure outside readiness checks has its own sample. Never substitute a later check.
  const failure_sample = failure_stage && sample && typeof sample === 'object' && !Array.isArray(sample) && sample.stage === failure_stage
    ? { stage: failure_stage, pose: metadata(sample.pose), cloud: metadata(sample.cloud) } : null;
  return { schema: value.schema, failure_stage, failure_code: DIAGNOSTIC_CODES.has(value.failure_code) ? value.failure_code : null,
    failure_sample, checks, phase_ms };
}
const pin = map => map && `${map.map_id || map.id}:${map.revision}`;
const issue = (code, current, required, remedy, step) => ({ code, current, required, remedy, step });
const samePin = (a, b) => Boolean(a && b && pin(a) === pin(b));

export function operationalPoseContextMatches(observation, source, map) {
  return Boolean(observation && source && map && samePin({ map_id: observation.map_id, revision: observation.map_revision }, map)
    && observation.bundle_generation === source.bundle_generation && source.bundle_generation
    && observation.localization_generation === source.localization_generation && Number.isInteger(source.localization_generation)
    && observation.runtime_instance_generation === source.runtime_instance_generation && source.runtime_instance_generation
    && observation.localization_map_id === source.localization_map_id && source.localization_map_id
    && observation.localization_map_revision === source.localization_map_revision && source.localization_map_revision
    && ['x', 'y', 'z', 'roll', 'pitch', 'yaw'].every(key => finite(observation.pose?.[key])));
}

export function preparationModel({ state, navigation = {}, draft3d, draft2d, error = '', available = true, handoffReady = false, handoffMatchAllowed = false, handoffArmed = false }) {
  navigation ||= {};
  const selected = state?.selected;
  const source = navigation.operational_localization;
  const enabled = Boolean(draft3d || selected || source || navigation.operational_expected);
  const active = ['starting', 'running', 'stopping'].includes(navigation.pipeline?.state);
  const running = navigation.pipeline?.state === 'running';
  const geometry = selected?.seed_geometry;
  const pairChecks = Array.isArray(state?.pair?.checks) ? state.pair.checks : [];
  const geometryCodes = new Set(['INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED', 'INITIAL_GEOMETRY_PROVENANCE_REQUIRED', 'HANDOFF_OBSERVATION_STOP_REQUIRED', 'HANDOFF_STOP_OUTCOME_UNKNOWN', 'HANDOFF_WORKER_NOT_SETTLED', 'HANDOFF_EXPIRED', 'HANDOFF_ALREADY_USED', 'HANDOFF_CONTINUITY_UNVERIFIED', 'HANDOFF_RUNTIME_CHANGED', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED', 'HANDOFF_MONITOR_PENDING', 'HANDOFF_MONITOR_UNAVAILABLE', 'SOURCE_OR_CONTEXT_CHANGED']);
  const geometryBlocked = pairChecks.some(check => geometryCodes.has(check.code));
  const legacySeed = selected && selected.workflow !== 'staged_navigation_pair' && Array.isArray(selected.seed_T_map_imu);
  const geometryReady = Boolean(!geometryBlocked && (legacySeed || geometry && ['z', 'roll', 'pitch'].every(key => finite(geometry[key])) && (geometry.source !== 'proposal_confirmed' || handoffReady)));
  const pairValid = state?.pair?.valid !== false || (pairChecks.length > 0 && pairChecks.every(check => geometryCodes.has(check.code)));
  const matched = pairValid && samePin(selected?.localization_3d, draft3d) && samePin(selected?.navigation_2d, draft2d);
  const applied = Boolean(running && source?.bundle_generation === selected?.generation
    && samePin(navigation.map, selected?.navigation_2d)
    && source?.localization_map_id === selected?.localization_3d?.map_id
    && source?.localization_map_revision === selected?.localization_3d?.revision);
  const marker = operationalPoseContextMatches(source?.accepted_initial_pose, source, navigation.map)
    && source.accepted_initial_pose.accepted === true ? source.accepted_initial_pose : null;
  const estimate = operationalPoseContextMatches(source?.estimated_pose, source, navigation.map) ? source.estimated_pose : null;
  const tracking = Boolean(matched && applied && source.fresh === true && source.ready === true && estimate && estimate.stale !== true
    && (geometry?.source !== 'proposal_confirmed' || handoffArmed && handoffReady && !geometryBlocked));
  const nodesReady = applied && source?.fresh === true && (navigation.safety?.can_set_initial_pose === true || Boolean(marker));
  const goalReady = tracking && navigation.safety?.can_send_goal === true;
  const goalContext = navigation.goal?.precision_evidence?.context;
  const currentGoal = navigation.pipeline?.job_id && navigation.goal?.goal_id
    && navigation.goal.precision_evidence?.goal_id === navigation.goal.goal_id
    && goalContext?.job_id === navigation.pipeline.job_id
    && goalContext?.map_id === navigation.map?.id && goalContext?.map_revision === navigation.map?.revision ? navigation.goal : null;
  const matchWaiting = ['WAITING_EXPLICIT_MAP_MATCH', 'WAITING_EXPLICIT_MATCH'].includes(source?.state);
  const issues = [];
  for (const check of pairChecks) issues.push(issue(check.code || 'PAIR_CHECK_FAILED', check.current || '서버 검사 미충족', check.required || '서버 검증 통과', check.remedy || '해당 단계를 다시 확인하세요.', geometryCodes.has(check.code) ? 2 : state.pair.restart_from_step || 1));
  if (!draft3d) issues.push(issue('MAP_3D_REQUIRED', '3D 지도 미선택', '위치추정용 저장 3D 지도', '3D 위치추정 지도에서 지도를 선택하세요.', 1));
  if (!draft2d) issues.push(issue('MAP_2D_REQUIRED', '2D 지도 미선택', '경로 계산용 2D 지도', '2D 경로 계산 지도를 선택하세요.', 1));
  if (draft3d && draft2d && !matched) issues.push(issue('PAIR_NOT_APPLIED', '선택한 지도 조합이 서버 준비 구성과 다름', '정확한 ID·revision과 검증된 변환 계보', '① 지도 연결 확인·적용을 누르세요. 실행 중이면 먼저 STOP하세요.', 1));
  if (selected && !geometryReady && !geometryBlocked) issues.push(issue('INITIAL_GEOMETRY_REQUIRED', '초기 높이·기울기 미확인', '지도 좌표의 본체 높이(m)·roll/pitch(rad)', '②에서 확인한 값을 직접 입력하고 초기 높이·기울기 저장을 누르세요.', 2));
  if (selected && selected.calibration?.verified !== true) issues.push(issue('CALIBRATION_REQUIRED', '검증된 교정 정보 없음', '본체·센서·TF와 지도 연결의 서버 검증', '교정·좌표 관계의 서버 검사 결과를 확인하세요.', 2));
  if (running && !applied) issues.push(issue('RUNTIME_SOURCE_MISMATCH', '실행 source 또는 지도·실행 세대 불일치', '선택한 구성과 동일한 실제 source', 'STOP 후 ①에서 지도 구성을 다시 확인하세요.', 3));
  if (applied && !nodesReady) {
    if (source.fresh !== true) issues.push(issue('RUNTIME_STATUS_STALE', '실행 상태 수신 오래됨', '신선한 센서·노드 검사 결과', '입력과 런타임 연결을 확인하고 ③부터 다시 확인하세요.', 3));
    for (const [key, label] of [['scan', '현재 /scan'], ['odometry', 'FAST-LIO 자세'], ['map_server', '지도 서버'], ['planner', '경로 계획 노드'], ['controller', '주행 제어 노드'], ['tf', 'TF']]) {
      if (navigation.readiness?.[key] !== true) issues.push(issue(`NOT_READY_${key.toUpperCase()}`, `${label} 준비 미확인`, `${label}의 실제 입력·노드 준비`, '③의 상세 지표와 주행 로그에서 입력·노드 상태를 확인한 뒤 다시 확인하세요.', 3));
    }
  }
  if (nodesReady && !marker) issues.push(issue('INITIAL_POSE_REQUIRED', '이번 실행의 초기 위치 접수 없음', '현재 지도·실행에 접수된 사용자 위치·방향', '④ INITIAL POSE로 지도에서 현재 위치·방향을 지정하고 SEND POSE를 누르세요.', 4));
  if (marker && !tracking) {
    const [reason, remedy] = REASONS[source.state] || [`정합 확인 필요: ${source.state || '입력 없음'}`, '⑤의 현재 잔차·겹침·입력·정지 상태와 주행 로그를 확인하세요.'];
    issues.push(issue(source.state || 'MATCH_REQUIRED', reason, '품질 검사에 통과한 신선한 저장 지도 보정', remedy, 5));
  }
  if (tracking && !goalReady) issues.push(issue('GOAL_CONDITIONS_REQUIRED', (navigation.safety?.blockers || []).join(' · ') || '목표 전송 조건 미충족', '기존 source·TF·정지·대기·제어 조건', '아래 안전 상태와 정지·대기 증거를 확인하세요. 조건이 회복되면 ⑥부터 다시 확인합니다.', 6));
  if (!available) issues.unshift(issue('STATUS_UNAVAILABLE', '현재 준비 상태 수신 실패', '신선한 서버 상태', '연결을 확인하고 현재 단계 다시 확인을 누르세요.', 1));
  if (error) issues.unshift(issue('REQUEST_REJECTED', error, '서버 검증 통과', '표시된 항목을 해결한 뒤 해당 버튼으로 다시 확인하세요.', 1));
  const statuses = ['미시작', '미시작', '미시작', '미시작', '미시작', '미시작', '미시작'];
  statuses[0] = matched ? '완료' : error || state?.pair?.valid === false ? '오류' : '사용자 입력 필요';
  if (matched) statuses[1] = geometryReady && selected.calibration?.verified === true ? '완료' : '사용자 입력 필요';
  if (statuses[1] === '완료') statuses[2] = nodesReady ? '완료' : navigation.pipeline?.state === 'failed' ? '오류' : active ? '확인 중' : '사용자 입력 필요';
  if (nodesReady) statuses[3] = marker ? '완료' : '사용자 입력 필요';
  if (marker) statuses[4] = tracking ? '완료' : matchWaiting ? '사용자 입력 필요' : /WAITING|CONFIRMING/.test(source?.state || '') ? '확인 중' : '오류';
  if (tracking) statuses[5] = goalReady ? '완료' : '사용자 입력 필요';
  if (goalReady || currentGoal) statuses[6] = currentGoal?.state === 'succeeded' ? '완료' : ['failed', 'rejected'].includes(currentGoal?.state) ? '오류' : ['pending', 'active', 'canceling'].includes(currentGoal?.state) ? '확인 중' : '사용자 입력 필요';
  const checks = [
    matched ? '서버가 준비한 지도 조합과 선택 ID·revision 일치' : '지도 선택 후 명시적 연결 검증 필요',
    geometry?.source === 'proposal_confirmed' && !handoffReady ? '서버 가설이 있으나 현재 문맥과 관측 종료 확인이 필요합니다.' : geometry ? `${geometry.source === 'proposal_confirmed' ? '서버에 보관된 본체 가설' : '명시된 본체 값'} · 높이 ${geometry.z} m · roll ${geometry.roll} · pitch ${geometry.pitch} rad` : legacySeed ? '기존 명시적 3D 초기값과 교정 구성 사용' : '높이·기울기 값이 없으면 자동으로 0을 사용하지 않습니다.',
    nodesReady ? '이번 실행의 Nav2 초기 위치 접수 조건 확인' : 'Nav2 시작 후 실제 센서·노드·TF 상태를 확인합니다.',
    marker ? '실제 런타임 접수 확인 · 초기 위치 점 보존' : '사용자 초기 위치는 아직 확인되지 않았습니다.',
    source ? `보정 ${source.correction_sequence ?? '—'}회 · 상태 ${source.state || '—'} · 나이 ${finite(source.correction_age_s) ? source.correction_age_s.toFixed(2) + ' s' : '미확인'}` : '현재 저장 지도 정합 결과 없음',
    estimate ? `${tracking ? '실제 정합 추정 위치 수신' : '마지막 추정 위치 · 현재 추적 미확인'} · z ${estimate.pose.z.toFixed(3)} m · roll ${estimate.pose.roll.toFixed(3)} / pitch ${estimate.pose.pitch.toFixed(3)} rad · 목표 전송은 별도 작업` : '지도상 로봇 위치 미확인',
    currentGoal ? `이번 실행의 Nav2 목표 상태: ${currentGoal.state}` : '이번 실행의 목표 전송 없음. 목표를 전송하면 실제 이동이 시작될 수 있습니다.',
  ];
  return { enabled, active, matched, applied, geometryReady, marker, estimate, tracking, matchWaiting, issues,
    canStart: Boolean(available && (!enabled || matched && geometryReady && selected.calibration?.verified === true && state?.pair?.can_start !== false)),
    canMatch: Boolean(available && matched && geometryReady && nodesReady && marker && matchWaiting && source.fresh === true && (geometry?.source !== 'proposal_confirmed' || handoffMatchAllowed)),
    steps: PREPARATION_STEPS.map(([title, condition], index) => ({ number: index + 1, title, condition, status: statuses[index], result: checks[index],
      issues: issues.filter(item => item.step === index + 1), next: statuses[index] === '완료' })),
  };
}

export function initializeNavigationPreparation({ host, map3dSelect, map2dSelect, api, context, onChange, actions }) {
  let state = null, busy = false, available = false, error = '', fetchError = '', checkedAt = 0, refreshing = false, draftTouched = false, actionStep = null;
  let lastContext = '', invalidated = '', selected3d = '', draft3dRevision = '', geometryGeneration = '';
  let inputs = null, inputsError = '', observationError = '', observationBusy = false, inputsRevision = 0, inputsRequestedAt = 0;
  let proposal = null, proposalError = '', proposalFailureDetail = '', proposalBusy = false, proposalEpoch = 0, proposalContext = null, proposalVerified = false, proposalCheckedAt = 0, proposalTimer = null, proposalExpiryTimer = null;
  let cleanup = null, cleanupId = null, cleanupTimer = null, cleanupEpoch = 0, advisoryAfter = 0, advisoryRefreshPending = false;
  let handoff = null, handoffReadAt = 0, handoffEpoch = 0, handoffTimer = null, handoffClock = null, handoffReading = false, handoffBusy = false, handoffError = '', handoffFailureDetail = '', handoffAwaitingStatus = false;
  const invalidHandoffs = new Map();
  const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
  host.innerHTML = `<div class="panel-header compact"><div><div class="eyebrow">STORED MAP NAVIGATION</div><h2>단계별 주행 준비</h2></div><button type="button" data-prep="refresh">현재 단계 다시 확인</button></div>
    <p data-prep="current"></p><p data-prep="selected"></p><p data-prep="applied"></p><p data-prep="invalidation" role="status"></p>
    <div class="navigation-preparation-actions"><button type="button" data-prep="pair">① 지도 연결 확인·적용</button><button type="button" data-prep="clear">기존 2D 모드로 복구</button></div>
    <section class="navigation-preparation-observation" aria-label="② 센서 관측과 초기값"><h3>② 센서 관측과 초기값</h3><p>관측은 정지 상태의 센서 입력 확인 전용입니다. 시작 조건은 서버가 다시 검사하며, 지도 선택이나 후보 확인만으로 정합·주행을 시작하지 않습니다.</p>
    <div class="navigation-preparation-actions"><button type="button" data-prep="observe-start">센서 관측 시작</button><button type="button" data-prep="observe-stop">센서 관측 종료</button></div>
    <p data-prep="observation-status" role="status"></p><p data-prep="observation-error" role="alert"></p><div data-prep="evidence"></div><div data-prep="candidates"></div>
    <button type="button" data-prep="proposal">초기 위치 제안 계산</button><div data-prep="proposal-result" role="status"></div>
    <label class="navigation-handoff-supervision"><input type="checkbox" data-prep="supervision"> 현장 정지 상태를 직접 감독하며 관측 종료와 다음 절차를 진행하겠습니다. 이 확인은 정지 측정이 아닙니다.</label>
    <button type="button" data-prep="confirm-handoff">이 가설을 초기 geometry로 확인</button><div data-prep="handoff-result" role="status"></div></section>
    <details class="navigation-seed-geometry"><summary>② 초기 높이·기울기 입력</summary><p>현재 로봇 본체 원점(base_link)의 지도 좌표 높이(m), roll·pitch(rad)를 확인해 입력하세요. 바닥 높이와 본체 원점의 높이는 다릅니다. 임의의 0이나 이전 실행값을 사용하지 않습니다. 참고값이나 자동 후보는 자동 입력·전송되지 않습니다.</p>
    <div><label>높이 z (m)<input data-geometry="z" type="number" step="0.001" placeholder="미지정"></label><label>roll (rad)<input data-geometry="roll" type="number" step="0.001" placeholder="미지정"></label><label>pitch (rad)<input data-geometry="pitch" type="number" step="0.001" placeholder="미지정"></label><button type="button" data-prep="geometry">초기 높이·기울기 저장</button></div><p data-prep="geometry-source"></p></details>
    <ol class="navigation-preparation-steps" data-prep="steps"></ol>
    <section class="navigation-preparation-issues" aria-label="준비 상태·해결할 항목"><h3>준비 상태·해결할 항목</h3><div data-prep="issues" role="status"></div></section>
    <details><summary>기술 상세 · 현재 검사 수치와 실행 정보</summary><pre data-prep="details"></pre></details>`;
  const el = name => host.querySelector(`[data-prep="${name}"]`);
  const selectors = node('div', undefined, 'navigation-preparation-map-selectors');
  for (const select of [map3dSelect, map2dSelect]) {
    const label = select.closest('label');
    if (label) selectors.append(label);
  }
  host.insertBefore(selectors, el('current'));
  function handoffRuntimeCompatible(value, selected, navigation) {
    const pipeline = navigation?.pipeline || {}, map = navigation?.map || {}, pin2d = selected?.navigation_2d || {};
    const uncertain = ['INVALID', 'EXPIRED', 'OUTCOME_UNKNOWN'].includes(value?.state);
    if ((value?.job_id && pipeline.job_id && value.job_id !== pipeline.job_id)
        || (map.id && map.id !== pin2d.map_id) || (map.revision && map.revision !== pin2d.revision)) return false;
    if (uncertain) return true;
    if (value?.job_id) return pipeline.state === 'running' && pipeline.job_id === value.job_id && samePin(map, pin2d);
    return ['idle', 'stopped', 'failed'].includes(pipeline.state);
  }
  function currentHandoff(draft3d, draft2d, navigation) {
    const selected = state?.selected, proof = selected?.seed_geometry?.handoff;
    const identified = Boolean(available && handoff?.schema === 'robot-scope.proposal-geometry-handoff.v1'
      && handoff.source === 'proposal_confirmed' && handoff.frame === 'map' && /^[a-f0-9]{32}$/.test(handoff.handoff_id || '')
      && handoff.handoff_id === proof?.handoff_id && handoff.bundle_generation === selected?.generation
      && handoff.observation_session_id === proof?.observation_session_id && selected?.seed_geometry?.source === 'proposal_confirmed'
      && handoff.proposal_id === proof?.proposal_id && handoff.bundle_generation === proof?.bundle_generation
      && proof?.calibration_sha256 && proof.calibration_sha256 === state?.pair?.calibration_sha256
      && handoff.policy?.id === 'robot-scope.proposal-handoff.local-v1' && handoff.policy?.ttl_s === 120
      && handoff.policy?.max_xy_m === 0.25 && handoff.policy?.max_yaw_rad === 0.20
      && samePin(selected?.localization_3d, draft3d) && samePin(selected?.navigation_2d, draft2d) && handoffRuntimeCompatible(handoff, selected, navigation));
    const remaining = finite(handoff?.expires_in_s) ? Math.max(0, handoff.expires_in_s - Math.max(0, performance.now() - handoffReadAt) / 1000) : null;
    const history = handoff?.match_history;
    const matchesHistory = source => Boolean(source && history && source.match_armed === true && source.match_receipt?.accepted === true
      && source.runtime_instance_generation === history.runtime_instance_generation && source.localization_generation === history.localization_generation
      && source.accepted_initial_pose?.accepted === true && source.accepted_initial_pose.stamp_ns === history.initial_pose_stamp_ns
      && source.match_receipt.request_id === history.match_request_id && source.match_receipt.localization_generation === history.localization_generation
      && history.match_request_id);
    const armed = Boolean(identified && handoff.state === 'MATCH_ARMED' && !handoff.reason && state?.runtime_fresh === true
      && navigation?.operational_localization?.fresh === true && matchesHistory(state.runtime) && matchesHistory(navigation.operational_localization));
    const unexpired = identified && remaining !== null && remaining > 0;
    const stopped = handoff?.stop_receipt?.state === 'INACTIVE_CONFIRMED';
    const geometryReady = Boolean(identified && stopped && !handoff.reason && (handoff.state === 'MATCH_ARMED' ? armed : unexpired)
      && ['OBSERVATION_STOPPED', 'SNAPSHOTTED', 'INITIAL_POSE_ACCEPTED', 'MATCH_ARMED'].includes(handoff.state));
    return { identified, remaining, armed, unexpired, geometryReady,
      matchAllowed: Boolean(geometryReady && unexpired && ['SNAPSHOTTED', 'INITIAL_POSE_ACCEPTED', 'MATCH_ARMED'].includes(handoff.state)),
      active: Boolean(identified && !['INVALID', 'EXPIRED', 'OUTCOME_UNKNOWN'].includes(handoff.state) && (handoff.state === 'MATCH_ARMED' ? armed : unexpired)) };
  }
  function clearHandoff() {
    ++handoffEpoch; clearTimeout(handoffTimer); clearTimeout(handoffClock); handoffTimer = null; handoffClock = null; handoff = null;
  }
  function handoffShape(value) {
    return value?.schema === 'robot-scope.proposal-geometry-handoff.v1' && /^[a-f0-9]{32}$/.test(value.handoff_id || '') && /^[a-f0-9]{24}$/.test(value.proposal_id || '')
      && value.source === 'proposal_confirmed' && value.frame === 'map' && /^[a-f0-9]{32}$/.test(value.bundle_generation || '')
      && /^[a-f0-9]{32}$/.test(value.observation_session_id || '') && finite(value.expires_in_s) && value.expires_in_s >= 0
      && value.expires_in_s <= 120
      && ['CONFIRMED_OBSERVATION_ACTIVE', 'STOP_PENDING', 'OBSERVATION_STOPPED', 'SNAPSHOTTED', 'INITIAL_POSE_ACCEPTED', 'MATCH_ARMED', 'INVALID', 'EXPIRED', 'OUTCOME_UNKNOWN'].includes(value.state);
  }
  function setHandoff(value, requestedAt) {
    if (!handoffShape(value)) { clearHandoff(); handoffAwaitingStatus = false; handoffError = '확인 상태의 형식을 검증하지 못했습니다.'; return; }
    const selected = state?.selected;
    const navigation = context().navigation || {};
    if (selected?.seed_geometry?.source !== 'proposal_confirmed' || selected.seed_geometry.handoff?.handoff_id !== value.handoff_id
        || selected.generation !== value.bundle_generation || selected.seed_geometry.handoff?.observation_session_id !== value.observation_session_id
        || selected.seed_geometry.handoff?.proposal_id !== value.proposal_id || selected.seed_geometry.handoff?.bundle_generation !== value.bundle_generation
        || !selected.seed_geometry.handoff?.calibration_sha256 || selected.seed_geometry.handoff.calibration_sha256 !== state?.pair?.calibration_sha256
        || !handoffRuntimeCompatible(value, selected, navigation)) {
      clearHandoff(); handoffAwaitingStatus = false; handoffError = '서버의 현재 지도·가설 문맥이 일치하지 않습니다.'; return;
    }
    if (handoff && handoff.handoff_id === value.handoff_id && requestedAt < handoffReadAt) return;
    const phaseOnlyInvalid = value.state === 'INVALID' && value.reason === 'HANDOFF_JOB_NOT_RUNNING';
    if (value.state === 'EXPIRED' || (value.state === 'INVALID' && !phaseOnlyInvalid)) {
      invalidHandoffs.set(value.handoff_id, { state: value.state, reason: value.reason });
      if (invalidHandoffs.size > 32) invalidHandoffs.delete(invalidHandoffs.keys().next().value);
    } else if (invalidHandoffs.has(value.handoff_id)) {
      const invalid = invalidHandoffs.get(value.handoff_id);
      value = { ...value, state: invalid.state, reason: invalid.reason, geometry: null, initial_pose_reference: null };
    }
    if (!handoff || handoff.handoff_id !== value.handoff_id) { clearHandoff(); }
    handoff = value; handoffReadAt = requestedAt; handoffError = ''; handoffAwaitingStatus = false;
    clearTimeout(handoffClock);
    const token = handoffEpoch;
    let expiryNotified = false;
    const tick = () => { if (token === handoffEpoch && handoff) { render(); if (!expiryNotified && performance.now() - handoffReadAt >= handoff.expires_in_s * 1000) { expiryNotified = true; onChange(); } handoffClock = setTimeout(tick, 1000); } };
    handoffClock = setTimeout(tick, 1000);
    scheduleHandoffRead();
  }
  function scheduleHandoffRead() {
    if (!handoff || handoffTimer || handoffReading || ['INVALID', 'EXPIRED', 'MATCH_ARMED'].includes(handoff.state)) return;
    const id = handoff.handoff_id, token = handoffEpoch;
    handoffTimer = setTimeout(async () => {
      handoffTimer = null; handoffReading = true; const requestedAt = performance.now();
      try {
        const value = await api(`/api/v1/navigation/operational-3d/initialization-handoffs/${id}`, { signal: AbortSignal.timeout(10000) });
        if (token !== handoffEpoch || handoff?.handoff_id !== id) return;
        if (value.handoff_id !== id) throw new Error('HANDOFF_CONTEXT_CHANGED');
        setHandoff(value, requestedAt);
      } catch (failure) {
        if (token !== handoffEpoch) return;
        handoffFailureDetail = failure.message; clearHandoff(); handoffError = '확인 상태 조회 실패 → 현재 서버 상태를 다시 확인하세요.';
      } finally {
        handoffReading = false; scheduleHandoffRead(); render(); onChange();
      }
    }, 2000);
  }
  function current() {
    const ctx = context();
    const maps = ctx.maps || [];
    const draft3d = maps.find(map => map.id === map3dSelect.value && map.kind === 'pointcloud3d');
    const handoffInfo = currentHandoff(draft3d, ctx.map, ctx.navigation || {});
    return { ...ctx, navigation: ctx.navigation || {}, draft3d, draft2d: ctx.map, handoffInfo, model: preparationModel({ state, navigation: ctx.navigation, draft3d, draft2d: ctx.map, error: error || fetchError, available, handoffReady: handoffInfo.geometryReady, handoffMatchAllowed: handoffInfo.matchAllowed, handoffArmed: handoffInfo.armed }) };
  }
  function syncOptions() {
    const maps = (context().maps || []).filter(map => map.kind === 'pointcloud3d' && map.revision);
    const desired = map3dSelect.value || (!draftTouched ? state?.selected?.localization_3d?.map_id : '') || '';
    const signature = maps.map(map => `${map.id}:${map.revision}:${map.name}`).join('|');
    if (map3dSelect.dataset.catalog === signature) return;
    map3dSelect.dataset.catalog = signature;
    map3dSelect.replaceChildren(node('option', '3D 위치추정 지도 선택'));
    map3dSelect.firstChild.value = '';
    maps.forEach(map => { const option = node('option', `${map.name} · ${map.revision.slice(0, 8)}`); option.value = map.id; map3dSelect.append(option); });
    if (maps.some(map => map.id === desired)) map3dSelect.value = desired;
    else if (desired) { invalidated = '지도 ID 또는 revision이 변경됐습니다. ①에서 지도를 다시 선택·확인하세요. 기존 목표 주석은 해당 지도에 그대로 보존됩니다.'; draftTouched = true; }
  }
  function proposalSource(evidence) {
    const cloud = evidence?.cloud, pose = evidence?.pose;
    if (evidence?.valid !== true || !/^[a-f0-9]{32}$/.test(cloud?.observer_id || '')
        || cloud.observer_id !== pose?.observer_id || !/^[a-f0-9]{32}$/.test(cloud?.publisher_epoch || '')
        || !/^[a-f0-9]{32}$/.test(pose?.publisher_epoch || '') || !/^[1-9][0-9]*$/.test(cloud?.source_stamp_ns || '')
        || cloud.source_stamp_ns !== pose?.source_stamp_ns) return null;
    return { observer_id: cloud.observer_id, cloud_epoch: cloud.publisher_epoch, pose_epoch: pose.publisher_epoch };
  }
  function proposalContextMatches(ctx = proposalContext) {
    const { model } = current(), pair = inputs?.pair, session = inputs?.observation, source = proposalSource(inputs?.evidence);
    return Boolean(ctx && available && model.matched && pair?.valid === true && pair.generation === ctx.generation
      && state?.selected?.generation === ctx.generation && samePin(pair.localization_3d, ctx.localization_3d)
      && samePin(pair.navigation_2d, ctx.navigation_2d) && pair.calibration_sha256 === ctx.calibration_sha256
      && session?.state === 'READY' && session.active === true && session.session_id === ctx.session_id && source
      && ['observer_id', 'cloud_epoch', 'pose_epoch'].every(key => source[key] === ctx.source?.[key]));
  }
  function invalidateProposal(message = '관측 또는 지도 상태가 바뀌어 이전 제안을 사용할 수 없습니다.') {
    if (!proposalContext && !proposal && !proposalBusy) return;
    ++proposalEpoch; clearTimeout(proposalTimer); clearTimeout(proposalExpiryTimer); proposalTimer = null; proposalExpiryTimer = null;
    proposal = null; proposalContext = null; proposalVerified = false; proposalError = message;
    el('supervision').checked = false;
    if (cleanupId && !cleanupSettled()) scheduleCleanupPoll();
  }
  function cleanupSettled() { return cleanup?.state === 'SETTLED' && cleanup.worker_active === false; }
  function recordCleanup(result, id) {
    if (result?.schema !== 'robot-scope.navigation-initialization-proposal.v1' || result.proposal_id !== id) return false;
    const wasSettled = cleanupId === id && cleanupSettled();
    const value = result.cleanup;
    cleanupId = id;
    cleanup = value && ['MONITORING', 'CANCELLING', 'CANCEL_PENDING', 'SETTLED', 'CANCEL_FAILED', 'JOB_UNAVAILABLE', 'CLEANUP_UNCONFIRMED'].includes(value.state)
      ? { state: value.state, cancellation_requested: value.cancellation_requested, worker_active: value.worker_active, terminal_state: value.terminal_state }
      : { state: 'CLEANUP_UNCONFIRMED' };
    if (cleanupSettled() && !wasSettled) { advisoryAfter = performance.now(); checkedAt = 0; if (refreshing || busy) advisoryRefreshPending = true; else void refresh(true); }
    return true;
  }
  function scheduleCleanupPoll() {
    if (!cleanupId || cleanupSettled()) return;
    clearTimeout(cleanupTimer);
    const token = ++cleanupEpoch, id = cleanupId;
    cleanupTimer = setTimeout(async () => {
      try {
        const result = await api(`/api/v1/navigation/operational-3d/initialization-proposals/${id}`, { signal: AbortSignal.timeout(10000) });
        if (token !== cleanupEpoch || id !== cleanupId) return;
        if (!recordCleanup(result, id)) cleanup = { state: 'CLEANUP_UNCONFIRMED' };
      } catch (failure) {
        if (token !== cleanupEpoch || id !== cleanupId) return;
        proposalFailureDetail = failure.message; cleanup = { state: 'CLEANUP_UNCONFIRMED' };
      }
      render(); if (!cleanupSettled()) scheduleCleanupPoll();
    }, 2000);
  }
  function proposalResponseMatches(value, ctx) {
    return Boolean(value?.schema === 'robot-scope.navigation-initialization-proposal.v1'
      && /^[a-f0-9]{24}$/.test(value.proposal_id || '') && value.operational_application === 'NOT_RUN'
      && value.pair?.generation === ctx.generation && value.observation_session_id === ctx.session_id
      && samePin(value.pair.localization_3d, ctx.localization_3d) && samePin(value.pair.navigation_2d, ctx.navigation_2d)
      && value.pair.calibration_sha256 === ctx.calibration_sha256);
  }
  function proposalPoseValid() {
    const age = proposal?.provenance?.pose_age_s;
    const fresh = finite(age) && age >= 0 && age + (performance.now() - proposalCheckedAt) / 1000 <= 1;
    const cleanupUnsafe = cleanup && (['CANCELLING', 'CANCEL_PENDING', 'CANCEL_FAILED', 'CLEANUP_UNCONFIRMED', 'JOB_UNAVAILABLE'].includes(cleanup.state) || cleanup.cancellation_requested === true);
    return Boolean(proposalVerified && proposal?.state === 'ready' && proposalContextMatches() && fresh && !cleanupUnsafe
      && proposal.imu_hypothesis?.pose_reference === 'FASTLIO_IMU' && proposal.imu_hypothesis?.units === 'metres_degrees'
      && proposal.imu_hypothesis?.approximate_only === true && proposal.imu_hypothesis?.requires_reanchor === true
      && proposal.body_candidate?.pose_reference === 'base_link' && proposal.body_candidate?.units === 'metres_radians'
      && proposal.body_candidate?.qualification === 'INFORMATIONAL_LOCALIZATION_MAP_ONLY'
      && proposal.imu_hypothesis?.frame && proposal.imu_hypothesis.frame === proposalContext?.localization_3d?.frame
      && proposal.body_candidate.frame === proposal.imu_hypothesis.frame && proposal.quality?.ambiguity_unresolved === false
      && proposal.quality?.qualification === 'GLOBAL_HYPOTHESIS_ONLY_NOT_OPERATIONAL_QUALITY' && proposal.quality?.residual_selection_gate_enabled === false
      && ['observer_id', 'cloud_epoch', 'pose_epoch'].every(key => proposal.provenance?.source_contract?.[key] === proposalContext?.source?.[key])
      && finite(proposal.quality?.overlap) && finite(proposal.quality?.rmse_m) && finite(proposal.provenance?.capture_age_s) && proposal.provenance.capture_age_s >= 0 && proposal.absolute_accuracy_m === null
      && ['x', 'y', 'z', 'roll', 'pitch', 'yaw'].every(key => finite(proposal.imu_hypothesis.pose?.[key]) && finite(proposal.body_candidate.pose?.[key])));
  }
  function render() {
    syncOptions();
    const liveNavigation = context().navigation || {};
    if (handoff && !handoffRuntimeCompatible(handoff, state?.selected, liveNavigation)) {
      clearHandoff(); handoffError = '새 실행 또는 지도 문맥을 다시 확인하세요.';
    }
    const { navigation = {}, map, model, draft3d, handoffInfo, busy: navigationBusy } = current();
    const source = navigation.operational_localization;
    const identity = source ? `${navigation.pipeline?.job_id}:${source.bundle_generation}:${source.localization_generation}:${source.runtime_instance_generation}` : '';
    if (lastContext && identity && lastContext !== identity) invalidated = '실행 또는 위치추정 세대가 변경됐습니다. ③~⑥의 현재 증거를 다시 확인하세요. 지도 구성이 같으면 ①~②는 유지됩니다.';
    if (identity) lastContext = identity;
    const selected = state?.selected;
    if (geometryGeneration !== (selected?.generation || '')) {
      geometryGeneration = selected?.generation || '';
      host.querySelectorAll('[data-geometry]').forEach(input => { input.value = ''; });
    }
    const mapName = pinValue => (context().maps || []).find(entry => samePin(entry, pinValue))?.name || pinValue?.map_id || '없음';
    const nextStep = busy && actionStep ? model.steps[actionStep - 1] : model.steps.find(step => step.status !== '완료') || model.steps[6];
    el('current').textContent = model.enabled || busy ? `현재 단계: ${nextStep.number}. ${nextStep.title} · ${busy ? '확인 중' : nextStep.status}` : '현재 모드: 기존 2D · 저장 지도 위치추정은 3D 지도 선택 후 준비';
    el('selected').textContent = `화면 선택: 3D ${draft3d?.name || '미선택'} / 2D ${map?.name || '미선택'} · 서버 준비 구성: ${selected ? `${mapName(selected.localization_3d)} / ${mapName(selected.navigation_2d)}` : '기존 2D 모드'}`;
    el('applied').textContent = source ? `실제 실행: ${source.source || 'source 미확인'} · 3D ${mapName({ map_id: source.localization_map_id, revision: source.localization_map_revision })} / 2D ${mapName(navigation.map)} · ${model.applied ? '준비 구성과 일치' : '구성 일치 미확인'} · ${model.tracking ? '추적 중' : '지도상 현재 위치 미확인'}` : '실제 실행: 저장 3D 지도 위치추정 미적용';
    el('invalidation').textContent = invalidated;
    map3dSelect.disabled = busy || navigationBusy || model.active;
    el('pair').disabled = busy || navigationBusy || model.active || !draft3d || !map;
    el('clear').disabled = busy || navigationBusy || model.active || !selected;
    el('geometry').disabled = busy || navigationBusy || model.active || !selected;
    host.querySelectorAll('[data-geometry]').forEach(input => { input.disabled = busy || navigationBusy || model.active || !selected; });
    const geometry = selected?.seed_geometry;
    el('geometry-source').textContent = geometry ? `출처: ${geometry.source || '사용자 명시 입력'} · 확인 시각: ${finite(geometry.confirmed_at) ? new Date(geometry.confirmed_at * 1000).toLocaleString() : '서버 확인 정보 참고'} · ${geometry.source === 'proposal_confirmed' ? '사용 가능 여부는 위 서버 상태와 시간을 확인하세요' : '현재 구성에만 적용'}` : '이번 구성에 확인된 높이·기울기 없음';
    const observation = inputs?.observation;
    const pair = inputs?.pair;
    const inputsCurrent = Boolean(available && model.matched && selected && pair?.valid === true && pair.generation === selected.generation && samePin(pair.localization_3d, selected.localization_3d) && samePin(pair.navigation_2d, selected.navigation_2d));
    const blockers = inputs?.start_blockers?.items;
    if (proposalContext && !proposalContextMatches()) invalidateProposal();
    el('observe-start').disabled = observationBusy || busy || navigationBusy || model.active || !inputsCurrent || observation?.can_start !== true || !Array.isArray(blockers) || blockers.length > 0;
    el('observe-stop').disabled = observationBusy || observation?.can_stop !== true || !/^[a-f0-9]{32}$/.test(observation?.session_id || '');
    const sessionLabels = { UNAVAILABLE: '사용 불가', CHECKING: '확인 중', STOPPED: '정지', FAILED: '시작 실패 또는 종료', STARTING: '시작 중', WAITING_INPUTS: '입력 대기', READY: '입력 준비', STOPPING: '종료 중', UNKNOWN: '상태 미확인' };
    el('observation-status').textContent = inputsError ? '관측 입력 확인 실패 → 연결과 상태를 다시 확인하세요.' : `관측 상태: ${sessionLabels[observation?.state] || '확인 중'} · ${observation?.reason || '서버 상태 확인 필요'} · 시작 사전 검사: ${Array.isArray(blockers) ? blockers.length ? blockers.map(inputReason).join(' · ') : '현재 차단 항목 없음' : inputReason('START_BLOCKERS_UNAVAILABLE')} · 사전 검사는 권고이며 서버의 최종 승인 보장이 아닙니다.`;
    const bridgeError = /control_bridge_not_inactive/i.test(observationError);
    el('observation-error').textContent = observationError ? bridgeError ? `관측 시작이 거절됐습니다. ${inputReason('CONTROL_BRIDGE_NOT_INACTIVE')} 자동 재시도하지 않습니다.` : '관측 요청이 거절됐거나 응답을 확인하지 못했습니다 → 기술 상세의 서버 사유를 확인하세요. 자동 재시도하지 않습니다.' : '';
    const evidence = inputs?.evidence;
    const provenance = value => value ? `출처 ${value.topic || '미확인'} · 좌표 ${value.frame_id || '미확인'} · 센서 시각 ${value.source_stamp_ns ? '기록됨' : '미확인'}` : '입력 없음';
    const reference = inputsCurrent && evidence?.valid === true && observation?.active === true && observation?.state === 'READY' ? inputs?.reference_pose : null;
    const requestAge = Math.max(0, (performance.now() - inputsRequestedAt) / 1000);
    const diagnostics = inputsCurrent && requestAge <= 10 ? preparationDiagnostics(evidence?.diagnostics) : null;
    const failedCheck = diagnostics?.checks.find(check => check.stage === diagnostics.failure_stage && check.ready === false);
    const diagnosticIssue = evidence?.valid === false && diagnostics?.failure_stage && diagnostics.failure_code
      ? `서버 최초 거절 검사(검사 당시): ${DIAGNOSTIC_STAGES[diagnostics.failure_stage]} · ${inputReason(diagnostics.failure_code)}${failedCheck?.failures.length ? ` · 실패 조건: ${failedCheck.failures.map(code => DIAGNOSTIC_FAILURES[code]).join(' · ')}` : ''}` : '';
    const vector = (value, keys) => keys.map(key => `${key} ${finite(value?.[key]) ? value[key].toFixed(3) : '미확인'}`).join(' · ');
    el('evidence').replaceChildren(
      node('p', `준비 구성: ${inputsCurrent ? '현재 선택과 일치' : '현재 선택과 일치 미확인'} · 관측 검사(조회 시점): ${evidence?.valid === true && inputsCurrent ? '통과' : evidence?.reason ? inputReason(evidence.reason) : '미확인'} · 조회 요청 후 ${inputs ? requestAge.toFixed(1) + '초 경과' : '시간 미확인'}`),
      node('p', `점군: ${provenance(evidence?.cloud)}`), node('p', `자세: ${provenance(evidence?.pose)}`),
      node('p', reference ? `본체 참고 자세 (과거 조회 결과, 지도 초기값 아님): ${reference.frame || '좌표 미확인'} → ${reference.child_frame || '미확인'} · 조회 요청 후 ${requestAge.toFixed(1)}초 경과 · 위치(m) ${vector(reference.position, ['x', 'y', 'z'])} · 자세(rad) ${vector(reference.orientation, ['roll', 'pitch', 'yaw'])}` : '본체 참고 자세 없음')
    );
    el('candidates').replaceChildren(...['z', 'roll', 'pitch'].map(key => {
      const candidate = inputs?.candidates?.[key];
      const age = candidate?.provenance?.age_s;
      const fresh = finite(age) && age >= 0 && age + (performance.now() - inputsRequestedAt) / 1000 <= 0.5;
      const candidateContext = model.tracking && source?.source === 'STORED_PCD_FASTLIO'
        && ['bundle_generation', 'runtime_instance_generation', 'localization_generation', 'correction_sequence'].every(name => candidate?.provenance?.[name] === source?.[name])
        && candidate?.provenance?.map_id === navigation.map?.id && candidate?.provenance?.map_revision === navigation.map?.revision
        && candidate?.provenance?.localization_map_id === source?.localization_map_id && candidate?.provenance?.localization_map_revision === source?.localization_map_revision;
      const usable = inputsCurrent && candidateContext && candidate?.available === true && candidate.frame === 'map' && finite(candidate.value) && fresh;
      const stale = candidate?.available === true && !fresh ? '후보 신선도 만료 또는 미확인 → 새 상태를 확인하세요.' : '';
      return node('p', usable ? `${key}: 자동 후보 ${candidate.value} ${key === 'z' ? 'm' : 'rad'} · 지도 좌표 · 현재 추정 기준 · 읽기 전용, 자동 입력·적용 없음` : `${key}: 부족 · ${inputsCurrent ? stale || (candidate?.available === true && !candidateContext ? '현재 실행·추정 상태가 다릅니다 → 현재 실행을 다시 확인하세요.' : candidate?.reason ? inputReason(candidate.reason) : '서버 후보가 없습니다 → 필요한 근거를 확인하세요.') : '현재 지도·실행 일치 미확인 → 지도 연결과 현재 상태를 확인하세요.'}`);
    }), node('p', `지도 추정: ${inputs?.map_estimate_reason ? inputReason(inputs.map_estimate_reason) : inputs?.candidates ? '서버 후보 참고' : '미확인'}`));
    const proposalReadyToRequest = Boolean(inputsCurrent && !busy && !navigationBusy && !model.active && !observationBusy
      && observation?.active === true && observation.state === 'READY' && /^[a-f0-9]{32}$/.test(observation.session_id || '')
      && /^[a-f0-9]{32}$/.test(pair?.generation || '') && proposalSource(inputs?.evidence) && pair.calibration_sha256
      && Array.isArray(blockers) && !blockers.some(code => ['OWNER_BUSY:global_observation', 'OWNER_UNKNOWN:global_observation', 'START_BLOCKERS_UNAVAILABLE', 'OBSERVATION_STATUS_UNAVAILABLE'].includes(code))
      && inputsRequestedAt >= advisoryAfter && (!cleanupId || cleanupSettled()));
    el('proposal').disabled = proposalBusy || handoffBusy || handoffAwaitingStatus || handoffInfo.active || ['capturing', 'running'].includes(proposal?.state) || !proposalReadyToRequest;
    const poseText = value => ['x', 'y', 'z', 'roll', 'pitch', 'yaw'].map(key => `${key} ${finite(value?.pose?.[key]) ? value.pose[key].toFixed(3) : '미확인'}`).join(' · ');
    const proposalAge = proposal?.provenance?.pose_age_s;
    const proposalFresh = finite(proposalAge) && proposalAge >= 0 && proposalAge + (performance.now() - proposalCheckedAt) / 1000 <= 1;
    const validPoses = proposalPoseValid();
    el('supervision').disabled = handoffBusy || handoffInfo.active;
    el('confirm-handoff').disabled = handoffBusy || handoffAwaitingStatus || !el('supervision').checked || !validPoses || !proposalReadyToRequest || !cleanupSettled() || handoffInfo.active;
    const proposalNodes = [node('p', '정보성 제안은 저장 3D 지도 기준이며 운영 보정 위치·Nav2 준비·TF 적용 결과가 아닙니다. 자동 입력·전송하지 않습니다.')];
    if (proposalBusy && !proposal) proposalNodes.push(node('p', '제안 계산 요청 중 · 자동 재전송하지 않습니다.'));
    else if (proposalError) proposalNodes.push(node('p', `제안 사용 불가: ${proposalError}`));
    else if (!proposal) proposalNodes.push(node('p', '제안 없음 · 관측 준비 후 명시적으로 계산하세요.'));
    else if (!proposalVerified) proposalNodes.push(node('p', '제안 접수 · 현재 관측과 지도 문맥을 다시 확인 중입니다.'));
    else if (validPoses) {
      proposalNodes.push(node('p', `FAST-LIO IMU 가설 (이력·근사값): 좌표 ${proposal.imu_hypothesis.frame || '미확인'} · 원본 스캔 ${proposal.provenance.capture_age_s.toFixed(1)}초 전(조회 시점) · 위치 m, 각도 도 · ${poseText(proposal.imu_hypothesis)}`));
      proposalNodes.push(node('p', `본체 위치 후보 (정보성): 좌표 ${proposal.body_candidate.frame || '미확인'} · 위치 m, 각도 rad · ${poseText(proposal.body_candidate)}`));
      proposalNodes.push(node('p', `제안 품질: 겹침 ${proposal.quality.overlap} · RMSE ${proposal.quality.rmse_m} m · 제안 기준 ${finite(proposal.quality.hypothesis_overlap_min) ? proposal.quality.hypothesis_overlap_min : '미확인'}과 운영 초기 기준 ${finite(proposal.quality.operational_initial_overlap_min) ? proposal.quality.operational_initial_overlap_min : '미확인'}는 별도입니다. 운영 잔차 검사를 통과한 결과나 실제 위치 정확도가 아닙니다. 검증 요청 후 ${((performance.now() - proposalCheckedAt) / 1000).toFixed(1)}초 경과`));
    } else if (proposal.state === 'ready') proposalNodes.push(node('p', proposalFresh ? '제안 형식 또는 현재 문맥을 확인하지 못했습니다 → 사용할 수 없습니다.' : '제안 관측이 오래됐거나 신선도를 확인하지 못했습니다 → 새 상태를 기다리세요.'));
    else if (['capturing', 'running'].includes(proposal.state)) proposalNodes.push(node('p', '제안 계산 중 · 운영 위치추정은 시작되지 않았습니다.'));
    else proposalNodes.push(node('p', `제안 계산 완료되지 않음: ${inputReason(proposal.reason)}`));
    const cleanupLabels = { MONITORING: '작업 진행과 종료 여부 확인 중', CANCELLING: '취소 요청 처리 중 · 작업 종료 미확인', CANCEL_PENDING: '취소 후 종료 확인 지연 · 작업이 남아 있을 수 있습니다', CANCEL_FAILED: '취소 요청 실패 · 작업 종료 미확인', CLEANUP_UNCONFIRMED: '작업 정리 상태 미확인', JOB_UNAVAILABLE: '작업 상태를 확인할 수 없음', SETTLED: cleanupSettled() ? '작업 종료 확인 · 현재 점유 상태도 확인합니다' : '작업 종료 상태를 확인하지 못했습니다' };
    if (cleanupId) proposalNodes.push(node('p', `이전 제안 작업: ${cleanupLabels[cleanup?.state] || '작업 정리 상태 미확인'}.`));
    if (Array.isArray(blockers) && blockers.includes('OWNER_BUSY:global_observation')) proposalNodes.push(node('p', '전역 관측 작업이 사용 중입니다 → 종료와 점유 해제를 기다리세요.'));
    else if (!Array.isArray(blockers) || blockers.includes('OWNER_UNKNOWN:global_observation')) proposalNodes.push(node('p', '전역 관측 점유 상태를 확인하지 못했습니다.'));
    el('proposal-result').replaceChildren(...proposalNodes);
    const handoffStates = { CONFIRMED_OBSERVATION_ACTIVE: '가설 확인됨 · 관측 종료를 별도로 요청하세요', STOP_PENDING: '관측 종료 요청 진행 중 · 종료 확인 대기', OBSERVATION_STOPPED: '정확한 관측 세대의 종료 확인', SNAPSHOTTED: '새 실행에 가설 예약됨', INITIAL_POSE_ACCEPTED: '초기 위치 접수됨 · 정합은 별도 시작', MATCH_ARMED: '정합 요청 접수 · 실제 보정과 운영 준비는 별도 확인', INVALID: '가설 사용 불가', EXPIRED: '가설 사용 시간 만료', OUTCOME_UNKNOWN: '가설 상태 불확실' };
    const receiptStates = { NOT_REQUESTED: '종료 요청 없음', DISPATCH_PENDING: '종료 요청 처리 중', DISPATCH_ACCEPTED: '종료 요청 접수 · 종료 미확인', INACTIVE_CONFIRMED: '관측 비활성 확인', OUTCOME_UNKNOWN: '종료 결과 불확실' };
    const handoffNodes = [node('p', '감독 확인은 측정된 정지나 위치 정확도의 증거가 아닙니다. 관측과 새 실행 사이의 센서 공백은 측정되지 않습니다.')];
    if (handoffBusy) handoffNodes.push(node('p', '가설 확인 요청 중 · 자동 재전송하지 않습니다.'));
    if (handoffAwaitingStatus) handoffNodes.push(node('p', '가설 확인 결과를 서버 상태에서 확인 중입니다.'));
    if (handoffError) handoffNodes.push(node('p', handoffError));
    if (handoffInfo.identified) {
      const h = handoff;
      const expired = !handoffInfo.armed && !handoffInfo.unexpired && !['INVALID', 'OUTCOME_UNKNOWN'].includes(h.state);
      const currentMatchUnknown = h.state === 'MATCH_ARMED' && !handoffInfo.armed;
      handoffNodes.push(node('p', `출처: 명시 확인된 proposal_confirmed · 상태: ${currentMatchUnknown ? '정합 수락 이력 · 현재 실행의 수락은 미확인' : expired ? '사용 시간 만료' : handoffStates[h.state] || '확인 불가'} · ${handoffInfo.armed ? '초기화 사용 시간은 정합 접수 전까지 적용' : `남은 초기화 시간 ${handoffInfo.remaining === null ? '미확인' : Math.ceil(handoffInfo.remaining) + '초'}`}`));
      handoffNodes.push(node('p', `관측 종료: ${receiptStates[h.stop_receipt?.state] || '상태 미확인'}${h.reason ? ` · ${inputReason(h.reason)}` : ''}`));
      if (h.match_history) handoffNodes.push(node('p', '이전 정합 요청 수락 이력이 있습니다. 현재 실행의 정합 상태는 별도로 확인합니다.'));
      if (h.geometry && h.initial_pose_reference && handoffInfo.active) handoffNodes.push(node('p', `서버 보관 가설 (지도 좌표): 높이 ${h.geometry.z} m · roll ${h.geometry.roll} · pitch ${h.geometry.pitch} rad · 초기 XY/yaw 기준 ${h.initial_pose_reference.x}, ${h.initial_pose_reference.y}, ${h.initial_pose_reference.yaw}`));
      handoffNodes.push(node('p', `로컬 후보 사용 범위: ${h.policy.ttl_s}초 · XY ${h.policy.max_xy_m} m · yaw ${h.policy.max_yaw_rad} rad. 주행 설정이나 실제 위치 정확도가 아닙니다.`));
      handoffNodes.push(node('p', '다음 조작은 각각 별도입니다: 관측 종료 확인 → 아래 START NAV2 → INITIAL POSE 지정·전송 → ⑤ 정합 시작.'));
    } else if (state?.selected?.seed_geometry?.source === 'proposal_confirmed') handoffNodes.push(node('p', '확인된 가설의 현재 서버 상태가 불확실합니다 → 상태를 다시 확인하세요.'));
    else if (!handoffBusy && !handoffAwaitingStatus) handoffNodes.push(node('p', '확인된 초기 geometry 가설이 없습니다.'));
    el('handoff-result').replaceChildren(...handoffNodes);
    el('steps').replaceChildren(...model.steps.map(step => {
      const item = node('li'); item.dataset.state = step.status;
      item.append(node('strong', `${step.number}. ${step.title}`), node('span', step.status, 'preparation-state'), node('p', `완료 조건: ${step.condition}`), node('p', `검사 결과: ${step.result}`));
      const missing = step.issues.map(value => value.current).join(' · ');
      if (missing) item.append(node('p', `부족/실패: ${missing}`, 'preparation-missing'));
      item.append(node('small', step.next ? '다음 단계 확인 가능' : step.number > 1 && model.steps[step.number - 2].status !== '완료' ? `${step.number - 1}단계 확인 후 진행` : '조건을 해결한 뒤 이 단계에서 다시 확인'));
      const guidance = { 3: '아래 주행 조작부에서 Nav2를 시작하세요.', 4: '아래 지도 조작부에서 INITIAL POSE를 지정·전송하세요.', 7: '아래 지도 조작부에서 GOAL POSE를 지정·전송하세요.' }[step.number];
      if (guidance) item.append(node('p', guidance));
      if (step.number === 5) { const button = node('button', '정합 시작'); button.type = 'button'; button.disabled = busy || navigationBusy || !model.canMatch; button.onclick = match; item.append(button); }
      return item;
    }));
    const issueNodes = model.issues.map(value => { const item = node('p'); item.append(node('strong', `${value.step}단계 · ${value.current}`), document.createElement('br'), node('span', `필요: ${value.required} → 해결: ${value.remedy}`)); return item; });
    if (diagnosticIssue) issueNodes.push(node('p', `② ${diagnosticIssue} · 최종 관측 결과는 위 관측 검사를 확인하세요. 검사 값은 실시간이 아닙니다.`));
    el('issues').replaceChildren(...(issueNodes.length ? issueNodes : [node('p', model.enabled ? '현재 확인된 필수 항목 충족. 다음 단계 버튼으로 진행하세요.' : '3D 지도를 선택하면 단계별 저장 지도 위치추정 준비가 시작됩니다. 기존 2D 모드의 상태는 아래에서 확인하세요.')]));
    const detailInputs = inputs ? { ...inputs, evidence: inputs.evidence ? { ...inputs.evidence } : inputs.evidence } : null;
    if (detailInputs?.evidence) { delete detailInputs.evidence.diagnostics; if (diagnostics) detailInputs.evidence.diagnostics = diagnostics; }
    el('details').textContent = JSON.stringify({ selected: selected ? { generation: selected.generation, localization_3d: selected.localization_3d, navigation_2d: selected.navigation_2d, seed_geometry: geometry } : null, pair: state?.pair, runtime: source, readiness: navigation.readiness, metrics: navigation.localization_health?.metrics, errors: model.issues.map(value => value.code), preparation_inputs: detailInputs, diagnostics_note: diagnostics ? '검사 당시 값이며 실시간이 아닙니다. phase_ms는 서버 구간 경과이며 네트워크 왕복이나 lock 전용시간이 아닙니다.' : undefined, preparation_inputs_error: inputsError, observation_error: observationError, initialization_proposal: proposal, proposal_cleanup: cleanup, proposal_display_valid: Boolean(validPoses), proposal_error: proposalError, proposal_failure_detail: proposalFailureDetail, initialization_handoff: handoff, handoff_error: handoffError, handoff_failure_detail: handoffFailureDetail }, null, 2);
    return model;
  }
  async function refresh(force = false) {
    if (refreshing || busy || (!force && Date.now() - checkedAt < 2500)) return;
    refreshing = true;
    const inputToken = ++inputsRevision, requestedAt = performance.now();
    let readValue = null;
    try {
      const value = readValue = await api('/api/v1/navigation/operational-3d/preparation-inputs', { signal: AbortSignal.timeout(10000) });
      if (inputToken !== inputsRevision) return;
      const status = value?.operational_state;
      if (value?.schema !== 'robot-scope.navigation-preparation-inputs.v1' || !status || value.operational_state_error
          || !Object.hasOwn(status, 'selected') || !Object.hasOwn(status, 'pair') || !['LEGACY_2D', 'NEXT_NAVIGATION_START'].includes(status.activation)) {
        throw new Error(value?.operational_state_error || '운영 준비 상태 미확인');
      }
      if (status.selected?.workflow === 'staged_navigation_pair' && (!value.pair || !status.pair
          || status.selected.generation !== value.pair.generation || status.pair.generation !== value.pair.generation
          || !samePin(status.selected.localization_3d, value.pair.localization_3d) || !samePin(status.selected.navigation_2d, value.pair.navigation_2d))) throw new Error('CONTEXT_CHANGED');
      inputs = value; inputsRequestedAt = requestedAt; inputsError = ''; state = status; available = true; fetchError = '';
      if (Object.hasOwn(status, 'initialization_handoff') && status.initialization_handoff !== null) setHandoff(status.initialization_handoff, requestedAt);
      else {
        clearHandoff();
        if (status.selected?.seed_geometry?.source === 'proposal_confirmed') handoffError = '서버에 확인된 가설의 현재 상태가 없습니다.';
        else if (handoffAwaitingStatus && !handoffError) handoffError = '서버에서 확인된 가설을 찾지 못했습니다. 현재 상태를 확인하세요.';
        else if (!status.selected || (status.selected.seed_geometry?.source && status.selected.seed_geometry.source !== 'proposal_confirmed')) { handoffError = ''; handoffFailureDetail = ''; }
        handoffAwaitingStatus = false;
      }
      if (!draftTouched && !map3dSelect.value && state.selected?.localization_3d?.map_id) map3dSelect.value = state.selected.localization_3d.map_id;
      // Expire the preview even if the next dashboard status poll is delayed.
      const ages = Object.values(value.candidates || {}).map(item => item?.provenance?.age_s).filter(age => finite(age) && age >= 0);
      const oldestMs = ages.length ? Math.max(...ages) * 1000 : 500;
      setTimeout(() => { if (inputToken === inputsRevision) render(); }, Math.max(0, 501 - oldestMs - (performance.now() - requestedAt)));
      if (value.evidence?.diagnostics) setTimeout(() => { if (inputToken === inputsRevision) render(); }, Math.max(0, 10001 - (performance.now() - requestedAt)));
      if (value.reference_pose) {
        const updateAge = () => { if (inputToken === inputsRevision) { render(); setTimeout(updateAge, 1000); } };
        setTimeout(updateAge, 1000);
      }
    } catch (failure) {
      if (inputToken === inputsRevision) { inputs = readValue?.observation ? { observation: readValue.observation } : null; state = null; available = false; inputsError = failure.message; fetchError = `상태 확인 실패: ${INPUT_REASONS[failure.message] || '연결 또는 서버 응답을 확인하세요.'}`; clearHandoff(); if (handoffAwaitingStatus) handoffError = '가설 확인 결과를 읽지 못했습니다. 재전송하지 않고 서버 상태를 확인하세요.'; handoffAwaitingStatus = false; }
    } finally { checkedAt = Date.now(); refreshing = false; render(); onChange(); if ((handoffAwaitingStatus && !handoffBusy) || (advisoryRefreshPending && !busy)) { advisoryRefreshPending = false; checkedAt = 0; queueMicrotask(() => { void refresh(true); }); } }
  }
  async function observe(action) {
    const session = inputs?.observation;
    const { model, busy: navigationBusy } = current();
    const pair = inputs?.pair;
    const blockers = inputs?.start_blockers?.items;
    if (observationBusy || (action === 'start' ? busy || navigationBusy || model.active || !available || !model.matched || !state?.selected || pair?.valid !== true || pair.generation !== state.selected.generation || !samePin(pair.localization_3d, state.selected.localization_3d) || !samePin(pair.navigation_2d, state.selected.navigation_2d) || session?.can_start !== true || !Array.isArray(blockers) || blockers.length > 0 : session?.can_stop !== true || !/^[a-f0-9]{32}$/.test(session?.session_id || ''))) return;
    invalidateProposal(); observationBusy = true; observationError = ''; available = false; ++inputsRevision; render();
    try {
      const result = await api(`/api/v1/observations/fastlio/${action}`, { method: 'POST', body: JSON.stringify({ confirmed: true, ...(action === 'stop' ? { session_id: session.session_id } : {}) }), signal: AbortSignal.timeout(12000) });
      inputs = { observation: result };
    } catch (failure) { observationError = `관측 ${action === 'start' ? '시작' : '종료'} 거절 또는 응답 실패: ${failure.message} · 자동 재시도하지 않습니다.`; inputs = null; }
    finally { observationBusy = false; checkedAt = 0; if (refreshing) { render(); } else { await refresh(true); } }
  }
  async function run(path, body, method = 'POST') {
    if (busy) return;
    if (!path.endsWith('/match')) invalidateProposal();
    busy = true; error = ''; actionStep = path.endsWith('/seed-geometry') ? 2 : path.endsWith('/match') ? 5 : 1; render(); onChange();
    try { state = await api(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(15000) }); available = true; invalidated = ''; }
    catch (failure) { error = failure.message; }
    finally { busy = false; actionStep = null; checkedAt = 0; await refresh(true); render(); onChange(); }
  }
  async function match() {
    const { model, navigation } = current();
    if (!model.canMatch) return;
    const source = navigation.operational_localization;
    await run('/api/v1/navigation/operational-3d/match', { map_id: navigation.map.id, map_revision: navigation.map.revision,
      bundle_generation: source.bundle_generation, localization_generation: source.localization_generation,
      initial_pose_stamp_ns: source.accepted_initial_pose.stamp_ns });
  }
  async function pollProposal(token, ctx, id) {
    if (token !== proposalEpoch || !proposalContextMatches(ctx)) { if (token === proposalEpoch) { invalidateProposal(); render(); } return; }
    try {
      const requestedAt = performance.now();
      const result = await api(`/api/v1/navigation/operational-3d/initialization-proposals/${id}`, { signal: AbortSignal.timeout(10000) });
      if (token !== proposalEpoch) return;
      recordCleanup(result, id);
      if (!proposalContextMatches(ctx) || !proposalResponseMatches(result, ctx) || result.proposal_id !== id) { invalidateProposal('제안의 지도·관측 문맥이 달라 사용할 수 없습니다.'); render(); return; }
      if (result.state === 'ready' && !['observer_id', 'cloud_epoch', 'pose_epoch'].every(key => result.provenance?.source_contract?.[key] === ctx.source?.[key])) {
        invalidateProposal('제안의 센서 출처가 현재 관측과 달라 사용할 수 없습니다.'); render(); return;
      }
      proposal = result; proposalVerified = true; proposalCheckedAt = requestedAt; clearTimeout(proposalExpiryTimer); render();
      if (result.state === 'ready') {
        const age = result.provenance?.pose_age_s;
        if (finite(age) && age >= 0) proposalExpiryTimer = setTimeout(() => { if (token === proposalEpoch) render(); }, Math.max(0, 1001 - age * 1000 - (performance.now() - requestedAt)));
      }
      if (['capturing', 'running', 'ready'].includes(result.state) || !cleanupSettled()) proposalTimer = setTimeout(() => { void pollProposal(token, ctx, id); }, 2000);
    } catch (failure) {
      if (token !== proposalEpoch) return;
      proposalFailureDetail = failure.message; invalidateProposal('제안 상태 조회 실패 → 현재 관측과 연결을 확인하세요. 자동 재요청하지 않습니다.'); render();
    }
  }
  async function calculateProposal() {
    if (el('proposal').disabled || proposalBusy) return;
    const pair = inputs?.pair, session = inputs?.observation;
    const ctx = { generation: pair.generation, localization_3d: pair.localization_3d, navigation_2d: pair.navigation_2d,
      calibration_sha256: pair.calibration_sha256, session_id: session.session_id, source: proposalSource(inputs.evidence) };
    if (!globalThis.crypto?.getRandomValues) { proposalError = '안전한 요청 식별자를 만들 수 없습니다.'; render(); return; }
    const requestId = [...globalThis.crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2, '0')).join('');
    clearTimeout(proposalTimer); clearTimeout(proposalExpiryTimer); clearTimeout(cleanupTimer); ++cleanupEpoch; cleanup = null; cleanupId = null; const token = ++proposalEpoch;
    proposal = null; proposalError = ''; proposalFailureDetail = ''; proposalContext = ctx; proposalVerified = false; proposalBusy = true; render();
    try {
      const result = await api('/api/v1/navigation/operational-3d/initialization-proposals', { method: 'POST',
        body: JSON.stringify({ request_id: requestId, bundle_generation: ctx.generation, observation_session_id: ctx.session_id }), signal: AbortSignal.timeout(15000) });
      if (proposalResponseMatches(result, ctx)) recordCleanup(result, result.proposal_id);
      if (token !== proposalEpoch) { if (cleanupId && !cleanupSettled()) scheduleCleanupPoll(); return; }
      if (!proposalContextMatches(ctx) || !proposalResponseMatches(result, ctx)) { invalidateProposal('제안의 지도·관측 문맥이 달라 사용할 수 없습니다.'); return; }
      proposal = result; void pollProposal(token, ctx, result.proposal_id);
    } catch (failure) {
      if (token !== proposalEpoch) return;
      proposalFailureDetail = failure.message;
      const reason = Object.keys(INPUT_REASONS).find(code => String(failure.message).includes(code));
      proposalError = `${reason ? inputReason(reason) : '제안 요청이 거절됐거나 응답을 확인하지 못했습니다 → 기술 상세를 확인하세요.'} 자동 재전송하지 않습니다.`;
      proposalContext = null;
    } finally { proposalBusy = false; advisoryAfter = performance.now(); checkedAt = 0; render(); if (refreshing || busy) advisoryRefreshPending = true; else void refresh(true); }
  }
  async function confirmHandoff() {
    const { model, handoffInfo, busy: navigationBusy } = current(), pair = inputs?.pair, session = inputs?.observation, blockers = inputs?.start_blockers?.items;
    if (el('confirm-handoff').disabled || handoffBusy || handoffAwaitingStatus || !el('supervision').checked || !proposalPoseValid()
        || !proposalContextMatches() || !cleanupSettled() || !available || busy || navigationBusy || model.active || observationBusy || handoffInfo.active
        || !Array.isArray(blockers) || blockers.some(code => ['OWNER_BUSY:global_observation', 'OWNER_UNKNOWN:global_observation', 'START_BLOCKERS_UNAVAILABLE', 'OBSERVATION_STATUS_UNAVAILABLE'].includes(code))
        || inputsRequestedAt < advisoryAfter || !pair || !session || !globalThis.crypto?.getRandomValues) return;
    const ctx = proposalContext, proposalId = proposal.proposal_id, token = proposalEpoch;
    const requestId = [...globalThis.crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2, '0')).join('');
    handoffBusy = true; handoffAwaitingStatus = true; handoffError = ''; handoffFailureDetail = ''; el('supervision').checked = false; ++inputsRevision; render();
    try {
      const result = await api(`/api/v1/navigation/operational-3d/initialization-proposals/${proposalId}/confirm-geometry`, { method: 'POST',
        body: JSON.stringify({ request_id: requestId, bundle_generation: ctx.generation, observation_session_id: ctx.session_id, confirmed: true, stationary_supervision_acknowledged: true }), signal: AbortSignal.timeout(15000) });
      if (!handoffShape(result) || result.proposal_id !== proposalId || result.bundle_generation !== ctx.generation || result.observation_session_id !== ctx.session_id) {
        handoffError = '확인 응답의 문맥을 검증하지 못했습니다. 서버 상태를 확인하세요.';
      } else if (token !== proposalEpoch || !proposalContextMatches(ctx)) {
        handoffError = '확인 중 관측 또는 지도가 바뀌었습니다. 현재 서버 상태를 확인하세요.';
      }
    } catch (failure) {
      handoffFailureDetail = failure.message;
      const reason = Object.keys(INPUT_REASONS).find(code => String(failure.message).includes(code));
      handoffError = `가설 확인 실패 또는 결과 불확실: ${reason ? inputReason(reason) : '서버 상태와 기술 상세를 확인하세요.'} 자동 재전송하지 않습니다.`;
    } finally {
      handoffBusy = false; checkedAt = 0; render(); if (!refreshing && !busy) void refresh(true);
    }
  }
  map3dSelect.addEventListener('change', () => { invalidateProposal(); clearHandoff(); draftTouched = true; selected3d = map3dSelect.value; draft3dRevision = current().draft3d?.revision || ''; error = ''; render(); onChange(); });
  map2dSelect.addEventListener('change', () => { invalidateProposal(); clearHandoff(); draftTouched = true; error = ''; });
  el('pair').onclick = () => { const { draft3d, map } = current(); if (!draft3d || !map) return; void run('/api/v1/navigation/operational-3d/pair', { map_id: draft3d.id, map_revision: draft3d.revision, navigation_map_id: map.id, navigation_map_revision: map.revision }); };
  el('clear').onclick = async () => { await run('/api/v1/navigation/operational-3d', undefined, 'DELETE'); if (!state?.selected) { map3dSelect.value = ''; draftTouched = true; render(); onChange(); } };
  el('geometry').onclick = () => {
    const values = Object.fromEntries([...host.querySelectorAll('[data-geometry]')].map(input => [input.dataset.geometry, input.value.trim() === '' ? null : Number(input.value)]));
    if (!['z', 'roll', 'pitch'].every(key => finite(values[key]))) { error = '높이·roll·pitch를 모두 명시적으로 입력하세요. 빈 값은 0으로 처리하지 않습니다.'; render(); return; }
    void run('/api/v1/navigation/operational-3d/seed-geometry', { generation: state?.selected?.generation, ...values });
  };
  el('refresh').onclick = () => { error = ''; void refresh(true); void actions.refresh(); };
  el('observe-start').onclick = () => { void observe('start'); };
  el('observe-stop').onclick = () => { void observe('stop'); };
  el('proposal').onclick = () => { void calculateProposal(); };
  el('supervision').onchange = () => { render(); };
  el('confirm-handoff').onclick = () => { void confirmHandoff(); };
  return { render() { const result = render(); const next = current().draft3d; if (selected3d && next?.id === selected3d && draft3dRevision && next.revision !== draft3dRevision) invalidated = '3D 지도 revision이 변경됐습니다. ①부터 다시 확인하세요.'; return result; }, refresh,
    canStart: () => { const value = current(); return !busy && !handoffBusy && !handoffAwaitingStatus && !observationBusy && value.model.canStart && (state?.selected?.seed_geometry?.source !== 'proposal_confirmed' || value.handoffInfo.unexpired && handoff?.state === 'OBSERVATION_STOPPED' && state?.pair?.can_start === true); }, permitsGoal: () => available && (!current().model.enabled || current().model.tracking),
    state: () => state };
}
