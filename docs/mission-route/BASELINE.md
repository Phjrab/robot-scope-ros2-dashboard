# MR 기준 상태와 경계

최초 조사 local `1b0ae5b` / fetch한 origin/main `eb9026a`, ahead1·dirty/staged 없음이었다. 기존 미게시 문서 커밋을 보존했다. 최신 AGENTS는 main 직접 작업·branch/worktree/PR 생성 금지, 전체 Python/관련 JS 검사 후 focused commit/push, Git 발행과 장비 배포 분리를 요구했다.

MS 단독 창의 구현/수정을 보존한 최종 MR base는 `7747ef7dd536a8aa0f313784374e00693e8696c3`다. MS의 d866a3b와7747ef7 exact CI는 성공했으며 과거38554448122 실패를 현재 상태로 쓰지 않는다. MR source는 `22c7913c879afcca536a78d552dcdf98f0f53098`다. 최초 조사와 최종 상태를 혼동하지 않으며 최신 검증/발행은 PROGRESS/VALIDATION을 따른다.

요청한 robot_scope_mission_route_new_chat.md는 첨부 디렉터리에 없었다. pack의00~04,20~27,90~92 해당 문서를 읽어 범위/계약/인수 기준으로 사용했다. 문서의 예시 PASS/수락 문구는 관측 결과로 취급하지 않았다. 단계27은 실행 권한이 없다.

기존 API missions → MissionCoordinator → NavigationCoordinator → gateway를 재사용한다. SavedMapsPort의 occupancy와 annotation revision, E1 validator/select_execution_waypoints와 geometry/revision을 읽는다. 새 mission_routes domain/API/workspace와 fixed ComputePathToPose adapter를 더했다. 원본 annotation/지도 migration은 없다.

기존 코드의 마지막 hold 생략, 첫 방문 사전 확인 우회, 비기본 tolerance 묵살, wall-clock pause/restart, foreign goal terminal 혼입을 수정하고 실제 coordinator synthetic 회귀로 검증했다. 정의별 repeated visit ID와 immutable run을 추가했다. 상세 계약은 DATA_MODEL/FLEXIBLE_EXECUTION/RECOVERY_AND_HISTORY다.

MR+legacy와 actual MR/MS code의 synthetic 통합/앱 wiring은 검증됐다. 설치된 ROS/Nav2·장비 runtime SHA/config·물리 도착/정지는 미확인이다. effective runtime policy provider(MR-MS-003)가 미연결이라 전체 인수는 PARTIAL이다. 운영 자원·사용자 데이터는 변경하지 않았다.
