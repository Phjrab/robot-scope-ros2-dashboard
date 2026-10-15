# 33 — 제품 NativePlanner acceptance

기록일: 2026-10-15 KST. Baseline source는 `2555f3763996c7b331389924bb5df48d62094736`이며 아래 변경은 그 위의 통합 변경이다. **SOFTWARE_TEST 통과 / 제품 native 실행 NOT_RUN / 운영 acceptance BLOCKED**다. 로컬 Mac의 `.venv/bin/python`은 Python 3.13.2이며 `ros2` executable과 `rclpy`가 없다. planner 하위 작업은 장비에 접속하지 않았다. 통합 담당의 read-only 장비 조사는 BASELINE.md에 별도 기록했다. 서비스 변경, ROS pipeline, 카메라, initialpose, motion goal은 실행하지 않았다. 전체 통합 source tip과 회귀 결과는 통합 진행 기록에 남긴다.

## 실제 제품 경로와 고친 결함

제품 호출은 `POST /api/v1/mission-plans/{identifier}/plan-preview` → 기존 `MissionRoutes.preview` → `NativePlanner.plan` → Humble `ComputePathToPose`다. dispatch 직전 경로는 기존 `MissionCoordinator._dispatch_preflight` → `MissionRoutes.preflight_dispatch` → 같은 adapter다. dispatch 계획은 controller trajectory 또는 실행 중 global replans의 증거가 아니다.

`/compute_path_to_pose`, `GridBased`, frame `map`, `use_start=true`, root namespace의 `/planner_server`를 고정한다. HTTP 입력으로 endpoint, domain, plugin을 고르지 못한다. 기본 resource window는 계속 false다. 시작 pose가 live인지 hypothetical인지는 기존 preview 계약이 명시한다. Native action은 pose 좌표만 받고 operational readiness를 만들지 않는다.

기존 adapter는 별도 `Context`를 만들면서 spin에는 global executor를 사용했다. 이제 해당 Context에 묶인 전용 `SingleThreadedExecutor`만 사용·정리한다. 또한 timeout 뒤 acceptance를 1초만 기다리고 context를 파괴하던 경로는 늦게 수락된 자기 goal을 정리하지 못할 수 있었다. 명시적 UUID를 발급하고 goal handle ID를 대조하며 자기 handle만 cancel한다. 이미 terminal인 goal은 불필요하게 cancel하지 않는다.

planner slot은 1개다. deadline은 기존 0.2~10초, 기본 5초를 유지한다. foreground 정리 1초 뒤에도 acceptance/result가 불명확하면 slot과 원래 ROS context를 격리한다. 추가 정리 thread는 최대 5초만 spin한다. terminal result(SUCCEEDED/CANCELED/ABORTED)를 확인해야 자원을 해제한다. cancel acknowledgement만으로 종료를 주장하지 않는다. 남은 불확실성은 `diagnostics()`의 `PLANNER_CLEANUP_UNCERTAIN`과 goal UUID로 남기고 신규 요청은 `PLANNER_CLEANUP_PENDING`으로 거부한다. 무기한 spin, cancel-all, 다른 요청의 context 파괴를 하지 않는다. 이 상태의 복구는 현재 운영자가 해당 UUID/server 상태를 조정하는 별도 resource 작업이며 자동 restart가 아니다.

## Source / runtime / config provenance

전송 전과 결과 수신 뒤 ROS graph에서 action owner가 정확히 하나인지 검사한다. owner 이름/namespace와 `/_action/status` publisher owner가 일치해야 하고 status publisher도 정확히 하나여야 한다. 유효한 24-byte status GID를 adapter lifetime에 핀하므로 실행 중 또는 요청 간 server restart는 `PLANNER_SERVER_IDENTITY_CHANGED`로 거부한다. 임의 이름의 다른 서버와 중복 이름의 서버도 통과시키지 않는다. 새 서버를 받아들이려면 승인된 새 resource window에서 adapter 인스턴스를 다시 만들어야 한다.

adapter 생성 시 dashboard process의 ROS domain, RMW, localhost/discovery/security 설정과 DDS XML 내용 hash를 핀한다. native Context는 그 domain을 명시적으로 사용하고 실제 resolved RMW를 기록한다. 요청 전후 환경 또는 XML bytes가 바뀌면 실패한다. XML 파일을 못 읽으면 unavailable이다. 환경 hash만으로 Nav2 process의 실제 interface나 plugin bytes가 입증되지는 않는다. 그 교차 검증과 mask/controller enforcement는 MR-MS-003의 실제 runtime policy provider 및 아래 native acceptance가 충족해야 한다.

adapter 결과는 기존 `poses`에 더해 `goal_id`, `action_name`, `planner_id`, `action_server{node_name,node_namespace,status_gid}`, `ros_environment{environment_digest,rmw,domain_id,localhost_only,profile_digests}`, `request{use_start,start,goal,header}`, `native_path{header,poses}`를 반환한다. 원래 path의 각 header/stamp, xyz, xyzw를 보존한다. path는 1~4096 pose, map frame, finite xyz, 정상화된 quaternion을 요구한다. UI용 yaw 투영을 원본 quaternion의 대체 증거로 쓰지 않는다. service는 preview leg에 원본 native evidence를, dispatch 이력에는 고정 provenance와 원본 path digest를 보존한다. 반복 HTTP cancel 중에도 foreground ownership과 quarantine을 예약으로 유지한다.

설치 Nav2 planner/costmap/RPP package version은 Humble1.1.20으로 read-only 확인했다. 실제 loaded plugin library hash, planner executable hash, active Nav2 config/mask hash, server PID/start generation은 **수집 안 됨**이다. local source test가 이 필드를 채우거나 production attestation을 만들지 않는다. 과거 독립 Navfn `path90 / 2.257095m`는 [새 지도 후속 기록](../hardware-validation/04_new_map_followup.md)의 역사적 증거이며 이번 제품 adapter 실행 결과가 아니다.

## SOFTWARE_TEST

명령: `.venv/bin/python -m unittest discover -s tests -p 'test_mission_route_planner.py' -v`. **17개 PASS**, `git diff --check` PASS. Transport fixture가 실제 adapter 코드를 호출하지만 rclpy/nav2 메시지는 fake다. `actual_nav2_run` 출력 flag를 검사하더라도 증거 분류는 SOFTWARE_TEST다.

검증 범위: default false/no transport, fixed ComputePath/use_start, request UUID와 원본 path metadata, 중복/다른 action/status owner 거부, effective RMW mismatch, domain/DDS profile drift, 결과 전후 server GID 변경, 요청 간 restart, wrong frame/empty·oversized path/nonfinite/invalid quaternion/ABORTED/rejected result, deadline·HTTP cancel·병렬 요청, timeout 뒤 acceptance, terminal 없는 cancel의 유한 격리, foreign UUID cancel 금지. 세부 최종 count와 전체 suite 결과는 통합 기록을 참조한다.

## 다음 최소 native acceptance

지원되는 격리 Humble/Nav2 개발 환경에서 먼저 실행한다. 운영 Jetson을 쓰려면 40~43단계의 **현재** 조건과 resource window가 먼저 충족되어야 한다. 이 문서 자체는 pipeline 기동이나 배포 승인이 아니다. 기존 도구/launch/config와 실제 제품 HTTP 경로를 재사용하고 별도 adapter를 작성하지 않는다.

| 행 | 현재 상태 | 다음 관측과 보존할 증거 |
| --- | --- | --- |
| dashboard client ↔ expected server | NOT_RUN | dashboard·Nav2 각각 process domain/RMW/interface config hash, `/planner_server` PID/start generation, status GID, loaded plugin/package/executable/config hash를 매칭 |
| free-space 연결 | NOT_RUN | 실제 제품 HTTP request/body revision과 start_source, adapter goal UUID, 원본 native path/header 및 policy/context pins, 성공 result와 owned cleanup |
| occupied / unknown / out-of-map | NOT_RUN | 목표별 개별 native result와 제품 거부 이유. wrong frame와 planner infeasible을 구분; 기존 unknown 허용 FAIL을 삭제하지 않음 |
| KEEP_OUT 중간 관통 | NOT_RUN | mask/info/annotation revision 및 hash, native path와 제품 footprint 검증, 실제 costmap enforcement 증거 |
| 좁은 통로 / footprint edge | NOT_RUN | effective footprint/plugin/config hash와 지도 resolution, 중심점 free라도 footprint 침범 시 제품 거부 |
| planning 중 context 변경 | NOT_RUN | map/annotation/mask/policy/source generation 각각 변경 후 stale 응답 폐기, 최초/최종 pins와 거부 이유 |
| timeout / late acceptance / restart | NOT_RUN | goal UUID별 accept/result/cancel timeline, terminal 또는 quarantine, slot 재사용 여부; cancel-all 없음 |
| 동시 preview / MS busy / MR active | NOT_RUN | 두 요청 identity, shared owner 상태, read-only admission 정책과 resource 충돌 거부; stop 경로 응답성 |
| live / hypothetical start 및 clock | NOT_RUN | use_start=true, 실측 operational source clock/generation/pose 또는 명시 hypothetical, stale live pose 거부; hypothetical 성공이 execution gate를 열지 않음 |

각 행은 exact source/runtime/config와 전후 graph를 함께 기록한다. `NavigateToPose`, `FollowPath`, `cmd_vel`, `initialpose`, ARM 또는 service 자동기동을 acceptance 도구가 호출하지 않아야 한다. planner 성공은 실제 경로 추종이나 물리 정지 증명이 아니다.
