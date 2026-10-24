# C1용 연결 제안 — 적용하지 않은 변경

이 문서는 base `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`의 정확한 호출 지점을 기준으로 한다. C1 브랜치는 읽거나 합치지 않았다. 아래 내용은 후속 검토·승인이 필요한 제안이며 production을 활성화하는 patch가 아니다.

## 최소 공용 wiring 제안 diff

아래 additive 함수는 등록 factory를 명시적으로 받을 때만 평가하며, 기존 `configure_mission_routes`나 app startup에서 호출하지 않는다. C1이 service-owned native registry를 구현한 뒤에만 사용한다.

```diff
--- a/robot_dashboard/mission_routes/wiring.py
+++ b/robot_dashboard/mission_routes/wiring.py
@@
+def configure_native_action_factory(runtime, *, factory=None, binding_review=None):
+    """Explicit future integration only; no factory invocation on status reads."""
+    if factory is None or binding_review is None:
+        return False
+    service = runtime.mission_routes
+    if service is None or runtime.mission is None or runtime.navigation is None:
+        return False
+    if runtime.mission._coordination_lock is not runtime.navigation.coordination_lock:
+        raise MissionConflict("EXACT_SHARED_COORDINATION_LOCK_REQUIRED")
+    # Registration only; factory receives existing owners/admission at explicit
+    # run admission, never constructs a MissionCoordinator or command publisher.
+    service.native_action_factory = factory
+    service.native_binding_review = binding_review
+    return True
```

이 diff만으로 실행 가능해지지 않는다. 연결되지 않은 factory 속성을 임의로 발견해서 활성화하는 경로를 추가하면 안 된다.

## 실제 메서드 계약과 후속 연결 위치

| 기준 파일/메서드 | 실제 계약 | C1의 연결 책임 |
|---|---|---|
| `mission_routes/service.py:MissionRoutes._transaction` | request-id + payload ledger, safety 예외 | 기존 durable ledger에서 native start/stop 요청을 감싸기. adapter 메모리 ledger는 보조이며 restart resume용이 아님 |
| `MissionRoutes.create_run` | coordinator.create에 waypoint와 context_revision 전달 | canonical definition을 변경하지 않고 내부 approach/exit LegBinding과 visit ID 매핑 생성. 새 step/generation에 정확한 pins 고정 |
| `MissionRoutes.action` | 기존 `_admission`으로 start/resume 호출 | fixture 흐름과 native adapter를 별도 분기. qualifier 없는 native는 계속 거부. native 진행 중 외부 resume/retry/skip은 internal gate를 우회하지 않도록 거부 |
| `MissionRoutes.preflight_dispatch` / `require_run_context` | exact map/context/planner 검증 | adapter에 위임해도 기존 검증을 생략하지 않음 |
| `application/mission_coordinator.py:_claim` | shared coordination lock으로 하나의 active mission 확보 | 기존 owner 재사용. adapter 바깥에서 같은 lock을 다시 잡으면 deadlock이므로 금지 |
| `_dispatch_current_locked` / `_finish_arrival` | 기존 owner가 Nav에 goal 요청/순차 진행 | native action 완료 barrier를 내부에 연결. next waypoint 자동 dispatch 전에 adapter postcondition 확인. 사용자 확인 요구로 바꾸지 않음 |
| `MissionCoordinator.pause` / `_cancel_current_locked` | exact goal cancel, terminal ACK 대기, owner 유지 | 접근 취소는 여기로 위임. idle/foreign/missing ACK를 완료로 간주하지 않음 |
| `MissionCoordinator.resume` | exact confirmation_token + admission | 성공한 approach 다음 leg의 server-only continuation에 실제 메서드 사용 가능. compiled native barrier와 operator-confirmation UI 의미를 분리해야 함 |
| `NavigationCoordinator.send_goal` / `cancel_goal` | `{'accepted': True, 'navigation': view}` / `{'navigation': view}` | raw owner를 만들거나 별도 goal sender 추가하지 않음. 실제 goal ID 확인 후 logical hex32 evidence ID에 매핑 |
| `control.py:ControlManager.tick`, 기존 navigation command consumer | lease, E-stop, command expiry | 최종 한 authority에서 latched HOLD, request sequence, generation barrier, 모든 owner 제약, fresh command/goal 적용. 새 publisher 금지 |
| `MissionRoutes.close` / `close_mission_routes` | 기존 shutdown hook | 활성 native adapter stop(restart=True), 기존 coordinator cleanup 유지. 상태 snapshot을 실행 가능하게 복원하지 않음 |

## 취소된 접근 leg의 atomic continuation hook

`CoordinatorNavigationPort(..., canceled_approach_continuation=...)`의 호출 형식:

```python
async def continue_canceled_native_approach(*, mission_id, previous_scope,
                                           next_visit_id, admission):
    # C1 implements this INSIDE the existing MissionCoordinator operation lock.
    # Return exactly {"mission": coordinator_public_snapshot} after dispatch.
    ...
```

이 hook은 base에 없으므로 C2에서는 구현된 것으로 취급하지 않는다. C1 구현에서 필요한 전제:

1. 기존 `_operation_lock` 안에서 active mission ID, managed admission, previous run/step/goal/generation, exact nav cancel terminal을 검증한다. 접근 실패/foreign goal은 진행하지 않는다.
2. HOLD ACK와 action postcondition의 exact request/generation을 확인한다. SDK ACK나 timer만으로 완료하지 않는다. service의 immutable pins/compiled next visit을 다시 검증한다.
3. 단순 `skip()`이나 `_current_index += 1` 호출로 우회하지 않는다. 내부 native barrier 상태와 증거 기록을 추가하고 “navigation 취소”와 “행동 접근조건 충족”을 별도 기록한다.
4. 기존 `_dispatch_current_locked` 및 monitor를 사용해 next leg를 dispatch하고 owner를 유지한다. external `resume/skip`은 이 경로를 호출할 수 없어야 한다.
5. STOP이 queued되었거나 cancel/constraint outcome이 불확실하면 전이하지 않는다. callback 오류는 C2 adapter가 HOLD/cancel로 닫는다.

## Live binding 검토 체크포인트

실제 camera/signal association/model/clock proof, 두 앞발의 교정된 관측, independent physical STOP, body containment/crossing, posture/terrain completion proof, departure evidence, 통합 arbiter ACK 및 동일 generation fresh command/goal가 필요하다. 입력은 온보드에서 생성·검증하고 브라우저나 외부 VM의 실시간 판단에 의존하지 않는다. 수동 GREEN API는 추가하지 않는다.

native cadence와 stop watchdog 스케줄은 실측 전 미확정이다. command 0.25초와 synthetic evidence 0.5초를 동일하게 hardcode하지 않는다. 설계 arena의 map_transform=null/course graph DRAFT와 규정 치수 불확실성도 변경하지 않는다.
