# C0 충전 후 재개 프롬프트 — 2026-10-31

아래 내용을 충전 후 같은 C0 채팅의 후속 지시로 사용한다. 다른 채팅을 만들지 않는다.

## 재개 지시

기존 C0 작업과 `review/20261030-c0-3d-field-sweep` 브랜치에서 이어서 구현·검증해줘. 먼저 이 파일과 같은 폴더의 `NAVIGATION_PAIR_RESULTS.md`, `CONTINUATION_RESULTS.md`를 읽고, 현재 장비 실행본과 연결 상태를 새로 확인해. 아래 과거 readback을 현재 상태로 단정하지 마.

사용자가 배터리 충전 때문에 2026-10-31 21:50 KST 작업 중지를 요청했다. 그 이후 새 기능 구현·배포·관측 시작·Nav2 시작·이동을 진행하지 않았다. 작업을 이어갈 때도 실시간 상태를 먼저 읽어줘.

현재 지도·교정·센서 설정·주행 파라미터와 확인된 기능을 보존해. 과거 HIGH_RESIDUAL, 지도 원점, 구·신 지도 RMSE 비교는 재조사하지 마. 현재 품질 판단에 필요한 잔차·겹침은 사용하되 실제 위치 정확도로 보고하지 마. C1~C7/D1~D3 통합은 범위 밖이다.

## 다음에 먼저 구현할 변경 — 아직 미구현·미배포

### ② 센서 관측 우선 준비

현재 화면은 초기 높이·기울기를 수동 확인한 다음 Nav2를 시작하도록 막혀 있다. 이를 다음 구조로 바꿔줘.

1. 비이동 센서 관측을 먼저 준비한다. 지도 선택만으로 관측·정합·주행을 자동 시작하지 않는다.
2. 현재 관측에서 확인 가능한 값은 출처·센서 시각·신선도·좌표 기준·교정 근거와 함께 자동 제시한다.
3. 확인할 수 없는 값만 개별 부족 항목으로 남긴다. 모든 항목을 한 덩어리의 “준비 대기”로 처리하지 않는다.
4. 사용자에게 확인된 본체 지도 높이(z)·roll·pitch 값은 **없다**. 0이나 과거 값을 채워 완료 처리하지 않는다.
5. FAST-LIO 상대 높이를 지도 절대 높이로 사용하지 않는다. 센서 좌표축을 본체 좌표축으로 간주하지 않는다. 지도와의 중력·자세 관계가 검증되지 않았다면 상대 자세는 참고값으로 구분한다.
6. 현재 값이 없거나 오래됨, 다른 source·지도·revision·실행 세대, 시각 불일치, 교정 부족을 구분해서 표시한다.
7. 자동 제시만으로 seed 전송·정합·goal·출발을 일으키지 않는다. 적용 시에도 서버 검증과 기존 안전 조건을 유지한다.
8. 관측 전용 실행과 Nav2가 센서·TF를 중복 점유하지 않게 한다. 관측 종료와 Nav2 시작 사이의 실행 세대·값 신선도를 다시 확인한다. 기존 ownership·bridge·stop/dwell/source 검사를 우회하지 않는다.

설계 감사만 진행했고 코드는 아직 작성하지 않았다. 다음은 검토 후보이며 실제 코드와 장비 근거를 확인해서 구현할 것:

- 기존 `FastlioObservationSession`과 `/api/v1/observations/fastlio`의 GET/start/stop을 재사용한다. `start`는 bridge inactive·작업 점유·정상 lifecycle을 검사한다. snapshot의 `can_start=true`만으로 모든 시작 조건이 충족됐다고 단정하지 않는다.
- 읽기 전용 `/api/v1/navigation/operational-3d/preparation-inputs` 후보: 현재 구성 generation, observation session, pose/cloud의 출처·동일 시각·신선도, 참고 본체 자세, z/roll/pitch별 자동 후보와 부족 사유를 반환한다.
- 신선한 `/Odometry`와 검증된 `T_imu_base`로 얻는 본체 자세는 우선 관측 좌표계의 참고값이다. 저장 지도 값으로 사용할 좌표 관계가 별도로 필요하다.
- 같은 지도·revision·실행에 속하고 신선도·품질 검사를 통과한 실제 지도 추정값이 있으면 자동 후보로 제시할 수 있다. 시작 시 없는 지도 위치를 이 경로가 이미 제공한다고 가정하지 않는다.
- 정확한 스캔 시각의 기존 pose pairing 경로를 재사용하고 원시 점군 전체를 상태 API에 실어 보내지 않는다.

### ③·④·⑦의 중복 조작 버튼 제거

단계별 준비 패널에 있는 다음 버튼은 제거하고 하단 조작부를 안내하는 일반 텍스트로 바꿔줘.

- ③ Nav2 시작
- ④ INITIAL POSE 지정
- ⑦ GOAL POSE 지정

아래의 기존 주행·초기 위치·목표 설정 부분에서만 실제 조작하게 해줘. 자동 스크롤·중복 이벤트·두 번 전송·서로 다른 상태를 만들지 마. 준비 패널은 검사 결과와 다음 조건을 표시하고 하단 조작부와 같은 서버 상태를 사용해야 한다. ⑤ 명시적 정합 시작과 지도 연결은 별도 기능으로 유지한다.

변경 대상 후보는 `robot_dashboard/static/features/navigation/preparation.js`, 관련 JS/E2E 검사 및 `app.js`의 불필요한 action callback 연결이다. 이 변경도 아직 작성·배포하지 않았다.

## 중단 당시 확정 상태

- 작업 폴더: `/home/desktop1/Documents/ChatGPT/robot/c0-field-sweep-20261030`
- GitHub: `https://github.com/Phjrab/robot-scope-ros2-dashboard`
- 브랜치: `review/20261030-c0-3d-field-sweep`
- 중단 직전 Git HEAD: `ed559ca6146ad44b5a7f599073ca3221f69c148b` — 기존 결과 보고서 커밋, push 완료.
- 실제 배포 코드: `bb77befe4e788adf084b9c4ba2d411142157eff7` — 문서 HEAD와 구분할 것.
- 실행 경로: `/home/unitree/robot-scope-releases/robot-scope-bb77befe4e78`
- 마지막 확인 PID: `140451` — 충전·재부팅 후 이 PID를 재사용하지 말 것.
- 이 인계 문서 작성 전 작업 트리는 clean. 위 두 후속 변경의 미커밋 코드/테스트는 없음.
- 지도·주석 125파일 보존. 설정 8파일 중 selector 1개의 release 경로만 변경, 나머지 7파일 동일. source 2,257파일과 실제 HTTP 자산 hash 확인.
- 마지막 API readback: Nav2 pipeline/goal idle, lease inactive, deadman false, 모든 속도 명령 0, 관측 서비스 STOPPED/inactive. 이는 API 상태이며 충전 이후 현장 상태 증거로 재사용하지 않는다.
- 제어 bridge 서비스는 직전 읽기에서 active/running이었다. 임의로 중단하거나 안전 검사를 무시해 관측기를 켜지 말 것. 필요한 정상 전환을 검증된 경로로 처리한다.
- `/pose`는 직전 읽기에서 `/utlidar/robot_odom`(odom→base_link)이었다. 이를 FAST-LIO `/Odometry` 관측으로 오인하지 않는다. 점군은 seq 0·source_points 0, FAST-LIO 관측 서비스는 정지 상태였다.
- 현재 준비 구성은 map1/map1_2D였고 generation은 `2ad929dfba2042c3ae64eef325940db6`. 실제 운영 matcher는 비활성, runtime fresh=false. 재시작하면 준비 선택은 재확인해야 한다.
- `seed_geometry`와 `seed_T_map_imu`는 null. 자동 초기값·정합·goal 전송 없음.

## 지도·설정 식별값

| 역할 | 이름 | ID | revision |
|---|---|---|---|
| 3D 위치추정 | map1 | 49ea555eea2f4ca1adaea223 | c9ad9bcc4c8b7c02a47a0db5822707853110b60cb4b9ef837e42b0c32e3c823e |
| 2D 경로 계산 | map1_2D | 2fc7070075fd522860e67480 | f691b8e98e81de784c89f98127de9f4ccff4aa487c76747b860bdd70a523cc76 |

서버의 실제 이름·ID·revision을 다시 확인한다. family ID `3df9ead4ab40285d7d687279`, 좌표 관계 `camera_init`→`map`의 `planar_xy_identity`. P1/P2 주석 revision `c639ebe083cd57a0dd1dcbe61703cecc08eff51e4a6974fd10ef75a95d7a345a` 보존. 이름이나 동일 frame 문자열만으로 좌표 일치를 단정하지 않는다.

교정 SHA256 `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226`. 현재 map 높이·중력 정렬을 증명하는 값은 확인되지 않았다. 교정의 과거 operator seed(z=0)는 현재 값으로 재사용하지 않는다.

주행 설정 revision `9a47e9d4a6c0d2b5beb0664cc1370a7bf6b70d647418815c5381f196d335645a`. 기존 사용자 저장값: 속도 0.5 m/s, XY tolerance 0.05 m, yaw tolerance 0.1 rad, progress radius 0.05 m, controller 10 Hz. 검증 중 연속 튜닝하지 않는다.

방향 정책 설정은 `ALL_DIRECTION_BASELINE`. 후방·측면 후보 `REAR_SIDE_QUALITY_V1`은 구현돼 있으나 NOT_ADOPTED/비활성이다. FAST-LIO 자체 수정으로 보고하지 않는다.

## 완료·실패·차단을 구분해서 인수

- PASS: map1/map1_2D 선택·계보 검증·준비 구성 적용, 부족 정보 표시, 잘못된 지도 조합 거절, 초기 높이 없는 Nav2 시작 거절, 지도·교정·P1/P2 보존.
- PASS(소프트웨어): 초기값 점/로봇 추정/목표 분리, stale·세대 불일치 차단, 명시적 정합 연결, 기존 안전 gate 회귀. 실제 센서·Nav2 검증으로 대체하지 않는다.
- FAIL 잔존: 상태 조회 간헐 지연. bb77 적용 직후 2건은 10초 timeout, 이후 5건은 0.7399/0.9471/4.0131/3.2725/0.9606초 성공. 완전 해결 아님.
- 수정된 부분: 반복 catalog 탐색을 줄이고 선택 파일은 매번 재검증. 조회 오류가 회복되면 화면의 조회 오류만 자동 해제. 적용 실패 오류는 유지.
- BLOCKED: 실제 저장 지도 지속 보정·Nav2 TF 반영, P1 도착·정지, 녹색 버튼→P2, 현재 운영 위치추정 경사로 연속성. 현재 초기값 근거가 없으며 실제 운영 matcher가 시작되지 않았다.
- 성공한 Nav2 시작·INITIAL POSE·정합 시작·goal·자세·실제 이동 명령은 모두 0회. 차단 확인용 Nav2 시작 API 1회는 HTTP409 `INITIAL_HEIGHT_TILT_REQUIRED`로 거절됨.
- 마지막 코드 검사: Python 3,186건 OK(skip 2), JS 78파일 PASS, 준비 화면 E2E 6건 PASS, 준비 모델 12건 PASS, JS 문법 113모듈 PASS. 최신 GitHub CI 전체 결과는 마지막 확인 때 진행 중이었다: https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41202027308

전체 1차 결과표와 독립 항목 우선 원칙을 유지한다. 특정 기능이 될 때까지 반복 주행하지 않는다. 실패는 증거를 남기고 독립 항목으로 넘어간다. PCD 편집·저장, 기존 2D Nav2, 계단·경사로 보행·기존 수동 기록은 처음부터 반복하지 않는다.

## 재개 순서·배포·복구

1. 동일 IP 연결과 실제 실행 SHA/PID/source/선택지도/TF·Nav2·제어/관측 상태를 짧게 읽는다. 이전 승인과 상태를 재사용하지 않는다.
2. ② 센서 우선 준비 및 ③④⑦ 텍스트 안내를 구현하고 의미 있는 회귀검사를 수행한다. 준비 상태 조회 지연은 별도 원인·검증 항목으로 관리한다.
3. 기존 C0 정상 backup·immutable release·service lifecycle 경로로 필요한 변경만 배포한다. 지도·교정·센서·주행 파라미터를 바꾸지 않는다.
4. 비이동 관측에서 출처·시각·좌표 관계·부족 항목과 하단 조작부 충돌 여부를 먼저 확인한다. 부족값이나 정합 품질을 가짜 값/완화된 기준으로 통과시키지 않는다.
5. 실제 이동 직전에 현재 현장 준비·충전 케이블 제거·통로·조종자·정지/회수 수단·새 시험 범위를 한 번 확인한다. 과거 두 목표/수동 5분 승인은 재사용하지 않는다. 같은 유효 시험창 하위 단계마다 승인을 반복하지 않는다.
6. 구현/배포/비이동/실제 이동 상태와 현재 정책·설정·복구 상태를 결과표와 GitHub에 기록한다.

private 증거 폴더: `/home/desktop1/Documents/ChatGPT/robot/c0-field-evidence-20261030/continue-20261031`.
현재 배포 백업: `/home/unitree/robot-scope-backups/c0-navigation-pair-bb77befe4e78-20261031`.
직전 release: `/home/unitree/robot-scope-releases/robot-scope-a7fbe197f3b7`.

다음 배포용 `build_pair_navigation_sensors_release.py` / `deploy_pair_navigation_sensors_release.py`가 private 증거 폴더에 준비돼 있다(BASE bb77). 구문검사만 했고 아직 빌드·업로드·실행하지 않았다. 재개 때 현재 실행본이 여전히 bb77인지 먼저 확인한다. 경로를 맹목적으로 재사용하지 않는다.

코드 rollback도 정상 idle·lease inactive·명령0·lifecycle 조건에서 selector를 직전 release로 변경하고 정상 restart API를 사용한다. 데이터는 보존한다. 원본 지도·교정 복원이나 강제 프로세스 종료는 임의로 수행하지 않는다.

비밀번호·키·원시 지도/점군·ROS bag·교정 전체·private 증거는 GitHub에 올리지 않는다. SSH 인증 정보는 이 프롬프트에 기록하지 않는다.
