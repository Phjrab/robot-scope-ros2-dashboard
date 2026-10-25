# C1 연결 계약 — Round4

최신 명세/결과는 [ROUND4.md](../../parallel-review/20261024/C2/ROUND4.md)다. C1 `85c5b6b85ca85e74503876b075e5ceba92dd4565`는 ROUND3 runtime/first receipt/STOP/계획 대기 후 guard 검사를 이미 채택했다. 아래 runtime 설명은 유지할 계약이며 재적용할 patch가 아니다. 이번 변경은 C4 `9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd`의 추론 설정 digest를 기존 immutable `SignalBinding`에 필수로 고정하는 것뿐이다.

## 실제 C2 public API

| 호출 | 반환/책임 |
|---|---|
| `configure_action(RuntimeConfig(...), RuntimePorts(...), clock=...)` | NativeRuntime. import/구성/snapshot에서 goal/task/timer 없음. policy는 source/receiver <= .25, continuity gap .5를 분리 |
| `runtime.scope` | immutable Scope. 현재 reserved/active generation 확인 |
| `await runtime.start(request_id, approach_pose=...)` | snapshot. 기존 C1 start/effect durable admission 유지 |
| `await runtime.receive(packet)` / `await runtime.tick()` | snapshot. tick은 receipt/sequence/action request를 생성하지 않음 |
| `await runtime.event_ack(event)` | `{accepted, reason, snapshot}`. exact scope/실제 goal ID/request/broker epoch/seq/session/clock 확인 |
| `runtime.continuation_proven(starting=False, completed=False)` | bool. 기존 C1 native owner guard에서 호출. 내부 normalizer/state/constraint 접근 불필요 |
| `runtime.require_dispatch_authorized(starting=False)` | 현재 guard가 false면 ValueError. 기존 awaited preflight의 **끝**에서 검증할 수 있는 함수 |
| `runtime.command_context()` | immutable CommandContext(scope, inputs_fresh, goal_receipt_s, estop, collision). C1의 현재 nav/mission ownership 검사는 별도로 유지 |
| `runtime.snapshot()` | state/scope/실제 goal/stop_requested/pending/내부 request_counts. 읽기 전용이며 항상 live_ready=false |
| `await runtime.stop(request_id)` / `await runtime.cleanup(request_id)` | retire snapshot. C1의 즉시 gate.retire + coordinator.fence_native_stop은 **await 전에** 유지 |

`continuation_proven`은 C2가 실제로 승인한 dwell 종료 frame을 보관하고, 그 원래 receipt/age로 판단한다. C1이 normalizer를 복제해 proof를 만들 필요가 없다. 새 generation HOLD가 실제 consumer의 `ack(request)`에서도 확인되어야 true다. ACK 이벤트만 보냈지만 consumer가 설치 상태를 보고하지 않으면 허용하지 않는다.

순서는 `dwell 증거 → 새 generation HOLD 요청 → EXIT_PREPARE → 설치 ACK → owner guard → await plan → guard 재검사 → exit goal ACK → EXIT_PENDING → RELEASE ACK → 독립 MOVING/departure → DEPARTING`이다. 기존 session의 `phase == EXIT_PENDING` 조건을 단순 치환하지 않는다. C1 guard가 보는 준비 상태는 EXIT_PREPARE이고, C2는 HOLD 미설치/오래된 proof/STOP/소비 gate 폐쇄 시 false를 반환한다. 준비 중 새 RED/불량 independent 관측도 proof를 무효화한다. 존재하지 않는 exit navigation ACK를 만들지 않는다.

## 기존 C1 coordinator를 호출하는 C2 포트

```python
port = CoordinatorNavigationPort(
    coordinator, navigation, mission_id=scope.mission_run_id,
    admission=existing_admission, legs=compiled_legs,
    native_owner=existing_native_token,
)
```

C1 r2의 실제 `start(..., native_owner=...)`, `pause(..., native_owner=...)`, `continue_native(mission_id, admission=..., token=..., previous_visit=..., next_visit_id=..., actual_goal_id=...)`를 호출한다. 성공은 기존 native_barrier를 확인하며 UI confirmation/resume으로 우회하지 않는다. 취소는 exact terminal+발행 cancel ID를 확인한다. C1의 `_operation_lock`, token, external_stop, STOP, pins/compiled visit 검증은 그대로다. 이전 C2 callback 계약도 유지하지만 새 metadata barrier를 C1에 필수로 요구하지 않는다.

C1 session은 `bind_native_owner(..., guard=session._continuation_proven)`을 유지하며 현재 함수는 `not session.closed and runtime.continuation_proven(...)`을 호출한다. `MissionCoordinator._dispatch_current_locked`의 awaited preflight 뒤 guard 재검사도 최신 C1에 있다. C2의 기존 pinned r2 교차 테스트는 preflight callback 끝에 `runtime.require_dispatch_authorized(...)`를 넣어 이 계약을 보존한다. 이 역사적 harness를 최신 C1 미완료 항목으로 해석하지 않는다.

## C4 실제 projection + C2 join

trusted owner가 관측 수신 전에 선택·검토한 추론 설정의 digest를 필수로 전달한다. 실제 변경 지점은 기존 `SignalBinding(...)` 생성 호출의 keyword 한 개다. C1 현재 `tests/competition_integration/harness.py::SoftwareHarness.asyncSetUp`에도 같은 인자가 필요하다. observation의 digest를 읽어 expected 값을 만드는 fallback은 금지한다.

```python
signal_binding = SignalBinding(
    producer_id=trusted_source_id, epoch=trusted_epoch,
    source_clock=verified_source_clock, config_hash=approved_traffic_config_hash,
    binding_id=approved_binding_id, model_sha256=approved_model_sha256,
    signal_id=approved_signal_id, crossing_id=approved_crossing_id,
    receiver_clock_id=session.runtime.config.receiver_clock_id,
    inference_settings_sha256=approved_inference_settings_sha256,
)
# Before the first observation, in the existing trusted composition code:
session.ingress.signal_binding = signal_binding
```

digest는 소문자 64자리 hex이며 누락·malformed·상이한 설정은 미션 결합을 거부한다. `observation_mode="mission"`도 명시되어야 한다. 설정/epoch를 바꾸려면 owner가 기존 실행을 종료하고 새 binding/runtime으로 검토해야 한다. 제자리 기대값 갱신이나 오래된 GREEN 재사용은 허용하지 않는다. 진단 observation/bbox/image는 수정하지 않으므로 별도 표시 경로를 유지할 수 있다. C1의 기존 ingress 오류 시 `gate.retire()`도 유지한다.

```python
from robot_dashboard.competition_traffic.projection import signal_fragment
from robot_dashboard.mission_routes.competition_native.fragments import project_signal

packet = project_signal(
    independent_packet, observation=sample.observation, projection=signal_fragment,
    binding=signal_binding, now_s=local_now, receiver_clock_id=verified_local_clock_id,
    first_received_s=sample.frame.received_s,
    source_age_at_first_receipt_s=sample.frame.source_age_s,
    processed_s=sample.observation.context["processed_s"],
)
```

별도 시각 인자는 생략할 수 있으나 제공하면 context와 정확히 같아야 한다. 첫 age는 context.source_age_at_first_receipt_s를 직접 사용한다. legacy source_age_s/receiver_age_s가 함께 있으면 완료시각 기준 계산과 일치해야 한다. context에 명시된 first/age/processed/identity_verified가 없으면 이전 형식으로 역산해 통과시키지 않는다. source/model/config/binding/epoch/sequence 검증을 유지한다. remote host monotonic 전달은 이 함수의 지원 범위가 아니다.

C1의 fixture-clock 전용 offline ingress 분기는 별도 명시적 synthetic 경로로 유지할 수 있다. 이 production-shaped C4 projection은 fixture clock을 거부한다. 관측 producer/물리 STOP/최종 actuator 검증이 없으므로 live motion은 활성화하지 않는다. 같은 JPEG라도 검증된 source seq와 stamp가 모두 전진하면 새 frame이며, polling이나 seq만 바꾼 동일 stamp는 새 frame이 아니다.
