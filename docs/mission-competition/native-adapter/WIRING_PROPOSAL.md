# C1 연결 계약 — C2 후속 제출

C2 구현 기준은 `efc2df6bfaad8f0032fee758b12e250435ffc71c`이며 공용 코드 기준은 그 조상 `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`다. 후속 작업 시작에 원격 main `3c09bca3f0f5cbe3d22d1206332118a5cb044c85`를 읽기 전용으로 확인했다. main/C1/D0/C4를 merge, cherry-pick, 파일 복사하지 않았다. 아래 **C2 callable은 구현**, **공용 owner/consumer 훅은 C1 구현 요구**다. 이 문서는 이전의 `resume(confirmation_token=...)` 제안을 대체한다.

## 구현된 구성과 owner-loop API

모듈: `robot_dashboard.mission_routes.competition_native.runtime`.

```python
runtime = configure_action(
    RuntimeConfig(
        action=compiled_action, scope=scope,
        policy=TimingPolicy(.25, .25, .5, .25),
        observation_bindings=verified_component_bindings,
        event_binding=EventBinding("existing-owner-event-broker", event_epoch),
        receiver_clock_id=local_clock_identity,
        activation=explicit_offline_activation,
    ),
    RuntimePorts(navigation_port, constraint_port, posture_port, terrain_port),
    clock=owner_monotonic_clock,
)
```

`RuntimeConfig`/`RuntimePorts`는 dataclass다. `scope`는 `Scope(owner_id, mission_run_id, step_id, config_hash, goal_id, goal_generation)`이며 실제 Nav goal ID와 logical hex32 goal ID는 다르다. bindings는 `envelope`와 component별 `ClockBinding(producer_id, epoch, source_clock, relation_verified=True)`의 mapping이다. posture/terrain port는 해당 행동에서만 필수다. 구성/import/snapshot은 clock/port를 호출하거나 task/timer/goal을 생성하지 않는다.

| 실제 callable | 입력 / 반환값 | 기존 owner의 호출 책임 |
|---|---|---|
| `configure_action(config, ports, *, clock)` | `NativeRuntime` | 명시적 admission 시 한 action 인스턴스 생성. 기존 durable request ledger와 pins 검증 후 호출 |
| `await runtime.start(request_id, *, approach_pose)` | snapshot dict | start intent를 먼저 기록. 같은 request/payload 재호출은 중복 goal 없음; 결과 불확실한 dispatch 재시도 금지 |
| `await runtime.receive(packet)` | snapshot dict | trusted joiner가 만든 `Packet(evidence, components, extras, receiver_session_id)` 전달. payload에서 scope/epoch/session을 임의 승격하지 않음 |
| `await runtime.event_ack(event)` | `{accepted: bool, reason: str, snapshot: dict}` | 아래의 정확한 이벤트 상관관계 검증. duplicate는 `accepted=False`, `DUPLICATE_ACK`이며 효과/TTL 갱신 없음 |
| `await runtime.tick()` | snapshot dict | 기존 loop의 watchdog 호출. 새 receipt/sequence를 만들지 않음. 최초 관측 전/이후 safety stale이면 닫힘 |
| `runtime.snapshot()` | dict | 읽기 전용. `state`, `scope`, `actual_goal_id`, receiver clock/session, `pending` request IDs/시각/constraint, `live_ready=False`, execution mode 포함 |
| `await runtime.stop(request_id)` | snapshot dict | lock 대기 전에 STOP intent와 HOLD를 먼저 요청하고 기존 port의 정확한 goal 취소 |
| `await runtime.cleanup(request_id)` | snapshot dict | shutdown용 retire. INTERRUPTED 상태를 실행 가능 상태로 복원하지 않음 |
| `await runtime.prepare_movement(request_id)` | snapshot dict | PARK 완료 후 STAND 요청. 관측 검증 전 이동 허가 없음 |

포트/clock 예외는 HOLD/cancel 시도 후 다시 발생할 수 있다. C1은 예외를 기존 owner의 실패 상태에 기록해야 한다. `event_ack`의 상관관계/시각 오류는 FAILED snapshot을 반환한다. `stop/cleanup`도 실제 장비 STOP을 보증하지 않으며 `CLEANUP_UNCONFIRMED`는 그대로 노출한다.

`Activation` 문자열/flags는 실측 검증이 아니다. 이 제출의 factory는 명시적 synthetic 설정으로 오프라인 구성 검사를 허용하지만 non-synthetic `start`는 `LIVE_FINAL_CONSUMER_BINDING_UNCONNECTED`로 거부한다. C1이 실제 consumer/provider와 cadence를 통합 검증하기 전 live gate를 열면 안 된다. 기존 저수준 adapter를 직접 호출해 이 제한을 우회하여 등록하지 않는다.

source/receiver 유효성 상한은 factory에서 각각 0.25초다. stop sample gap 0.5초는 별도 설정이다. 가상 clock 테스트 cadence를 실측 capability로 등록하지 않는다. 기존 `TimingPolicy.synthetic()`의 0.5초 TTL은 이전 저수준 회귀 전용이다.

## 실제 이벤트 타입과 ACK 경계

`contracts.ActionEvent(kind, scope, actual_goal_id, request_id, producer_id, epoch, sequence, first_received_s, source_age_s, receiver_clock_id, receiver_session_id, status, cancel_ack=False)`.

- producer는 신뢰된 기존 owner event broker 하나다. 센서 publisher의 자기 주장이나 HTTP 입력으로 event를 생성하지 않는다. sequence는 종류별이 아닌 **broker epoch 전체**에서 증가한다. session은 현재 runtime snapshot의 nonce이며 새 세션에 이전 event를 재표기하지 않는다.
- `first_received_s`는 같은 receiver clock의 최초 ACK 수신 시각, source age는 그 시점 기준이다. 현재 유효 age는 `source_age_s + now - first_received_s`; 0.25초 이하이고 취득 하한 `first_received_s - source_age_s`가 요청 시각보다 뒤여야 한다. 중복 event 기록은 최대 128개이며 새 action 필요 상태를 명시한다.
- `APPROACH_TERMINAL`: 현재 실제 approach ID, status `SUCCEEDED`/`FAILED`이면 goal request ID, `CANCELED`이면 cancel request ID와 `cancel_ack=True`. 취소 요청의 ACK와 nav terminal 확인을 혼동하지 않는다. `cancel_ack=False`는 대기이며 HOLD/dwell을 시작하지 않는다.
- `HOLD_ACK`/`RELEASE_ACK`: 현재 `ConstraintRequest`의 exact scope/request/mode, status `ACKNOWLEDGED`. broker는 실제 최종 consumer 설치 receipt를 확인한 뒤 전달한다. 새 generation HOLD 중 아직 exit goal이 없으면 `actual_goal_id=""`; 그 외에는 snapshot의 실제 goal ID와 같아야 한다.
- `EXIT_ACK`: 현재 exit 실제 ID/request, status `ACTIVE`. `GoalReceipt(..., acknowledged=False)`는 제출/접수만 된 상태다. coordinator port는 pending을 ACTIVE ACK로 바꾸지 않는다.
- `GoalReceipt(..., acknowledged=True)` 및 포트에서 반환한 `ConstraintAck`는 이미 **정확한 수신 ACK**일 때만 사용한다. adapter는 그 반환 시점을 receiver barrier로 기록한다. poll ACK를 다시 읽어 barrier 시각을 갱신하지 않는다.

새 generation HOLD의 ACK가 지연되면 `EXIT_PREPARE`에서 기다린다. 기존 owner의 tick/event 경로로 확인하고, 0.25초 안에 확인되지 않으면 종료한다. HOLD 설치 ACK가 있어도 independent feet/STOP 샘플이 없거나 샘플 취득 시각이 ACK 이전이면 dwell 0이다. 움직임/출발 샘플은 exit ACK와 RELEASE ACK보다 뒤에 취득되어야 한다.

## C1 coordinator 훅 — 성공과 취소를 분리

C2가 사용하는 실제 constructor:

```python
CoordinatorNavigationPort(
    existing_coordinator, existing_navigation,
    mission_id=scope.mission_run_id, admission=existing_managed_admission,
    legs={(scope.step_id, "approach"): LegBinding(approach_visit, pose_tuple),
          (scope.step_id, "exit"): LegBinding(exit_visit, exit_pose_tuple)},
    successful_approach_continuation=continue_native_success,
    canceled_approach_continuation=continue_native_canceled,
)
```

C1이 기존 service registry에 admission/pins와 초기 Scope 및 두 compiled visit을 명시적으로 등록한 뒤 `runtime.start`를 호출한다. C2는 새 MissionCoordinator나 owner를 만들지 않는다. 기존 shared coordination lock identity와 `_managed_admission` identity가 정확히 같아야 한다.

C1은 기존 `_finish_arrival`의 자동 다음 waypoint 전이 전에 다음 **별도 native barrier**를 설치해야 한다. 취소 경로는 정확한 nav terminal 확인 후 같은 shape에 `CANCELED`를 기록한다. 실제 nav 취소와 action 완료 여부는 별도 사실로 유지한다.

```python
mission = {
    # existing mission snapshot fields remain required
    "state": "paused", "phase": "native_action_barrier",
    "native_barrier": {
        "scope": vars(previous_scope),
        "actual_goal_id": exact_approach_nav_id,
        "terminal_status": "SUCCEEDED",  # or CANCELED, never interchangeable
        "token": opaque_single_use_native_token,
    },
    # id, ownership_active, current_index, current_waypoint, waypoints, ...
}
```

일반 `after_arrival_confirmation`과 사용자 confirmation token은 이 barrier가 아니다. C2는 이 경우 `NATIVE_BARRIER_REQUIRED:COORDINATOR_CONTINUATION_HOOK_REQUIRED`로 거부한다. `resume`/`skip`으로 대체하지 않는다.

C1이 구현할 두 callback의 정확한 시그니처/반환값:

```python
async def continue_native_success(*, request: ContinuationRequest, admission): ...
async def continue_native_canceled(*, request: ContinuationRequest, admission): ...
# Return {"mission": coordinator_snapshot_after_dispatch}
```

`ContinuationRequest`의 실제 필드:

- `authorization: ExitAuthorization(previous_scope, next_scope, hold_request, hold_ack)`
- `actual_approach_goal_id`, `next_visit_id`, `terminal_status`
- `native_barrier_token`, `cancel_request_id` (성공은 None, 취소는 정확한 발행 ID)
- `request_id` (exit dispatch intent의 idempotency key)

C2 `prepare_exit(authorization)`는 새 goal ID와 이전+1 generation, 동일 owner/run/step/config, 새 generation HOLD ACK를 확인한 뒤 callback에 전달한다. callback은 **기존 coordinator `_operation_lock` 안에서** 다음을 다시 검증한다. C2에서 읽은 snapshot만 믿으면 TOCTOU가 생긴다.

1. 현재 managed admission, active mission/run, immutable pins, 두 compiled visit/pose, previous scope 및 실제 approach ID가 일치한다. 성공 callback은 SUCCEEDED, 취소 callback은 exact cancel terminal 및 cancel request를 각각 확인한다.
2. 현재 native barrier token은 사용되지 않았고 같은 terminal/scope에 속한다. UI confirmation token은 거부한다. next visit은 정확한 compiled successor다.
3. final consumer가 **지금도** 새 scope의 동일 HOLD request/sequence를 설치한 상태인지 확인한다. snapshot에 저장된 ACK만으로 허가하지 않는다. C2 registry의 action postcondition/새로운 GREEN 등도 재검증한다. C1이 임의 HTTP action에서 `ContinuationRequest`를 만들어 호출하게 하지 않는다.
4. STOP intent/종료/lease 해제/불확실한 cancel 또는 HOLD가 있으면 거부한다. 기존 `_dispatch_current_locked`와 monitor를 사용해 딱 한 번 dispatch한다. 중복 key에 같은 결과를 반환하고 payload 변경은 거부한다. index만 증가하거나 `skip`으로 우회하지 않는다.
5. 반환 mission은 `ownership_active=True`, `current_waypoint.visit_id=next_visit_id`, 정확한 `goal_id`를 가진다. `navigation.view().goal`도 동일 ID의 pending/active여야 한다. C2는 이 결과를 다시 확인한다. ambiguous 결과의 재발행은 없다.

C1 통합 회귀: lock 대기 중 token/owner/STOP 변경; 일반 UI token 거부; 성공·취소 ACK 교차 거부; 새 generation HOLD의 오래된 ACK 거부; 중복 request의 단일 goal; 취소 terminal 지연 동안 owner 유지; 잘못된 실제 ID의 cancel 금지. C2는 실제 base coordinator의 admission/cancel/UI barrier 거부와 가짜 callback 경계까지만 검증했다.

## C1 최종 consumer 및 기존 loop 훅

`authority.FinalConsumerConstraintPort(consumer_id=..., install=...)`는 ACK 연결부이며 controller가 아니다.

```python
async def install(request: ConstraintRequest) -> ConsumerReceipt | None:
    # C1: atomically install at the EXISTING final command consumer.
    # Enqueued-only => None. Installed => exact ConsumerReceipt.
    ...

port.acknowledge(ConsumerReceipt(consumer_id, exact_request, installed=True))
# Used for asynchronous consumer receipts; port.ack(request) is read-only.
```

`ConstraintRequest(scope, request_id, mode, reason, command_ttl_s, sequence)`를 그대로 전달한다. `ConsumerReceipt`는 exact request 전체, consumer ID, 설치 여부를 포함한다. wrapper는 이전 generation/sequence/late receipt를 거부하지만 **실제 consumer 내부의 atomic fencing을 대체하지 않는다**. await 후 늦게 도착한 RELEASE가 새 HOLD를 설치 단계에서 덮어쓸 수 없어야 한다. 미확인 ACK/누락 owner는 HOLD; HOLD는 만료되어 열리지 않는다. command/goal은 해당 generation의 0.25초 이내 새 입력이어야 하고 RELEASE 이전 입력은 재생하지 않는다. E-stop/충돌 > 모든 owner HOLD > terrain caps > tracking 순서를 기존 마지막 소비 지점 하나에서 적용한다. `CommandBoundary`는 이 규칙의 pure reference이고 속도 publisher가 아니다.

C1 service/runtime 연결 위치는 기존 `MissionRoutes._transaction/create_run/action/preflight_dispatch/require_run_context`, coordinator owner loop, `ControlManager.tick` 또는 실제 navigation final consumer, `MissionRoutes.close/close_mission_routes`다. native registry의 인스턴스를 기존 loop가 구동하며 status 조회에서 runtime을 생성하지 않는다. `receive/event_ack/tick`은 owner가 순서대로 await한다. STOP은 pending port IO 중에도 즉시 별도 intent로 전달할 수 있다. 최종 consumer watchdog은 adapter lock/IO에 의존하지 않는다. 종료 시 native cleanup을 await하고 기존 coordinator cleanup도 유지한다.

`EXIT_PREPARE`의 HOLD 대기 외에는 새 generation으로 바뀐 뒤 최초의 신선한 관측을 공급하기 전에 무관한 tick을 넣으면 안전하게 실패한다. C1의 queue/loop 순서는 실제로 검증해야 한다. snapshot을 재시작 실행 자료로 복원하거나 이전 RELEASE를 재적용하지 않는다. 실제 provider/consumer/시계/cadence와 ROS/장비 검증은 이 제출에서 미연결이다.
