/** Presentation only. Runtime admission remains authoritative for every command. */
export const PREPARATION_STEPS = [
  ['지도 선택·연결 확인', '사용자가 3D에서 변환한 2D 지도인지와 같은 좌표 기준인지를 확인하고 적용'],
  ['센서·교정·초기값 준비', '센서 관측과 출처·좌표 기준을 확인하고 지도 기준 초기 높이·기울기 준비'],
  ['Nav2 시작·노드와 TF 확인', '실행 source, 현재 점군·자세, Nav2 노드와 TF 입력 확인'],
  ['INITIAL POSE 지정·전송', '지도에서 지정한 현재 위치·방향의 실제 런타임 접수 확인'],
  ['현재 LiDAR와 저장 지도 정합', '명시적으로 정합을 시작하고 실제 보정 갱신·품질 확인'],
  ['추정 위치·주행 준비 확인', '신선한 추정 위치, TF 반영과 기존 주행 안전 조건 충족'],
  ['목표 전송·경로 진행', '사용자가 별도로 목표를 전송하고 실제 Nav2 종료 확인'],
];

const REASONS = {
  WAITING_EXPLICIT_INITIAL_POSE: ['초기 위치·방향 미지정', '실제 정지 상태에서 INITIAL POSE를 지정·전송하세요.'],
  WAITING_EXPLICIT_MAP_MATCH: ['정합 시작 입력 필요', '초기 위치 접수 후 ④ 정합 시작을 누르세요.'],
  WAITING_EXPLICIT_MATCH: ['정합 시작 입력 필요', '초기 위치 접수 후 ④ 정합 시작을 누르세요.'],
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
  CONTROL_BRIDGE_NOT_INACTIVE: '현재 bridge의 관측용 명령 차단을 확인하지 못했습니다 → bridge 상태와 관측 세션을 확인하세요.',
  CONTROL_BRIDGE_INHIBIT_UNSUPPORTED: '활성 bridge가 관측용 명령 차단 계약을 지원하지 않습니다 → 검증된 bridge 버전이 필요합니다.',
  CONTROL_BRIDGE_INHIBIT_RETAINED: '이전 관측의 명령 차단이 남아 있습니다 → 관측 종료와 bridge 복구 상태를 확인하세요.',
  CONTROL_BRIDGE_INHIBIT_STALE: 'bridge의 서명된 명령 차단 상태가 오래됐습니다 → 새 상태가 필요합니다.',
  CONTROL_BRIDGE_INHIBIT_UNREADY: 'bridge의 현재 제어 상태가 불확실합니다 → 정지·연결·제어 상태를 확인하세요.',
  CONTROL_BRIDGE_COMMAND_BUSY: '기존 제어권 또는 대기 명령이 있습니다 → 기존 제어 작업을 종료하세요.',
  CONTROL_BRIDGE_INHIBIT_VIOLATED: '관측 도중 bridge 차단 조건을 잃었습니다 → 이번 관측을 종료하고 원인을 확인하세요.',
  CONTROL_BRIDGE_INHIBIT_RELEASE_PENDING: '관측은 정지됐으나 bridge 명령 차단 해제를 확인 중입니다.',
  OBSERVATION_STATUS_UNCONFIRMED: '관측 상태 조회가 실패했습니다 → 이번 관측은 재사용하지 않고 종료 상태를 확인하세요.',
  OBSERVATION_START_PENDING: '관측 시작 요청 후 실제 실행 세대를 기다립니다 → 명령 차단을 유지합니다.',
  OBSERVATION_STOP_ACCEPTANCE_UNCONFIRMED: '관측 종료 요청의 수락을 확인하지 못했습니다 → 명령 차단을 유지하며 담당자의 정지·회수 확인이 필요합니다.',
  OBSERVATION_START_OUTCOME_UNKNOWN: '관측 시작 결과가 불명입니다 → 명령 차단을 유지하며 현재 세션과 종료 상태를 확인하세요.',
  OBSERVATION_OWNER_CHANGED_OR_UNKNOWN: '관측 도중 다른 작업의 소유권이 바뀌었거나 불명입니다 → 이번 관측을 종료하고 상태를 확인하세요.',
  CONTROL_BRIDGE_STATE_UNKNOWN: '제어 bridge 상태를 확인하지 못했습니다 → 연결과 상태를 확인하세요.',
  START_BLOCKERS_UNAVAILABLE: '시작 조건을 확인하지 못했습니다 → 연결과 상태를 다시 확인하세요.',
  OBSERVATION_STATUS_UNAVAILABLE: '관측 상태를 확인하지 못했습니다 → 연결과 상태를 다시 확인하세요.',
  MAP_PAIR_CHANGED: '지도 구성이 바뀌었습니다 → 현재 지도와 관측을 다시 확인하세요.',
  OBSERVATION_SESSION_CHANGED: '관측 실행이 바뀌었습니다 → 새 관측에서 다시 계산하세요.',
  GLOBAL_BACKEND_UNAVAILABLE: '전역 위치 제안 기능을 사용할 수 없습니다 → 서버 구성을 확인하세요.',
  GLOBAL_JOB_NOT_READY: '위치 제안 계산이 아직 준비되지 않았습니다 → 현재 상태를 확인하세요.',
  GLOBAL_AMBIGUOUS: '서로 구분되지 않는 위치 후보가 있습니다 → 관측과 지도 단서를 확인하세요.',
  PRIOR_NO_MATCH: '서버 검증 한도 안에 조건을 충족하는 후보가 없습니다 → 초안과 관측을 다시 확인하세요.',
  PRIOR_MULTIPLE_MATCHES: '서버 검증 한도 안에 여러 후보가 있습니다 → 모호성이 남아 있습니다.',
  CANDIDATE_RETENTION_UNCONFIRMED: '비교할 후보 집합의 완전성을 확인하지 못했습니다.',
  CANDIDATE_QUALITY_UNAVAILABLE: '후보 품질을 모두 확인하지 못했습니다.',
  OPERATOR_PRIOR_EXPIRED: '사용자 초안의 사용 시간이 지났습니다 → 현재 위치를 다시 확인하세요.',
  PRIOR_HANDOFF_MISMATCH: '초안과 후보가 기존 초기 위치 허용 범위를 벗어났습니다 → 다시 확인하세요.',
  CONDITIONAL_PRIOR_CONFIRMATION_REQUIRED: '조건부 후보의 명시적 확인이 필요합니다.',
  OPERATOR_PRIOR_PROOF_CHANGED: '초안 또는 후보 근거가 변경됐습니다 → 다시 확인하세요.',
  INITIAL_POSE_PRIOR_MISMATCH: '초기 위치가 초안 기준 검증 한도를 벗어났습니다 → 다시 확인하세요.',
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
  if (typeof code === 'string' && code.startsWith('CONTROL_BRIDGE_INHIBIT_')) return 'bridge의 관측용 명령 차단을 확인할 수 없습니다 → 이번 관측을 종료하고 bridge 상태를 확인하세요.';
  if (typeof code === 'string' && code.startsWith('CONTROL_') && code.includes('DURING_OBSERVATION')) return '관측 도중 제어 상태가 바뀌었거나 불명입니다 → 이번 관측을 종료하고 상태를 확인하세요.';
  const owners = { mapping: '지도 작성', navigation: '주행', slam: 'SLAM', control: '수동 제어', raw_capture: '센서 원본 기록', dataset: '데이터 기록', mission: '미션', mission_routes: '미션 경로', route_planner: '경로 계획', lifecycle: '실행 전환', global_observation: '전역 관측', relocalization: '위치 재추정', sensor_tracking: '센서 추적' };
  if (typeof code === 'string' && code.startsWith('OWNER_BUSY:')) return `${owners[code.slice(11)] || '다른 작업'}이 센서를 사용 중입니다 → 해당 작업의 종료 상태를 확인하세요.`;
  if (typeof code === 'string' && code.startsWith('OWNER_UNKNOWN:')) return `${owners[code.slice(14)] || '다른 작업'}의 점유 상태를 확인하지 못했습니다 → 현재 작업 상태를 확인하세요.`;
  return '상세 원인을 확인하지 못했습니다 → 기술 상세에서 서버의 검사 결과를 확인하세요.';
}
const finite = value => typeof value === 'number' && Number.isFinite(value);
const validGeometry = value => Boolean(value && finite(value.z) && Math.abs(value.z) <= 1000
  && finite(value.roll) && Math.abs(value.roll) <= Math.PI && finite(value.pitch) && Math.abs(value.pitch) <= Math.PI / 2);
const geometryText = value => `높이 ${value.z.toFixed(3)} m · roll ${value.roll.toFixed(3)} rad · pitch ${value.pitch.toFixed(3)} rad`;
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
    // Diagnostics retain rejected observed values; admission uses separate gates.
    result.state = text(source.state);
    result.units = text(source.units);
    result.sent_points = Number.isInteger(source.sent_points) && source.sent_points >= 0 && source.sent_points <= 2147483647 ? source.sent_points : null;
    result.receipt_after_session_start = typeof source.receipt_after_session_start === 'boolean' ? source.receipt_after_session_start : null;
    result.source_stamp_ns = typeof source.source_stamp_ns === 'string' && /^\d{1,20}$/.test(source.source_stamp_ns) ? source.source_stamp_ns : null;
    for (const key of ['receipt_age_s', 'graph_age_s']) result[key] = finite(source[key]) && Math.abs(source[key]) <= 1e9 ? source[key] : null;
    result.graph_state = text(source.graph_state);
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
const CONDITIONAL_POLICY = 'robot-scope.proposal-handoff.operator-prior-v1';
const originalAmbiguityLabel = unresolved => unresolved ? '원본 판정: 모호성 미해결 · 원래 모호성은 유지됩니다.' : '원본 판정: 비모호 · 원본 판정은 유지됩니다.';
function sameOperatorPrior(a, b) {
  const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
  const base = ['frame','pose_reference','units','pose','source','stationary_current_pose_confirmed','navigation_map_id','navigation_map_revision','calibration_sha256'];
  const shape = value => value && keys(value, Object.hasOwn(value, 'bounds') ? [...base, 'bounds'] : base) && keys(value.pose, ['x','y','yaw']) && (!Object.hasOwn(value, 'bounds') || keys(value.bounds, ['xy_m','yaw_rad']));
  return Boolean(shape(a) && shape(b) && Object.hasOwn(a, 'bounds') === Object.hasOwn(b, 'bounds')
    && ['frame', 'pose_reference', 'units', 'source', 'stationary_current_pose_confirmed', 'navigation_map_id', 'navigation_map_revision', 'calibration_sha256'].every(key => a[key] === b[key])
    && ['x', 'y', 'yaw'].every(key => a.pose?.[key] === b.pose?.[key]) && (!Object.hasOwn(a, 'bounds') || ['xy_m', 'yaw_rad'].every(key => a.bounds?.[key] === b.bounds?.[key])));
}
function priorResolutionBounds(proof) {
  if (!proof || !proof.operator_prior || typeof proof.operator_prior !== 'object') return null;
  const prior = proof.operator_prior, explicit = Object.hasOwn(prior, 'bounds');
  const sourcePresent = Object.hasOwn(proof, 'bounds_source'), effectivePresent = Object.hasOwn(proof, 'effective_bounds');
  if (sourcePresent !== effectivePresent) return null;
  if (!sourcePresent) return explicit ? prior.bounds : null;
  const bounds = proof.effective_bounds;
  if (!bounds || typeof bounds !== 'object' || Array.isArray(bounds) || Object.keys(bounds).length !== 2 || !Object.hasOwn(bounds, 'xy_m') || !Object.hasOwn(bounds, 'yaw_rad')) return null;
  if (proof.bounds_source === 'server_policy' && !explicit && bounds.xy_m === .25 && bounds.yaw_rad === .20) return bounds;
  if (proof.bounds_source === 'operator_prior' && explicit && bounds.xy_m === prior.bounds?.xy_m && bounds.yaw_rad === prior.bounds?.yaw_rad) return bounds;
  return null;
}
function priorBoundsText(proof) {
  const bounds = priorResolutionBounds(proof);
  const source = proof.bounds_source === 'server_policy' ? '서버 정책' : '사용자 입력 범위';
  return `후보 선택에 적용된 범위 (${source}): 위치 ${bounds.xy_m} m · 방향 ±${bounds.yaw_rad} rad. 사용자 불확실성 측정이나 실제 정확도가 아닙니다.`;
}
const GROUPING_FIELDS = ['grouping_policy', 'matching_hypothesis_count', 'matching_retained_candidate_count', 'matching_member_indices', 'matching_member_geometry', 'verified_duplicate_count'];
function validPriorCandidateGrouping(proof) {
  if (!GROUPING_FIELDS.some(key => Object.hasOwn(proof, key))) return proof.matching_candidate_count === 1;
  const indices = proof.matching_member_indices, geometry = proof.matching_member_geometry, count = proof.matching_retained_candidate_count;
  if (proof.grouping_policy !== 'PINNED_V031_SE3_FIRST_REPRESENTATIVE_V1' || proof.matching_hypothesis_count !== 1
      || !Number.isInteger(count) || count < 1 || count > proof.eligible_candidate_count || proof.matching_candidate_count !== count
      || !Number.isInteger(proof.verified_duplicate_count) || proof.verified_duplicate_count < count - 1 || proof.verified_duplicate_count >= proof.eligible_candidate_count
      || !Array.isArray(indices) || indices.length !== count || !Array.isArray(geometry) || geometry.length !== count
      || indices[0] !== proof.candidate_index || !indices.every((value, i) => Number.isInteger(value) && value >= 0 && value < proof.retained_candidate_count && (!i || value > indices[i - 1]))) return false;
  const representative = geometry[0], wrap = value => Math.atan2(Math.sin(value), Math.cos(value));
  return geometry.every((member, i) => member && member.candidate_index === indices[i]
    && ['z_m', 'roll_rad', 'pitch_rad', 'z_delta_m', 'roll_delta_rad', 'pitch_delta_rad'].every(key => finite(member[key]))
    && Math.abs(member.z_delta_m - (member.z_m - representative.z_m)) < 1e-8
    && Math.abs(wrap(member.roll_delta_rad - wrap(member.roll_rad - representative.roll_rad))) < 1e-8
    && Math.abs(wrap(member.pitch_delta_rad - wrap(member.pitch_rad - representative.pitch_rad))) < 1e-8);
}
function validPriorCurrentMembers(proof, current, stored = false) {
  if (!proof?.grouping_policy) return true;
  const checks = current?.member_checks, indices = proof.matching_member_indices, bounds = priorResolutionBounds(proof);
  if (!Array.isArray(indices) || !Array.isArray(checks) || checks.length !== indices.length || !checks.length
      || !/^[1-9][0-9]{0,19}$/.test(current?.pose_stamp_ns || '') || !finite(bounds?.xy_m) || !finite(bounds?.yaw_rad)) return false;
  const valid = checks.every((item, i) => item && item.candidate_index === indices[i]
    && finite(item.xy_distance_m) && item.xy_distance_m >= 0 && finite(item.absolute_wrapped_yaw_rad) && item.absolute_wrapped_yaw_rad >= 0 && item.absolute_wrapped_yaw_rad <= Math.PI
    && typeof item.within_prior_bounds === 'boolean' && item.within_prior_bounds === (item.xy_distance_m <= bounds.xy_m && item.absolute_wrapped_yaw_rad <= bounds.yaw_rad));
  if (!valid) return false;
  const all = checks.every(item => item.within_prior_bounds);
  if (stored) return all;
  const first = checks[0];
  return typeof current.all_members_within_prior_bounds === 'boolean' && current.all_members_within_prior_bounds === all
    && finite(current.pose_age_s) && current.pose_age_s >= 0 && current.pose_age_s <= 1
    && finite(current.xy_distance_m) && Math.abs(current.xy_distance_m - first.xy_distance_m) < 1e-8
    && finite(current.yaw_delta_rad) && Math.abs(Math.abs(current.yaw_delta_rad) - first.absolute_wrapped_yaw_rad) < 1e-8
    && current.within_prior_bounds === first.within_prior_bounds
    && typeof current.within_existing_handoff_reference === 'boolean'
    && current.within_existing_handoff_reference === (first.xy_distance_m <= .25 && first.absolute_wrapped_yaw_rad <= .20);
}
function validConditionalResolution(proof, ctx) {
  const prior = proof?.operator_prior, bounds = priorResolutionBounds(proof), diagnostic = proof?.candidate_vs_prior;
  const distanceOk = finite(diagnostic?.xy_distance_m) && diagnostic.xy_distance_m >= 0 && finite(diagnostic?.absolute_wrapped_yaw_rad) && diagnostic.absolute_wrapped_yaw_rad >= 0;
  return Boolean(proof?.schema === 'robot-scope.operator-prior-resolution.v1' && proof.classification === 'CONDITIONAL_ON_OPERATOR_PRIOR'
    && proof.original_ambiguity_preserved === true && typeof proof.original_ambiguity_unresolved === 'boolean' && proof.global_uniqueness_verified === false && proof.absolute_accuracy_m === null
    && /^[a-f0-9]{32}$/.test(proof.prior_id || '') && /^[a-f0-9]{64}$/.test(proof.source_contract_sha256 || '') && /^[a-f0-9]{64}$/.test(proof.original_observation_sha256 || '')
    && /^[1-9][0-9]{0,19}$/.test(proof.prior_anchor_stamp_ns || '') && finite(proof.accepted_monotonic_s) && finite(proof.expires_monotonic_s)
    && proof.accepted_monotonic_s >= 0 && proof.expires_monotonic_s > proof.accepted_monotonic_s && proof.expires_monotonic_s <= proof.accepted_monotonic_s + 120
    && proof.bundle_generation === ctx.generation && proof.observation_session_id === ctx.session_id && proof.calibration_sha256 === ctx.calibration_sha256
    && samePin(proof.localization_3d, ctx.localization_3d) && samePin(proof.navigation_2d, ctx.navigation_2d)
    && prior?.frame === 'map' && prior.pose_reference === 'base_link' && prior.units === 'metres_radians' && prior.source === 'OPERATOR_CURRENT_MAP_DRAFT'
    && prior.stationary_current_pose_confirmed === true && prior.navigation_map_id === ctx.navigation_2d?.map_id && prior.navigation_map_revision === ctx.navigation_2d?.revision
    && prior.calibration_sha256 === ctx.calibration_sha256 && sameOperatorPrior(prior, prior) && ['x','y','yaw'].every(key => finite(prior.pose?.[key])) && Math.abs(prior.pose.x) <= 1000 && Math.abs(prior.pose.y) <= 1000 && Math.abs(prior.pose.yaw) <= Math.PI
    && finite(bounds?.xy_m) && bounds.xy_m >= .1 && bounds.xy_m <= 3 && finite(bounds?.yaw_rad) && bounds.yaw_rad >= Math.PI / 180 && bounds.yaw_rad <= Math.PI / 2
    && (!ctx.operatorPrior || sameOperatorPrior(prior, ctx.operatorPrior))
    && Number.isInteger(proof.candidate_index) && Number.isInteger(proof.retained_candidate_count) && Number.isInteger(proof.eligible_candidate_count)
    && proof.candidate_index >= 0 && proof.candidate_index < proof.retained_candidate_count && proof.retained_candidate_count <= 18
    && proof.eligible_candidate_count >= 1 && proof.eligible_candidate_count <= proof.retained_candidate_count && validPriorCandidateGrouping(proof)
    && proof.projection_basis === 'NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE' && distanceOk
    && diagnostic.xy_distance_m <= bounds.xy_m && diagnostic.absolute_wrapped_yaw_rad <= bounds.yaw_rad
    && typeof diagnostic.within_existing_handoff_reference === 'boolean'
    && diagnostic.within_existing_handoff_reference === (diagnostic.xy_distance_m <= .25 && diagnostic.absolute_wrapped_yaw_rad <= .20));
}
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
  for (const check of pairChecks) issues.push(issue(check.code || 'PAIR_CHECK_FAILED', check.current || '서버 검사 미충족', check.required || '서버 검증 통과', check.code === 'INITIAL_HEIGHT_TILT_REQUIRED' ? '②에서 초기 위치 제안을 계산해 감독 확인 후 적용하거나, 확인한 지도 기준 값을 직접 입력·저장하세요.' : check.remedy || '해당 단계를 다시 확인하세요.', geometryCodes.has(check.code) ? 2 : state.pair.restart_from_step || 1));
  if (!draft3d) issues.push(issue('MAP_3D_REQUIRED', '3D 지도 미선택', '위치추정용 저장 3D 지도', '3D 위치추정 지도에서 지도를 선택하세요.', 1));
  if (!draft2d) issues.push(issue('MAP_2D_REQUIRED', '2D 지도 미선택', '경로 계산용 2D 지도', '2D 경로 계산 지도를 선택하세요.', 1));
  if (draft3d && draft2d && !matched) issues.push(issue('PAIR_NOT_APPLIED', '선택한 지도 조합이 아직 적용되지 않았거나 변경됨', '사용자의 변환 관계·동일 좌표 기준 확인', '지도 조합 확인란을 체크하고 ① 지도 연결 확인·적용을 누르세요. 실행 중이면 먼저 STOP하세요.', 1));
  if (selected && !geometryReady && !geometryBlocked) issues.push(issue('INITIAL_GEOMETRY_REQUIRED', '초기 높이·기울기 미확인', '지도 좌표의 본체 높이(m)·roll/pitch(rad)', '②에서 초기 위치 제안을 계산해 감독 확인 후 적용하거나, 확인한 지도 기준 값을 직접 입력·저장하세요.', 2));
  if (selected && selected.calibration?.verified !== true) issues.push(issue('CALIBRATION_REQUIRED', '검증된 교정 정보 없음', '본체·센서·TF 교정 확인', '본체·센서 교정의 서버 검사 결과를 확인하세요.', 2));
  if (running && !applied) issues.push(issue('RUNTIME_SOURCE_MISMATCH', '실행 source 또는 지도·실행 세대 불일치', '선택한 구성과 동일한 실제 source', 'STOP 후 ①에서 지도 구성을 다시 확인하세요.', 3));
  if (applied && !nodesReady) {
    if (source.fresh !== true) issues.push(issue('RUNTIME_STATUS_STALE', '실행 상태 수신 오래됨', '신선한 센서·노드 검사 결과', '입력과 런타임 연결을 확인하고 ③부터 다시 확인하세요.', 3));
    for (const [key, label] of [['scan', '현재 /scan'], ['odometry', 'FAST-LIO 자세'], ['map_server', '지도 서버'], ['planner', '경로 계획 노드'], ['controller', '주행 제어 노드'], ['tf', 'TF']]) {
      if (navigation.readiness?.[key] !== true) issues.push(issue(`NOT_READY_${key.toUpperCase()}`, `${label} 준비 미확인`, `${label}의 실제 입력·노드 준비`, '③의 상세 지표와 주행 로그에서 입력·노드 상태를 확인한 뒤 다시 확인하세요.', 3));
    }
  }
  if (nodesReady && !marker) issues.push(issue('INITIAL_POSE_REQUIRED', '이번 실행의 초기 위치 접수 없음', '현재 지도·실행에 접수된 사용자 위치·방향', '④ INITIAL POSE로 지도에서 현재 위치·방향을 지정하고 SEND POSE를 누르세요.', 4));
  if (marker && !tracking) {
    const [reason, remedy] = REASONS[source.state] || [`정합 확인 필요: ${source.state || '입력 없음'}`, '④의 현재 잔차·겹침·입력·정지 상태와 주행 로그를 확인하세요.'];
    issues.push(issue(source.state || 'MATCH_REQUIRED', reason, '품질 검사에 통과한 신선한 저장 지도 보정', remedy, 5));
  }
  if (tracking && !goalReady) issues.push(issue('GOAL_CONDITIONS_REQUIRED', (navigation.safety?.blockers || []).join(' · ') || '목표 전송 조건 미충족', '기존 source·TF·정지·대기·제어 조건', '아래 안전 상태와 정지·대기 증거를 확인하세요. 조건이 회복되면 ⑤부터 다시 확인합니다.', 6));
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
    matched ? `${selected?.map_binding?.source === 'operator_confirmed' ? '사용자 확인에 따른 지도 연결 (좌표 관계 실측 아님)' : '기존 변환 계보에 따른 지도 연결'} · 선택 ID·revision 일치` : '지도 선택 후 사용자 확인·적용 필요',
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

/** Bounded, historical display data only. Never used by admission or handoff. */
export function priorRejectionDiagnostics(value) {
  const poseValid = p => p && ['x', 'y', 'yaw'].every(k => typeof p[k] === 'number' && Number.isFinite(p[k]));
  if (value?.schema !== 'robot-scope.prior-rejection-diagnostics.v1'
      || value.qualification !== 'HISTORICAL_PRIOR_COMPARISON_ONLY'
      || value.frame !== 'map' || value.pose_reference !== 'base_link' || value.units !== 'metres_radians'
      || value.projection_basis !== 'NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE'
      || !poseValid(value.prior_pose) || !['server_policy', 'operator_prior'].includes(value.bounds_source)
      || value.global_uniqueness_verified !== false || value.absolute_accuracy_m !== null) return null;
  const b = value.effective_bounds, rows = value.candidates;
  if (!b || !Number.isFinite(b.xy_m) || !Number.isFinite(b.yaw_rad) || b.xy_m < .1 || b.xy_m > 3 || b.yaw_rad < Math.PI / 180 || b.yaw_rad > Math.PI / 2
      || value.bounds_source === 'server_policy' && (b.xy_m !== .25 || b.yaw_rad !== .20)
      || !Number.isInteger(value.retained_candidate_count) || value.retained_candidate_count < 6 || value.retained_candidate_count > 18
      || !Array.isArray(rows) || rows.length > value.retained_candidate_count || value.eligible_candidate_count !== rows.length
      || !Number.isInteger(value.matching_hypothesis_count) || value.matching_hypothesis_count < 0 || value.matching_hypothesis_count > rows.length) return null;
  const indices = new Set();
  for (const c of rows) {
    if (!Number.isInteger(c?.candidate_index) || c.candidate_index < 0 || c.candidate_index >= value.retained_candidate_count || indices.has(c.candidate_index)
        || !(c.duplicate_of === null || Number.isInteger(c.duplicate_of) && indices.has(c.duplicate_of)) || !poseValid(c.pose)
        || !Number.isFinite(c.xy_distance_m) || !Number.isFinite(c.absolute_wrapped_yaw_rad) || c.xy_distance_m < 0 || c.absolute_wrapped_yaw_rad < 0 || c.absolute_wrapped_yaw_rad > Math.PI
        || c.within_xy_bound !== (c.xy_distance_m <= b.xy_m) || c.within_yaw_bound !== (c.absolute_wrapped_yaw_rad <= b.yaw_rad)) return null;
    const delta = c.pose.yaw - value.prior_pose.yaw;
    if (Math.abs(Math.hypot(c.pose.x - value.prior_pose.x, c.pose.y - value.prior_pose.y) - c.xy_distance_m) > 1e-8
        || Math.abs(Math.abs(Math.atan2(Math.sin(delta), Math.cos(delta))) - c.absolute_wrapped_yaw_rad) > 1e-8) return null;
    indices.add(c.candidate_index);
  }
  if (rows.filter(c => c.duplicate_of === null && c.within_xy_bound && c.within_yaw_bound).length !== value.matching_hypothesis_count) return null;
  return { prior_pose: { x: value.prior_pose.x, y: value.prior_pose.y, yaw: value.prior_pose.yaw },
    effective_bounds: { xy_m: b.xy_m, yaw_rad: b.yaw_rad }, bounds_source: value.bounds_source,
    matching_hypothesis_count: value.matching_hypothesis_count,
    candidates: rows.map(c => ({ candidate_index: c.candidate_index, duplicate_of: c.duplicate_of,
      pose: { x: c.pose.x, y: c.pose.y, yaw: c.pose.yaw }, xy_distance_m: c.xy_distance_m,
      absolute_wrapped_yaw_rad: c.absolute_wrapped_yaw_rad, within_xy_bound: c.within_xy_bound, within_yaw_bound: c.within_yaw_bound })) };
}

export function initializeNavigationPreparation({ host, map3dSelect, map2dSelect, api, context, onChange, actions, getOperatorDraft = () => ({ status: 'none' }) }) {
  let state = null, busy = false, available = false, error = '', fetchError = '', checkedAt = 0, refreshing = false, draftTouched = false, actionStep = null;
  let refreshTask = null, refreshRequested = false;
  let draftContextEpoch = 0, draftContextConfirmed = false, draftRefreshPending = false, priorAckRevision = null, observationDraftPending = false, observationDraftAction = null;
  let lastContext = '', invalidated = '', selected3d = '', draft3dRevision = '', geometryGeneration = '';
  let pairConsent = null;
  let inputs = null, inputsError = '', observationError = '', observationBusy = false, inputsRevision = 0, inputsRequestedAt = 0;
  let proposal = null, proposalError = '', proposalFailureDetail = '', proposalBusy = false, proposalEpoch = 0, proposalContext = null, proposalVerified = false, proposalCheckedAt = 0, proposalTimer = null, proposalExpiryTimer = null, proposalConsentBinding = null, proposalProofBinding = null;
  let cleanup = null, cleanupId = null, cleanupTimer = null, cleanupEpoch = 0, advisoryAfter = 0, advisoryRefreshPending = false;
  let proposalRejectionHistory = null, rejectionDetailsOpen = false;
  let handoff = null, handoffReadAt = 0, handoffEpoch = 0, handoffTimer = null, handoffClock = null, handoffReading = false, handoffBusy = false, handoffError = '', handoffFailureDetail = '', handoffAwaitingStatus = false;
  const invalidHandoffs = new Map();
  const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
  host.innerHTML = `<div class="panel-header compact"><div><div class="eyebrow">STORED MAP NAVIGATION</div><h2>단계별 주행 준비</h2></div><button type="button" data-prep="refresh">현재 단계 다시 확인</button></div>
    <p data-prep="current"></p><p data-prep="selected"></p><p data-prep="applied"></p><p data-prep="invalidation" role="status"></p>
    <label><input type="checkbox" data-prep="pair-confirmation"> 선택한 2D 지도가 선택한 3D 지도에서 만들어졌으며 같은 원점·축·미터 단위를 사용함을 직접 확인했습니다.</label>
    <p>지도 조합과 좌표 관계는 사용자가 확인합니다. 서버는 변환 계보를 요구하지 않으며 파일·버전과 센서 교정은 계속 검사합니다. 크롭 후 원점이 보정된 지도는 같은 좌표를 유지할 수 있습니다. 회전 저장으로 벽의 좌표가 바뀐 지도는 좌표 변환을 맞추기 전에는 같은 좌표로 확인하지 마세요.</p>
    <div class="navigation-preparation-actions"><button type="button" data-prep="pair">① 지도 연결 확인·적용</button><button type="button" data-prep="clear">기존 2D 모드로 복구</button></div>
    <section aria-label="① 사용자 위치 초안"><h3>① 사용자 위치 초안</h3><p>아래 지도 조작부의 기존 INITIAL POSE 도구로 현재 위치와 방향을 그리세요. 미전송 사용자 가정이며 센서 측정이나 실제 위치 정확도가 아닙니다.</p>
    <p data-prep="prior-status" role="status"></p><p>다른 창·탭으로 이동해도 완성한 위치·방향은 보존됩니다. 돌아오면 현재 위치·방향을 확인하고 정지 가정 확인을 다시 체크하세요. 드래그 도중 중단하거나 지도·실행 상태가 바뀐 초안은 다시 지정해야 합니다. 계산의 거절 사유는 아래 이전 계산 기록에서 확인할 수 있습니다.</p><p>새 초안의 후보 선택에는 서버 기본 검증 한도 위치 0.25 m · 방향 ±0.20 rad (약 ±11.5°)가 적용됩니다. 이 한도는 사용자 위치 불확실성 측정이나 실제 정확도의 보증이 아닙니다.</p>
    <label><input type="checkbox" data-prep="prior-stationary"> 이 초안이 현재 지도에서 정지 중인 로봇의 위치·방향에 대한 제 가정임을 확인합니다. 실제 정지나 정확도를 측정한 증거는 아닙니다.</label></section>
    <section class="navigation-preparation-observation" aria-label="② 센서 관측과 초기값"><h3>② 센서 관측과 초기값</h3><p>관측은 정지 상태의 센서 입력 확인 전용입니다. 시작 조건은 서버가 다시 검사하며, 지도 선택이나 후보 확인만으로 정합·주행을 시작하지 않습니다.</p>
    <div class="navigation-preparation-actions"><button type="button" data-prep="observe-start">센서 관측 시작</button><button type="button" data-prep="observe-stop">센서 관측 종료</button></div>
    <p data-prep="observation-status" role="status"></p><p data-prep="observation-error" role="alert"></p><div data-prep="evidence"></div><div data-prep="candidates"></div>
    <button type="button" data-prep="proposal">초기 위치 제안 계산</button><div data-prep="proposal-result" role="status"></div><p data-prep="geometry-preview" role="status"></p><p data-prep="geometry-applied" role="status"></p>
    <label class="navigation-handoff-supervision"><input type="checkbox" data-prep="supervision"> 현장 정지 상태를 직접 감독하며 관측 종료와 다음 절차를 진행하겠습니다. 이 확인은 정지 측정이 아닙니다.</label>
    <label data-prep="conditional-label" hidden><input type="checkbox" data-prep="conditional-ack"> 사용자 초안과 서버 검증 한도에 조건부로 한 후보가 선택되었고 전역 유일성·실제 위치 정확도는 확인되지 않았음을 이해합니다.</label><button type="button" data-prep="confirm-handoff">제안값 확인·②에 적용</button><div data-prep="handoff-result" role="status"></div></section>
    <details class="navigation-seed-geometry"><summary>② 초기 높이·기울기 입력</summary><p>현재 로봇 본체 원점(base_link)의 지도 좌표 높이(m), roll·pitch(rad)를 확인해 입력하세요. 바닥 높이와 본체 원점의 높이는 다릅니다. 임의의 0이나 이전 실행값을 사용하지 않습니다. 제안값은 위에 별도 표시되며 아래 수동 입력칸에 복사되지 않습니다. 빈 칸은 수동 입력이 없다는 뜻이며 위의 서버 확인값과 별개입니다.</p>
    <div><label>높이 z (m)<input data-geometry="z" type="number" step="0.001" placeholder="미지정"></label><label>roll (rad)<input data-geometry="roll" type="number" step="0.001" placeholder="미지정"></label><label>pitch (rad)<input data-geometry="pitch" type="number" step="0.001" placeholder="미지정"></label><button type="button" data-prep="geometry">초기 높이·기울기 저장</button></div><p data-prep="geometry-source"></p></details>
    <ol class="navigation-preparation-steps" data-prep="steps"></ol>
    <section class="navigation-preparation-issues" aria-label="준비 상태·해결할 항목"><h3>준비 상태·해결할 항목</h3><div data-prep="issues" role="status"></div></section>
    <details><summary>기술 상세 · 현재 검사 수치와 실행 정보</summary><pre data-prep="details"></pre></details>`;
  const el = name => host.querySelector(`[data-prep="${name}"]`);
  const pairConsentKey = (draft3d, map) => draft3d && map ? JSON.stringify([draft3d.id, draft3d.revision, map.id, map.revision]) : null;
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
    const conditionalProof = proof?.operator_prior_resolution;
    const conditionalContext = { generation: selected?.generation, session_id: handoff?.observation_session_id, calibration_sha256: proof?.calibration_sha256, localization_3d: selected?.localization_3d, navigation_2d: selected?.navigation_2d };
    const identified = Boolean(available && handoff?.schema === 'robot-scope.proposal-geometry-handoff.v1'
      && handoff.source === 'proposal_confirmed' && handoff.frame === 'map' && /^[a-f0-9]{32}$/.test(handoff.handoff_id || '')
      && handoff.handoff_id === proof?.handoff_id && handoff.bundle_generation === selected?.generation
      && handoff.observation_session_id === proof?.observation_session_id && selected?.seed_geometry?.source === 'proposal_confirmed'
      && handoff.proposal_id === proof?.proposal_id && handoff.bundle_generation === proof?.bundle_generation
      && proof?.calibration_sha256 && proof.calibration_sha256 === state?.pair?.calibration_sha256
      && ((handoff.policy?.id === 'robot-scope.proposal-handoff.local-v1' && !conditionalProof) || (handoff.policy?.id === CONDITIONAL_POLICY && proof?.policy_id === CONDITIONAL_POLICY && validConditionalResolution(conditionalProof, conditionalContext) && validPriorCurrentMembers(conditionalProof, proof.operator_prior_current_members, true) && conditionalProof.source_contract_sha256 === proof.source_contract_sha256 && conditionalProof.candidate_vs_prior.within_existing_handoff_reference === true)) && handoff.policy?.ttl_s === 120
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
  function operatorPriorInput() {
    const draft = getOperatorDraft() || { status: 'none' };
    if (draft.status === 'none') return { status: state?.selected?.workflow === 'staged_navigation_pair' ? 'required' : 'none' };
    if (draft.status !== 'ready' || !draft.pose || ![draft.pose.x, draft.pose.y, draft.pose.yaw].every(finite) || Math.abs(draft.pose.x) > 1000 || Math.abs(draft.pose.y) > 1000 || Math.abs(draft.pose.yaw) > Math.PI || !Number.isSafeInteger(draft.revision)) return { status: 'unavailable' };
    const pair = inputs?.pair;
    if (!el('prior-stationary').checked || priorAckRevision !== draft.revision || !pair?.calibration_sha256
        || draft.bundle_generation !== pair.generation || draft.navigation_map?.id !== pair.navigation_2d?.map_id
        || draft.navigation_map?.revision !== pair.navigation_2d?.revision || draft.localization_map?.id !== pair.localization_3d?.map_id || draft.localization_map?.revision !== pair.localization_3d?.revision) return { status: 'incomplete' };
    return { status: 'ready', revision: draft.revision, prior: { frame: 'map', pose_reference: 'base_link', units: 'metres_radians',
      pose: { ...draft.pose }, source: 'OPERATOR_CURRENT_MAP_DRAFT',
      stationary_current_pose_confirmed: true, navigation_map_id: draft.navigation_map.id,
      navigation_map_revision: draft.navigation_map.revision, calibration_sha256: pair.calibration_sha256 } };
  }
  function proposalContextMatches(ctx = proposalContext) {
    const { model } = current(), pair = inputs?.pair, session = inputs?.observation, source = proposalSource(inputs?.evidence);
    const currentPrior = ctx?.operatorPrior ? operatorPriorInput() : null;
    return Boolean(ctx && (!ctx.operatorPrior || currentPrior?.status === 'ready' && currentPrior.revision === ctx.draftRevision && JSON.stringify(currentPrior.prior) === JSON.stringify(ctx.operatorPrior)) && available && model.matched && pair?.valid === true && pair.generation === ctx.generation
      && state?.selected?.generation === ctx.generation && samePin(pair.localization_3d, ctx.localization_3d)
      && samePin(pair.navigation_2d, ctx.navigation_2d) && pair.calibration_sha256 === ctx.calibration_sha256
      && session?.state === 'READY' && session.active === true && session.session_id === ctx.session_id && source
      && ['observer_id', 'cloud_epoch', 'pose_epoch'].every(key => source[key] === ctx.source?.[key]));
  }
  function invalidateProposal(message = '관측 또는 지도 상태가 바뀌어 이전 제안을 사용할 수 없습니다.') {
    if (!proposalContext && !proposal && !proposalBusy) return;
    ++proposalEpoch; clearTimeout(proposalTimer); clearTimeout(proposalExpiryTimer); proposalTimer = null; proposalExpiryTimer = null;
    proposal = null; proposalContext = null; proposalVerified = false; proposalConsentBinding = null; proposalProofBinding = null; proposalError = message;
    el('supervision').checked = false; el('conditional-ack').checked = false;
    if (cleanupId && !cleanupSettled()) scheduleCleanupPoll();
  }
  function cleanupSettled() { return cleanup?.state === 'SETTLED' && cleanup.worker_active === false; }
  function recordCleanup(result, id) {
    if (result?.schema !== 'robot-scope.navigation-initialization-proposal.v1' || result.proposal_id !== id) return false;
    if (result.state === 'rejected' && result.operational_application === 'NOT_RUN'
        && /^[a-f0-9]{24}$/.test(id) && typeof result.reason === 'string' && result.reason.length <= 128) {
      proposalRejectionHistory = { proposal_id: id, reason: result.reason,
        received_at: proposalRejectionHistory?.proposal_id === id ? proposalRejectionHistory.received_at : new Date().toISOString(),
        bundle_generation: result.pair?.generation, observation_session_id: result.observation_session_id,
        navigation_map_id: result.pair?.navigation_2d?.map_id, navigation_map_revision: result.pair?.navigation_2d?.revision,
        navigation_map_name: typeof result.pair?.navigation_2d?.name === 'string' ? result.pair.navigation_2d.name.slice(0, 120) : null,
        diagnostics: priorRejectionDiagnostics(result.prior_rejection_diagnostics) };
    }
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
  function proposalConsentKey() {
    const ctx = proposalContext;
    if (!ctx?.operatorPrior || !proposalVerified || proposal?.state !== 'ready' || !proposal.operator_prior_resolution) return null;
    return JSON.stringify([proposal.proposal_id, ctx.generation, ctx.session_id, ctx.calibration_sha256,
      ctx.localization_3d, ctx.navigation_2d, ctx.source, ctx.operatorPrior, ctx.draftRevision, proposal.operator_prior_resolution]);
  }
  function proposalPoseValid(ignoreFreshness = false) {
    const age = proposal?.provenance?.pose_age_s;
    const ageValid = finite(age) && age >= 0;
    const fresh = ageValid && age + (performance.now() - proposalCheckedAt) / 1000 <= 1;
    const cleanupUnsafe = cleanup && (['CANCELLING', 'CANCEL_PENDING', 'CANCEL_FAILED', 'CLEANUP_UNCONFIRMED', 'JOB_UNAVAILABLE'].includes(cleanup.state) || cleanup.cancellation_requested === true);
    const conditional = proposalContext?.operatorPrior ? proposal?.classification === 'CONDITIONAL_ON_OPERATOR_PRIOR' && typeof proposal?.quality?.ambiguity_unresolved === 'boolean' && proposal.quality.ambiguity_unresolved === proposal.operator_prior_resolution?.original_ambiguity_unresolved && validConditionalResolution(proposal.operator_prior_resolution, proposalContext) && validPriorCurrentMembers(proposal.operator_prior_resolution, proposal.current_vs_prior) && (!proposal.operator_prior_resolution.grouping_policy || ignoreFreshness || proposal.current_vs_prior.pose_age_s + (performance.now() - proposalCheckedAt) / 1000 <= 1) : proposal?.quality?.ambiguity_unresolved === false && !proposal?.operator_prior_resolution && !proposal?.classification;
    return Boolean(conditional && proposalVerified && proposal?.state === 'ready' && proposalContextMatches() && ageValid && (ignoreFreshness || fresh) && !cleanupUnsafe
      && proposal.imu_hypothesis?.pose_reference === 'FASTLIO_IMU' && proposal.imu_hypothesis?.units === 'metres_degrees'
      && proposal.imu_hypothesis?.approximate_only === true && proposal.imu_hypothesis?.requires_reanchor === true
      && proposal.body_candidate?.pose_reference === 'base_link' && proposal.body_candidate?.units === 'metres_radians'
      && proposal.body_candidate?.qualification === 'INFORMATIONAL_LOCALIZATION_MAP_ONLY'
      && proposal.imu_hypothesis?.frame && proposal.imu_hypothesis.frame === proposalContext?.localization_3d?.frame
      && proposal.body_candidate.frame === proposal.imu_hypothesis.frame
      && proposal.navigation_geometry_candidate?.frame === 'map' && proposal.navigation_geometry_candidate?.pose_reference === 'base_link'
      && proposal.navigation_geometry_candidate?.units === 'metres_radians' && validGeometry(proposal.navigation_geometry_candidate.pose)
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
    const stageOnePrior = operatorPriorInput();
    const stageOneReady = stageOnePrior.status === 'ready' || selected?.seed_geometry?.source === 'operator' || (selected?.seed_geometry?.source === 'proposal_confirmed' && handoffInfo.active);
    const stageOne = { ...model.steps[0], title: '지도 연결·사용자 위치 초안', condition: '지도 연결 후 미전송 위치·방향 초안과 현재 정지 가정 확인; 후보는 서버 검증 한도 적용', status: model.matched && selected?.workflow === 'staged_navigation_pair' && !stageOneReady ? '사용자 입력 필요' : model.steps[0].status };
    const viewSteps = [stageOne, ...model.steps.slice(1, 3), { ...model.steps[4], number: 4, title: 'INITIAL POSE 접수·지도 정합',
      condition: '사용자 위치 접수 후 명시적으로 정합 시작·품질 확인', status: model.marker ? model.steps[4].status : model.steps[3].status,
      result: `${model.steps[3].result} · ${model.steps[4].result}`, issues: [...model.steps[3].issues, ...model.steps[4].issues] },
      { ...model.steps[5], number: 5 }, { ...model.steps[6], number: 6 }];
    viewSteps.forEach(step => { step.next = step.status === '완료'; });
    const nextStep = busy && actionStep ? viewSteps[actionStep > 4 ? actionStep - 2 : actionStep - 1] : viewSteps.find(step => step.status !== '완료') || viewSteps[5];
    el('current').textContent = model.enabled || busy ? `현재 단계: ${nextStep.number}. ${nextStep.title} · ${busy ? '확인 중' : nextStep.status}` : '현재 모드: 기존 2D · 저장 지도 위치추정은 3D 지도 선택 후 준비';
    el('selected').textContent = `화면 선택: 3D ${draft3d?.name || '미선택'} / 2D ${map?.name || '미선택'} · 적용한 준비 구성: ${selected ? `${mapName(selected.localization_3d)} / ${mapName(selected.navigation_2d)}` : '기존 2D 모드'}`;
    el('applied').textContent = source ? `실제 실행: ${source.source || 'source 미확인'} · 3D ${mapName({ map_id: source.localization_map_id, revision: source.localization_map_revision })} / 2D ${mapName(navigation.map)} · ${model.applied ? '준비 구성과 일치' : '구성 일치 미확인'} · ${model.tracking ? '추적 중' : '지도상 현재 위치 미확인'}` : '실제 실행: 저장 3D 지도 위치추정 미적용';
    el('invalidation').textContent = invalidated;
    map3dSelect.disabled = busy || navigationBusy || model.active;
    if (pairConsent !== pairConsentKey(draft3d, map)) { pairConsent = null; el('pair-confirmation').checked = false; }
    el('pair-confirmation').disabled = busy || navigationBusy || model.active || !draft3d || !map;
    el('pair').disabled = el('pair-confirmation').disabled || !pairConsent || !el('pair-confirmation').checked;
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
    el('observe-start').disabled = refreshing || observationBusy || busy || navigationBusy || model.active || !inputsCurrent || observation?.can_start !== true || !Array.isArray(blockers) || blockers.length > 0;
    el('observe-stop').disabled = observationBusy || observation?.can_stop !== true || !/^[a-f0-9]{32}$/.test(observation?.session_id || '');
    const sessionLabels = { UNAVAILABLE: '사용 불가', CHECKING: '확인 중', STOPPED: '정지', FAILED: '시작 실패 또는 종료', STARTING: '시작 중', WAITING_INPUTS: '입력 대기', READY: '입력 준비', STOPPING: '종료 중', UNKNOWN: '상태 미확인', INVALIDATED: '관측 무효화' };
    el('observation-status').textContent = inputsError ? '관측 입력 확인 실패 → 연결과 상태를 다시 확인하세요.' : `관측 상태: ${sessionLabels[observation?.state] || '확인 중'} · ${observation?.reason?.startsWith('CONTROL_') || observation?.reason?.startsWith('OBSERVATION_') ? inputReason(observation.reason) : observation?.reason || '서버 상태 확인 필요'} · 시작 사전 검사: ${Array.isArray(blockers) ? blockers.length ? blockers.map(inputReason).join(' · ') : '현재 차단 항목 없음' : inputReason('START_BLOCKERS_UNAVAILABLE')} · 사전 검사는 권고이며 서버의 최종 승인 보장이 아닙니다.`;
    const guard = observation?.bridge_guard;
    if (guard?.mode === 'active_inhibited') {
      const labels = { HELD: '관측 중 동작 명령 차단 확인', WAITING: '차단 응답 대기', INVALID: '차단 조건 유실', RELEASING: '차단 해제 확인 중' };
      const age = finite(guard.status_age_s) ? `${guard.status_age_s.toFixed(2)}초 전` : '신선도 미확인';
      el('observation-status').textContent += ` · 제어 bridge 켜짐 · ${labels[guard.state] || '차단 상태 미확인'} · 서명된 bridge 상태 ${age}. 실제 정지 상태는 현장에서 확인해야 합니다.`;
    }
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
    const draft = getOperatorDraft() || { status: 'none' };
    if (priorAckRevision !== null && draft.revision !== priorAckRevision) { priorAckRevision = null; el('prior-stationary').checked = false; }
    const priorInput = operatorPriorInput();
    el('prior-status').textContent = draft.status === 'ready' && draft.pose && [draft.pose.x, draft.pose.y, draft.pose.yaw].every(finite) ? `미전송 사용자 초안 · X ${draft.pose.x.toFixed(3)} m · Y ${draft.pose.y.toFixed(3)} m · yaw ${draft.pose.yaw.toFixed(3)} rad · 현재 정지 가정을 직접 확인하세요.` : draft.status === 'none' ? '초안 없음 · 아래 지도에서 현재 위치와 방향을 지정하세요.' : draft.status === 'pending' ? '초안의 현재 문맥 확인 중입니다.' : '이전 초안은 미확인 또는 미완성입니다 · 아래 지도에서 다시 지정하세요.';
    const proposalReadyToRequest = Boolean(['none', 'ready'].includes(priorInput.status) && inputsCurrent && !busy && !navigationBusy && !model.active && !observationBusy
      && observation?.active === true && observation.state === 'READY' && /^[a-f0-9]{32}$/.test(observation.session_id || '')
      && /^[a-f0-9]{32}$/.test(pair?.generation || '') && proposalSource(inputs?.evidence) && pair.calibration_sha256
      && Array.isArray(blockers) && !blockers.some(code => (['START_BLOCKERS_UNAVAILABLE', 'OBSERVATION_STATUS_UNAVAILABLE'].includes(code) || code.startsWith('CONTROL_') || code.startsWith('OWNER_UNKNOWN:') || (code.startsWith('OWNER_BUSY:') && !['OWNER_BUSY:fastlio_observation', 'OWNER_BUSY:legacy_alignment'].includes(code))))
      && inputsRequestedAt >= advisoryAfter && (!cleanupId || cleanupSettled()));
    el('proposal').disabled = proposalBusy || handoffBusy || handoffAwaitingStatus || handoffInfo.active || ['capturing', 'running'].includes(proposal?.state) || !proposalReadyToRequest;
    const poseText = value => ['x', 'y', 'z', 'roll', 'pitch', 'yaw'].map(key => `${key} ${finite(value?.pose?.[key]) ? value.pose[key].toFixed(3) : '미확인'}`).join(' · ');
    const proposalAge = proposal?.provenance?.pose_age_s;
    const proposalFresh = finite(proposalAge) && proposalAge >= 0 && proposalAge + (performance.now() - proposalCheckedAt) / 1000 <= 1;
    const validPoses = proposalPoseValid();
    const preview = validPoses ? proposal.navigation_geometry_candidate.pose : null;
    el('geometry-preview').textContent = preview ? `② 미리 본 제안값 (조회 당시 · 미적용 · 지도 기준 base_link): ${geometryText(preview)} · 확인 전 읽기 전용, 서버 확정값과 다를 수 있습니다`
      : proposalBusy || ['capturing', 'running'].includes(proposal?.state) ? '② 제안값 계산 중 · 아직 적용되지 않았습니다.'
      : proposal?.state === 'ready' ? '② 제안값 미확인 또는 만료 · 새로 계산하고 확인하세요.'
      : proposalError || proposal?.state === 'rejected' || proposal?.state === 'stale' ? '② 제안값 사용 불가 · 새 상태를 확인하세요.'
      : '② 제안값 없음 · 계산과 명시적 확인이 필요합니다.';
    const confirmed = geometry?.source === 'proposal_confirmed';
    const handoffGeometry = handoff?.geometry;
    const confirmedValues = confirmed && handoffInfo.identified && handoffInfo.active && validGeometry(geometry) && validGeometry(handoffGeometry)
      && ['z', 'roll', 'pitch'].every(key => geometry[key] === handoffGeometry[key]);
    el('geometry-applied').textContent = handoffBusy || handoffAwaitingStatus ? '② 적용 결과 확인 중 · 서버 재조회 전에는 적용을 확인할 수 없습니다.'
      : confirmedValues ? `② 서버 확인 적용값 (지도 기준 base_link · 제안 출처): ${geometryText(handoffGeometry)} · ${handoffInfo.geometryReady ? '관측 종료 확인됨' : '관측 종료 확인 필요'}`
      : confirmed ? '② 적용값 만료·무효 또는 서버 상태 미확인 · 현재 상태를 다시 확인하세요.'
      : available && model.matched && geometry?.source === 'operator' && geometry?.frame === 'map' && validGeometry(geometry) ? `② 서버 저장 수동 입력값 (지도 기준 base_link): ${geometryText(geometry)}`
      : '② 서버 확인 적용값 없음';
    const conditional = Boolean(proposalContext?.operatorPrior && validPoses);
    const withinHandoff = !conditional || (proposal.operator_prior_resolution.candidate_vs_prior.within_existing_handoff_reference === true && (!proposal.operator_prior_resolution.grouping_policy || (proposal.current_vs_prior?.all_members_within_prior_bounds === true && proposal.current_vs_prior?.within_existing_handoff_reference === true)));
    const consentAvailable = Boolean(proposalProofBinding && proposalPoseValid(true) && proposalConsentKey() === proposalProofBinding);
    const preserveConsent = Boolean(proposalConsentBinding && consentAvailable && proposalConsentBinding === proposalProofBinding);
    if (proposalConsentBinding && !preserveConsent) { proposalConsentBinding = null; el('conditional-ack').checked = false; el('supervision').checked = false; }
    el('conditional-label').hidden = !consentAvailable;
    if (!consentAvailable) el('conditional-ack').checked = false;
    el('supervision').disabled = handoffBusy || handoffInfo.active;
    el('confirm-handoff').disabled = (conditional && (!el('conditional-ack').checked || !withinHandoff)) || handoffBusy || handoffAwaitingStatus || !el('supervision').checked || !validPoses || !proposalReadyToRequest || !cleanupSettled() || handoffInfo.active;
    const proposalNodes = [node('p', '정보성 제안은 저장 3D 지도 기준이며 운영 보정 위치·Nav2 준비·TF 적용 결과가 아닙니다. 자동 입력·전송하지 않습니다.')];
    if (conditional) { const status = withinHandoff ? '사용자 초안과 서버 검증 한도에 조건부로 한 후보가 선택되었습니다.' : proposal.operator_prior_resolution.grouping_policy && !proposal.current_vs_prior?.all_members_within_prior_bounds ? '현재 시점에 그룹의 모든 후보가 초안 기준 검증 한도 안에 있지 않아 확인할 수 없습니다.' : '조건부 후보가 기존 초기 위치 허용 범위(0.25m / 0.20rad)를 벗어나 확인할 수 없습니다. 사용자 초안과 관측을 다시 확인하세요.'; proposalNodes.push(node('p', `${status} ${originalAmbiguityLabel(proposal.operator_prior_resolution.original_ambiguity_unresolved)} 보존된 후보 집합과 사용자 초안에 조건부이며 전역 유일성·실제 위치 정확도는 확인되지 않았습니다.`)); }
    if (conditional) proposalNodes.push(node('p', priorBoundsText(proposal.operator_prior_resolution)));
    if (conditional && proposal.operator_prior_resolution.grouping_policy) { const proof = proposal.operator_prior_resolution; proposalNodes.push(node('p', `서버가 검증한 원본 후보 ${proof.matching_retained_candidate_count}개가 초안 기준 검증 한도 안의 한 그룹을 이룹니다. 대표 후보 ${proof.candidate_index} 기준 높이·기울기 차이: ${proof.matching_member_geometry.map(member => `#${member.candidate_index} Δz ${member.z_delta_m.toFixed(3)}m · Δroll ${member.roll_delta_rad.toFixed(3)}rad · Δpitch ${member.pitch_delta_rad.toFixed(3)}rad`).join(' / ')}. 지도·정지·실제 정확도의 검증 결과가 아닙니다.`)); }
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
    if (proposalRejectionHistory) {
      const h = proposalRejectionHistory, d = h.diagnostics;
      el('proposal-result').append(node('p', `이전 계산 거절 · 수신 ${new Date(h.received_at).toLocaleTimeString()} · 지도 ${h.navigation_map_name || h.navigation_map_id?.slice(0, 8) || '미확인'}: ${inputReason(h.reason)} 당시 입력의 기록이며 현재 제안·실제 위치·실행 승인이 아닙니다.`));
      if (d) {
        const detail = node('details'); detail.append(node('summary', '거절 당시 후보별 위치·방향 차이'));
        detail.open = rejectionDetailsOpen;
        detail.addEventListener('toggle', () => { if (detail.isConnected) rejectionDetailsOpen = detail.open; });
        detail.append(node('p', `초안 당시 map → base_link 기준 · 초안 X ${d.prior_pose.x.toFixed(3)} m / Y ${d.prior_pose.y.toFixed(3)} m / yaw ${d.prior_pose.yaw.toFixed(3)} rad · 검증 한도 ${d.effective_bounds.xy_m} m / ${d.effective_bounds.yaw_rad} rad · 일치 후보 그룹 ${d.matching_hypothesis_count}개`));
        for (const c of d.candidates) detail.append(node('p', `후보 #${c.candidate_index}${c.duplicate_of === null ? '' : ` (#${c.duplicate_of}와 같은 그룹)`} · X ${c.pose.x.toFixed(3)} / Y ${c.pose.y.toFixed(3)} m / yaw ${c.pose.yaw.toFixed(3)} rad · 위치 차이 ${c.xy_distance_m.toFixed(3)} m (${c.within_xy_bound ? '범위 안' : '범위 밖'}) · 방향 차이 ${c.absolute_wrapped_yaw_rad.toFixed(3)} rad (${c.within_yaw_bound ? '범위 안' : '범위 밖'})`));
        detail.append(node('p', '보존된 후보와 당시 초안의 비교이며 실제 위치 정확도를 보장하지 않습니다. 후보 좌표를 자동 입력하거나 거절 조건을 완화하지 않습니다.'));
        el('proposal-result').append(detail);
      }
    }
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
      if (h.policy?.id === CONDITIONAL_POLICY) handoffNodes.push(node('p', `사용자 초안에 조건부인 확인값입니다. ${originalAmbiguityLabel(state.selected.seed_geometry.handoff.operator_prior_resolution.original_ambiguity_unresolved)} 보존된 후보 집합과 사용자 초안에 조건부이며 전역 유일성과 실제 위치 정확도는 확인되지 않았습니다.`));
      handoffNodes.push(node('p', `출처: 명시 확인된 proposal_confirmed · 상태: ${currentMatchUnknown ? '정합 수락 이력 · 현재 실행의 수락은 미확인' : expired ? '사용 시간 만료' : handoffStates[h.state] || '확인 불가'} · ${handoffInfo.armed ? '초기화 사용 시간은 정합 접수 전까지 적용' : `남은 초기화 시간 ${handoffInfo.remaining === null ? '미확인' : Math.ceil(handoffInfo.remaining) + '초'}`}`));
      handoffNodes.push(node('p', `관측 종료: ${receiptStates[h.stop_receipt?.state] || '상태 미확인'}${h.reason ? ` · ${inputReason(h.reason)}` : ''}`));
      if (h.match_history) handoffNodes.push(node('p', '이전 정합 요청 수락 이력이 있습니다. 현재 실행의 정합 상태는 별도로 확인합니다.'));
      if (h.geometry && h.initial_pose_reference && handoffInfo.active) handoffNodes.push(node('p', `서버 보관 가설 (지도 좌표): 높이 ${h.geometry.z} m · roll ${h.geometry.roll} · pitch ${h.geometry.pitch} rad · 초기 XY/yaw 기준 ${h.initial_pose_reference.x}, ${h.initial_pose_reference.y}, ${h.initial_pose_reference.yaw}`));
      if (h.policy?.id === CONDITIONAL_POLICY) handoffNodes.push(node('p', priorBoundsText(state.selected.seed_geometry.handoff.operator_prior_resolution)));
      handoffNodes.push(node('p', `별도 handoff 로컬 후보 사용 범위: ${h.policy.ttl_s}초 · XY ${h.policy.max_xy_m} m · yaw ${h.policy.max_yaw_rad} rad. 주행 설정이나 실제 위치 정확도가 아닙니다.`));
      handoffNodes.push(node('p', '다음 조작은 각각 별도입니다: 관측 종료 확인 → 아래 START NAV2 → INITIAL POSE 지정·전송 → ④ 정합 시작.'));
    } else if (state?.selected?.seed_geometry?.source === 'proposal_confirmed') handoffNodes.push(node('p', '확인된 가설의 현재 서버 상태가 불확실합니다 → 상태를 다시 확인하세요.'));
    else if (!handoffBusy && !handoffAwaitingStatus) handoffNodes.push(node('p', '확인된 초기 geometry 가설이 없습니다.'));
    el('handoff-result').replaceChildren(...handoffNodes);
    el('steps').replaceChildren(...viewSteps.map(step => {
      const item = node('li'); item.dataset.state = step.status;
      item.append(node('strong', `${step.number}. ${step.title}`), node('span', step.status, 'preparation-state'), node('p', `완료 조건: ${step.condition}`), node('p', `검사 결과: ${step.result}`));
      const missing = step.issues.map(value => value.current).join(' · ');
      if (missing) item.append(node('p', `부족/실패: ${missing}`, 'preparation-missing'));
      item.append(node('small', step.next ? '다음 단계 확인 가능' : step.number > 1 && viewSteps[step.number - 2].status !== '완료' ? `${step.number - 1}단계 확인 후 진행` : '조건을 해결한 뒤 이 단계에서 다시 확인'));
      const guidance = { 3: '아래 주행 조작부에서 Nav2를 시작하세요.', 4: '아래 지도 조작부에서 INITIAL POSE를 지정·전송하세요. 접수 후 정합을 시작하세요.', 6: '아래 지도 조작부에서 GOAL POSE를 지정·전송하세요.' }[step.number];
      if (guidance) item.append(node('p', guidance));
      if (step.number === 4) { const button = node('button', '정합 시작'); button.type = 'button'; button.disabled = busy || navigationBusy || !model.canMatch; button.onclick = match; item.append(button); }
      return item;
    }));
    const issueNodes = model.issues.map(value => { const item = node('p'); item.append(node('strong', `${value.step > 4 ? value.step - 1 : value.step}단계 · ${value.current}`), document.createElement('br'), node('span', `필요: ${value.required} → 해결: ${value.remedy}`)); return item; });
    if (diagnosticIssue) issueNodes.push(node('p', `② ${diagnosticIssue} · 최종 관측 결과는 위 관측 검사를 확인하세요. 검사 값은 실시간이 아닙니다.`));
    el('issues').replaceChildren(...(issueNodes.length ? issueNodes : [node('p', model.enabled ? '현재 확인된 필수 항목 충족. 다음 단계 버튼으로 진행하세요.' : '3D 지도를 선택하면 단계별 저장 지도 위치추정 준비가 시작됩니다. 기존 2D 모드의 상태는 아래에서 확인하세요.')]));
    const detailInputs = inputs ? { ...inputs, evidence: inputs.evidence ? { ...inputs.evidence } : inputs.evidence } : null;
    if (detailInputs?.evidence) { delete detailInputs.evidence.diagnostics; if (diagnostics) detailInputs.evidence.diagnostics = diagnostics; }
    el('details').textContent = JSON.stringify({ selected: selected ? { generation: selected.generation, localization_3d: selected.localization_3d, navigation_2d: selected.navigation_2d, seed_geometry: geometry } : null, pair: state?.pair, runtime: source, readiness: navigation.readiness, metrics: navigation.localization_health?.metrics, errors: model.issues.map(value => value.code), preparation_inputs: detailInputs, diagnostics_note: diagnostics ? '검사 당시 값이며 실시간이 아닙니다. phase_ms는 서버 구간 경과이며 네트워크 왕복이나 lock 전용시간이 아닙니다.' : undefined, preparation_inputs_error: inputsError, observation_error: observationError, initialization_proposal: proposal, proposal_cleanup: cleanup, proposal_rejection_history: proposalRejectionHistory, proposal_display_valid: Boolean(validPoses), proposal_error: proposalError, proposal_failure_detail: proposalFailureDetail, initialization_handoff: handoff, handoff_error: handoffError, handoff_failure_detail: handoffFailureDetail }, null, 2);
    return model;
  }
  function refresh(force = false) {
    if (busy) {
      if (force) advisoryRefreshPending = true;
      return refreshTask || Promise.resolve();
    }
    if (refreshing) {
      // A forced read must observe changes after the in-flight request took
      // its snapshot. Coalesce requests, discard that older response, and let
      // callers await the subsequent read as well.
      if (force) refreshRequested = true;
      return refreshTask;
    }
    if (!force && Date.now() - checkedAt < 2500) return Promise.resolve();
    refreshing = true;
    render();
    refreshTask = (async () => {
      try {
        do {
          refreshRequested = false;
          advisoryRefreshPending = false;
          await readInputs();
        } while (!busy && (refreshRequested || draftRefreshPending || (handoffAwaitingStatus && !handoffBusy) || advisoryRefreshPending));
      } finally { refreshing = false; render(); onChange(); }
    })();
    return refreshTask;
  }
  async function readInputs() {
    const inputToken = ++inputsRevision, requestedAt = performance.now(), draftEpoch = draftContextEpoch;
    draftRefreshPending = false;
    let readValue = null;
    try {
      const value = readValue = await api('/api/v1/navigation/operational-3d/preparation-inputs', { signal: AbortSignal.timeout(10000) });
      if (inputToken !== inputsRevision || draftEpoch !== draftContextEpoch || busy || refreshRequested) return;
      const status = value?.operational_state;
      if (value?.schema !== 'robot-scope.navigation-preparation-inputs.v1' || !status || value.operational_state_error
          || !Object.hasOwn(status, 'selected') || !Object.hasOwn(status, 'pair') || !['LEGACY_2D', 'NEXT_NAVIGATION_START'].includes(status.activation)) {
        throw new Error(value?.operational_state_error || '운영 준비 상태 미확인');
      }
      if (status.selected?.workflow === 'staged_navigation_pair' && (!value.pair || !status.pair
          || status.selected.generation !== value.pair.generation || status.pair.generation !== value.pair.generation
          || !samePin(status.selected.localization_3d, value.pair.localization_3d) || !samePin(status.selected.navigation_2d, value.pair.navigation_2d))) throw new Error('CONTEXT_CHANGED');
      inputs = value; inputsRequestedAt = requestedAt; inputsError = ''; state = status; available = true; fetchError = '';
      draftContextConfirmed = draftEpoch === draftContextEpoch && !busy; observationDraftPending = false; observationDraftAction = null;
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
      if (inputToken === inputsRevision && draftEpoch === draftContextEpoch && !busy && !refreshRequested) { draftContextConfirmed = false; observationDraftPending = false; observationDraftAction = null; inputs = readValue?.observation ? { observation: readValue.observation } : null; state = null; available = false; inputsError = failure.message; fetchError = `상태 확인 실패: ${INPUT_REASONS[failure.message] || '연결 또는 서버 응답을 확인하세요.'}`; clearHandoff(); if (handoffAwaitingStatus) handoffError = '가설 확인 결과를 읽지 못했습니다. 재전송하지 않고 서버 상태를 확인하세요.'; handoffAwaitingStatus = false; }
    } finally { checkedAt = Date.now(); render(); onChange(); }
  }
  async function observe(action) {
    const session = inputs?.observation;
    const { model, busy: navigationBusy } = current();
    const pair = inputs?.pair;
    const blockers = inputs?.start_blockers?.items;
    if (observationBusy || (action === 'start' ? refreshing || busy || navigationBusy || model.active || !available || !model.matched || !state?.selected || pair?.valid !== true || pair.generation !== state.selected.generation || !samePin(pair.localization_3d, state.selected.localization_3d) || !samePin(pair.navigation_2d, state.selected.navigation_2d) || session?.can_start !== true || !Array.isArray(blockers) || blockers.length > 0 : session?.can_stop !== true || !/^[a-f0-9]{32}$/.test(session?.session_id || ''))) return;
    invalidateProposal(); observationDraftPending = true; observationDraftAction = action; observationBusy = true; observationError = ''; available = false; ++inputsRevision; render(); onChange();
    try {
      const result = await api(`/api/v1/observations/fastlio/${action}`, { method: 'POST', body: JSON.stringify({ confirmed: true, ...(action === 'stop' ? { session_id: session.session_id } : {}) }), signal: AbortSignal.timeout(12000) });
      inputs = { observation: result };
    } catch (failure) { observationError = `관측 ${action === 'start' ? '시작' : '종료'} 거절 또는 응답 실패: ${failure.message} · 자동 재시도하지 않습니다.`; inputs = null; }
    finally { observationBusy = false; checkedAt = 0; if (refreshing) { advisoryRefreshPending = true; render(); } else { await refresh(true); } }
  }
  async function run(path, body, method = 'POST') {
    if (busy) return;
    if (!path.endsWith('/match')) invalidateProposal();
    ++draftContextEpoch; draftContextConfirmed = false; draftRefreshPending = true;
    busy = true; error = ''; actionStep = path.endsWith('/seed-geometry') ? 2 : path.endsWith('/match') ? 5 : 1; render(); onChange();
    try { state = await api(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(15000) }); available = true; invalidated = ''; }
    catch (failure) { error = failure.message; }
    finally { busy = false; actionStep = null; checkedAt = 0; if (!refreshing) await refresh(true); render(); onChange(); }
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
      proposal = result; proposalVerified = true; proposalCheckedAt = requestedAt; clearTimeout(proposalExpiryTimer);
      const readyKey = proposalConsentKey(), validBinding = proposalPoseValid(true);
      if (proposalProofBinding && (!validBinding || readyKey !== proposalProofBinding)) { invalidateProposal('제안 증명이나 현재 문맥이 바뀌어 이전 동의를 사용할 수 없습니다.'); render(); return; }
      if (ctx.operatorPrior && validBinding) proposalProofBinding = readyKey;
      render();
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
    const pair = inputs?.pair, session = inputs?.observation, requestedPrior = operatorPriorInput();
    if (!['none', 'ready'].includes(requestedPrior.status)) return;
    const ctx = { ...(requestedPrior.status === 'ready' ? { operatorPrior: requestedPrior.prior, draftRevision: requestedPrior.revision } : {}), generation: pair.generation, localization_3d: pair.localization_3d, navigation_2d: pair.navigation_2d,
      calibration_sha256: pair.calibration_sha256, session_id: session.session_id, source: proposalSource(inputs.evidence) };
    if (!globalThis.crypto?.getRandomValues) { proposalError = '안전한 요청 식별자를 만들 수 없습니다.'; render(); return; }
    const requestId = [...globalThis.crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2, '0')).join('');
    clearTimeout(proposalTimer); clearTimeout(proposalExpiryTimer); clearTimeout(cleanupTimer); ++cleanupEpoch; cleanup = null; cleanupId = null; proposalRejectionHistory = null; rejectionDetailsOpen = false; const token = ++proposalEpoch;
    if (proposalContext || proposal || proposalProofBinding || proposalConsentBinding) { el('supervision').checked = false; el('conditional-ack').checked = false; }
    proposalProofBinding = null; proposalConsentBinding = null;
    proposal = null; proposalError = ''; proposalFailureDetail = ''; proposalContext = ctx; proposalVerified = false; proposalBusy = true; render();
    try {
      const result = await api('/api/v1/navigation/operational-3d/initialization-proposals', { method: 'POST',
        body: JSON.stringify({ request_id: requestId, bundle_generation: ctx.generation, observation_session_id: ctx.session_id, ...(ctx.operatorPrior ? { operator_prior: ctx.operatorPrior } : {}) }), signal: AbortSignal.timeout(15000) });
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
    if (el('confirm-handoff').disabled || (proposalContext?.operatorPrior && (!el('conditional-ack').checked || proposal?.operator_prior_resolution?.candidate_vs_prior?.within_existing_handoff_reference !== true || (proposal?.operator_prior_resolution?.grouping_policy && (proposal?.current_vs_prior?.all_members_within_prior_bounds !== true || proposal?.current_vs_prior?.within_existing_handoff_reference !== true)))) || handoffBusy || handoffAwaitingStatus || !el('supervision').checked || !proposalPoseValid()
        || !proposalContextMatches() || !cleanupSettled() || !available || busy || navigationBusy || model.active || observationBusy || handoffInfo.active
        || !Array.isArray(blockers) || blockers.some(code => (['START_BLOCKERS_UNAVAILABLE', 'OBSERVATION_STATUS_UNAVAILABLE'].includes(code) || code.startsWith('CONTROL_') || code.startsWith('OWNER_UNKNOWN:') || (code.startsWith('OWNER_BUSY:') && !['OWNER_BUSY:fastlio_observation', 'OWNER_BUSY:legacy_alignment'].includes(code))))
        || inputsRequestedAt < advisoryAfter || !pair || !session || !globalThis.crypto?.getRandomValues) return;
    const ctx = proposalContext, proposalId = proposal.proposal_id, token = proposalEpoch;
    const requestId = [...globalThis.crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2, '0')).join('');
    handoffBusy = true; handoffAwaitingStatus = true; handoffError = ''; handoffFailureDetail = ''; el('supervision').checked = false; el('conditional-ack').checked = false; proposalConsentBinding = null; ++inputsRevision; render();
    try {
      const result = await api(`/api/v1/navigation/operational-3d/initialization-proposals/${proposalId}/confirm-geometry`, { method: 'POST',
        body: JSON.stringify({ request_id: requestId, bundle_generation: ctx.generation, observation_session_id: ctx.session_id, confirmed: true, stationary_supervision_acknowledged: true, ...(ctx.operatorPrior ? { conditional_prior_acknowledged: true } : {}) }), signal: AbortSignal.timeout(15000) });
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
  map3dSelect.addEventListener('change', () => { pairConsent = null; el('pair-confirmation').checked = false; invalidateProposal(); clearHandoff(); draftTouched = true; selected3d = map3dSelect.value; draft3dRevision = current().draft3d?.revision || ''; error = ''; render(); onChange(); });
  map2dSelect.addEventListener('change', () => { pairConsent = null; el('pair-confirmation').checked = false; invalidateProposal(); clearHandoff(); draftTouched = true; error = ''; });
  el('pair-confirmation').onchange = () => { const { draft3d, map } = current(); pairConsent = el('pair-confirmation').checked ? pairConsentKey(draft3d, map) : null; render(); };
  el('pair').onclick = () => { const { draft3d, map } = current(); if (el('pair').disabled || !draft3d || !map || !pairConsent || pairConsent !== pairConsentKey(draft3d, map)) return; pairConsent = null; el('pair-confirmation').checked = false; void run('/api/v1/navigation/operational-3d/pair', { map_id: draft3d.id, map_revision: draft3d.revision, navigation_map_id: map.id, navigation_map_revision: map.revision, pair_confirmation: 'derived_same_coordinates' }); };
  el('clear').onclick = async () => { await run('/api/v1/navigation/operational-3d', undefined, 'DELETE'); if (!state?.selected) { map3dSelect.value = ''; draftTouched = true; render(); onChange(); } };
  el('geometry').onclick = () => {
    const values = Object.fromEntries([...host.querySelectorAll('[data-geometry]')].map(input => [input.dataset.geometry, input.value.trim() === '' ? null : Number(input.value)]));
    if (!['z', 'roll', 'pitch'].every(key => finite(values[key]))) { error = '높이·roll·pitch를 모두 명시적으로 입력하세요. 빈 값은 0으로 처리하지 않습니다.'; render(); return; }
    void run('/api/v1/navigation/operational-3d/seed-geometry', { generation: state?.selected?.generation, ...values });
  };
  el('refresh').onclick = () => { error = ''; void refresh(true); void actions.refresh(); };
  el('observe-start').onclick = () => { void observe('start'); };
  el('observe-stop').onclick = () => { void observe('stop'); };
  el('prior-stationary').onchange = () => { const draft = getOperatorDraft(); priorAckRevision = el('prior-stationary').checked && draft?.status === 'ready' ? draft.revision : null; invalidateProposal('초안 확인이 바뀌어 이전 제안을 사용할 수 없습니다.'); render(); };
  el('proposal').onclick = () => { void calculateProposal(); };
  el('supervision').onchange = () => { render(); };
  el('conditional-ack').onchange = () => {
    proposalConsentBinding = el('conditional-ack').checked && proposalProofBinding && proposalPoseValid(true) && proposalConsentKey() === proposalProofBinding ? proposalProofBinding : null;
    if (!proposalConsentBinding) el('conditional-ack').checked = false;
    render();
  };
  el('confirm-handoff').onclick = () => { void confirmHandoff(); };
  return { render() { const result = render(); const next = current().draft3d; if (selected3d && next?.id === selected3d && draft3dRevision && next.revision !== draft3dRevision) invalidated = '3D 지도 revision이 변경됐습니다. ①부터 다시 확인하세요.'; return result; }, refresh,
    canStart: () => { const value = current(); return !busy && !handoffBusy && !handoffAwaitingStatus && !observationBusy && value.model.canStart && (state?.selected?.seed_geometry?.source !== 'proposal_confirmed' || value.handoffInfo.unexpired && handoff?.state === 'OBSERVATION_STOPPED' && state?.pair?.can_start === true); }, permitsGoal: () => available && (!current().model.enabled || current().model.tracking),
    state: () => state,
    draftChanged: (reason = '사용자 초안이 바뀌어 이전 제안을 사용할 수 없습니다.') => { priorAckRevision = null; el('prior-stationary').checked = false; invalidateProposal(reason); render(); },
    draftContext: () => ({ state, epoch: draftContextEpoch, observing: observationBusy || observationDraftPending, observationAction: observationDraftAction, available: available && draftContextConfirmed && !busy }) };
}
