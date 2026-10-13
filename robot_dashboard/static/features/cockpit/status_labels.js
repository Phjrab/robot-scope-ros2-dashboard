// Presentation only. Transport enums and freshness decisions stay with their owners.
const STATUS_LABELS = Object.freeze({
  CONNECTED: '연결됨', NOT_CONNECTED: '연결 안 됨', OFFLINE: '연결 끊김',
  LIVE: '실시간 수신', 'CONTROL LIVE': '제어 상태 수신',
  WAITING: '데이터 대기', STALE: '오래된 데이터', ERROR: '오류',
  UNKNOWN: '확인 안 됨', UNAVAILABLE: '사용 불가',
  FIXTURE: '합성 예시', REPLAY: '기록 재생',
  READY: '준비됨', 'SERVER READY': '서버 준비됨',
  IDLE: '대기', CAPTURING: '수집 중', STOPPED: '중지됨',
  RECONNECTING: '다시 연결 중',
});

export function statusLabel(value) {
  const raw = String(value ?? '');
  return STATUS_LABELS[raw.toUpperCase()] || raw;
}

// The first four codes are emitted by ros/navigation_gateway.py. lowstate_stale
// is supported as an explicit input label and exercised by the UI fixture only.
const NAVIGATION_BLOCKER_LABELS = Object.freeze({
  navigation_transport_unavailable: '주행 명령 전송 경로가 준비되지 않았습니다. 주행 연결 설정을 확인하세요.',
  control_target_mismatch: '주행 제어 대상이 일치하지 않습니다. 선택한 로봇과 제어 대상을 확인하세요.',
  bridge_or_lowstate_unavailable: '제어 연결 또는 로봇 상태 정보를 사용할 수 없습니다. 제어 연결과 LowState 수신을 확인하세요.',
  cmd_vel_publisher_count: '주행 속도 명령 발행자 수가 예상값과 다릅니다. cmd_vel 발행자가 하나인지 확인하세요.',
  lowstate_stale: '로봇 상태 정보가 오래되었습니다. LowState 상태 수신을 확인하세요.',
});

export function navigationBlockerLabel(value) {
  const messages = {
    navigation_unavailable: 'Nav2 패키지 또는 허용된 launcher가 준비되지 않았습니다.',
    robot_offline: '로봇 연결이 없어 새 주행 명령을 보낼 수 없습니다.',
    manual_control_active: '수동 제어가 ARM되어 있습니다. Controls에서 먼저 DISARM하세요.',
    mapping_active: '공유 위치추정 파이프라인이 이미 실행 중입니다. Navigation이 이 센서 파이프라인을 재사용합니다.',
    mapping_transition: '공유 위치추정 파이프라인이 전환 중입니다. 잠시 기다리거나 STOP으로 시작 작업을 정리하세요.',
    mapping_operation_active: '지도 저장·변환 작업이 끝난 뒤 Nav2를 시작할 수 있습니다.',
    navigation_transition: 'Navigation 시작 또는 중지 작업이 진행 중입니다.',
    localization_pipeline_not_running: '공유 위치추정 센서 파이프라인을 준비하지 못했습니다. Navigation 로그를 확인하세요.',
    map_required: '정적 2D 지도를 선택하세요.',
    initial_pose_required: '지도에서 로봇의 초기 위치와 방향을 지정하세요.',
    localization_lost: '위치추정이 유실되었습니다. 초기 위치를 다시 지정하세요.',
    parameters_unavailable: '안전한 파라미터 snapshot이 없습니다.',
  };
  if (messages[String(value || '')]) return messages[String(value || '')];
  const raw = String(value ?? '');
  return NAVIGATION_BLOCKER_LABELS[raw] || raw;
}
