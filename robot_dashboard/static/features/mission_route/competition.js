// PROPOSED v0.1 presentation only. No browser dwell, signal FSM or motion decision.
export const actionLabels = {
  NAVIGATE_ADAPTIVE: '장애물 구간', TRAFFIC_STOP_AND_GO: '신호 정차·출발',
  TRAVERSE_TERRAIN: '경사·계단', PARK_SIT_HOLD: '주차·앉기', FINISH_CROSSING: 'OUT 완전 통과',
};
export function nativeBlockers(definition, registry) {
  if (!definition?.competition) return [];
  return definition.visits.map(v => {
    const cap = registry?.actions?.[v.mission_action?.type];
    return `${v.label}: ${(cap?.components || []).filter(c => c.status !== 'CONNECTED').map(c => c.reason).join(', ') || 'COMPETITION_ADAPTER_UNCONNECTED'}`;
  });
}
export function competitionSummary(definition, run, mission, registry) {
  if (!definition?.competition) return '';
  const c = definition.competition;
  return `${c.review_status} · 미션 ${run?.definition_id || '저장 전'} / 시도 ${run?.id || '없음'}\n지도 ${definition.map_family.occupancy_revision.slice(0,12)}… · arena ${c.arena_id}@${c.arena_revision}\nmodel ${c.model_revision} · profile ${c.profile_revision}\nVM evidence ${registry?.vm_evidence?.traffic_signals?.scope || '미연결'} · detector 입력 필요 / 발 실측 미확인 / native Nav2·Jetson NOT_RUN\n모드 ${run?.mode === 'fixture' ? 'FIXTURE · 합성 관측 / 실제 주행 아님' : '편집 · 실장비 실행 미연결'} · backend ${registry?.contract_status || 'UNCONNECTED'}\n타이머·행동 owner: 온보드 backend · 경과 ${mission?.elapsed_s ?? '—'}s\n정비 최대 ${c.maintenance_limit}회 · 경기시간 포함 · ${c.resume_position_rule}\n점수: 미산정 / 보조용, 심판 공식 점수 아님`;
}
export function observationText(mission) {
  const e = mission?.observation;
  const lines = [
    `실행 ${mission?.state || '없음'} · ${mission?.phase || '—'} · ${mission?.reason || '관측 대기'}`,
    `owner ${mission?.owner_id || '미연결'} · goal ${mission?.goal_id || '없음'} · generation ${mission?.goal_generation ?? '—'}`,
    `유효 조건 누적 ${mission?.dwell_elapsed_s ?? 0}s · 서버 snapshot (브라우저 추정 없음)`,
    '2초 정차 / 앉기 확인 후 5초는 최소값입니다. 명령 송신·Nav2 성공과 물리 정지는 별도입니다.',
  ];
  if (!e) return [...lines, '관측 없음 · 카메라 / pose / executor를 각각 확인하세요.'].join('\n');
  return [...lines,
    `회피 ${e.obstacle_state} · source ${e.obstacle_source ?? 'null'} · age ${e.observation_age_s ?? 'null'}s`,
    `계획 revision ${e.planned_path_revision ?? 'null'} · 실제 최소여유 ${e.minimum_clearance_m ?? 'null'}m`,
    `신호 RAW ${e.raw_state} / stable ${e.stable_state} · signal ${e.signal_id ?? '없음'} / crossing ${e.crossing_id ?? '없음'}`,
    `confidence ${e.confidence ?? 'null'} (calibrated probability 보장 없음) · frame age ${e.source_age_s}s · 서버 수신 age ${mission?.receipt_age_s ?? 'null'}s`,
    `품질 ${e.quality_flags.join(', ') || '추가 flag 없음'} · exposure ${JSON.stringify(e.exposure_metadata)}`,
    `왼앞발 ${e.front_left_status} / 오른앞발 ${e.front_right_status} · ${e.feet_evidence_kind} · physical stop ${e.body_motion_status}`,
    `완전 포함 ${e.full_body_inside} · 자세 ${e.posture} · 전체 OUT 통과 ${e.full_body_crossed}`,
    `원본 RGB ROI ${JSON.stringify(e.roi_xyxy_native)} / native size ${JSON.stringify(e.native_image_size)}`,
    `원본 RGB ${e.native_image ?? '미연결'} · mask/전처리 ${e.processed_image ?? '미연결'} · profile ${e.preprocess_profile ?? '미연결'}`,
    `이미지/관측 증거 ${e.evidence_type} · 합성 fixture에는 실제 카메라 이미지가 없습니다.`,
    '다음 출발 조건: 접근 goal 완료/취소 ACK → HOLD ACK → 앞발 두 개·실제 정지 연속 2초 → 연결된 fresh GREEN·path clear·현재 pose → 새 goal leg',
    '신호 주기 안내 5초는 GREEN 예측에 사용하지 않습니다. RED/UNKNOWN 수동 우회 없음.',
  ].join('\n');
}
export function addCompetitionEditor({right, visit, input, make, update, currentAction}) {
  const action = visit.mission_action;
  if (!action) return;
  right.append(make('strong', `${actionLabels[action.type]} · ${action.type}`));
  const ids = make('details'); ids.append(make('summary', 'step / visit ID'), make('p', `step ${action.step_id} · visit ${visit.visit_id}`)); right.append(ids);
  right.append(make('p', visit.target === 'unplaced' ? '좌표 DRAFT · 지도 도구의 선택 step 위치 지정을 사용하세요.' : '목표 좌표는 기존 지도 편집기를 사용합니다.'));
  const fields = {
    NAVIGATE_ADAPTIVE: [['corridor_id','허용 corridor'], ['avoidance_profile','회피 profile']],
    TRAFFIC_STOP_AND_GO: [['zone_id','정지 zone'], ['signal_id','signal ID'], ['crossing_id','crossing ID']],
    TRAVERSE_TERRAIN: [['terrain_segment','terrain segment'], ['gait_profile','gait executor profile']],
    PARK_SIT_HOLD: [['zone_id','주차 polygon ID']], FINISH_CROSSING: [['zone_id','OUT line ID']],
  };
  for (const [key, label] of fields[action.type]) input(label, 'text', action[key] || '', value => update({[key]: value || null})).maxLength = 64;
  const heading = input('접근 방향(°)', 'number', action.approach_heading * 180 / Math.PI, value => update({approach_heading: value * Math.PI / 180})); heading.min = '-180'; heading.max = '180';
  if (action.type === 'TRAFFIC_STOP_AND_GO') {
    const dwell = input('유효 정차 최소(초)', 'number', action.dwell_seconds, value => update({dwell_seconds: value})); dwell.min = '2'; dwell.max = '300';
    right.append(make('p', '출구 goal 좌표 미확정 시 실실행 차단. fixture는 합성 goal 수신만 검증합니다.'));
    for (const axis of ['x','y','yaw']) {
      const value = action.exit_pose?.[axis] ?? 0;
      const control = input(`출구 ${axis}${axis === 'yaw' ? '(°)' : '(m)'}`, 'number', axis === 'yaw' ? value * 180 / Math.PI : value, v => update({exit_pose: {...(currentAction().exit_pose || {x:0,y:0,yaw:0}), [axis]: axis === 'yaw' ? v * Math.PI / 180 : v}}));
      control.min = axis === 'yaw' ? '-180' : '-10000'; control.max = axis === 'yaw' ? '180' : '10000';
    }
  }
  if (action.type === 'PARK_SIT_HOLD') { const sit = input('앉기 확인 후 최소(초)', 'number', action.sit_seconds, value => update({sit_seconds: value})); sit.min = '5'; sit.max = '300'; }
  const timeout = input('행동 timeout(초)', 'number', action.timeout_seconds, value => update({timeout_seconds: value})); timeout.min = '10'; timeout.max = '3600';
}
export function pathEvidence(plan) {
  if (!plan) return 'unavailable';
  if (/fixture|synthetic/i.test(`${plan.evidence_type || ''} ${plan.scope || ''}`)) return 'fixture';
  return plan.actual_nav2_run === true ? 'native' : 'unavailable';
}
