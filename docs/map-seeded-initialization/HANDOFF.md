# I1 — 지도 클릭 초기값과 지역 정합

작성: 2026-10-27 KST. 독립 개발·검증 후 사용자의 배포 승인으로 실장비에 적용했다.

**지도 클릭/방향 → 실제 seed 기반 지역 ICP → 후보 비교 → 명시적 관측 기준점 적용을 구현했다.**
배포와 실제 정지 점군의 후보 계산·관측 기준점 적용을 확인했다. 세 번 중 두 번은
`NOT_CONVERGED`로 거부됐고 세 번째가 통과했다. 로봇 이동·운영 위치 적용은 `NOT_RUN`이다.

## 소스와 기존 작업 보존

| 항목 | 값 |
| --- | --- |
| 검토 브랜치 | `review/20261026-i1-map-seed` |
| 실제 검사한 구현 SHA | `f7c41d189a5f1766502b703bf72ae833a1f9051c` |
| 실제 장비 배포 SHA | `54721fe6dd33f73de81a08cfb2d241218056b003` |
| 최종 기준 main | `a79dc18b50a0cddee2056fe4748781cdca03aec9` |
| main의 실행 코드 기준 | `d6e3fe9675f31e436f5236b390e36e188934f473` |
| 기존 통합 branch HEAD | `7777f471654d6da0afd3580a870d80b7b0b3eb4d` |
| 구현 다음 commit | 이 문서·합성 화면만 추가. 실행 소스와 테스트는 위 구현 SHA와 동일 |

PR #3은 이미 병합됐다. 참고 SHA로 reset하지 않았다. 작업 중 추가된 `a79dc18`의
배포 문서 3개를 fast-forward로 반영했다. 독립 checkout에서만 편집했으며 원본
checkout의 `dashboard-polish.css`, `map_editor3d/editor.css` 사용자 변경을 보존했다.
L1의 연결 상실 이유·stale geometry 제거는 유지한다. source가 끊겨도 재사용 가능한
지도 prior 숫자는 보존하되 활성 관측과 계산 후보는 무효화하는 것이 이번 의도된 변경이다.
C4 개발 checkout/브랜치·기존 통합 브랜치를 수정하지 않았다.

## 사용법

1. Maps에서 저장 **3D 지도**를 고른다. 센서가 없어도 위치 초안은 지정할 수 있다.
2. **지도에서 초기 위치 지정**을 누른다. 기존 화면이 top view로 바뀐다.
3. 클릭 후 드래그로 방향을 정하거나, 첫 클릭은 위치·두 번째 클릭은 방향으로 사용한다.
   짧은 클릭은 방향 대기로 남는다. 기존 draft가 있으면 **기존 방향 유지**도 가능하다.
4. 모델/방향 끝 핸들을 드래그하거나 **다시 지정**으로 수정한다. 휠 확대,
   Shift/우클릭 이동을 유지한다. **취소 / Esc**는 이전 초안·숫자·카메라를 복원한다.
5. 관측 입력이 준비된 **정지 상태**에서 **이 주변에서 자동 정합**을 누른다.
   이 동작이 오래된/오프라인 draft를 현재 IMU pose에 연결하는 명시적 확인이다.
6. 주황 초기값, 파란 후보, 기존 활성 관측 위치를 비교한다. 이동량·방향 변화·Z 변화,
   RMSE·overlap·계산 시간·다른 장소 모호함 미검증 표시를 확인한 뒤 **제안 위치로 적용**한다.
   적용 직전 서버에서 fresh proposal을 다시 읽어 현재 odometry로 전파한다.

숫자 입력은 **기준점 설정 → 고급 좌표 수정**에 있다. 클릭·숫자·기존 프리셋은 같은
초안과 동기화되며 프리셋 저장 API/형식은 유지한다. 편집·프리셋 불러오기·전역/지역
계산 시작만으로 기존 정상 관측 기준점을 지우지 않는다. 현재 위치 적용은 별도 동작이다.

후보가 없거나 품질 검사를 통과하지 못하면 초안과 활성 관측은 유지한다. `OUTSIDE_SEED_BOUNDS`
후보는 원래 좌표로 비교 표시하며 적용을 막는다. **범위 넓히기**는 초안의 범위만 변경하고
다시 계산해야 한다. **기준점 설정 → 지도 전체에서 찾기**는 명시적으로 고르는 기존 경로다.
자동 전역 fallback, 결과 clamp, 먼 후보 자동 적용은 없다.

![합성 지도: 초기값·후보·현재 관측 분리](synthetic-scene.png)

![합성 입력: seed/후보 비교와 명시적 적용](synthetic-controls.png)

위 화면은 Playwright의 합성 입력이다. 화면의 `.02m / 90% / .35초`는 UI fixture 값이며
아래 실제 수치 solver 측정값이나 실장비 정확도가 아니다. Z=2.4m는 바닥 클릭을 IMU
높이로 바꾸지 않는 것을 확인하기 위한 의도적인 테스트 값이다.

## 실제 정합 연결

새 엔진이나 새 start endpoint를 만들지 않았다.

```text
RobotScene3D.screenToMapPlane → MapSeedDraft
  → POST /api/v1/observations/global-jobs
      search_mode=seeded_local, input_kind=fastlio_imu, seed={...}
  → GlobalObservationCoordinator의 기존 단일 job slot/capture/context fence
  → RegistrationWorker.solve → solve_prepared → prepare_seed → register_se3
  → GET /global-jobs/{job_id}/anchor-proposal
  → 사용자 적용 → 기존 LiveMapObservation.setAnchor
```

`seed`는 revision, 6개 pose 값, `FASTLIO_IMU`, metres/degrees, map frame,
높이 출처, xy/yaw/z/tilt 범위, source epoch/subscription 계약을 전달한다.
알 수 없는 필드·비유한 값·잘못된 단위·범위·raw input 조합을 거부한다.
동일 request_id의 다른 seed/지도/범위는 충돌이다. 입력 거부 후에는 수정한 값으로 새
request_id를 사용한다. 네트워크 결과 미확인 시에는 같은 요청 재확인이 기존 ID/seed를 유지한다.

시각 ts는 클릭 시각이 아니라 **정합 요청 시 신선한 현재 pose에 seed를 확인한 시각**이다.
캡처 tc는 ts 이상인 점군과 정확히 같은 source stamp의 odometry가 있을 때만 사용한다.

```text
T_M_O_seed      = T_M_I(ts) × inverse(T_O_I(ts))
T_M_I_init(tc)  = T_M_O_seed × T_O_I(tc)
T_M_O_candidate = T_M_I_refined(tc) × inverse(T_O_I(tc))
T_M_I(now)      = T_M_O_candidate × T_O_I(now)
```

`/cloud_registered`는 이미 odometry 좌표다. 기존 `capture_registered_imu`에서
`inverse(T_O_I(tc))`를 한 번 적용해 IMU frame으로 재표현한다. LiDAR extrinsic을
다시 적용하지 않는다. source/지도 revision/job/draft revision/stamp 연결이 달라지면
이전 결과가 새 초안을 덮거나 적용되는 것을 차단한다. 센서 timestamp는 대체하지 않는다.

### 범위·평가·처리량

- 기본값: XY 반경 **0.75m**, yaw **±25°**, Z **±0.30m**, roll/pitch 각각 **±10°**.
  기존 correspondence gate 0.75m와 coarse-to-fine 경로를 활용한 UI 초기값이다.
  실측 안전 범위나 이 범위 전체의 수렴 보장이 아니다.
- 단일 초기값 coarse-to-fine SE3로 6개 변수를 보정한다. 최종 해와 캡처 시각 seed의
  XY norm/Z/yaw/roll·pitch 차이를 제한한다. yaw 차이는 ±180° 경계를 wrap한다.
  solver 내부의 매 반복을 hard constrain한 exhaustive 탐색은 아니다.
- target 반경 = `max(norm(scan point)) + hypot(xy_bound, z_bound) + 0.75m`.
  로봇 중심의 허용 반경만 남겨 관측 벽을 잘라내지 않는다. 정합 대상의 실제 스캔 범위를 포함한다.
- full cached registered query를 그대로 최종 평가한다. 추가 query downsample은 없다.
  입력은 이미 Dashboard 캐시 정책의 sampling을 포함할 수 있다. raw sensor archive가 아니다.
- 평가 범위는 `FULL_CAPTURE_AGAINST_PRIOR_REACHABLE_SCAN_FOOTPRINT`다.
  full-map/global score와 동일한 의미로 비교하지 않는다.
- 기존 품질 기준 유지: RMSE ≤0.05m, overlap ≥0.6, 수렴, 입력·matched geometry ≥0.002,
  최소 60점. 기존 provisional 0.10m 정책을 지역 초기화 성공으로 확대하지 않았다.
- 기존 수치 경로 한도: query 60–4,000점, 선택 target 60–100,000점.
  full-map snapshot의 기존 1,000,000점/32MiB 한도도 유지한다. 한도를 넘으면 명시적으로
  거부하고 몰래 sampling/quality 완화하지 않는다. 매우 큰 지도는 이 경로에서 지원되지 않을 수 있다.
- 기존 취소 가능한 job owner를 재사용한다. 수치 계산은 기존 별도 프로세스에서 하고
  취소 시 IPC 대기를 깨워 terminate/reap한다. 정리 전에는 동일 owner의 새 작업을 받지 않는다.
  0.6초 제한·TTL 완화·무제한 queue/thread를 추가하지 않았다.
- 단일 seed만 시험하므로 다른 장소의 모호함은 **미검증**이다. `hypotheses_tested=1`,
  `ambiguity_unresolved=true`를 보존한다. RMSE가 작아도 정답/절대 정확도라고 표시하지 않는다.

XY는 명시적인 작업 평면에 역투영한다. 기존 호환 prior의 Z/roll/pitch를 보존하며,
호환되는 현재 IMU 위치가 없으면 숫자/기본값을 **높이·자세 근사**로 표시한다.
바닥 Z를 IMU Z로 사용하지 않는다. 미리보기는 IMU=본체 가정의 근사 실루엣이고,
telemetry robot과 별도 레이어다. 본체 extrinsic 검증이나 물리 이동 명령으로 연결하지 않는다.

## 수치·회귀 검증

| 검사 | 결과 |
| --- | --- |
| Python 전체 unittest | 2,845 실행, 실패/오류 0, 14 SKIP (106.431초) |
| 신규 실제 수치/API 검사 | 9 PASS; 위 전체 검사에 포함 |
| JavaScript 전체 | 674 PASS, 0 SKIP |
| 관련 Playwright | 관측·전역 제안·history 34/34 PASS; 최종 renderer/fixture 조정 후 해당 2개 및 최종 1개 재검사 PASS |
| Ruff / mypy / JS syntax | PASS; mypy는 저장소 설정의 4개 source, JS 109 modules |
| tracked source credential scan / diff whitespace | PASS |
| 실제 장비에 이 기능 배포·정지 관측 | 배포 PASS; 실점군 3회 중 1회 후보 통과·관측 적용, 2회 미수렴 거부 |
| Jetson 기존 Python 환경의 신규 수치/API 회귀 | 9/9 PASS, 2.289초; 합성 입력 테스트이며 아래 실점군 시험과 구분 |

로컬 Python 3.13 환경이다. 첫 전체 실행은 `cv2` 부재로 오류 11개였고, 임시 검사 폴더에
저장소 지정 OpenCV를 설치한 뒤 전체 재실행했다. 기존 venv/장비는 변경하지 않았다.
최종 SKIP 14개는 C4 replay의 `jsonschema` 부재 10개, 선택 SVG/rosbags 2개,
Linux `/proc` 전용 검사 2개다. 이를 기능 PASS로 포함하지 않는다.

신규 수치 테스트는 실제 격리 worker로 실행했다. 240점 3D 구조 두 곳을 14m/-9m 떨어뜨린
합성 지도에서 seed별로 해당 구역으로 수렴한다. XY/yaw 오차와 nonzero Z/roll/pitch,
범위 이탈 해 보존·적용 거부, 잘못된 seed 실패, yaw wrap, ts→tc→now 전파,
source epoch 변경, 동일 ID 다른 seed, HTTP 입력 거부, 취소/reap를 검사했다.
전역 backend가 unavailable이어도 지역 경로가 성공하며 전역 runner를 호출하지 않는 것도 확인했다.

UI/JS는 클릭·두 번 탭·드래그·짧은 드래그·취소·Shift pan, CSS 크기/DPR/회전/FIT 역투영,
음수·큰 원점 좌표, preset/숫자 왕복, metadata 이름 보존·revision 무효화,
활성 관측 보존, late response 폐기, 범위 이탈·잘못된 범위 입력,
취소/source 변경과 L1 연결 상실을 검사했다. 클릭·정합·적용의 HTTP writes는
기존 정합 start/cancel뿐이다. goal/initialpose/TF/속도/자세/ARM 경로를 추가하지 않았다.

### 실제 저장 지도 + 합성 query의 추가 검사

읽기 전용으로 현재 Jetson의 최신 3D map ZIP을 받았다. 원본 PCD/ZIP은 Git에 넣지 않았다.

- 지도: `map_20261026_173131`, ID `f6a60130d5ffccd3ba0625cd`
- revision: `5ce46f877a6ad7b3d6310b0c20df1328f8394bfed0ced5e9a021242ac97eadb4`
- PCD SHA-256: `db811e4fcd92fc21cc1ab104f9d1e9e1134ece9de9455ef8c5a9c11a0809d1a8`
- 원본 24,895점, frame `camera_init`. 5m 안에서 고정 RNG 61로 400점을 선택해
  합성 IMU transform으로 재표현했다. 실센서 query나 재방문 시험이 아니다.
- 합성 truth: XYZ `(0,0,0.35)m`, RPY `(0.04,-0.03,0.20)rad`.
- solver seed: XYZ `(0.12,-0.10,0.37)m`, RPY `(0.06,-0.01,0.25)rad`.

| 측정 | 값 |
| --- | --- |
| 초기 XY / yaw / Z 오차 | 0.156205m / 2.864789° / 0.020000m |
| 최종 translation error | 3.99e-16m (동일 지도 점의 합성 query이므로 실측 정확도 아님) |
| 최종 RMSE / overlap | 2.53e-15m / 1.0 |
| inlier / 반복 | 400 / 13 |
| query / 선택 target / full map | 400 / 20,707 / 24,895점 |
| target 반경 | 6.53849m |
| end-to-end 수치 작업 / ICP 보고 시간 | 491.97ms / 315.00ms |
| 판정 | CANDIDATE, bounds 통과, 다른 장소 모호함 미검증 |

단일 로컬 측정이며 Jetson 성능 목표가 아니다. 동일 입력의 no-seed/global 실제 backend 비교는
수행하지 않아 전역 대비 속도 개선이나 정확도 우위를 주장하지 않는다.

## 원격 CI

구현 SHA `f7c41d189a5f1766502b703bf72ae833a1f9051c`의
[GitHub Actions 40449936004](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40449936004)가
**SUCCESS**다. 배포 SHA `54721fe6dd33f73de81a08cfb2d241218056b003`의
[GitHub Actions 40450252787](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40450252787)도
**SUCCESS**를 확인한 뒤 전환했다. 두 실행 모두 Ubuntu 22.04/Python 3.10,
Ubuntu 24.04/Python 3.12 hardware-free 검사와 competition-offline-integration이 통과했다.

## 승인된 배포와 복구 범위

배포 전 읽기 확인된 장비 실행 cwd는 `robot-scope-releases/robot-scope-d6e3fe9675f3`였다.
기존 checkout의 dirty Git HEAD `d7807de...`를 실행본으로 오인하지 않았다.
사용자가 배포·정지 검증을 승인했고, 로봇 정지 상태 및 지도 seed를 직접 확인했다.
소유 상태의 일시적인 UNKNOWN 때문에 첫 전환 시도는 서비스 변경 전에 중단됐다.
다시 확인한 busy/unknown 없음, FAST-LIO STOPPED, 외부 broker의 소유 세션 없음 상태에서
기존 고정 서비스 관리 도구로 Dashboard만 정지·시작했다. 기존 main의
[배포/복구 기록](../integration-acceptance/MERGE_DEPLOY_VERIFY_20261026.md)을 따랐다.

수정 실행 파일은 API router 1개, application의 `global_observation.py`/`anchor_proposal.py`,
relocalization의 `seeded_initialization.py`/`observation_worker.py`, Maps의 `map_seed.js`/
`global_observation_contract.js`/`live_observation.js`/`live_observation.css`/`anchor_proposal.js`,
`scene3d.js`/`go2_official_model.js`다. 새 패키지·SLAM 엔진·설정값·지도/DB migration은 없다.
기존 프리셋 데이터 형식도 변경하지 않았다.

2026-10-27 13:51 KST경 정확한 Git archive의 2,125개 파일을 별도 읽기 전용 release로
설치했다. 실행 cwd는 `/home/unitree/robot-scope-releases/robot-scope-54721fe6dd33`,
PID는 `71071`이며 모든 source hash를 대조했다. HTTP로 제공되는 `map_seed.js`,
`live_observation.js`, `scene3d.js`도 배포 source hash와 일치했다. 서비스 unit과
ExecStart는 유지하고 `robot-scope.env`의 `ROBOT_SCOPE_DIR` 한 값만 바꿨다.
`control.env`와 제어 비활성값 0, venv, ROS workspace, camera 서비스와 container는 유지했다.
main 병합은 하지 않았다.

장비 비공개 백업 폴더는 `/home/unitree/robot-scope-backups/i1-20261027-54721fe6dd33`다.
두 환경 파일을 원문·권한 그대로 보존했다. Dashboard 정지 중 사용자 데이터 4,385개
파일을 867,860,480-byte tar로 보존하고 archive 내 파일 hash를 대조했다. 전후 지도
28개 ID/revision과 지도·preset 관련 82개 파일 hash가 동일했다. 기존 dirty checkout도
그대로이며 로컬의 사용자 CSS 두 파일은 이 commit에 포함하지 않았다.

복구 시에는 활성 관측을 정상 종료하고 ownership/broker 무소유를 다시 확인한 뒤 위 백업의
두 환경 파일을 복원하고 기존 고정 Dashboard 서비스 도구로 재시작한다. 이전 `d6e3fe9`
release는 그대로 남아 있다. 백업의 `deploy.py rollback`이 이 환경 복원과 재시작을 수행한다.
실행 경로·source hash·지도 보존·제어 비활성 검사 실패 시 자동 복구하도록 준비했으며,
이번 전환은 통과하여 실제 rollback은 실행하지 않았다. 지도·프리셋·관측 기록을
일괄 되돌릴 필요가 없다. 비공개 설정·점군·지도 원본은 Git에 넣지 않았다.

## 실제 정지 점군으로 사용한 결과

13:52 KST경 Maps에서 최신 저장 3D 지도 `map_20261026_173131`를 선택하고 기존
관측 전용 FAST-LIO를 시작했다. 사용자가 지도에서 XY·방향을 직접 지정한 뒤
“지정 완료, 이 값으로 정합”, “지금 저 위치가 초기위치 맞으니 저 위치로 진행하면됨”으로
확인했다. 세 요청 모두 같은 seed revision 20, XY `(0.441751,-0.156115)m`, yaw
`88.691837°`, Z/R/P=0(근사), 기본 범위를 사용했다. 바닥 높이를 검증된 IMU 높이로
간주하지 않았다. 서버의 seed와 `initial_map_from_scan`까지 실제 전달을 확인했다.

이 ROS runtime은 메시지별 publisher 정보를 제공하지 않아 기존
`subscription_observation` 옵션을 사용했다. `/cloud_registered`와 `/Odometry`는
동일 source stamp로 짝지었으며 ROS graph는 각각 단일 `laser_mapping` publisher였다.
메시지별 출처, 본체 extrinsic, 절대 위치 정확도는 여전히 미검증이다.

| 실점군 작업 | query / target 점 | 반복 | RMSE / overlap | 수치 작업 / job 생성→완료 | 판정 |
| --- | --- | --- | --- | --- | --- |
| `e7c3e6f295079d026af0d97d` | 211 / 24,895 | 40 | 0.04091m / 100% | 0.640 / 4.599초 | NOT_CONVERGED, 적용 차단 |
| `c1fa31230d6cc01f536c264a` | 211 / 24,895 | 40 | 0.04476m / 100% | 0.565 / 4.430초 | NOT_CONVERGED, 적용 차단 |
| `72db90f6cca27d2de2525b4b` | 209 / 24,895 | 38 | 0.04215m / 100% | 0.534 / 4.732초 | CANDIDATE, 관측 적용 |

시간은 `run_seeded_arrays` 내부의 작업 시간으로 HTTP 왕복·UI 표시 완료 시간은 아니다.
첫 작업의 job 생성→완료는 4.599초였고 실제 ICP는 0.117초였다. 성공 작업의 ICP는
0.110초였다. 선택 footprint가 이 작은 지도 전체를 포함했으므로 target 감소나 전역
탐색 대비 속도 우위를 주장하지 않는다. 서로 다른 스캔의 세 번 시도이며 반복 성공률의
통계적 측정도 아니다. 앞선 거부를 숨기지 않았고 품질·수렴 기준을 완화하지 않았다.

추가 독립 진단에서 새 실점군/pose 한 쌍 209점을 저장하고, 동일 입력에 반복 한도
40/80/120을 비교했다. 세 조건 모두 28회에 수렴했고 RMSE 0.04662m로 같았다.
이는 앞선 두 실패 스캔의 재현이 아니며, 반복 한도를 올리는 수정의 근거가 아니다.
진단 프로세스 안에서만 비교했으며 서비스 코드·설정의 반복 한도 40은 유지했다.

세 번째 결과는 초기값 대비 XY 0.17298m, yaw 4.93596°, Z 0.04837m, tilt 0.58922°로
모든 요청 범위를 통과했다. seed stamp `1793077069793576955`에서 capture stamp
`1793077069993793010`까지 약 0.200초의 같은 세대 odometry 전파를 확인했다.
적용 시 새 proposal을 다시 읽었고 화면에 “제안 위치를 관측 기준점으로 적용했습니다”와
`SAME_START_ODOMETRY_ESTIMATE`가 표시됐다. 약 `(0.395,-0.323,0.048)m`, yaw 93.7°의
현재 관측과 원래 주황 seed가 분리되어 표시됐다. 새 계산·초안 편집 중 이전 활성 위치
보존, late response·범위 이탈·잘못된 seed 회귀는 위 로컬/E2E 검사 결과이며, 이번
실장비 창에서 모든 실패 조건을 강제로 재현한 것은 아니다.

적용 후 control lease/출력/동작 pending 0, navigation/localization/goal idle를 확인했다.
ARM·이동·자세·Nav2 goal·`/initialpose`·운영 TF 명령은 수행하지 않았다.
실제 지도/제어 화면 PNG와 원문 job/pose/진단 배열은 로컬 비공개
`robot-scope-hardware-validation-private/i1-20261027`에 보존했다. 관측은 30분 제한의
기존 세션으로 사용자가 결과를 확인할 수 있게 유지했다.

**남은 다음 한 가지:** 같은 초기값에서 미수렴한 정확한 스캔을 보존·재현해, 정지
스캔별 수렴 편차의 원인을 좁힌다. 현재 구현의 지도 클릭→seed 전달→실수치 정합→
거부/비교→명시적 관측 적용은 검증했지만, 안정적인 반복 수렴과 절대 정확도는 미검증이다.

## 2026-10-27 후속 수정: 수렴·URDF·지도별 코스 영역

앞 절의 첫 배포 기록은 그대로 보존한다. 이후 사용자는 계속 진행, 실제 Go2 URDF 사용,
코스/주변 점의 다른 비중, 중앙 코스 영역 자동 제안 후 확인, 향후 경기장 지도에서 직접
경계를 표시·저장·재사용하는 기능을 요청했다. 최신 origin/main은
`a79dc18b50a0cddee2056fe4748781cdca03aec9`, 통합 브랜치는 `7777f47`이며 reset/merge하지 않았다.
기존 사용자 CSS 두 파일과 다른 채팅의 C4 작업을 수정하지 않았다.

### 확인된 미수렴 원인과 최소 보정

첫 독립 단일 스캔 진단은 실패를 재현하지 못했다. 그 뒤 같은 정지 세션에서 **정확히
짝지은 점군/pose 20쌍**을 6.6005초 동안 보존해 각각 동일 입력으로 비교했다. 점 수는
208~211, odometry XYZ 범위는 0.003282/0.002644/0.001141m였다. 기존 fine ICP 40회에서
14/20 수렴, 6/20 NOT_CONVERGED였다. 같은 입력 80/120회에서는 모두 수렴했고 결과가
일치했다. 실패 샘플 2/8/11/13/14/17의 최종 반복 수는 52/47/41/46/64/41이었다.
40회 시점에 남은 업데이트는 0.36~1.48mm, 5.5e-5~7.4e-4rad로 기존 1e-5 수렴 기준을
넘었다. 이 고정 입력에서는 시간 초과·입력 단절이 아닌 **수렴 전 반복 종료**를 확인했다.

`seeded_initialization.py`에서 NOT_CONVERGED이고 중간 결과가 **원래 seed 범위 안**일
때만 기존 worker로 한 번 더 이어 계산한다. 입력 배열·지도·source stamp·취소 이벤트·
절대 deadline은 같으며 fine ICP 전역 상수 40은 바꾸지 않았다. 최대 두 pass, 합계 80회다.
품질 거부와 범위 이탈에는 이어 계산하지 않고, 최종 범위도 원래 seed로 검사한다.
기존 coarse 단계와 모든 품질/신선도 기준은 유지했다. 0.6초 제한을 도입하지 않았다.

새 실제 격리 worker 재생은 20/20 수렴했고 진단 80회 결과와 transform이 1e-8 이내로
일치했다. 로컬 worker 시간 중앙값 340.63ms, 최대 536.57ms였다. 고정 corpus의 재현
검사이며 새로운 환경의 성공률이나 Jetson 성능을 의미하지 않는다.

### 실제 어떤 지도점을 쓰는가

선택 지도 `f6a60130d5ffccd3ba0625cd`, revision
`5ce46f877a6ad7b3d6310b0c20df1328f8394bfed0ced5e9a021242ac97eadb4`, camera_init 기준이다.
이 지도는 스캔 footprint 안에 24,895점 모두 들어간다. 실제 목적함수는 query마다 최근접
대응점 하나를 사용한다. 표본 14는 210개 inlier / 209개 고유 map 대응점이며,
후보 위치에서 수평 거리 0~1/1~2/2~3/3~5/5~20m 구간은 9/29/25/70/77점이었다.
147/210(70%)가 3m 밖에 있었다. 중앙 구조물과 실험실 외곽이 함께 쓰이며, 거리가
멀다는 것만으로 벽이라고 판정할 수 없다.

### 코스 경계 저장·재사용과 실제 가중 계산

- Maps의 기존 scene에 `코스 경계 직접 표시`로 3~64개 꼭짓점을 차례로 찍고,
  `경계 표시 완료` → 이름 입력 → `영역 확인·저장`한다. Esc/마지막 점 취소/다시 그리기를 지원한다.
- `중앙 영역 자동 제안`은 표시 점군 XY의 5~95 percentile 사각형에 각 변 25% inset을 준
  **초안**이다. 구조물의 의미 분류가 아니며 확인·저장 전에는 가중 정합을 시작하지 않는다.
- 코스 안 비중 1, 주변 초기 비중 .25이며 .5/1도 선택할 수 있다. .25는 검증된 최적값이
  아닌 사용자 조정용 초기 설정이다. 경계는 XY에만 적용하고 모든 높이의 점을 포함한다.
- 기존 `NavigationPresetStore`의 파일 잠금·원자적 쓰기·경로/용량 제한을 재사용한다.
  저장 위치는 runtime의 `observation-courses/<map_id>/presets.json`이다. 지도 원본이나
  기존 anchor preset 형식은 변경하지 않는다. 새 이름으로 최대 64개 저장 가능하며
  같은 이름을 덮어쓰지 않는다. `사용 안 함`으로 현재 정합에서 제외할 수 있다.
- 지도 id/revision/frame이 모두 같은 저장 영역만 불러온다. 다시 열면 마지막 호환 저장
  영역을 기본으로 선택한다. 지도 복사·crop·재매핑 등 다른 geometry에는 자동 이식하지
  않고 다시 표시·확인한다. 이름만 바뀌면 유지한다.
- 확인된 polygon과 비중은 seed request → coordinator → immutable job context →
  기존 격리 worker → coarse/fine ICP까지 전달된다. 매 반복의 **매칭된 지도점**이 경계
  안이면 1, 밖이면 설정 비중을 사용해 weighted centroid/covariance/Kabsch를 계산한다.
- 최종 RMSE·overlap·기존 전체 target/매칭 geometry 검사는 **가중하지 않은 전체 입력**으로
  유지한다. 추가로 weighted matched geometry를 확인하고 코스 대응점이 0이면 거부한다.
  주변을 제거해 점수를 좋게 보이게 하지 않는다. 화면에 코스/주변 대응점 수, 비중,
  코스 가중 기여를 표시한다. 후보 계산은 관측용이며 지속 추적·운영 위치 정책은 바꾸지 않는다.
- 경계/비중 편집은 새 seed revision으로 처리한다. 늦은 load/save/proposal 응답은 새
  초안을 덮어쓰지 않는다. 현재 정상 관측 anchor는 명시적 후보 적용 전까지 보존한다.

실험실 자동 제안은 X [-1.082192,2.629171], Y [-4.020236,2.566195]m이며 map 점
4,429개를 포함한다. **사용자 확인 대기 상태**이며 실제 장비에 저장·사용한 경계로
간주하지 않는다. 이 가상 경계로 보관 입력을 로컬 비교한 결과는 아래와 같다.

| 같은 20개 보관 입력 | 동일 비중 + 수렴 보정 | 코스 1 / 주변 .25 + 수렴 보정 |
| --- | --- | --- |
| 수렴 및 기존 전체 품질 통과 | 20/20 | 20/20 |
| 전체 입력 비가중 RMSE 범위 | .041624~.046383m | .041078~.046179m |
| 로컬 worker 시간 중앙값 / 최대 | 340.63 / 536.57ms | 393.79 / 525.77ms |
| 코스 대응점 | 구분 없이 동일 비중 | 46~47점 (query 208~211점) |
| 코스 가중 기여 | 약 22%의 대응점 | 52.72~53.56% |

동일 비중 결과 대비 최대 XY 차이는 .02242m, yaw 차이는 .61032°다. 정답 위치가 없는
실측 데이터이므로 이 변화나 작은 RMSE 차이를 **정확도 개선 근거로 사용하지 않는다**.
원본 지도/점군/실측 그림은 Git에서 제외했다. 비공개 evidence의
`stationary-series/weighted-proposal-offline-replay.json`에 미확인 경계임을 명시했다.

### 실제 URDF 미리보기

`go2_official_model.js`의 기존 URDF-derived mesh/hierarchy를 초기값·후보에도 사용한다.
metric scale 1, 각 레이어 고유 pose/색상/반투명 표시를 사용하고 telemetry 위치를 읽거나
덮어쓰지 않는다. 신선한 관측 관절을 쓰고 없으면 asset 기본 자세를 쓴다. 기존 body/ground
높이 보정을 추가하지 않는다. IMU=본체 원점은 근사라는 안내를 유지한다. 로딩 중에는
기존 metric fallback을 사용한다.

### 후속 검증 범위

실제 수치 검사에서 코스와 주변에 서로 다른 위치 오차를 준 합성 점군을 사용했다.
가중치를 바꾸면 worker 결과가 변하며, 주변 비중 1이면 기존 결과와 1e-9 이내로 일치한다.
전체 RMSE가 .05m를 넘는 경우 가중 목적함수가 좋아도 HIGH_RESIDUAL로 거부한다.
영역 밖 지도, 자기 교차/퇴화 polygon, 다른 지도 revision, 미확인 영역, origin guard,
저장 재생성, 중복 이름 보존도 검사했다. API→실제 worker 검사에서도 course 안/밖 대응점과
전달된 .25 비중을 확인했다. UI 검사에서는 수동 다각형, 저장·불러오기, 비중 취소,
late saved region/proposal, draft/active 분리와 무주행을 확인했다.

새 주요 파일은 `course_regions.py`, `api/routers/course_regions.py`,
`static/features/maps/course_region.js`다. 기존 scene·map_seed·preset store·runtime·
coordinator/anchor proposal·SE3/seed/worker 경로를 확장했다. 별도 지도나 정합 엔진,
새 패키지·운영 TF·주행 명령은 추가하지 않았다.

최종 로컬 검사: Python **2,851 tests, 실패/오류 0, 14 skips** (107.914초),
JavaScript **678 pass**, Playwright 관측 전체 **28/28 pass**. 마지막 pointer/표시 변경 후
코스 저장·late 응답·좁은 화면 3개도 다시 통과했다. Ruff, mypy(설정된 4개 source),
tracked-source credential scan, diff check가 통과했다. 최초 전체 실행의 API inventory
수량 및 app.py 크기 제한 4개 실패는 새 endpoint 수 반영과 기존 runtime 구성 모듈로의
저장소 초기화 이동으로 해결했으며 제한값을 올리지 않았다.

### 코스 기능 첫 배포와 사용자 경계 확인

`b8e438dfe4099aea8dcc1d62aef5fc2941ecfd5b`를 2026-10-27 15:00 KST경 배포했다.
실제 cwd는 `/home/unitree/robot-scope-releases/robot-scope-b8e438dfe409`, PID 148083,
source 2,130개 hash 일치, 지도 28개와 기존 지도/preset 파일 82개 hash가 보존됐다.
백업은 `/home/unitree/robot-scope-backups/i1-20261027-b8e438dfe409`이며 사용자 데이터
4,388개 파일 / 868,454,400-byte tar와 두 환경 파일을 보존했다. 기존 관측 세션은 30분
제한으로 종료됐다. 일시적인 ownership UNKNOWN으로 첫 시도는 변경 전에 중단했고,
재확인 후 고정 서비스 도구로 전환했다. rollback 대상은 이전 `54721fe6dd33` release다.
control 비활성 0을 유지하고 실제 로봇 명령은 수행하지 않았다.

새 장비 실행본에서 같은 사용자 seed로 계산한 job `0222ccde177e300812812139`는
209점, fine 33회, 558.76ms, overlap 1.0, RMSE .05690371m였다. 수렴했지만 기존 .05m
기준 때문에 HIGH_RESIDUAL로 거부됐고 관측 적용은 차단됐다. 앞의 보관 입력 20쌍과
다른 새 스캔이므로 수렴 보정/가중 효과의 전후 비교로 쓰지 않는다.

사용자는 초기 제안에서 위쪽을 30% 확장하고 좌우도 넓히도록 수정한 뒤 최종 그림에
“이 경계로 저장”으로 확인했다. 최종 polygon은 X [-1.6388967931,3.1858759820],
Y [-4.0202355385,4.5421241760]m다. 최초 제안 대비 상단 +1.975929m, 좌우 각각
.556705m이며 지도점 6,328개를 포함한다. `실험실 중앙 코스 · 위·좌우 확장` 이름,
ID `user-90302feea07b435eabd398617f1854a1`, 코스 1/주변 .25로 실제 서버에 저장했다.
GET 재읽기와 실제 Maps의 “저장된 코스 영역 사용” 및 초록색 경계 표시를 확인했다.
앞의 미확인 초기 제안 replay와 **최종 저장 경계는 다르다**.

이 커밋의 원격 [CI 40458049716](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40458049716)는
Python/JS/통합 검사를 통과했지만 UI consistency의 합성 API fixture에 새 course-regions
GET이 없어 404로 실패했다. `ui_consistency.spec.mjs`에 실제 API와 같은 빈 저장 목록
응답을 추가했으며 오류 무시/검사 완화는 하지 않았다. 수정 후 390/1440px·dark/light
네 조건이 로컬에서 통과했다.

### 사용자 추가 요청: 전체 점군 오차 한도 해제

위 HIGH_RESIDUAL 결과를 본 뒤 사용자가 명시적으로 “전체 점군 오차 제한 해제”를
요청했다. 앞 절의 기본 .05m 제한 유지 방침에 대한 **후속 사용자 변경**이다.
새 UI `전체 점군 오차 한도 사용 (5cm)`를 끄면 해당 seeded-local 요청에만
`enforce_residual_limit:false`를 전달한다. 서버 기본값과 기존 전역/일반 정합 경로의
기본 .05m 정책은 유지한다. 선택은 이 브라우저에 저장되며 화면에 한도 해제를 표시한다.

전체 RMSE는 그대로 계산·전달·표시하고, 후보가 원래 5cm 조건을 통과했는지도
`residual_policy.original_passed`로 남긴다. 수렴·overlap·geometry·코스 대응점 존재·
원래 seed 범위·source/시각·명시적 관측 적용 조건은 유지한다. 반경 .75m의 최근접
대응점 탐색 gate는 이 RMSE 한도와 별개이며 변경하지 않는다. 미수렴 보정 두 pass도
동일 입력과 deadline으로 제한한다. 한도 해제 후보는 오차 기준 통과나 정확도 보증으로
표시하지 않는다. 한도를 다시 켜거나 정책을 바꾸면 이전 계산 후보를 무효화한다.

실제 격리 수치 검사에서 동일 high-residual 입력의 transform/RMSE가 한도 해제 전후
같고 적용 여부만 바뀜을 확인했다. 잘못된 코스, geometry/overlap/수렴/seed 범위 거부는
유지되며 bool 이외 정책 입력을 거부한다. API→worker 전달, UI 요청, 후보 무효화,
브라우저 새로고침 후 선택 유지도 검사했다.

오차 정책 변경의 최종 로컬 검증: Python **2,851 tests, 실패/오류 0, 14 skips**
(103.669초), JavaScript **679 pass**, 관측 E2E **29/29**, 최종 저장 선택/정책 유지 및
UI consistency **5/5**. 한 번의 전체 실행에서 기존 C++ extended benchmark subprocess가
실패했으나 단독 재실행과 브라우저 시험을 겹치지 않은 최종 전체 실행이 통과했다.
이 실패를 코드 결함 또는 부하 원인으로 확정하지 않았다. 기준/timeout을 변경하지 않았다.
Ruff, mypy, credential scan, diff check도 통과했다.
