# 2026-10-31 C0 남은 실기 후속 — 진행 중

**OPEN: 후속 실기 완료표가 아니다.** 사용자의 새 지시에 따라 현재 source·실행본·준비 상태와 독립 비이동 표시 검증을 실행했다. 이번 실제 goal·자세·ARM·이동 명령은0건이다. 현재 source 선택, P1/P2 목표, 새 현장 시험창이 필요하다. 이전 사용자 주행의 canceled 결과를 이번 C0 실기 FAIL로 세지 않는다.

첨부 이름 `ROBOT_SCOPE_C0_CONTINUE_20261031.md`는 제공된 경로와 PC 파일 검색에서 찾지 못해 경로를 요청했다. 지금 메시지에 직접 작성된 후속 범위를 적용해 비이동 준비를 계속했다. 새 채팅·확장 브랜치 통합·재배포·현재 지도/설정/교정 변경은 없다. 요청에서 제외한 지도 정합·과거 원점/잔차 비교 조사는 하지 않는다.

## 후속 표 — 기존 결과와 분리

| ID | 기능 | 현재 결과 | 실제 근거·남은 의존성 |
|---|---|---|---|
| C00 | 실행본·실제 설정 인수 | PASS | PID/cwd, 실제 생성 YAML·로드된 shim hash 읽기; 설정·교정 private 백업 |
| C01 | 현재 source·TF·Nav2 진입 | BLOCKED_SOURCE_SELECTION | 노드·TF 입력 준비, 운영 selected=null/LEGACY_2D. gateway session idle, health NAVIGATION_INACTIVE, can_send_goal=false. 사용할 source 확인 대기 |
| C02 | 실제 Nav2 정지점 도착·정지 | NOT_RUN | C01 + P1/P2 + 새 현장 준비·시험창 필요 |
| C03 | 측정 정지·dwell→시험 녹색→다음 goal1개→출발·종료 | BLOCKED_DEPENDENCY | 기존 gate의 live STORED_PCD_FASTLIO·실제 success·정지/dwell·generation 조건 미충족. 가짜 proof/강제 상태0 |
| C04 | 경사로 현재 운영 위치추정·주행 연속성 | NOT_RUN | 사용할 운영 source와 새 현장 창 필요. 기존 raw/LIO 수동 기록 반복 안 함 |
| C05 | 현재 로봇 URDF·pose·12관절 표시 | PASS 범위 한정 | 실제 전용 관측 화면 Go2 URDF 표시; pose 최대 age.060s·관절.014s, seq/stamp 증가. 물리 위치 정확도 판정 아님 |
| C05b | 새 목표 URDF·실제 이동 상태 | NOT_RUN | 이번 goal 미발행. 과거 canceled 목표 화면을 새 시험으로 승격하지 않음 |
| C06 | 안전 종료·복구·전체 결과표 | PENDING_SWEEP | 임시 검사 탭과2초 읽기 전용 계측만 종료. 장비 runtime은 보존. 본격 실기 종료는 아직 아님 |

실행 중인 Nav2 job은 `e23037232e5a4db4b551dc040267a1d8`이며 현재 지도 ID는 `9a382e3eb990fb02fe1a3569`, revision `d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552`다. 저장 장소는0개여서 이번 P1 정지점과 P2 다음 목표를 요청했다. 이전 goal/과거 이동 승인을 재사용하지 않는다.

현재 브릿지는 이미 active·authenticated·ready다. 이번 C0가 켠 것으로 기록하지 않는다. lease inactive, 명령 전축0을 읽었다. 노드 readiness와 TF freshness가 있어도 gateway의 주행 진입이 잠겨 있으므로 실제 이동 준비 완료로 간주하지 않는다. source를 임의로 바꾸거나 가드를 강제로 통과시키지 않았다. 기존 시험 gate는 운영3D source를 요구하므로 현재 legacy source에서 버튼을 통과한 것으로 표현할 수 없다.

## 현재 실행본·보존한 설정

dashboard PID1016/cwd `robot-scope-15706c48c5e6`와 기존 전체 배포 영수증의 SHA `15706c48c5e6df28be105b6f5bde825dce7c4b1f`를 구분해 기록했다. 이번에 전체 소스 재감사·재배포는 하지 않았다. 실제 controller PID93068의 로드된 `libnav2_rotation_shim_controller.so` SHA256은 `95c6ee9b0294651c182092031eb4926291946eb8e72be5cf1bfb976219f1754d`다.

saved revision `71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387`, 생성 YAML SHA `69804bc0a5dacf1122fe52e2a1aa313c8c65576525c2262f10eeea6783c50ccc`를 인수했다. 저장/생성/live XY.10m·yaw.10rad, 속도.25m/s·10Hz, SimpleProgressChecker를 읽었고 바꾸지 않았다. 생성 YAML 원본·FAST-LIO 설정·기존 운영 교정 파일을 private에 그대로 복사했다. 운영 교정 SHA256은 `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226`이며 내용 재해석/수정은 하지 않았다.

읽기 전용 HTTP 계측은 navigation/control/pose/operational 상태를2초 동안2표본·오류0으로 저장했다. 새 ROS publisher·명령 경로는 없다. 실제 이동 시험용 같은 계측기는 최대30분·20MB로 제한되어 있고 아직 이동창 기록으로 시작하지 않았다. 현재 URDF 화면·절대 좌표·설정/교정 원본은 private에만 둔다. 검사 중 전용 관측 창은 기존 화면의 정식 URL로 확인했고 검사 후 임시 탭을 닫아 사용자 원래 주행 탭을 보존했다.

## 다음 단계의 경계

사용자가 준비한 운영3D source를 선택할지 현재 source를 유지할지 확인 중이다. 정상 runtime 연결 복구는 선택된 현재 자산을 보존하는 범위에서만 진행한다. P1/P2가 구체화되면 실제 두 goal·측정 정지/dwell·시험 버튼·종료와 필요한 경사로 관측의 횟수/상한을 묶어 새 현장 준비를 한 번 확인한다. 동일 유효 창의 하위 단계마다 재승인을 요구하지 않는다.

실행 가능한 전체 행을 먼저 검증하고 결과표를 마감한 뒤 원인 분석·최소 수정으로 넘어간다. 이번 준비 상태를 최종 실기 성공/실패나 복구 완료로 승격하지 않는다. 앱·테스트·CI 코드 변경은 없으며 이전 보고서6개 불변, 증거 hash·계측·표시 입력 검사를 통과했다. [집계 JSON](CONTINUE_PROGRESS_20261031.json)에 상세 근거를 보존했다. 이번 문서 SHA CI는 제출 후 확인하며 옛 통과를 대신하지 않는다.


## 후속 연결 기록

첨부 `ROBOT_SCOPE_C0_CONTINUE_20261031.md`는 이후 실제 파일로 읽었다. 위 상태는 당시 snapshot이며 현재 상태로 재사용하지 않는다. [20261031 후속 전체 표](../20261031/CONTINUATION_RESULTS.md), [후보 구현·동일 입력 비교](../20261031/REAR_SIDE_COMPARISON.md), [편집 PCD 변환·최종 배포·복구](../20261031/EDITED_PCD_CONVERSION.md), [인계](../20261031/HANDOFF.md)로 이어진다. 사용자 준비 2D/P1/P2, 정상 STOP 후 source binding 응답 timeout과 교정 복구, 실제 map1→map1_2d 성공 및 UI 추적 보완을 새 사건으로 기록했다. 3D 이동 sweep은 OPEN이고 후방·측면 후보는 NOT_ADOPTED/기본 비활성이다.
