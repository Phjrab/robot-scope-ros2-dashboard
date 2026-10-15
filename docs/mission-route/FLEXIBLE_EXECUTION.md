# FLEXIBLE 경로 → 정의 → 실행

## E1 초안 변환

`GET /api/v1/mission-route-drafts/{route_id}`는 기존 저장 경로와 `select_execution_waypoints`를 읽어 새 visit id의 STOP 후보 목록을 만든다. 원본 geometry와 exact route revision/map family를 보존한다. 표시된 STOP 목록을 사용자가 검토·수정·저장한 뒤 compile한다. compile 버튼만으로 경로를 실행하지 않는다.

직접 작성한 visit은 geometry 샘플과 별개다. 같은 좌표/POI의 반복 방문과 개별 yaw/대기/확인을 유지한다. 정의 상한 32 visits를 넘으면 strict validation으로 거부하며 숨은 truncation을 하지 않는다. E1의 기존 최대 geometry와 selector 한도는 재사용한다.

기존 주문/픽업/배달의 작업 의미를 자동 수입하는 새 mapping은 현재 없다. legacy advanced 진입점과 데이터는 보존한다. 불명확한 route task를 새 일반 미션의 완료 작업으로 기록하지 않는다.

## compile과 run

compile은 exact definition/route/map/annotation pin과 지원 정책을 확인해 `{compiled, validation}`을 반환하는 idempotent transaction이다. `start_sent=false`이며 TF·lease·ARM·goal이 없다. run 생성도 별도 데이터 동작이다.

run 생성 시 방문을 기존 MissionCoordinator waypoint로 변환한다. `mission_local_pose`는 기존 NavigationCoordinator `send_goal`을, 기본 `annotation_ref`는 기존 `send_annotation_goal`을 사용한다. annotation `heading_yaw` override가 있으면 exact annotation x/y와 override yaw를 기존 `send_goal`에 전달한다. annotation을 몰래 생성/이동하지 않는다. run에는 정의 snapshot/context pin을 고정하며 source/runtime SHA는 실제 근거가 없어 null이다.

## 실제 실행 경로

새 run의 start/resume/retry/skip은 MR façade가 현재 pin을 확인하고 admission을 전달한다. MR context가 있는 run을 legacy API로 우회 실행하면 `MISSION_ROUTE_API_REQUIRED`다. 실제 dispatch는 기존 coordinator의 단일 operation lock/active id/monitor 아래에서 진행한다.

공유 `pipeline_coordination_lock`의 admission guard는 MS 전환을 검사한다. 각 dispatch에서 실제 현재 pose와 next visit의 native path를 재검사하고 그 뒤 navigation readiness와 context를 다시 읽는다. hypothetical start나 이전 preview를 실행 출발점으로 사용하지 않는다.

지원 순서는 접근 전 확인 → 이동 → Nav2 성공 도착 단계 → 대기 → 도착 후 확인 → 다음 방문이다. 마지막 방문에도 같은 순서를 적용한다. unsupported action/speed/tolerance/constraint를 삭제해 성공시키지 않는다.

## FLEXIBLE 한계

방문 순서·목적지는 고정하지만 각 leg 안에서는 Nav2가 새 경로를 찾을 수 있다. dense 작성선 정밀 추종, CORRIDOR/STRICT, 무정차 경유를 보장하지 않는다. PASS_THROUGH를 자동 STOP으로 바꾸지 않는다. E1 STOP 초안은 명시 검토/저장 단계다.

공유 hook, native planner resource window, effective 정책 증거가 없어도 작성·저장·compile 구현은 진행할 수 있다. 실제 실행 가능 상태를 가장하지 않으며 현재 production start는 runtime proof 부재로 BLOCKED다.

## 검증·rollback

최종 focused83 및 전체 Python1939(skip2/fail0), Node381·Chromium96 PASS. 저장 → compile → run → 기존 coordinator + synthetic navigation 순서 실행, pause/resume/complete, 중복 요청/immutable run/현재 출발점, annotation heading dispatch와 legacy admission 우회 차단을 검증했다. actual MS/MR code 교차8, app wiring과 E1 browser compile도 통과했다. synthetic 성공은 live 주행 성공이 아니며 effective runtime policy 연결은 PROPOSED/BLOCKED, 실제 native/실기는 NOT_RUN이다. 상세 evidence는 VALIDATION.json이다.

source rollback은 MR 연결과 해당 코드 변경만 정상 revert한다. 이미 생성된 정의/run은 private data로 보존하며 이전 reader 호환성 검사가 필요하다. source revert를 위해 데이터 파일을 삭제하거나 운영 서비스를 재시작하지 않는다.
