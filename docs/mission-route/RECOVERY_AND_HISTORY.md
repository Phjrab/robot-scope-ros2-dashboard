# 실행·복구·이력

## 단일 owner와 phase

기존 MissionCoordinator state enum을 유지하면서 `phase`를 추가한다. planning, navigating, holding, before_departure_confirmation, after_arrival_confirmation, uncertain, completed를 구분한다. active id는 paused/pausing/canceling에서도 다른 미션과 MS context 변경을 막는 근거다.

Nav2 action SUCCEEDED는 도착 단계 진입 근거다. fresh pose·bridge zero·물리 정지를 독립 측정한 것으로 표시하지 않는다. 완료는 마지막 방문의 hold와 사후 확인까지 끝난 뒤이며 skip이 있으면 `completed_with_skips`다.

## 대기와 확인

대기는 process monotonic deadline으로 계산한다. pause 시 남은 시간을 저장하고 deadline을 제거하며 resume 때 남은 시간으로 다시 구성한다. wall clock 변경은 대기를 줄이지 않는다. 이미 도착한 holding 방문을 resume하며 goal을 다시 보내지 않는다.

각 사전/사후 확인에 새 token을 발급한다. MR resume은 현재 run/visit/action의 token과 맞아야 하며 과거 확인을 다른 단계에 사용할 수 없다. request_id ledger가 중복 HTTP를 재실행하지 않게 한다. 첫 start도 방문의 사전 확인을 건너뛰지 않는다.

run 요청 ledger는 전체 run/trajectory를 매번 복제하지 않고 bounded `run_ref`를 저장한다. 재전송은 해당 run의 현재 상태를 읽어 반환하므로 오래된 state를 고정해 보여주거나 물리 동작을 다시 수행하지 않는다.

legacy `requires_operator_confirmation`는 접근 전 의미를 유지한다. 기존 마지막 hold 생략과 첫 확인 생략은 의도한 설정이 실행에 반영되도록 수정한다. 저장된 비기본 tolerance는 더 이상 묵살하지 않고 실행 차단한다.

## pause / abort / retry / skip

pause는 현재 소유 goal의 cancel과 terminal settlement를 거친 뒤 paused가 된다. cancel 응답을 물리 정지로 표현하지 않는다. timeout/불확실성은 ownership을 보존하며 새 goal을 보내지 않는다. unrelated goal의 id를 취소하거나 그 성공으로 현재 방문을 완료하지 않는다.

abort는 해당 run 종료와 cleanup이다. 수동 전환은 기존 navigation takeover 절차를 사용하며 ARM을 자동 수행하지 않는다. planning 중 stop 요청도 dispatch 전에 확인한다. 다른 ready run의 abort가 active run과 monitor를 보존하는 회귀는 PASS했다.

저장 실패·request ledger 포화가 pause/abort를 막지 않는다. 기존 소유 goal 정리를 먼저 처리할 수 있는 경로를 두고 내구성 기록이 없으면 `STOP_APPLIED_WITHOUT_DURABLE_HISTORY` 또는 `STOP_APPLIED_WITHOUT_DURABLE_REQUEST_RECEIPT`를 `audit_warning`으로 반환한다. audit 실패 중 cancel도 불확실하면 ownership을 유지한다. 이 안전 정지 예외는 새 start나 실행 재개에 확대하지 않는다.

resume/retry/skip은 현재 지도/annotation/route/source generation/planner/context pin을 재검증한다. stale pin은 새 검사·새 run을 요구한다. retry는 명시 요청이며 자동 무한 retry가 없다. skip은 취소 확인 뒤 결과를 skipped로 기록한다. aborted/interrupted run은 skip으로 재개할 수 없다.

MR run의 legacy start/resume/retry/skip 우회는 admission guard로 거부한다. HTTP timeout이나 다른 client가 원래 MR preflight를 건너뛰어 goal을 보낼 수 없다. 이 우회 거부를 synthetic 회귀로 확인했다.

## restart와 uncertain

서버 재시작은 paused를 포함한 저장 active 상태를 `failed/outcome=interrupted`로 기록하고 active ownership을 복원하지 않는다. 재시작/브라우저 reload/SLAM 복구가 자동 resume/ARM을 발생시키지 않는다. physical goal 상태는 새로운 실행 전 기존 navigation 소유권 검사로 다시 확인해야 한다.

goal 제출 결과가 불확실하면 `canceling/uncertain`과 ownership을 유지하고 cleanup을 요구한다. request 결과 기록 전 crash도 `REQUEST_OUTCOME_UNCERTAIN`으로 남긴다. 사진 등 외부 side effect executor는 미지원이며 active/completed/uncertain을 가진 범용 외부 action ledger가 구현됐다고 주장하지 않는다.

## 이력과 관측

run은 immutable definition/revision, snapshot pin, 생성/시작/종료 UTC, waypoint status/attempt/대기·확인 로그, outcome, 최근 dispatch preview를 저장한다. `source_sha`와 `runtime_sha` 필드는 null이며 `provenance_status`는 build identity unavailable을 명시한다. `live_plan`도 frame/time provenance를 확보하지 못해 unavailable이다. preview를 runtime 최신 계획으로 대신하지 않는다.

실행 요청 events는 최대 200개, coordinator logs도 bounded, trajectory는 최대 256개다. trajectory는 운영 pose observation이며 truth trajectory나 localization accuracy가 아니다. 동일 context 내 관측도 수신 gap가 2초를 넘거나 pose가 unavailable하면 epoch를 끊는다. 좌표 오차 통계·물리 latency·근거 없는 ETA는 제공하지 않는다.

pose의 fresh 여부는 `readiness.localization`을 사용하고 `can_send_goal`과 분리했다. 이동 중 새 goal admission이 닫혀도 fresh pose는 관측할 수 있다. stale localization이면 관측을 이어 붙이지 않으며 source 미상·effective footprint 누락 역시 실행을 차단한다.

정의 64/run 32/request 256/512KiB 상한에 도달하면 명시 archive 필요 오류를 반환한다. 현재 maintenance/archive API는 없으며 장기 운용 정리 절차는 미구현이다. pause/abort는 ledger 상한 때문에 차단하지 않는다. 정의 DELETE는 exact revision과 idle 상태를 확인하고 기존 run 이력을 보존한다. GET run export는 allowlist 필드만 반환하고 confirmation token을 제거하며 `executable=false`다. 자동 삭제·import resume·raw sensor export는 없다. lease/인증정보/운영 절대경로를 새 이력에 넣지 않는다.

## 검증 경계

최종 focused83 및 전체 Python1939(skip2/fail0), Node381·Chromium96 PASS. monotonic 최종 hold/잔여 대기/첫·사후 확인/stale token, wrong goal·source generation, aborted skip 차단, paused restart, uncertain ownership, 저장/audit 실패 중 정지, active copy/delete/export를 synthetic provider와 실제 coordinator code에서 확인했다. UI는 현재/다음 방문, disconnect, takeover 상태, 다른 지도 이력 조회·draft 복귀와 revision/time/outcome/attempts 비교를 local HTTP fixture로 검증했다. 같은 지도·각 epoch의 비교 trajectory를 표시하며 오차 통계를 만들지 않는다.

physical stop/도착/실장비 crash 복구는 NOT_RUN이다. runtime policy provider가 연결되지 않아 새 start는 production에서 차단된다. 상세 로그·hash·시각은 VALIDATION.json이다.
