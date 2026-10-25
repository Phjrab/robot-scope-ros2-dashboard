# C2 native action adapter — review only

기준: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`, 2026-10-24 KST.
제출: `review/20261024-c2-mission-adapter`. 사용자 후속 지시로 local-only/main-only 제출 정책을 대체했다. main·공용 파일·다른 역할 소스는 수정하지 않는다. 실제 로봇·ROS·카메라·서비스·배포는 실행하지 않는다.

최신 후속 계약과 검증은 `docs/parallel-review/20261024/C2/ROUND4.md` 및 `WIRING_PROPOSAL.md`를 따른다. C1 `85c5b6b`는 ROUND3 runtime/first receipt/STOP와 관측 ledger를 이미 채택했다. 이번에는 `SignalBinding.inference_settings_sha256` 필수 owner pin만 추가하며 상태기를 동결한다. 최초 제출 `REVIEW.md`, `INPUTS.json`, `VALIDATION.json`의 65개 테스트/기준 SHA는 과거 제출 기록이다.

## 구현 범위

`competition_native`는 기존 run coordinator에서 호출할 **단일 행동 단위** adapter다. 새로운 미션 run engine, 자동 monitor, timer task, 명령 publisher, ROS node, 장비 factory를 생성하지 않는다. `NativeActionAdapter.snapshot()`과 import는 port 호출을 하지 않는다. 기본 `Activation()`은 비활성이다. 명시적 binding/검증 참조와 행동별 capability, native cadence가 모두 공급되어야 start를 허용한다. 문자열 참조는 운영자가 검토한 사실을 전달하는 내부 설정이지 검증 자체가 아니다. 합성 PASS를 등록 근거로 사용하면 안 된다.

- `state.decide`: 입력·상태→다음 상태/효과의 순수 함수. 상태 이름은 내부 진단이며 공용 enum 변경이 아니다.
- `adapter.NativeActionAdapter`: 단일 step에서 목표·제한·취소·자세·terrain port 호출, 요청 중복/세대 fencing, 비동기 STOP 경합 처리. 호출 intent를 먼저 소비하여 결과 불확실한 명령을 자동 재시도하지 않는다.
- `observations.Normalizer`: 기존 `Evidence.model_validate` 재사용. component별 시각·sequence·epoch·scope·수신시각과 receiver session을 보존한다. 신규 공용 HTTP/ROS 입력을 만들지 않는다.
- `coordinator.CoordinatorNavigationPort`: 실제 `MissionCoordinator.start/pause/snapshot`과 별도 native continuation callback, `NavigationCoordinator.view/coordination_lock` 계약을 호출한다. 공유 lock을 바깥에서 다시 잡지 않는다. admission은 기존 `MissionRoutes._admission`과 정확히 같아야 한다.
- `runtime.configure_action`: config/ports/clock으로 구성하는 실제 owner-loop API. receive/event_ack/tick/stop/cleanup을 명시 호출하며 snapshot은 항상 live_ready=false다. non-synthetic start는 미연결로 거부한다.
- `fragments.join_signal`: C4 signal_fragment와 sidecar를 independent evidence에 결합한다. 최신 C4의 명시적 최초 age와 first_received_s를 사용한다. legacy 완료시각 age는 모순 검사에만 사용하고 receipt를 갱신하지 않는다.
- `authority.FinalConsumerConstraintPort`: 설치 callback/정확한 consumer receipt를 연결한다. enqueue 결과를 설치 ACK로 승격하지 않으며 실제 consumer는 C1 연결 필요다.
- `authority.CommandBoundary`: 단일 최종 command consumer에 필요한 계약의 **순수 참조 구현**. 속도 tuple을 반환할 뿐 actuator를 제어하지 않는다. 기존 `ControlManager`나 navigation command bridge를 대체하거나 자동 연결하지 않는다.

## 행동과 증거

신호: 접근 goal은 traffic HOLD 없이 기존 coordinator로 보낸다. 접근 SUCCEEDED 또는 정확한 CANCELED+ACK 이후 HOLD를 요청한다. exact request/scope HOLD ACK 뒤 두 앞발·physical STOP의 실제 샘플 연속 2초를 요구한다. RED 대기와 obstacle wait/replanning/failure는 분리한다. 연관된 fresh GREEN/pose/path에서 **새 exit generation을 먼저 HOLD**, 새 goal을 dispatch하고 새 generation 관측을 기다린다. 그 다음 RELEASE를 ACK 받아도 departure latch는 세우지 않는다. exit ACK와 RELEASE ACK 이후 취득한 fresh departure sidecar + MOVING + GREEN 증거에서만 latch한다. 출발 전 RED/UNKNOWN/stale/잘못된 ACK는 HOLD/cancel이고, 출발 뒤 RED는 통과할 수 있지만 E-stop·충돌·path/pose/safety stale은 계속 우선한다. blind recovery/costmap clear/spin/backup 호출은 없다.

주차: full containment + SIT + 검증 참조 + STOP을 5초 요구한다. 조건이 깨지면 다시 누적한다. SDK ACK는 상태 증거가 아니다. 완료 후에도 HOLD를 유지하며, `prepare_movement`의 STAND 요청 이후 검증된 STAND/STOP을 받아야 READY_TO_MOVE가 된다. 이것도 주행 허가가 아니며 다음 step은 새 goal generation이 필요하다.

Terrain: 접근 종료 후 주입된 gait/terrain executor를 호출한다. 완료 boolean에 더해 해당 구성요소의 신선한 검증 결과와 참조를 요구한다. 시간 경과로 성공하지 않는다. 중단 시 navigation과 시작된 posture/terrain executor 모두 cancel을 시도한다.

OUT: full-body crossing 증거만 통과로 인정한다. attempted_steps, traversed_segments, full_body_crossed를 각각 보존한다. OUT 성공을 모든 구간·미션 성공이나 공식 점수로 승격하지 않는다. 몸체 중심점은 판정 입력으로 사용하지 않는다.

## 시각·관측 경계

공용 `competition.v0.1`, `mission-action.v0.1`, `competition-evidence.v0.1` 및 canonical schema는 수정하지 않았다. `Packet/ComponentStamp/Extras`는 내부 Python sidecar이며 공용 메시지로 주장하지 않는다.

1. ClockBinding은 trusted receiver가 검증한 producer/epoch/clock 관계다. payload가 보내는 `clock_verified` 플래그는 받지 않는다. native에는 synchronized_ros/utc만 허용한다. source_age_s는 해당 동기화 도메인에서 오차 상한까지 포함해 계산한 나이여야 한다. 서로 다른 호스트 monotonic을 빼지 않는다. 시계 검증·오차 측정 자체는 아직 live binding의 책임이다.
2. signal/feet/motion/pose/path/navigation/body/posture/terrain/departure/safety/coverage 각각의 source age와 최초 receiver monotonic receipt를 유지한다. 기준은 `source_age_at_receipt + receiver_elapsed`와 별도의 receiver TTL이다. RouteStatus observation_age_s도 별도로 검사한다.
3. 동일 component sequence의 정확히 같은 재사용은 원래 receipt를 유지한다. 다른 값으로 바꾸면 거부한다. sequence 증가로 동일 source stamp를 새 데이터처럼 세탁할 수도 없다. 전체 envelope duplicate/retired epoch/다른 scope는 캐시를 비우고 전이에 사용하지 않는다.
4. adapter마다 새 receiver session nonce를 생성한다. trusted ingress는 producer와 이 session을 명시적으로 재바인딩해야 한다. 오래된 메시지에 새 nonce/receipt를 붙여 재전송하면 안 된다. 재연결은 현재 action을 INTERRUPTED로 닫으며 새 run identity·epoch·session이 필요하다. 이전 실행 이력을 executable resume 자료로 import하는 경로는 없다.
5. 새 runtime factory는 source/receiver TTL 상한 0.25초와 stop observation gap 0.5초를 구분한다. 이전 저수준 회귀의 synthetic evidence TTL은 0.5초다. `TimingPolicy()`는 native cadence가 미확정이라 실행을 거부한다. `TimingPolicy.synthetic()`는 테스트 전용이다. 운영 값은 센서/온보드 실측과 watchdog 검증 뒤 명시한다. 캐시 polling으로 dwell 시간을 늘리지 않고 첫 유효 수신 시각부터 마지막 샘플의 취득 하한(receipt-source_age)까지 보수적으로 누적한다. HOLD ACK 이전 취득 관측은 제외한다.

최초 base VM에는 별도의 `SignalObservation/StopZoneObservation/RouteStatus` 클래스가 없다. 실제 타입은 `traffic_signals/core.py:StopInput`과 dict 기반 출력이다. `from_vm_stop_input`은 그 shape를 변환하며 scope·epoch·sequence·개별 signal/route age를 보존해야 한다. `approach_ack`를 native SUCCEEDED/cancel ACK로 승격하지 않는다. OpenCV/ROS를 import하지 않는다. 후속에서는 D0의 실제 TrafficLifecycle/ActionEvent 및 C4 signal_fragment exact 제출을 읽고 대조했다. C2 단일 runtime owner와 D0 의미 회귀 벡터를 사용하며 D0의 exit intent를 두 번째 goal sender로 실행하지 않는다. 양쪽 실제 패키지를 import해 조합하는 통합 검사는 C1 담당이며 아직 NOT_RUN이다.

## 기존 계약과의 차이 / live 차단점

- 기존 Navigation goal ID는 16..128 token이고 canonical evidence ID는 hex32다. port는 둘을 분리해 보관하고, 실제 ID가 정확히 일치할 때만 logical ID로 투영한다. 임의 ID를 잘라 넣거나 foreign goal을 cancel하지 않는다.
- 최초 base coordinator에는 취소된 접근 waypoint의 native continuation hook이 없다. C1 r2에는 이미 구현되어 있으며 이번 포트는 그 실제 native_owner/continue_native 계약을 호출한다. fake port에서는 이 경로의 전이를 끝까지 검증하지만 실제 bridge는 `COORDINATOR_CONTINUATION_HOOK_REQUIRED`로 거부한다. 선택 callback을 주입하는 계약만 제공하며 base에 있는 API라고 주장하지 않는다.
- C1 r2 연결에서는 기존 native_owner token/native_barrier/continue_native API를 사용한다. 이전 별도 callback 방식도 보존한다. 일반 after_arrival_confirmation/사용자 token은 거부한다. 성공과 취소 callback은 서로 다른 terminal 증거를 검증하며, 공용 훅의 정확한 입력/잠금/반환값은 WIRING_PROPOSAL에 고정했다. adapter는 API router·canonical 정의·저장·공용 executor를 수정하지 않는다.
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

프로젝트 Python 가상환경과 Ruff 0.6.9를 사용한다. 실물 입력·native Nav2·ROS·실제 모델/영상 replay는 NOT_RUN이다. 테스트는 기존 MissionCoordinator도 사용하지만 navigation과 모든 physical port는 fake다. 최초 검사 기록은 `docs/parallel-review/20261024/C2/REVIEW.md`, 후속 검사 결과와 tested code SHA는 `docs/parallel-review/20261024/C2/FOLLOWUP.md`에 기록한다.

삭제/이동/바이너리 변경은 없다. 롤백 범위는 새 competition_native 패키지·전용 tests·문서뿐이다. 기존 지도·설정·저장소 migration·장비 상태에 영향이 없다. 통합 승인 전 다른 작업 브랜치를 병합하지 않는다.
