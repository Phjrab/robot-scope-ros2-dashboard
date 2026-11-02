# C0 전체 1차 결과 — 2026-10-30

1차 판정 마감: 2026-10-30T17:46:26.511120+09:00. **전항목 판정 완료, 전항목 합격 아님.** 현재 장비 연결 불가로 실기 완료를 주장하지 않는다. 이 문서를 먼저 확정하고 별도 진단을 작성한다.

## 실행 신원과 범위

- 원격 조회한 main 및 이번 검사 source: `846121b4988ed2932d329020857925558f8f2c79`.
- C0 독립 clone/브랜치: `c0-field-sweep-20261030` / `review/20261030-c0-3d-field-sweep`. 기존 C1~C7/D1~D3 checkout·dirty 변경은 건드리지 않았다.
- 마지막 **보고된** 실기 배포: `5154761bba6fa4f171881e61f986901e2b415ed9`. main과의 diff는 현장 문서 2개뿐. 현재 실행 SHA/PID/cwd/manifest/overlay는 조회하지 못했다.
- 첨부에서 요청한 `ROBOT_SCOPE_C0_START_20261030.md`라는 정확한 파일명은 찾지 못했다. 실제 제공 경로의 `01_C0_MASTER_PROMPT.md`와 관련 분할 팩을 읽었으며 사용자 직접 지시를 우선했다. 문서의 요구사항과 과거 보고를 이번 실행 증거로 취급하지 않았다.
- 이동·서비스 재시작·배포·설정·지도·STOP/lease 변경 0건, 신규 goal 0건. 다른 채팅 생성·메시지·확장 브랜치 통합 0건.

## V00~V09 전체 결과

| ID | 기능 | 구현/이번 비이동 근거 | 배포·과거 실기 | 이번 결과 | 막힌 조건/다음 독립 항목 |
|---|---|---|---|---|---|
| V00 | 인수·실행 기준 | 독립 clone/전용 브랜치·main 고정 완료 (SOURCE_REVIEW) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_DEPENDENCY** | 현재 장비 연결 불가: 실행 PID/cwd/SHA·소유권·STOP·lease 미확인 |
| V01 | 소프트웨어·UI 대표 회귀 | 핵심 Python 157, JS 700, 합성 Chromium 18 통과 (SOFTWARE) | 장비 결과 아님 | **PASS** | 실장비 표시·제어 성공과 구분; main 원격 CI 실패는 별도 보존 |
| V02 | E1~E3 전체 PCD 편집·저장·reference | 12,000 source/150 preview 실 저장 흐름·hash·사본 재조회 회귀 PASS (SYNTHETIC) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_DEPENDENCY** | 장비 실제 원본/사본·worker pin readback 필요 |
| V03 | N1~N4 정지 초기화·운영 위치 소비 | exact stamp/단일 authority/body odom/rollback 회귀 PASS (SOFTWARE) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_DEPENDENCY** | V00 현재 정지·source·bundle·consumer 및 브라우저 독립 갱신 미확인 |
| V04 | N5/G2 stop 접근·실제 정지 | 기존 구현 보존, 신규 goal 0건 (SOURCE_REVIEW) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_OPERATOR** | V00/V03·현장 준비·새 시험창 필요; 이전 두 목표 승인 사용 완료 |
| V05 | G1~G4 버튼·1회 다음 goal·출발 | 부정 사례·2초 dwell·one-shot·최종 dispatch guard 회귀 PASS (SOFTWARE) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_DEPENDENCY** | V03 실제 source와 V04 실제 success/정지/dwell 부재; 강제 통과 안 함 |
| V06 | R1/R4 경사로 전체 방향 baseline | ALL_DIRECTION_BASELINE 및 단계별 계측 구현 인수 (SOURCE_REVIEW) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_OPERATOR** | 장비·현장·관측 전용 소유권/안전한 수동 경로·새 시험창 필요. V04 정밀 도착 성공과 독립 |
| V07 | R2/R3 경사로 경계·전방 관측·동일 입력 비교 | localization exclusion이 전체 obstacle scan을 지우지 않는 회귀 PASS (SOFTWARE) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_DEPENDENCY** | V06 실제 cloud+pose+reference 입력 없음. rear/side 비교 INPUT_REQUIRED, BASELINE_RETAINED 판정 불가 |
| V08 | 정지·복구·증거 보존 | 기존 bounded sink·비차단 STOP 관련 회귀 PASS; 장비 변경 0 (SOFTWARE) | 현재 미확인; 세부 요구표 참조 | **BLOCKED_DEPENDENCY** | 현재 실제 ZERO/ACK/측정 정지/STOP latch/lease readback 불가 |
| V09 | 전체 판정·진단 분리 | V00~V08 및 E/N/G/R 모두 판정; 이 파일을 진단보다 먼저 생성 (SOURCE_REVIEW) | 장비 결과 아님 | **PASS** | 전항목 판정 완료이며 전항목 합격을 뜻하지 않음 |

V02/V03/V05/V07/V08의 software PASS는 각각 장비 실기 BLOCKED를 대체하지 않는다. V06의 수동 경사로 관측은 정밀 도착 성공에 의존시키지 않았다. 현 장비·안전 조건이 없어 실행할 수 없었다.

## 원래 E/N/G/R 인수표

| ID | 요구 | 구현 | 과거 증거 | 이번 software | 이번 실기 | 연결 |
|---|---|---|---|---|---|---|
| E1 | 영역/Z 선택·제외·undo/redo | 기존 구현 | 과거 FIELD_PASS | PASS | BLOCKED_DEPENDENCY | V02 |
| E2 | 전체 PCD 사본 저장·재조회·속성 보존 | 기존 구현 | 과거 FIELD_PASS | PASS | BLOCKED_DEPENDENCY | V02 |
| E3 | 사본 reference hash/revision 실제 worker 일치 | 기존 구현 | 과거 FIELD_PASS | PASS | BLOCKED_DEPENDENCY | V02/V03 |
| N1 | 3D/2D map bundle·frame·origin | 기존 구현 | 과거 FIELD_PASS | PASS | BLOCKED_DEPENDENCY | V03 |
| N2 | 브라우저 독립 지속 저장 지도 정합 | 기존 구현 | 과거 FIELD_PASS | PASS | BLOCKED_DEPENDENCY | V03 |
| N3 | TF/body/controller odom 실제 소비 | 기존 구현 | 과거 FIELD_PASS | PASS | BLOCKED_DEPENDENCY | V03 |
| N4 | idle 전환·재시작 비복원·rollback | 기존 구현 | 과거 보고/회귀 | PASS | BLOCKED_DEPENDENCY | V03 |
| N5 | 새 3D source의 실제 짧은 Nav2 목표 | 기존 구현 | 기존 허용오차 FIELD_PASS; 정밀 기준 실패 | NOT_RUN | BLOCKED_OPERATOR | V04 |
| G1 | 시험 모드·현재 stop 이벤트 | 기존 구현 | 전체 실기 NOT_RUN | PASS | BLOCKED_DEPENDENCY | V05 |
| G2 | 실제 success·측정 정지 2초 dwell | 기존 구현 | 전체 실기 NOT_RUN | PASS | BLOCKED_DEPENDENCY | V04/V05 |
| G3 | 중복/만료/이전 stop/source 변경 차단 | 기존 구현 | software 증거 | PASS | BLOCKED_DEPENDENCY | V05 |
| G4 | 버튼→다음 goal 1개→실제 출발·종료 | 기존 구현 | NOT_RUN | PASS | BLOCKED_DEPENDENCY | V05 |
| R1 | 평지·진입·상승·정상·하강·복귀 baseline | 계측 구현 | NOT_RUN | PASS | BLOCKED_OPERATOR | V06 |
| R2 | 동일 입력 후방/측면 후보 비교 | 운영 미구현/미채택; 조건부 | NOT_RUN | NOT_RUN | BLOCKED_DEPENDENCY | V07 |
| R3 | 품질·전방 관측·CPU/지연 손익 | 지표 기반 구현; 실비교 없음 | NOT_RUN | PASS | BLOCKED_DEPENDENCY | V07 |
| R4 | 실제 경사로 위치추정 결과 | 관측 경로 실기 미검증 | NOT_RUN | NOT_RUN | BLOCKED_OPERATOR | V06 |

모든 행의 현재 배포는 UNVERIFIED다. 기존 editor, 운영 FAST-LIO/TF/body odom 및 Nav2, 시험 gate와 계단·경사로 보행을 재개발하지 않았다. R2는 baseline에서 문제가 확인돼 동일 입력 비교가 필요한 경우에만 후속 구현한다.

## 이번 검사와 발견 사실

- 핵심 Python 157개 PASS; 전체 JS 700개 PASS (Node 20.20.2); 실제 Chromium 합성 UI 18개 PASS.
- UI 검사는 polygon/높이/history, 12,000 전체 source와 150 preview 구분, 사본 저장·재조회·source hash 보존·저장만으로 source 비전환, 정합 pin/초기화/rollback, 시험 mode·dwell/stale/reconnect·현재 stop one-shot, 공식 Initial/Goal URDF를 포함한다.
- 핵심 Python은 PCD non-XYZ 속성/원본 보존, worker의 사본 pin, exact-stamp cloud/odom, source 교체 무효화, TF authority, body odom 소비, localization exclusion과 전체 장애물 scan 분리, final guard·만료·취소·source 변경 및 bounded sink를 포함한다.
- Ruff PASS, mypy 지정 4파일 PASS, Node20 JS 구문 112모듈 PASS, tracked secret scan PASS.
- 전체 Python은 1차 표 확정 시 진행 중이다. 최종 집계/exit는 VALIDATION.json에 보존한다.
- 초기 인프라 실패: sandbox 브라우저 bind EPERM, sandbox asyncio 검사 진행 정지, host 기본 Node18 ES-module 구문 실패. 기존 Node20/의존성을 사용한 제한된 비이동 재실행으로 위 검사 완료. 첫 JS sandbox 결과 77은 파일 종료 집계여서 개별 700개 결과로 사용하지 않았다.
- SSH와 대시보드 후보 GET 모두 No route to host. 인증 단계나 live API 응답에 도달하지 못했다. 후보 주소가 현재 장비라고 확정하지 않는다.
- 원격 main CI 41001998475: Ubuntu24.04/3.12 browser E2E **FAIL**, Ubuntu22.04/3.10 및 competition integration PASS. 실패는 navigation_goal_urdf.spec.mjs:114의 old-revision Goal 숨김 poll timeout. 같은 대표 검사를 이번 1회 로컬 실행에서는 재현하지 못했다. 원격 실패를 PASS로 덮거나 flaky로 단정하지 않았다.

## 실제 도착·버튼·경사로

이번 stop goal/next goal/mission/stop/event/dispatch/result/정지 ACK/측정 정지 영수증은 없다. 요청 수신이나 software fixture를 실제 출발로 표시하지 않는다. .10m/.10rad 외부 정밀 기준과 기존 stop acceptance를 분리하며 둘 다 이번 실기는 NOT_RUN이다.

경사로 평지·진입·상승·정상·하강·복귀는 모두 NOT_RUN. pitch/raw/LIO/correction/TF/scan/costmap/CPU/RSS/정답 기반 정확도는 NOT_MEASURED. 실제 baseline이 없으므로 BASELINE_RETAINED나 후방 가중 성능 개선을 주장하지 않는다.

## 보고된 설정과 현재 미확인값

아래 값은 10월30일 기존 보고서의 마지막 실기 설정이다. **현재 saved/generated/live 읽기값이 아니다.**

| 항목 | 마지막 보고값 |
|---|---|
| release/ROS/Nav2 | robot-scope-5154761bba6f / Humble / Nav2 1.1.20 |
| 실제 로드 overlay SHA256 | 95c6ee9b0294651c182092031eb4926291946eb8e72be5cf1bfb976219f1754d |
| 보존된 원본 .so SHA256 | 1cd261a56261e20b10e1d3cc6da3ff14423b467bef23238c8dbc84235f6f0965 |
| saved parameter revision | 71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387 |
| generated YAML SHA256 | 69804bc0a5dacf1122fe52e2a1aa313c8c65576525c2262f10eeea6783c50ccc |
| controller/속도/주기 | RotationShim/RPP / .25m/s / 10Hz |
| goal/progress checker | SimpleGoalChecker stateful=true .10m/.10rad; SimpleProgressChecker .20m/10s |
| RPP approach | .60m / minimum .05m/s (당시 live 기본값) |
| source/weighting | STORED_PCD_FASTLIO / ALL_DIRECTION_BASELINE |
| reference | 13,546점; SHA256 6ec38aa876ffcfe505ee81204d94fa84e1c3cb438ae706a6a6b7fc0048970b5a |
| 3D ID/revision | e1dd40cc6911404dbdfc073b / c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5 |
| 2D ID/revision | 9a382e3eb990fb02fe1a3569 / d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552 |

yaw .05rad/PoseProgressChecker 후보는 장비에 적용하지 않았다. operator_free 영역, 속도·progress·TF 패치·scan 필터·quality threshold·후방 가중치를 변경하지 않았다.

## 보존·종료 및 재개 조건

현재 STOP latch/lease/active goal/mission/job/command/센서 소유권은 UNKNOWN. 마지막 보고의 idle·lease inactive·세 축 zero를 현재 상태로 복사하지 않았다. 해당 보고의 estop=null도 해제 증거가 아니다. 장비 변경을 하지 않았으므로 이번 배포 rollback은 해당 없음이며, 현재 실제 정지나 복구 완료를 보증하지 않는다.

기존 release robot-scope-5c1ffe3ba3c0와 원본 /opt/ros, private selector 백업·복구 프리셋의 존재는 과거 보고로만 인수했다. 다음 연결에서 idle/미저장 지도/소유자와 backup 유효성을 먼저 확인하고 필요한 증분만 보존한다. main이 문서 변경뿐이므로 최신 SHA를 이유로 재배포하지 않는다.

연결 복구 후 비이동 readback·실제 사본/reference·정지 initial pose/worker 소비를 확인한다. 실제 움직임 직전에 현재 운영자·충전 케이블·비어 있는 구간·정지/수동 회수·STOP/lease/goal/센서 소유권과 새 시험창을 한 번 확인한다. 제안 창은 새 stop+next 최대 2 goal(각 30초 상한) 및 독립 수동 경사로 baseline 1회(최대 5분); 경로/거리/heading은 현장 화면에서 확정해야 한다. 이것은 승인 요청 또는 실행 권한이 아니다. 이전 두 목표 승인은 재사용하지 않는다.

## 근거

- [기존 10월30일 실기 보고](../../operational-3d-navigation/GOAL_HEADING_FIELD_CHECK_20261030.md)
- [기존 운영 진행표](../../operational-3d-navigation/PROGRESS.md)
- [기존 운영 인계](../../operational-3d-navigation/HANDOFF.md)
- [기존 full-source 계약](../../full-source-pcd-editing.md)
- [JSON 결과](ROUND1_RESULTS.json), [입력/hash](SOURCE_INTAKE.json)
- private 원시 실행 로그·합성 브라우저 artifact는 공개 Git에서 제외한다. 최종 hash/재현 명령은 VALIDATION.json에 기록한다.

## 1차 판정 뒤 최종 제출 검사

2026-10-30T17:50:59.369959+09:00에 고정 역사 의존성을 갖춘 전체 Python **3,132개 실행·실패0·선택 의존성 skip2**를 확인했다. JS700·합성 Chromium18 및 static 검사는 위와 같다. 행별 1차 판정은 변경하지 않았다. [최종 집계와 hash](VALIDATION.json), [별도 사후 진단](POST_SWEEP_DIAGNOSIS.md), [이번 진행률 재현](POST_SWEEP_PROGRESS_REPRO.json)을 참조한다.
