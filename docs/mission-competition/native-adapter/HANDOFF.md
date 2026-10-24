# C2 native action adapter — review only

기준: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`, 2026-10-24 KST.
제출: `review/20261024-c2-mission-adapter`. 사용자 후속 지시로 local-only/main-only 제출 정책을 대체했다. main·공용 파일·다른 역할 소스는 수정하지 않는다. 실제 로봇·ROS·카메라·서비스·배포는 실행하지 않는다.

## 구현 범위

`competition_native`는 기존 run coordinator에서 호출할 **단일 행동 단위** adapter다. 새로운 미션 run engine, 자동 monitor, timer task, 명령 publisher, ROS node, 장비 factory를 생성하지 않는다. `NativeActionAdapter.snapshot()`과 import는 port 호출을 하지 않는다. 기본 `Activation()`은 비활성이다. 명시적 binding/검증 참조와 행동별 capability, native cadence가 모두 공급되어야 start를 허용한다. 문자열 참조는 운영자가 검토한 사실을 전달하는 내부 설정이지 검증 자체가 아니다. 합성 PASS를 등록 근거로 사용하면 안 된다.

- `state.decide`: 입력·상태→다음 상태/효과의 순수 함수. 상태 이름은 내부 진단이며 공용 enum 변경이 아니다.
- `adapter.NativeActionAdapter`: 단일 step에서 목표·제한·취소·자세·terrain port 호출, 요청 중복/세대 fencing, 비동기 STOP 경합 처리. 호출 intent를 먼저 소비하여 결과 불확실한 명령을 자동 재시도하지 않는다.
- `observations.Normalizer`: 기존 `Evidence.model_validate` 재사용. component별 시각·sequence·epoch·scope·수신시각과 receiver session을 보존한다. 신규 공용 HTTP/ROS 입력을 만들지 않는다.
- `coordinator.CoordinatorNavigationPort`: 실제 `MissionCoordinator.start/resume/pause/snapshot`, `NavigationCoordinator.view/coordination_lock` 계약을 호출한다. 공유 lock을 바깥에서 다시 잡지 않는다. admission은 기존 `MissionRoutes._admission`과 정확히 같아야 한다.
- `authority.CommandBoundary`: 단일 최종 command consumer에 필요한 계약의 **순수 참조 구현**. 속도 tuple을 반환할 뿐 actuator를 제어하지 않는다. 기존 `ControlManager`나 navigation command bridge를 대체하거나 자동 연결하지 않는다.

## 행동과 증거

신호: 접근 goal은 traffic HOLD 없이 기존 coordinator로 보낸다. 접근 SUCCEEDED 또는 정확한 CANCELED+ACK 이후 HOLD를 요청한다. exact request/scope HOLD ACK 뒤 두 앞발·physical STOP의 실제 샘플 연속 2초를 요구한다. RED 대기와 obstacle wait/replanning/failure는 분리한다. 연관된 fresh GREEN/pose/path에서 **새 exit generation을 먼저 HOLD**, 새 goal을 dispatch하고 새 generation 관측을 기다린다. 그 다음 RELEASE를 ACK 받아도 departure latch는 세우지 않는다. fresh departure sidecar + MOVING + GREEN 증거에서만 latch한다. 출발 전 RED/UNKNOWN/stale/잘못된 ACK는 HOLD/cancel이고, 출발 뒤 RED는 통과할 수 있지만 E-stop·충돌·path/pose/safety stale은 계속 우선한다. blind recovery/costmap clear/spin/backup 호출은 없다.

주차: full containment + SIT + 검증 참조 + STOP을 5초 요구한다. 조건이 깨지면 다시 누적한다. SDK ACK는 상태 증거가 아니다. 완료 후에도 HOLD를 유지하며, `prepare_movement`의 STAND 요청 이후 검증된 STAND/STOP을 받아야 READY_TO_MOVE가 된다. 이것도 주행 허가가 아니며 다음 step은 새 goal generation이 필요하다.

Terrain: 접근 종료 후 주입된 gait/terrain executor를 호출한다. 완료 boolean에 더해 해당 구성요소의 신선한 검증 결과와 참조를 요구한다. 시간 경과로 성공하지 않는다. 중단 시 navigation과 시작된 posture/terrain executor 모두 cancel을 시도한다.

OUT: full-body crossing 증거만 통과로 인정한다. attempted_steps, traversed_segments, full_body_crossed를 각각 보존한다. OUT 성공을 모든 구간·미션 성공이나 공식 점수로 승격하지 않는다. 몸체 중심점은 판정 입력으로 사용하지 않는다.

## 시각·관측 경계

공용 `competition.v0.1`, `mission-action.v0.1`, `competition-evidence.v0.1` 및 canonical schema는 수정하지 않았다. `Packet/ComponentStamp/Extras`는 내부 Python sidecar이며 공용 메시지로 주장하지 않는다.

1. ClockBinding은 trusted receiver가 검증한 producer/epoch/clock 관계다. payload가 보내는 `clock_verified` 플래그는 받지 않는다. native에는 synchronized_ros/utc만 허용한다. source_age_s는 해당 동기화 도메인에서 오차 상한까지 포함해 계산한 나이여야 한다. 서로 다른 호스트 monotonic을 빼지 않는다. 시계 검증·오차 측정 자체는 아직 live binding의 책임이다.
2. signal/feet/motion/pose/path/navigation/body/posture/terrain/departure/safety/coverage 각각의 source age와 최초 receiver monotonic receipt를 유지한다. 기준은 `source_age_at_receipt + receiver_elapsed`와 별도의 receiver TTL이다. RouteStatus observation_age_s도 별도로 검사한다.
3. 동일 component sequence의 정확히 같은 재사용은 원래 receipt를 유지한다. 다른 값으로 바꾸면 거부한다. sequence 증가로 동일 source stamp를 새 데이터처럼 세탁할 수도 없다. 전체 envelope duplicate/retired epoch/다른 scope는 캐시를 비우고 전이에 사용하지 않는다.
4. adapter마다 새 receiver session nonce를 생성한다. trusted ingress는 producer와 이 session을 명시적으로 재바인딩해야 한다. 오래된 메시지에 새 nonce/receipt를 붙여 재전송하면 안 된다. 재연결은 현재 action을 INTERRUPTED로 닫으며 새 run identity·epoch·session이 필요하다. 이전 실행 이력을 executable resume 자료로 import하는 경로는 없다.
5. 명령 TTL 상한 0.25초와 합성 evidence TTL/gap 0.5초를 구분한다. `TimingPolicy()`는 native cadence가 미확정이라 실행을 거부한다. `TimingPolicy.synthetic()`는 테스트 전용이다. 운영 값은 센서/온보드 실측과 watchdog 검증 뒤 명시한다. 캐시 polling으로 dwell 시간을 늘리지 않고 필요한 실제 샘플의 수신 시각으로만 누적한다.

기준 VM에는 별도의 `SignalObservation/StopZoneObservation/RouteStatus` 클래스가 없다. 실제 타입은 `traffic_signals/core.py:StopInput`과 dict 기반 출력이다. `from_vm_stop_input`은 그 shape를 변환하며 scope·epoch·sequence·개별 signal/route age를 보존해야 한다. `approach_ack`를 native SUCCEEDED/cancel ACK로 승격하지 않는다. OpenCV/ROS를 import하지 않는다. 실제 C4 output과의 compatibility는 아직 검증하지 않았다.

## 기존 계약과의 차이 / live 차단점

- 기존 Navigation goal ID는 16..128 token이고 canonical evidence ID는 hex32다. port는 둘을 분리해 보관하고, 실제 ID가 정확히 일치할 때만 logical ID로 투영한다. 임의 ID를 잘라 넣거나 foreign goal을 cancel하지 않는다.
- 기존 coordinator에는 취소된 접근 waypoint를 서버가 안전하게 완료 처리하고 exit로 이동하는 native hook이 없다. fake port에서는 이 경로의 전이를 끝까지 검증하지만 실제 bridge는 `COORDINATOR_CONTINUATION_HOOK_REQUIRED`로 거부한다. 선택 callback을 주입하는 계약만 제공하며 base에 있는 API라고 주장하지 않는다.
- 접근 성공은 기존 after-arrival barrier와 정확한 token을 이용해 다음 leg를 시작할 수 있다. C1은 이것을 **내부 native barrier**로 컴파일/표시해야 하고 사용자 원격 확인/skip에 의존하게 해서는 안 된다. adapter는 API router·canonical 정의·저장·공용 executor를 수정하지 않는다.
- live ConstraintPort, authenticated ObservationPort, foot/body/physical-stop/departure provider, posture/gait/terrain validation이 없다. 따라서 운영상 native 등록은 계속 비활성이다. 없는 capability는 해당 action에만 표시한다. 편집·검사와 독립 단계는 계속 가능하다.
- 기존 `ControlManager`의 STOP/lease/TTL과 navigation command consumer 사이에 최종 authority 계약을 연결해야 한다. HOLD ACK는 command gate가 설치됐다는 ACK이며 physical stop 증명이 아니다. HOLD는 latch, RELEASE는 자기 owner 제한만 해제하며 old command/goal 재생은 금지한다. E-stop/충돌 > 모든 owner HOLD > terrain cap > tracking을 가장 제한적으로 적용한다. 새 request sequence보다 늦게 도착한 RELEASE는 HOLD를 덮어쓸 수 없어야 한다.
- 효과 처리 중에도 최종 authority의 독립 watchdog/E-stop은 작동해야 한다. 이 adapter 자체는 스케줄러/하드웨어 안전장치가 아니다. `observe(None)`을 호출하지 않으면 Python action state가 스스로 시간을 진행하지 않는다. production scheduler를 추가로 만들지 않고 기존 backend 소유 loop에 연결해야 한다.

## 검증과 재현

```bash
python3 -m unittest discover -s tests/competition_native -t tests -v
python3 -m unittest discover -s tests -v
python3 -m ruff check robot_dashboard scripts tests/competition_native
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 scripts/check_repository_secrets.py
```

프로젝트 Python 가상환경과 Ruff 0.6.9를 사용한다. 실물 입력·native Nav2·ROS·실제 모델/영상 replay는 NOT_RUN이다. 테스트는 기존 MissionCoordinator도 사용하지만 navigation과 모든 physical port는 fake다. 최종 검사 결과와 tested code SHA는 `docs/parallel-review/20261024/C2/REVIEW.md`에 기록한다.

삭제/이동/바이너리 변경은 없다. 롤백 범위는 새 competition_native 패키지·전용 tests·문서뿐이다. 기존 지도·설정·저장소 migration·장비 상태에 영향이 없다. 통합 승인 전 다른 작업 브랜치를 병합하지 않는다.
