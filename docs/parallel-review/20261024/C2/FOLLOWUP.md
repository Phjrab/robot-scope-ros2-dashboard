# C2 후속 — callable runtime와 교차 계약

브랜치: `review/20261024-c2-mission-adapter`.
이전 검토 HEAD `efc2df6bfaad8f0032fee758b12e250435ffc71c`를 보존해 이어서 작업했다. 실제 구현 조상은 `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`다. 시작에 확인한 원격 main은 `3c09bca3f0f5cbe3d22d1206332118a5cb044c85`; 안내문의 `2a92fd781af09b8e5fc1b083977a73e82e6668ed` 이후 변경을 읽기 전용 확인했으며 되돌리거나 합치지 않았다. 제출 전 원격 main은 `e29808eb3572abcedc2fec0a769593c43568c043`으로 이동한 것을 재확인했다. 해당 main과의 통합 검증은 수행하지 않았다. main에는 C2 변경을 push하지 않았다. 독립 clone에서 C2 패키지/전용 테스트/문서만 수정했다.

검증 대상 코드 커밋: `e3c2ac555a3c83df3338df2c19b57e4fac0a92df`.
문서를 포함한 최종 제출 HEAD는 마지막 응답에서 별도로 보고한다. 최초 `REVIEW.md`와 `VALIDATION.json`은 원래 65개 회귀의 과거 기록으로 보존했다.

## 이전 대비 바뀐 동작

| 이전 검토 상태 | 이번 구현 | 회귀 증거 |
|---|---|---|
| adapter 내부 메서드만 있고 owner-loop 계약 미완성 | `RuntimeConfig/RuntimePorts/configure_action`, start/receive/event_ack/tick/snapshot/stop/cleanup | 생성/status에 port 호출 없음, 참조 문자열이 있어도 live start 거부 |
| 성공 approach가 일반 UI confirmation을 사용 | 별도 native barrier/token 및 성공/취소 callback 분리 | 실제 base coordinator의 UI token 거부, lock 안 callback 전달, 중복 goal 없음 |
| cancel 후 continuation callback 입력 불명확 | `ExitAuthorization` + `ContinuationRequest`의 exact scope/terminal/request/HOLD와 반환 snapshot | delayed/foreign/duplicate ACK, 성공·취소 다른 훅, old cancel 차단 |
| immediate port 결과와 최종 consumer 설치 ACK 사이 경계 미정 | `FinalConsumerConstraintPort`/`ConsumerReceipt`, enqueue는 None, 뒤늦은 설치 receipt 별도 수신 | 늦은 RELEASE가 새 HOLD/generation을 덮어쓰지 못함 |
| 새 generation HOLD를 즉시 확인해야 함 | `EXIT_PREPARE`에서 ACK 대기, tick에서 dispatch, 미확인 timeout 종료 | ACK 이전 exit goal 없음, 확인 후 한 번만 생성 |
| receipt만으로 dwell, 출발 관측의 취득시각 불충분 | HOLD 이후 source-supported stop 구간, exit/RELEASE ACK 이후 취득 MOVING만 latch | walltime gap, pre-ACK/foreign goal MOVING, RED/UNKNOWN/stale 전후 분기 |
| C4 signal_fragment/sidecar 실제 shape 미대조 | `join_signal`이 signal 필드만 결합하고 original first arrival/0.25s cap 보존 | 처리 age 한 번, polling TTL 연장 없음, 색이 feet/STOP/path를 만들지 않음 |
| cleanup 시 ACK 누락 진단 불충분 | HOLD ACK 누락도 `CLEANUP_UNCONFIRMED:HOLD_ACK_UNCONFIRMED` | INTERRUPTED 유지, 자동 재시작 없음; clock 실패에도 HOLD/cancel 시도 |

신규 파일: `competition_native/runtime.py`, `competition_native/fragments.py`, `tests/competition_native/test_runtime_contract.py`, `tests/competition_native/fixtures/runtime_contract.json`, 이 문서. 기존 C2의 `__init__/contracts/adapter/coordinator/authority/observations/state`와 전용 `test_actions/test_coordinator`, `HANDOFF/WIRING_PROPOSAL`만 수정했다. 공용 service/coordinator/runtime/API/CI, 다른 역할 소스 수정과 파일 삭제/이동은 없다.

## C1이 사용할 계약

[WIRING_PROPOSAL](../../../mission-competition/native-adapter/WIRING_PROPOSAL.md)에 실제 메서드/타입, error/return, 기존 owner loop 호출 순서, 별도 native barrier shape, callback의 owner lock 안 재검증, final consumer 설치 ACK를 명시했다.

- `configure_action(RuntimeConfig(...), RuntimePorts(...), clock=...) -> NativeRuntime`. 모든 진행은 명시적인 async 호출이다. import/snapshot이 새로운 FSM 실행자/goal/monitor를 만들지 않는다.
- `event_ack(ActionEvent)`는 `{accepted, reason, snapshot}`. exact scope/실제 goal ID/request/receiver session/clock/broker epoch/sequence/age를 검사한다. HOLD ACK는 물리 정지 증거가 아니다.
- coordinator 두 callback은 각각 `async (*, request: ContinuationRequest, admission) -> {"mission": snapshot}`. **기존** `_operation_lock` 안에서 token/owner/pins/terminal/STOP/현재 consumer HOLD/postcondition을 다시 확인한다. C2는 외부 `skip/resume`을 사용하지 않는다.
- `FinalConsumerConstraintPort(consumer_id=..., install=...)`는 ACK 경계만 구현한다. C1의 `install(ConstraintRequest)`가 마지막 실제 소비 지점에 atomic fence를 설치한 뒤 `ConsumerReceipt`를 반환하거나 나중에 `acknowledge`한다. consumer 내부 구현과 실제 velocity publisher는 여전히 미연결이다.
- factory snapshot은 `live_ready=false`. explicit synthetic 설정은 오프라인 실행을 허용한다. capability 참조 문자열만으로 native 등록을 허용하지 않는다. 실측 cadence/provider 미연결은 live 활성화 차단점이며 합성 조합 검사를 막는 조건이 아니다.

## exact D0/C4 대응표

읽기 전용으로 확인한 원격 제출:

- D0 [`6403aab3afef96efa778b5265afd7ce5b351265c`](https://github.com/Phjrab/robot-scope-ros2-dashboard/tree/6403aab3afef96efa778b5265afd7ce5b351265c), `review/20261024-d0-vm-offline`: `traffic_signals/lifecycle.py`의 **TrafficLifecycle/ActionEvent**, `traffic_signals/core.py`의 **StopInput**, `integration/adapter.py`의 strict source/epoch/sequence와 lifecycle constraint adapter.
- C4 [`e2e9c5087767f3953d715c61e76388e4769d34b4`](https://github.com/Phjrab/robot-scope-ros2-dashboard/tree/e2e9c5087767f3953d715c61e76388e4769d34b4), `review/20261024-c4-traffic-replay`: `robot_dashboard/competition_traffic/pipeline.py`의 **Observation(signal, context, mask)**, `projection.py`의 **signal_fragment**. 전체 Evidence가 아니다.

| 항목 | D0 exact 계약 | C4 exact 계약 | C2/C1 결합 규칙 |
|---|---|---|---|
| source 시각/domain | strict adapter source stamp/clock 검증; ActionEvent는 age+receipt 사용 | context `source_stamp_ns`, `source_clock`, `clock_verified` | component별 `ClockBinding`을 trusted ingress에서 고정. remote monotonic끼리 빼지 않음 |
| source age 기준 | ActionEvent.source_age_s는 event receipt 시점; StopInput.signal_age_s/observation_age_s는 StopInput.receipt_s 시점 | context.source_age_s는 **처리 완료 시점**의 age. 추론/처리 residence 이미 포함 | C4 initial_age = context.source_age_s - context.receiver_age_s. 이후 now-first_received를 딱 한 번 추가 |
| 최초 receiver 도착 | ActionEvent.receipt_s, StopInput.receipt_s | 원래 `Frame.received_s`; context.receiver_age_s = 완료시각 - Frame.received_s | `ComponentStamp.first_received_s`, `receiver_clock_id`. C4/C2가 같은 clock일 때만 join_signal 허용; remote 전달은 별도 로컬 clock/age 재검증 필요 |
| 완료 시각/fragment projection | event 취득하한 receipt-age > 요청시각 | `signal_fragment(obs, now_s, received_s)`는 context age에 now-received를 추가 | `processed_s = first_received_s + context.receiver_age_s`. C4 projection의 received_s에는 이 완료시각을 사용; C2 stamp의 first_received는 원래 도착시각 유지. 둘을 혼동하면 처리시간 이중 계산 |
| epoch/seq | 이벤트/관측 각 epoch/sequence. 재시작 lifecycle 닫힘 | context.producer_epoch/sequence/source_stamp_ns | source binding과 broker binding 별도. 같은 component 재사용은 원래 receipt 보존; seq만 증가시킨 동일 source stamp 거부 |
| owner/run/step | ActionEvent.run_id/step_id, lifecycle session; constraint owner | 신호 fragment에 mission 소유권 없음 | C1 admitted `Scope`를 independent packet에 결합. C4 source가 run/owner를 결정하지 않음 |
| goal/generation | ActionEvent.goal_id/goal_generation; observe의 observed_goal_id/observed_goal_generation가 exit tuple과 일치해야 함 | 없음 | 실제 nav ID는 CoordinatorNavigationPort가 exact 확인 후 logical ID에 매핑. source component scope와 broker event 실제 ID가 모두 일치해야 함. D0 StopInput.generation만으로 실제 exit goal ACK를 만들지 않음 |
| signal/crossing | StopInput.signal_id/crossing_id/visit_id/zone_id | signal.signal_id/crossing_id + context.binding_id/association_verified | SignalBinding이 source/epoch/config/model/binding/signal/crossing을 고정. C4 config_hash와 mission config_hash는 별개 |
| 수신/source TTL | TrafficLifecycle 기본 각각 .25s | receipt_ttl_s=.25, projection age 상한 .25 | 새 runtime 각각 .25 이하; C4 component 자체 validity_s=.25. fresh = age_at_first+residence AND receipt TTL |
| stop gap / duration | stop_gap_s=.5, source-supported stop 구간 2초 | stop 증거 없음; stability_s=.4는 색 안정성 | .5는 sample 연속성, .25는 freshness. 둘을 합치지 않음. HOLD 이후 두 앞발+STOP의 첫 receipt~마지막 취득하한만 누적 |
| ACK vs physical facts | APPROACH_TERMINAL / HOLD_ACK / EXIT_ACK 구분 | feet/physical_stop/posture/path_clear=None, departure_authorized=False | C4 색으로 feet/STOP/path/자세/출발을 채우지 않음. RELEASE ACK만으로 departure latch하지 않음 |
| 반복 조회/재시작 | event duplicate/retired epoch 거부; 새 session 필요 | current_state는 새 stamp/seq를 만들지 않음 | tick은 read-only cache 평가. old RELEASE/nonce/pins/epoch를 새 실행에 복원하지 않음 |

시각 예: first=10.00, processing 완료=10.08, C4 age=.10이면 initial_age=.02다. now=10.15에서 age=.17로 fresh, now=10.240001에서 .260001로 stale이다. 같은 signal을 다른 envelope로 polling해도 first=10.00은 유지된다. path의 별도 observation_age_s도 first-receipt 기준으로 residence를 더하며 stamp age와는 max를 사용한다.

C2를 **유일한 runtime 행동 소유자**로 유지한다. D0 TrafficLifecycle의 terminal/HOLD/exit ACK/취득시각 의미를 이 회귀에 반영하되, D0 lifecycle/constraint adapter의 exit intent를 C2와 동시에 실행하지 않는다. C4에는 색 관측만 맡긴다. 기존 `from_vm_stop_input`은 최초 base의 필드 변환 helper이지 최신 TrafficLifecycle를 통째로 연결한 wrapper가 아니다. 실제 D0/C4 패키지를 C1 통합 clone에서 import하여 clock/event/source mapping을 조합 검증하는 작업은 C1 담당이며 이 제출에서는 NOT_RUN이다.

## 작은 재현 입력 및 검증

`tests/competition_native/fixtures/runtime_contract.json`은 17개의 합성 입력/expected phase/departed 및 예상 port 호출을 담는다. 원본 영상/모델/로봇 로그가 아니다. 성공 approach → HOLD → 실제 샘플 2초 → 새 generation HOLD → exit → RELEASE → 출발 확인 → 출발 후 RED → 완료를 가상 clock으로 재생한다.

```bash
python -m unittest tests.competition_native.test_runtime_contract.RuntimeContractTests.test_reviewable_synthetic_trace -v
python -m unittest discover -s tests/competition_native -t . -v
python -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
ruff check --no-cache robot_dashboard scripts tests/competition_native
python -m mypy --config-file mypy.ini
python scripts/check_repository_secrets.py
```

환경: Linux, Python 3.12.3 + Pydantic 2.13.4(기존 프로젝트 venv), Node v24.19.0(기존 bundled runtime), Ruff 0.6.9 및 기존 quality venv의 mypy. 새 의존성 설치 없음. 절대 실행 경로는 로컬 검증 환경에만 해당하므로 재현 명령은 실행파일 이름으로 표기했다.

| 검사 | 실제 결과 |
|---|---|
| C2 전용 unittest | PASS 83/83 (기존 65 + 새 회귀 18), 0.357초 |
| 전체 Python unittest | OK: 2,774개 실행, 2,772 PASS / 2 SKIP, 98.249초 |
| JavaScript 단위 회귀 | PASS 660/660, 약 1.475초 |
| JavaScript syntax | PASS 104 modules |
| Ruff 0.6.9 | PASS; robot_dashboard/scripts 및 C2 tests |
| mypy 설정 범위 | PASS 4 source files; native 패키지 전체 type 검증으로 주장하지 않음 |
| tracked-source secrets / git diff whitespace | PASS |

두 SKIP: optional rosbags backend 미설치, `PCD_EDIT_NODE` 미설정에 따른 기존 PCD JS parity 선택 검사. 테스트가 출력한 BLOCKED/COMPUTED_DECLARED_INPUTS JSON은 기존 fixture의 예상 진단 출력이며 suite 실패가 아니다. 검사 후 source/test 변경 없이 위 코드 커밋을 만들었다. 이후 이 제출 문서만 별도 커밋한다.

최초 샌드박스 내 coordinator 회귀는 asyncio executor 종료가 멈춰 완료 판정하지 않았다. 동일한 장비 없는 로컬 테스트를 승인된 sandbox escalation 환경에서 실행하여 확인했다. 테스트 작성 중 polling 시각을 10.240001에서 10.24로 되돌린 1건은 CLOCK_ROLLBACK 검출이 올바르게 작동한 테스트 오류였고 시각을 고쳐 통과했다. 테스트 삭제/완화로 통과시키지 않았다.

NOT_RUN: native Nav2/ROS simulation, 실제 모델/영상 replay, 실제 robot/camera/SSH/ARM/goal/velocity/posture, actual final consumer install, 공용 C1 hook의 구현·D0/C4 실제 import 조합, 로컬 browser E2E. Node 단위/syntax 통과는 browser E2E 통과가 아니다. push workflow는 hardware-free CI만 확인했으며 원격 CI 상태는 제출 HEAD와 함께 별도로 조회한다.

## 남은 통합과 롤백 범위

남은 일은 C1의 공용 owner registry/별도 native barrier·성공/취소 atomic continuation, 실제 최종 consumer/ACK/watchdog, trusted observation joiner, backend tick/events/shutdown 연결 및 실측 cadence 검증이다. fake callback 테스트는 실제 공용 훅 구현을 증명하지 않는다. C2만으로 live-ready를 선언하지 않는다. D0/C4와 source/epoch/clock/projection 결합의 실제 compatibility는 아직 통합 검증 전이다.

이번 수정은 C2 새 패키지/전용 테스트/문서 안에 한정돼 다른 역할과 예상 파일 충돌이 없다. 검토 승인 후 C1은 public hook → source/event mapping → one-owner action/consumer 통합 → 합성 trace 및 실제 package 통합 → live qualification 순서로 진행할 수 있다. 등록 전에는 저장된 map/mission migration이나 장비 상태 변화가 없다. 롤백도 이 C2 변경 범위에 한정된다. C1 완료를 기다리는 monitor나 자동 재시작 작업은 생성하지 않았다.
