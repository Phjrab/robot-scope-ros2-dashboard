# C0 후속 — 지도 조합·단계별 주행 준비 결과

**지도 선택·준비 구성 적용과 배포·비이동 차단 검사는 PASS다. 상태 조회의 간헐적 시간 초과는 남아 있어 응답성은 FAIL로 기록한다. 현재 초기 본체 높이·roll/pitch가 확인되지 않아 실제 저장 지도 정합과 Nav2 이동은 BLOCKED다.** 최종 준비 지도는 `map1` / `map1_2D`이며 Nav2는 idle, 운영 matcher는 비활성이다. 준비 구성 적용을 위치추정·주행 성공으로 계산하지 않는다.

이 기록은 사용자의 주행 화면 연결 지시 이후 결과다. 가중치 구현 전에 동결한 [F00~F06 1차 결과표](CONTINUATION_RESULTS.md), [기존 지도 변환·추적 복구](EDITED_PCD_CONVERSION.md), [후방·측면 후보 비교](REAR_SIDE_COMPARISON.md)는 보존한다. PCD 편집·저장, 기존 2D Nav2, 계단·경사로 보행과 이전 수동 기록을 이번 PASS에 중복 계산하지 않는다. 과거 HIGH_RESIDUAL 원인·지도 원점·구/신 지도 RMSE 비교는 재조사하지 않았다.

## 구현·배포·현재 상태

| 항목 | 최종 확인 |
|---|---|
| C0 브랜치 | `review/20261030-c0-3d-field-sweep` |
| 코드·실제 배포 SHA | [`bb77befe4e788adf084b9c4ba2d411142157eff7`](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/bb77befe4e788adf084b9c4ba2d411142157eff7) |
| 실제 실행 경로 | `/home/unitree/robot-scope-releases/robot-scope-bb77befe4e78` |
| readback 시각·PID | 2026-10-31 21:41:14 KST · `140451` |
| 실행본 검증 | manifest의 **2,257개 파일** hash 일치, 실제 PID/cwd 일치, HTTP의 app.js/navigation.js/index.html 및 preparation.js hash 일치 |
| 지도·설정 보존 | 지도·주석 **125개 파일** 동일. 설정 **8개 중 7개** 동일, selector 1개는 `ROBOT_SCOPE_DIR` 경로만 변경 |
| 런타임 경로 | 기존 `.venv`와 `workspaces` 심볼릭 링크 대상 보존 |
| 서버 준비 구성 | generation `2ad929dfba2042c3ae64eef325940db6`, 정확한 `map1` / `map1_2D` 조합 |
| 실제 실행 | pipeline=`idle`, goal=`idle`, 실행 지도 없음, 운영 matcher 없음, runtime fresh=`false` |
| 제어 | lease inactive, deadman false, 선속도·횡속도·각속도 명령 모두 0 |
| 다음 의존 조건 | `seed_geometry=null`, `seed_T_map_imu=null`, `can_start=false`, `INITIAL_HEIGHT_TILT_REQUIRED` |

준비 구성의 activation은 `NEXT_NAVIGATION_START`다. 지도 선택은 보존됐지만 실행 source가 활성화됐다는 의미는 아니다. 방향 정책 설정은 `ALL_DIRECTION_BASELINE`; `REAR_SIDE_QUALITY_V1`은 코드 포함·비활성·`NOT_ADOPTED`를 유지한다. 이번 작업에서 FAST-LIO 상대 추정, 센서 설정, 교정, 후방 가중치, yaw tolerance, 속도, progress checker를 조정하지 않았다.

주행 설정 revision은 `9a47e9d4a6c0d2b5beb0664cc1370a7bf6b70d647418815c5381f196d335645a`다. 기존 사용자 저장값인 속도 `0.5 m/s`, XY tolerance `0.05 m`, yaw tolerance `0.1 rad`, required movement radius `0.05 m`, controller frequency `10 Hz`를 보존했다. 교정 파일 SHA256은 `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226`으로 유지됐다.

주행 화면에는 3D 위치추정 지도와 2D 경로 계산 지도 선택란을 추가했다. 화면 선택, 서버 준비 구성, 실제 실행 지도를 구분하며 선택만으로 센서 실행·정합·목표 전송을 하지 않는다. 서버는 정확한 ID/revision과 변환 계보·좌표 관계를 확인하고 검증된 본체·센서 교정 및 기존 TF 발행 경로를 재사용한다. 원본 교정 파일을 지도 조합별로 덮어쓰지 않는다.

준비 과정은 ① 지도 연결 → ② 초기 높이·기울기와 교정 → ③ Nav2·센서 입력·노드·TF → ④ INITIAL POSE → ⑤ 명시적 정합 시작 → ⑥ 실제 추정·주행 조건 → ⑦ 별도 목표 전송으로 나뉜다. 부족 항목마다 현재 내용·필요 정보·해결 방법을 표시한다. 재검증 실패는 해당 단계부터 표시하고, 초기 높이·기울기 재확인은 ②부터 재개한다. Nav2 시작 과정에서 준비되는 센서 입력은 ③에서 실제 수신을 검사하며 ②에서 관측됐다고 처리하지 않는다.

INITIAL POSE는 사용자 입력 점·방향으로 보존한다. 실제 접수된 값만 같은 지도·실행·위치추정 세대에 복원하며 복원이 재전송을 일으키지 않는다. 로봇 URDF는 저장 지도 정합으로 추정한 본체 위치·6D 자세를 사용한다. 오래된 추정은 마지막 위치와 오래된 상태로 표시하고 목표 전송을 차단한다. 초기값 점·추정 로봇·목표를 분리한 동작은 소프트웨어 회귀에서 확인했으며, 이번 실제 센서 정합 결과로 확인한 것은 아니다.

동일 시각 현재 스캔·FAST-LIO 자세를 사용하는 기존 저장 지도 정합 엔진에 명시적 초기값 접수와 정합 시작을 연결했다. 누적 지도점을 새 독립 관측으로 사용하지 않으며 기존 TF 권한·품질·source·stop/dwell 검사를 유지한다. 실제 장비의 지속 보정 횟수·잔차·겹침·신선도·Nav2 TF 반영은 초기 정보 부족으로 미검증이다. 정합 잔차를 실제 위치 정확도로 보고하지 않는다.

## 지도 식별과 보존

다음 이름·ID·revision을 최종 서버 catalog와 준비 구성 양쪽에서 확인했다.

| 역할 | 이름 | ID | revision |
|---|---|---|---|
| 3D 위치추정 | `map1` | `49ea555eea2f4ca1adaea223` | `c9ad9bcc4c8b7c02a47a0db5822707853110b60cb4b9ef837e42b0c32e3c823e` |
| 2D 경로 계산 | `map1_2D` | `2fc7070075fd522860e67480` | `f691b8e98e81de784c89f98127de9f4ccff4aa487c76747b860bdd70a523cc76` |

`map1`은 18,166점이고 PCD SHA256은 `930e7be693eac04fabeed0974031b0dccef4351c2365b6abd274fa4646be191c`다. 변환 family ID는 `3df9ead4ab40285d7d687279`, 명시된 좌표 관계는 `camera_init` → `map`의 `planar_xy_identity`다. 이름이 같다는 이유로 좌표 관계를 추정하지 않는다.

P1/P2를 포함한 주석 revision `c639ebe083cd57a0dd1dcbe61703cecc08eff51e4a6974fd10ef75a95d7a345a`와 두 점의 존재를 최종 확인했다. 주석 파일 hash도 보존됐다. 이름 변경으로 ID/revision이 바뀌면 ①부터 재검증하며 이전 지도 목표를 새 지도에 자동 이식하지 않는다.

## 이번 전체 결과표

| ID | 항목 | 구현 | 배포 | 소프트웨어 비이동 검증 | 실제 장비 비이동 검증 | 실제 이동 |
|---|---|---|---|---|---|---|
| N01 | 3D·2D 선택·계보 검증·준비 구성 적용 | PASS | PASS | PASS — 잘못된 조합·revision·이름 변경 차단 | **PASS — 최종 실제 UI 적용 및 정확한 지도·세대 readback**. 최초 timeout은 아래 이력 보존 | 해당 없음 |
| N02 | 부족 정보 표시·단계 재개·초기 높이/기울기 | PASS | PASS | PASS — 빈 값/명시적 0 구분, 새 실행 재확인, 의존 단계 표시 | **차단 동작 PASS / 입력 준비 BLOCKED** — 현재 높이·roll/pitch 없음, 시작 요청 409로 거절 | 해당 없음 |
| N03 | INITIAL POSE 점·추정 로봇·목표 분리 | PASS | PASS | PASS — 동일 실행 복원, 세대 불일치 차단, stale 표시 | **BLOCKED — N02 의존**, 실제 초기값 접수·정합 추정 없음 | NOT_RUN |
| N04 | 명시적 정합·지속 보정·Nav2 TF 연결 | PASS | PASS | PASS — 실제 receipt와 source·품질 검사 유지 | **BLOCKED — N02 의존**, 보정 횟수·잔차·겹침·TF 반영 미검증 | NOT_RUN |
| N05 | 실제 3D Nav2 P1 도착·측정 정지 | 기존 경로 보존 | PASS | 기존 gate 회귀 PASS | **BLOCKED_DEPENDENCY — N04 미충족** | NOT_RUN |
| N06 | 실제 success·정지/dwell→시험 녹색→P2 출발·종료 | 기존 경로 보존 | PASS | 기존 버튼·중복/오래된 허가 회귀 PASS | **BLOCKED_DEPENDENCY — 실제 도착·정지/dwell 근거 없음** | NOT_RUN |
| N07 | 현재 운영 위치추정 경사로 연속성 | 기존 운영 엔진 보존 | PASS | 이전 후보 비교는 별도 인수 | **BLOCKED_DEPENDENCY — 운영 matcher 비활성** | NOT_RUN, 새 기록 없음 |
| N08 | 정상 대기·기존 모드 복구·설정 보존 | PASS | PASS | 기존 모드 복구 회귀 PASS | **PASS — idle·제어0·지도/설정 보존**. a7 실행에서 해제/재적용 실제 확인, 최종 조합 복원 | 이동 종료 시험 NOT_RUN |
| N09 | 상태 조회 응답성·오류 표시 복구 | 최소 수정 완료 | PASS | 조회 오류 후 자동 복구 회귀 PASS | **FAIL — 간헐 10초 timeout 잔존**, 이후 성공 표본과 구분 | 해당 없음 |

성공한 Nav2 시작 **0회**, INITIAL POSE 전송·정합 시작·goal·자세 명령·실제 이동 **0회**다. 단, 부족 정보 차단을 확인하는 **Nav2 시작 API 요청 1회**는 `409 INITIAL_HEIGHT_TILT_REQUIRED`로 거절됐으며 실제 pipeline은 시작되지 않았다. 잘못된 지도 조합 요청도 거절됐고 기존 준비 선택이 보존됐다. 정밀 도착 오차와 stop-and-go 성공은 각각 미측정·미검증이다.

사용자는 현재 초기 높이·기울기 확인값이 없음을 답변했다. 임의의 0이나 과거 값을 채워 ②를 통과시키지 않았다. 이전 이동 승인을 재사용하거나 stop/dwell/source 검사를 강제로 통과시킨 작업은 없다.

## 비이동 회귀와 실장비 근거

| 검사 | 결과 | 범위·한계 |
|---|---|---|
| 최종 Python 전체 | **3,186건 · OK, skip 2** | 서버 API·지도 묶음·실행·기존 안전 경로 포함 |
| JavaScript 전체 직접 실행 | **78개 파일 PASS** | 준비 모델·표시 문맥·기존 모드 포함 |
| 최종 준비 화면 브라우저 회귀 | **6건 PASS** | 단계·부족 정보·문맥·실행 잠금·stale·조회 오류 복구 |
| 준비 모델 단위 검사 | **12건 PASS** | 서버 누락 항목·재개 단계·문맥·차단 상태 |
| JavaScript 문법 | **113개 모듈 PASS** | 최종 배포 정적 모듈 |
| 잘못된 실제 지도 조합 | **PASS — HTTP 409 `MAP_PAIR_LINEAGE_MISMATCH`** | 기존 generation과 선택 유지 |
| 초기 높이 없는 실제 시작 요청 | **PASS — HTTP 409 `INITIAL_HEIGHT_TILT_REQUIRED`** | 최종 pipeline/goal idle, 성공한 Nav2 시작 0 |
| 최종 읽기 전용 readback | **기록된 모든 체크 PASS** | 2,257 source 파일·HTTP 자산·125 지도·8 설정·현재 pair·제어 상태. 전체 응답성 해결이나 실기 PASS를 뜻하지 않음 |
| 최신 GitHub CI | **진행 중·전체 결과 미확정** | [bb77 실행 41202027308](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41202027308). 로컬 PASS를 원격 전체 PASS로 대체하지 않음 |

최초 `36525d6`의 GitHub CI에서 브라우저 검사 5건이 실패했다. 관련 fixture와 INITIAL POSE를 URDF로 기대하던 검사를 `a7fbe19`에서 갱신했고 관련 로컬 11건을 PASS했다. 이 실패 이력을 삭제하지 않는다. [a7 실행 41200931966](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41200931966) 및 최신 bb77 실행의 전체 CI 결과는 최종 확인 시 별도 갱신한다.

브라우저 회귀는 모의 HTTP 서버를 사용한 소프트웨어 검사다. 실제 센서·ROS·로봇 소비자가 없으므로 지속 정합이나 실제 주행 성공을 대신하지 않는다. 실제 장비 UI에서는 준비 구성 적용과 ② 부족 정보 표시를 확인했다.

비공개 증거는 `navigation-pair-status-python-full.log`, `navigation-pair-final-readonly-private.json`, `navigation-pair-negative-probes-private.json`, `navigation-pair-deployed-missing-geometry.png`에 보관했다. raw 지도·센서 기록·위치 좌표·교정 전체·비밀번호·실장비 화면은 이 공개 보고서나 Git에 넣지 않는다.

## 실패 원인과 수정·비교 — 결과표 이후 별도 기록

### 요청 지연과 최소 연결 수정

| 실행본 | 관측·결과 | 수행한 수정·판정 |
|---|---|---|
| [`36525d6`](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/36525d64a5c2233d9eb81e6d085fa7631b15c7ab) | 최초 실제 pair 적용 요청 timeout | **FAIL 이력 보존**. 독립 호출·스택·catalog 경로를 조사하고 중복 전체 catalog 접근과 잠금 대기를 관측 |
| [`a7fbe19`](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/a7fbe197f3b7b022ea2bbbd8ea8bddf577302978) | 실제 pair 적용 **4.05초 성공**, 기존 2D 모드 해제·재적용 UI 성공. 상태 조회는 약9.7초 및 timeout 발생 | 한 요청의 catalog 확인을 재사용하도록 변경. **적용 기능 PASS, 조회 응답성 미해결** |
| [`bb77bef`](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/bb77befe4e788adf084b9c4ba2d411142157eff7) | 선택한 경로를 직접 재검증하도록 수정, UI 조회 오류 자동 복구 추가. 배포·적용 직후 조회 **2건은 각10초 timeout**, 세 번째 **1.323초 성공** | 최종 UI 준비 구성 적용과 ID/revision 확인 PASS. **간헐 지연 FAIL 잔존**, 완전 해결로 판정하지 않음 |

최종 bb77에서 후속 상태 조회 5건은 각각 **0.7399 / 0.9471 / 4.0131 / 3.2725 / 0.9606초**에 HTTP 200으로 응답했고 동일 generation, `valid=true`, `can_start=false`였다. 별도 최종 읽기 전용 검사에서 operational 상태 조회는 **5.8439초**였다. 성공 표본만으로 앞선 timeout을 지우거나 응답 시간 보장을 주장하지 않는다.

잘못된 조합은 3.9085초에 409, 초기 높이 없는 시작 요청은 9.8139초에 409로 거절됐다. 차단 결과는 확인됐지만 이 지연도 남은 응답성 문제에 포함한다. 정확한 전체 서버 지연 원인은 확정하지 못했다. 반복 catalog 접근을 줄인 효과와 서버 전체 지연의 근본 원인 해결은 구분한다.

최종 상태 조회는 선택된 PCD의 전체 SHA와 manifest, 2D revision·format·family, 교정 SHA를 매번 다시 확인한다. 오래된 PASS 결과를 그대로 반환하는 방식이 아니다. 2D 전체 파일 hash 검증은 기존 job snapshot 단계에 유지한다. 이름 변경·revision 변경·교정 변경의 재검증과 기존 품질 기준을 완화하지 않았다.

### 초기 정보 부족과 실기 의존 조건

본체 원점의 지도 좌표 높이는 바닥 높이와 다르다. 현재 검증된 관측 또는 사용자 확인값이 없으므로 초기 높이·roll/pitch를 요구하는 ②가 미완료다. 이미 준비된 지도·교정·P1/P2는 보존하고, 이 입력이 확보되면 ②부터 재개한다.

현재 정합 엔진은 위치·방향을 포함한 6D 초기값으로 정합을 시작하지만, 높이·roll/pitch를 사람이 수동 입력하는 방식 자체가 필수인 것은 아니다. 센서 관측을 먼저 준비하고 출처·신선도·좌표 관계가 검증된 z/roll/pitch를 자동으로 제시하는 경로는 **이번에 미구현**이다. 현재 구현은 ② 수동 geometry 확인을 ③ 센서 준비보다 먼저 요구하므로 이 순서에는 개선 여지가 있다. 현재 사용자 미확인값을 0으로 처리하지 않고 차단하는 상태를 유지한다.

이후 정지 상태에서 Nav2 시작·센서 입력·노드/TF → 사용자 INITIAL POSE 접수 → 명시적 정합 → 보정 횟수·공통 잔차·겹침·신선도·Nav2 TF 반영을 먼저 확인한다. 실제 이동 직전에는 현재 현장 준비·정지/회수 수단·새 P1→dwell→시험 녹색→P2 범위를 한 번 확인한다. 같은 유효 시험창의 하위 단계마다 승인을 반복 요청하지 않는다. 운영 경사로 기록은 현재 source의 부족한 증거를 얻어야 할 때만 추가한다.

실기 차단 중에는 독립적인 표시·부족 정보·잘못된 조합 차단·설정 보존·회귀·배포 검증을 진행했다. 반복 주행이나 주행 파라미터 변경은 수행하지 않았다.

## 복구 상태

현재 최종 준비 구성은 `map1` / `map1_2D`로 복원돼 있고, 높이·기울기 미입력 때문에 시작이 차단된 정상 idle 상태다. 지도·교정·센서·주행 설정 데이터의 원복은 필요하지 않았다. 비공개 배포 백업은 `/home/unitree/robot-scope-backups/c0-navigation-pair-bb77befe4e78-20261031`에 보존했다.

**기존 2D 모드로 복구**는 정상 idle에서 준비 구성을 해제한다. 이 UI의 해제·재적용은 a7 실행본에서 실제 확인했으며 최종 bb77에서는 pair 선택 상태가 복원됐음을 readback했다. 해제나 화면 복원 자체는 Nav2 재시작·초기 위치 재전송·자동 출발을 하지 않는다.

직전 검증 release `/home/unitree/robot-scope-releases/robot-scope-a7fbe197f3b7`을 남겼다. 코드 rollback은 정상 STOP·idle·lease inactive·명령0·lifecycle 차단 없음 확인 후 selector만 해당 release로 변경하고 정상 service restart API를 사용한다. 현재 지도·주석·교정·주행 설정은 보존하며 PID/cwd·HTTP 자산·source·보호 파일 hash를 다시 확인한다. **최종 bb77에서 a7로의 rollback을 실제 실행한 것은 아니다.**

전체 C0 실기는 미완료다. 남은 항목은 초기 높이·기울기 근거 확보와 검증된 센서 관측의 자동 제시 경로, 상태 조회의 간헐 지연 원인 규명, 실제 저장 지도 보정·Nav2 반영, P1 정지·녹색 버튼 P2, 현재 운영 경사로 연속성과 최신 CI 전체 결과 확인이다.
