# C0 병렬 준비 작업 결과 — 2026-11-01

사용자의 최신 지시에 따라 C1.1~C1.4를 별도 채팅으로 실행하고 C0가 측정 검토, 후속 지시, 통합 및 장비 변경 순서를 관리했다. 모두 `gpt-6.1-terra` / `xhigh`. 기존 C0 브랜치 `review/20261030-c0-3d-field-sweep`를 사용했다. 과거 C1~C7/D1~D3 확장 브랜치 통합은 하지 않았다.

**후속 코드 통합:** `c414a519bd18ece9ecf46469074046bb94dac33e`의 정보성 초기 위치 제안과 단일 준비 조회를 구현·검사했다. 배포는 C0-W04C에서 완료했으며 실제 실행 PID82325·신규2268파일/HTTP4자산 및 보호125+8 항목을 확인했다. 센서 기반 제안 계산은 별도 W05에서 확인한다. [새 결과와 남은 의존 사항](INITIALIZATION_PROPOSAL_RESULTS.md)을 참조한다. 아래 W02/W03 배포·실기 결과는 당시 증거로 보존한다.

이 문서는 11월 1일의 증거다. [10월 31일 전체 결과](../20261031/CONTINUATION_RESULTS.md)와 [지도 연결 결과](../20261031/NAVIGATION_PAIR_RESULTS.md)의 과거 판정을 새 실기 PASS로 덮어쓰지 않는다.

## 전체 1차 결과표

| 담당 / 기능 | 구현 | 배포 | 소프트웨어 검증 | 이번 장비 검증 | 실제 이동 |
|---|---|---|---|---|---|
| C1.1 센서 관측·초기값 출처 | PASS | PASS | PASS | W03 실제 동일 시각 점군·자세 및 관측계 본체 참고값 PASS; 지도 기준 후보는 BLOCKED | NOT_RUN |
| C1.2 단계별 준비 UI | PASS | PASS | 준비 8 + 기존 목표 4 fixture PASS | 실제 HTTP 자산 4개 hash PASS; 현재 센서 표시 검증은 W03 | NOT_RUN |
| C1.3 연결·회귀·배포 | PASS | PASS | Python/Node/문법/E2E PASS | SSH/실행본/백업/보호자료/지도 쌍 PASS | NOT_RUN |
| C1.3 간헐 응답 지연 | 제한적 작업량 감소 | PASS | 인위적 지연 만료 검사 PASS | W03 준비 GET 5.479초로 긴 응답 재관측; 원인 및 해결 미확정 | 해당 없음 |
| C1.4 저장 지도 보정→TF→Nav2 | 기존 구현 보존, 독립 교차검토 PASS | 기존 기능 포함 | binding 9·3D 19·TF 12 등 합성 검사 PASS | BLOCKED: 운영 runtime 없음, 지도 기준 z/roll/pitch 근거 없음 | BLOCKED |
| P1 이동·정지 / 녹색 버튼 다음 목표 / 경사로 운영 추정 | 기존 상태 보존 | 변경 없음 | 이번 새 실기 성공으로 간주하지 않음 | 상위 조건 의존, 이번 미수행 | BLOCKED |

실제 goal·자세·이동 명령은 보내지 않았다. 현재 위치 정확도를 측정하거나 정합 잔차로 정확도를 주장하지 않았다.

## 구현 및 통합 검사

- 코드 SHA: `4f90612379705b7b7c8c86cca99941266e3ae611`.
- 새 읽기 전용 `GET /api/v1/navigation/operational-3d/preparation-inputs`: 관측 시작 차단 사유, 동일 시각 점군·자세의 출처, 검증된 본체 변환에 의한 **관측 좌표계 참고 자세**, 각각의 지도 기준 후보와 부족 사유를 제공한다. 응답은 `no-store`; 원시 점군을 반환하지 않는다.
- 참고 자세는 지도상의 절대 높이·기울기가 아니다. 지도 후보는 현재 실행 job/bundle, 양쪽 지도 revision, runtime/localization 세대, 품질 gate, correction sequence 및 0.5초 신선도에 묶인다. 정지·재시작 직후 이전 실행의 fresh 캐시도 차단한다.
- 후보는 정보 제시 전용이다. 자동 복사·적용·seed·정합·goal 전송이 없다. 기존 수동 geometry API는 후보 provenance를 재검증하는 자동 적용 API가 아니므로 이후 자동 적용 기능에는 별도 계약이 필요하다.
- ③ Nav2, ④ INITIAL POSE, ⑦ GOAL POSE의 준비 패널 중복 버튼을 일반 안내로 교체했다. 기존 하단 조작부와 ⑤ 명시적 정합 버튼, 기존 안전 gate를 유지했다. 부족 사유는 한글로 표시하고 상세 코드·시각·SHA·세대는 펼침 항목에 보존한다.
- 준비 입력 요청은 지도·교정 증거를 매번 다시 검증한다. 한 요청 안에서 중복하던 검증을 2회에서 1회로 줄였고 요청 간 증거 캐시는 추가하지 않았다. UI의 별도 기존 상태 조회까지 총 2회이므로 현장 부하·간헐 지연이 해결됐다는 뜻은 아니다.
- 전체 Python 3,198건: 최초 API 목록 기대치 미갱신으로 1건 FAIL, 2건 skip. 새 GET을 명시한 테스트 계약만 보정한 후 전체 재실행 **3,196 PASS / 2 skip / 0 FAIL**, 100.812초. 전후 코드 해시 동일 확인.
- Node 78 PASS, 프론트 문법 113 모듈 PASS, 모의 서버 E2E 12 PASS, secret scan 및 diff check PASS. 합성 검사와 브라우저 fixture는 실제 센서·TF·주행의 증거가 아니다.

## 장비 실행본과 지도·설정

12:59 KST C1.3 W02 완료 기준:

- 실행 SHA `4f90612379705b7b7c8c86cca99941266e3ae611`, PID `24983`, cwd `/home/unitree/robot-scope-releases/robot-scope-4f9061237970`.
- 새 release의 정규 소스 2,261개 경로 집합·mode·hash 및 app.js/navigation.js/index.html/preparation.js 실제 HTTP hash 일치.
- 지도·주석 125개와 설정 8개를 비공개 백업했다. selector의 release 경로 변경을 제외한 보호자료는 보존했다. 백업 tar의 정규 파일 집합·중복·내용 hash를 검증했다.
- 3D `map1`: ID `49ea555eea2f4ca1adaea223`, revision `c9ad9bcc4c8b7c02a47a0db5822707853110b60cb4b9ef837e42b0c32e3c823e`.
- 2D `map1_2D`: ID `2fc7070075fd522860e67480`, revision `f691b8e98e81de784c89f98127de9f4ccff4aa487c76747b860bdd70a523cc76`.
- P1/P2 annotation revision `c639ebe083cd57a0dd1dcbe61703cecc08eff51e4a6974fd10ef75a95d7a345a` 보존.
- 교정 SHA `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226` 보존. 주행 설정 revision `9a47e9d4a6c0d2b5beb0664cc1370a7bf6b70d647418815c5381f196d335645a`: 속도 0.5 m/s, XY 0.05 m, yaw 0.1 rad, progress radius 0.05 m, controller 10 Hz 변경 없음.
- 재시작 후 요청한 지도 쌍을 한 번 복구했다. generation `b64ebca592b64ca7bd614f9eaebcc2b3`, pair valid, activation `NEXT_NAVIGATION_START`. **준비 선택이며 실행된 Nav2 지도나 정합이 아니다.** geometry/seed null, `INITIAL_HEIGHT_TILT_REQUIRED`, can_start=false.
- Nav2/goal idle, lease inactive, deadman false, 명령 0, 관측 STOPPED. bridge active로 관측 시작 사전 항목에 `CONTROL_BRIDGE_NOT_INACTIVE`가 표시됐다.
- 설정 정책은 `ALL_DIRECTION_BASELINE`; 운영 matcher는 실행되지 않았다. 후방·측면 후보는 기존 NOT_ADOPTED 상태 보존. 이번에 FAST-LIO·가중치·센서 교정·주행 허용 기준을 바꾸지 않았다.

## 조회 측정 및 남은 원인

배포 전 선택 pair status loopback 3회: 0.5438 / 0.5635 / 0.5439초. 배포 후 새 preparation-inputs loopback 3회: 0.7147 / 0.5913 / 0.5728초, 전부 HTTP 200. 서로 다른 API의 소표본이므로 직접 성능 개선율이나 간헐 timeout 해결로 해석하지 않는다.

현재 API는 관측 미실행, Nav2 job 없음, 지도 절대 높이·중력 관계 미확인을 구분했다. 센서의 상대 z·roll/pitch 또는 사용자가 찍는 XY/yaw만으로 지도 기준 z·roll/pitch가 입증되지는 않는다. 과거 HIGH_RESIDUAL/원점/구·신 지도 비교를 다시 조사하지 않았다. 가짜 0이나 이전 seed로 준비 단계를 통과시키지 않았다.

## 다음 담당과 사용자 입력

C1.4는 사용자 정지 확인 후 W03의 관측 1회와 원상 복구를 완료했다. 동일 시각 점군·자세 및 관측계 본체 참고값은 PASS, 지도 기준 초기 geometry와 실제 운영 연결은 BLOCKED다. 관측은 약 25.4초에 정상 종료 요청했고, bridge·source 선택 정책을 복구했다. 보호 파일 133개의 해시 집합은 동일했으며 점군 source의 in-memory origin 표시만 `persisted`에서 `user`로 바뀌었다. [W03 실제 증거](W03_SENSOR_EVIDENCE.md)를 참조한다. Nav2·초기 위치·정합·goal·물리 이동 명령은 없었다.

C0의 후속 결과 회수 공백을 확인해 처음에는 2분 주기 후속 확인을 설정했다. 이후 사용자의 직접 지시로 해당 자동화는 PAUSED로 바꾸고, 하위 채팅이 완료 결과를 C0에 직접 보내는 방식으로 전환했다. C1.1은 최초 geometry와 실행 후 후보 사이의 순환 의존 재현 및 최소 연결 계약, C1.2는 배포된 실제 UI 검증, C1.3은 CI와 응답 지연 원인 분석, C1.4는 전역 후보의 좌표·세대 전달에 대한 독립 검토를 담당한다. 전역 정합의 이력용 IMU 후보를 현재의 확정된 본체 위치 또는 운영 ready 상태로 취급하지 않는다. 실제 운영의 정지/dwell·독립 3스캔·겹침·TF/source 품질 검사를 유지한다.

사용자 현재 위치 입력이나 실제 주행 감독이 필요한 이후 단계는 배정된 하위 채팅이 자기 Codex 대시보드에서 직접 요청한다. C0는 단일 장비 소유권을 관리한다. 같은 유효 시험창 안에서 중복 승인을 요구하지 않으며 과거 승인을 재사용하지 않는다.

## 복구

이전 bb77 release를 보존했다. 비공개 백업은 `/home/unitree/robot-scope-backups/c0-navigation-pair-4f9061237970-20261031/`에 있다. 기존 지도·교정·센서·주행 설정을 덮어쓰지 않는다. 필요 시 현재 idle·lease·관측·lifecycle 조건을 재확인하고 selector만 이전 release로 되돌린 뒤 정상 lifecycle API로 재시작한다. 이번에는 rollback을 실행하지 않았으므로 실제 rollback 성공을 주장하지 않는다. 기본 2D 모드 복구의 기존 gate도 유지했다.

원시 지도·센서 기록·교정 전문·인증정보 및 비공개 배포 receipt는 Git에 포함하지 않았다.
