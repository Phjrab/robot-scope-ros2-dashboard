# 검사와 실제 Nav2 미리보기

## 세 검사 수준

1. 작성 검사: strict schema, exact 지도/annotation/route pin, 방문 endpoint, 원본 route geometry, occupancy/unknown/KEEP_OUT, 지원 action/정책을 검사한다.
2. 계획 검사: current 또는 가상 start부터 각 방문까지 실제 planner가 반환한 모든 leg와 양끝 connector를 검사한다.
3. 실행 준비: 실제 운영 pose·세대·소유권·context·effective planner/footprint·runtime 정책을 재검증한다. 작성 PASS나 과거 preview PASS는 실행 승인과 다르다.

작성 방문 연결선은 선호 표시이므로 FLEXIBLE에서는 그 직선의 장애물 교차와 실제 planned path를 분리한다. 직접 입력 방문의 endpoint를 검사하고, E1 참조 geometry는 원본 전체를 검사한다. 실제 planner 결과는 모든 선분과 start/goal connector를 다시 검사한다.

## native adapter

`NativePlanner`는 Humble `nav2_msgs.action.ComputePathToPose`를 사용한다. 고정 action `/compute_path_to_pose`, planner `GridBased`, frame `map`이며 HTTP가 이를 바꿀 수 없다. `use_start=true`로 요청한 start를 고정한다. NavigateToPose, FollowPath, cmd_vel, initialpose, ARM, lifecycle start를 호출하지 않는다.

기본 비활성이다. 수락된 MR-MS-002 CLI hook이 적용돼도 명시된 자원 창 없이 실제 호출하지 않는다. 허용 시 ROS 모듈 import/서버 availability를 확인하고, 0.2~10초 범위 timeout·한 요청 concurrency·해당 preview goal만 bounded cancel/cleanup한다. 서버를 자동 시작하거나 재시작하지 않는다.

결과는 성공 status, `map` frame, 1~4096 points, finite pose, quaternion normalization을 검사한다. native adapter만 `actual_nav2_run=true`를 반환한다. 테스트 fixture는 synthetic으로 표시한다. 설치된 장비 action/plugin의 실제 호환성은 아직 NOT_RUN이다.

preview 전체는 기존 coordinator와 MS가 공유하는 coordination lock 안에서 수행한다. MS busy이면 차단하고 실제 planner navigation map의 id/revision이 작성 정의의 occupancy pin과 다르면 `PLANNER_MAP_MISMATCH`다. lock으로 map/resource 교체를 막되 motion owner·goal·lease를 만들지 않는다. 가상 시작점을 쓴 preview에도 지도 gate를 적용한다.

## geometry와 pin

기존 E0 validator와 map coordinate 규칙을 재사용하며 KEEP_OUT 경계까지 circular footprint 거리를 추가 검사한다. footprint provider가 없을 때 기존 `ROBOT_RADIUS_M` 0.25m는 작성용 근사일 뿐 실행 증거가 아니다. 실제 모델 반경과 더 보수적인 값을 사용하며 임의 제조사 기준으로 부르지 않는다.

pin은 definition, map family, annotation, route, navigation context, planner digest, footprint revision이다. preview 완료 시 definition/context/generation을 다시 대조한다. pose sequence는 context identity에 포함하지 않고 운영 source generation 변화는 포함한다. wrong frame/nonfinite/세대 변경/늦은 응답은 거부한다.

계획 길이는 반환 leg의 합이며 작성선 길이와 다르다. ETA는 실제 속도 증거가 없어 null이다. `계획 시점 결과 · 실행 중 재계획 가능`을 표시한다. preview 취소와 mission STOP은 별개다.

현재 `live_plan`은 `status=unavailable`, `reason=NAV2_RUNTIME_PATH_WITH_PROVENANCE_UNAVAILABLE`이다. runtime path의 frame/time provenance를 확보하기 전에는 실행 직전 계획이나 preview를 실제 최신 Nav2 경로로 승격하지 않는다.

## 실행 시 재계획 경계

FLEXIBLE은 지정 순서의 STOP/TASK를 NavigateToPose로 방문한다. preview polyline의 정밀 추종을 보장하지 않는다. MR dispatch preflight는 각 실제 dispatch 직전에 현재 운영 pose부터 다음 방문의 계획을 다시 만들고 검사한다. 그 사이 Nav2 내부 재계획은 wrapper 검사만으로 보장되지 않는다.

따라서 runtime unknown/KEEP_OUT 및 global/local costmap/controller 적용 증거가 없으면 `RUNTIME_POLICY_NOT_ENFORCED`로 실행을 차단한다. effective planner/footprint 증거가 없으면 `EFFECTIVE_PLANNER_CONFIG_UNAVAILABLE`이다. MR-MS-003은 PROPOSED/BLOCKED이며 production proof를 true로 설정하지 않았다.

이동 중 pose 관측은 `readiness.localization` freshness로 판단하고 새 goal admission(`can_send_goal`)과 분리한다. 이동 중 goal admission이 닫혀도 fresh 관측은 궤적에 남길 수 있다. stale localization, 운영 pose source 미상, 유효한 effective footprint 누락은 실행 준비를 차단한다.

## 검증 상태

focused83과 전체 Python1939(skip2/fail0), Node381·Chromium96 PASS. 실제 adapter code + synthetic ROS transport4개에서 고정 action/planner, timeout·자기 preview cancel, HTTP cancel cleanup, frame/nonfinite/rejection을 검사했다. 서비스 fixture는 unknown crossing connector, family/context/process generation, resource/map gate, 각 leg fresh start, compile/preview 무동작을 검사한다. 좌표 회전 변환은 JS roundtrip·기존 spatial regression으로 확인했다.

실제 ROS graph·설치된 planner·effective footprint·runtime unknown/KEEP_OUT enforcement는 NOT_RUN/BLOCKED다. MR-MS-003 provider는 PROPOSED, app 기본값은 {}다. 실제 runtime plan의 provenance도 미확보다. 독립 software PASS가 runtime proof를 대신하지 않는다. 상세 evidence는 VALIDATION.json이다.
