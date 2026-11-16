# 오프라인 3D 포즈 그래프 보정

기존 FAST-LIO, Nav2, TF 발행, 운영 지도와 독립적인 분석 도구입니다. 대시보드의
확장 기능 → 주행 기록 보정에서 접근합니다. 여러 지도 병합과 함께 사용하는
[통합 로컬 실행 방법](OFFLINE_WORKBENCH.md)을 권장하며 아래 단독 실행도 지원합니다. 자동 시작,
센서 구독 추가, 서비스 변경, 로봇 배포, 지도 채택 또는 위치 보정 적용은 없습니다.

## 실행

분석 PC에서 Python 3.10 이상을 사용합니다. 별도 가상환경에 설치하며 운영 로봇의
패키지를 업그레이드하지 않습니다. 아래 명령은 저장소 루트에서 실행합니다.

```bash
python -m pip install -r requirements-offline-slam.txt
python -m robot_dashboard.offline_slam.server --root runtime/offline-slam --port 8091
```

Windows의 현재 개발 환경에서는 `python` 대신 `.venv/Scripts/python.exe`를 사용할 수
있습니다. 브라우저에서 `http://127.0.0.1:8091/`을 엽니다. 다른 PC에서 운영 대시보드를
보고 있더라도 링크는 **브라우저가 실행되는 PC**의 분석 서버를 엽니다. 분석 서버가
없으면 연결되지 않습니다. 서버는 loopback에만 바인딩하며 API의 변경 요청은
same-origin만 허용합니다. ROS 라이브러리는 오프라인 분석 서버에 필요하지 않습니다.

## 실제 주행 기록

기록기는 배포 후 사용자가 명시적으로 실행할 도구이며 이번 작업에서 실행하지 않습니다.
기존 FAST-LIO `/cloud_registered`와 `/Odometry`를 읽습니다. 드라이버를 시작하지 않고
제어 명령, TF, 서비스 요청을 발행하지 않습니다. 실제 구독이 추가되면 CPU·디스크·DDS
부하는 발생하므로 향후 장비 시험에서 수신율과 지연을 측정해야 합니다.

```bash
# ROS 2 Humble 환경을 source한 별도 셸에서 실행. Ctrl+C로 종료·저장.
python -m robot_dashboard.offline_slam.record --live \
  --calibration-id INSTALLED_CALIBRATION_SHA256 --sensor-origin-body X Y Z --output run.json

# 기존 bag은 ROS로 재생하지 않고 읽어서 변환.
python -m robot_dashboard.offline_slam.record --bag /path/to/bag \
  --calibration-id INSTALLED_CALIBRATION_SHA256 --sensor-origin-body X Y Z --output run.json
# MCAP bag에는 --storage-id mcap 추가
```

원본 센서까지 보존하려면 별도 rosbag에 LiDAR·IMU·TF와 위 두 토픽을 함께 기록합니다.
`X Y Z`는 교정 파일에서 확인한 FAST-LIO body 좌표계의 LiDAR 원점(m)입니다.
회전은 이미 body로 변환된 점군에 포함되어 있고, 이 병진은 점유 격자 광선 시작점에
사용합니다. 임의로 0을 입력하지 말고 실제 교정값을 확인해야 합니다.
이 도구의 JSON은 원시 패킷·원시 IMU 보관물이 아닙니다. FAST-LIO가 처리한 전역 점군을
동일한 **header stamp**의 자세로 역변환한 body 로컬 점군입니다. `camera_init → body`
프레임 계약을 검사하며 수신 시각으로 대체하거나 근접 시각 자세를 섞지 않습니다.
입력 소스 재시작·좌표계 변경은 새 기록으로 분리해야 합니다. 과거 bag에 여러 발행자가
섞였는지는 토픽 이름만으로 입증할 수 없으므로 기록 provenance를 별도로 확인합니다.

키프레임 조건은 이동 0.3 m 또는 회전 0.15 rad입니다. 8 cm voxel 선택 후 최대
2,000점을 보존하며 세션은 최대 400개 키프레임·64 MiB입니다. 화면 표시 점군과
독립적이지만 전체 센서 해상도는 아닙니다. 장거리 주행은 세션을 나눠 기록해야 합니다.
이 초기 버전에는 서로 다른 세션을 합치는 최적화가 없습니다.

키프레임마다 `run.json.partial.jsonl`에 flush/fsync합니다. 오류·전원 중단으로 최종
JSON이 없으면 완전히 기록된 행만 복구할 수 있습니다. 기존 파일은 덮어쓰지 않습니다.

```bash
python -m robot_dashboard.offline_slam.record --recover run.json.partial.jsonl \
  --output recovered.json
```

복구 시 교정 ID는 journal 안의 값을 유지합니다. 최소 세 키프레임이 있어야 분석합니다.

## 분석과 저장

1. `run.json` 업로드 또는 기존 세션 선택.
2. 루프 후보 반경, 시간상 최소 프레임 간격, 정합 오차·중첩 임계값 설정.
3. 루프 검색·최적화 실행. 별도 CPU 프로세스에서 한 작업만 수행합니다.
4. 같은 축척의 전후 점군·궤적, 후보 채택/기각 사유, 비용을 확인합니다.
5. 새 지도 저장 후 ZIP을 내려받습니다. 저장 결과는 불변이며 다른 설정을 시험하려면
   같은 기록을 새 세션으로 가져옵니다.

ZIP에는 `session.json`, `result.json`, `optimized.pcd`, `map.pgm`, `map.yaml`,
`manifest.json`이 들어갑니다. source/result revision과 각 파일 SHA-256을 보관합니다.
저장 라이브러리는 오프라인 서버 전용입니다. 운영 지도 목록에 자동 등록하거나 기존
지도를 대체하지 않습니다. Nav2 사용과 POI·경로 이전은 별도 검증 단계입니다.

작업 취소·600초 제한·프로세스 오류는 성공과 구분합니다. 서버를 재시작하면 미완료
작업은 자동 재개하지 않습니다. 루프가 검증되지 않으면 `NO_LOOP`이며 새 보정 지도를
저장할 수 없습니다. 입력과 결과 revision이 맞지 않는 저장도 거부합니다.
같은 저장소를 여러 서버에서 동시에 열지 못하도록 OS 파일 잠금을 유지합니다.
최적화 시도마다 독립 디렉터리를 사용하므로 이전 프로세스의 늦은 결과가 새 시도를
덮어쓰지 않습니다. 세션당 다섯 번까지 계산할 수 있습니다.

## 수학과 구현 범위

`T_parent_body`는 body 점을 parent로 변환합니다. 엣지 `Z_ij`는 j 로컬 점을 i 로컬로
변환합니다. 잔차는 `inverse(Z_ij) @ inverse(T_i) @ T_j`의 병진(m)과 SO(3) 회전
로그(rad)입니다. 첫 노드는 변수에서 제외하여 정확히 고정합니다. 희소 Jacobian
구조를 지정한 SciPy least_squares와 soft-L1 손실로 가중 잔차를 최소화합니다.
전후 비용은 **루프 엣지를 포함한 같은 그래프**에서 비교합니다.

기본 표준편차는 odometry 이동 0.08 m·회전 0.04 rad, loop 이동 0.03 m·회전 0.02 rad입니다.
이는 조정 가능한 가정이며 센서가 실제 보고한 공분산으로 주장하지 않습니다.
`Omega = diag(1/sigma²)`이고 solver 잔차에는 `diag(1/sigma)`를 적용합니다.

후보는 odometry 공간 근접성과 프레임 간격으로 찾고 프레임마다 가까운 후보 세 개까지만
검사합니다. ICP는 3D trimmed point-to-point 정합이며 양방향 중첩, 최근접점 중복 비율,
양방향 잔차의 최댓값, 선형 퇴화와 과도한 보정을 검사합니다. 후보의 `rmse_m`은
`forward_rmse_m`, `reverse_rmse_m` 중 큰 값입니다. 완전한 장소 인식, Scan Context,
큰 초기 방향 오차에 대한 전역 정합, 반복 선반에서의 오인식 완전 방지는 아닙니다.
soft-L1은 오인식 검증을 대신하지 않습니다. 끝점이 출발점이라는 정답 제약은 넣지 않습니다.

3D 지도는 모든 저장 로컬 점군을 수정 자세로 재투영합니다. 2D 지도는 **고정된 parent
좌표계 높이 구간**의 반사점을 사용하여 각도별 가까운 반사점까지 Bresenham ray와
log-odds로 생성합니다. PGM은 위쪽 행부터 기록하고 YAML origin은 아래쪽 원점입니다.
다층·경사로용 traversability 지도가 아니며 ground-plane 자동 추정도 없습니다.
맵 크기는 최대 400만 셀, 축당 4,000셀입니다. 2D 생성 실패 시 전체 결과를 채택하지 않습니다.
2D 경계는 실제 높이 구간과 0.1–30 m XY 거리 조건을 통과한 반사점 및 센서 원점으로
계산합니다. 제외된 상층·원거리 점은 3D PCD에는 남지만 2D 크기를 늘리지 않습니다.

## 하드웨어 없는 검증

```bash
python -m unittest discover -s tests -p test_offline_slam.py -v
python -m unittest discover -s tests -p test_offline_slam_validation.py -v
node --test tests/test_offline_slam.mjs
python -m robot_dashboard.offline_slam.demo --output runtime/synthetic-run.json
# Playwright 브라우저가 설치된 분석 환경에서:
node scripts/smoke_offline_slam.mjs
```

브라우저 테스트의 Python 경로는 `OFFLINE_SLAM_PYTHON`으로 지정할 수 있습니다.
생성하는 fixture와 화면은 항상 `synthetic_fixture`입니다. 수치 보정·프로세스·API·
저장·UI 검증은 실장비 정확도나 ROS bag/live 연결의 인수 성공을 뜻하지 않습니다.

### 2026-11-15 개발 PC 검증

- 신규 Python 13개: 통과. 3D 정합·고정 앵커·잔차 감소·잘못된 입력·퇴화 후보·정확한
  시각 대응·기록 복구·취소·시간 제한·시도 격리·저장 해시·HTTP origin 검사 포함.
- 전체 JavaScript 781개: 통과. 신규 표시 로직 2개 포함.
- Headless Chromium: 합성 기록 업로드 → 실제 최적화 → 전후 비교 → 저장 → ZIP 다운로드
  → 새로고침 후 조회 통과. 1440px/390px 화면 검사 및 JavaScript 오류 0건.
- Ruff: 신규 Python 모듈과 테스트 통과.
- 합성 순환 예제: 끝점 간격 약 0.499 m → 0.021 m, 동일 그래프의 soft-L1 비용
  약 79.457 → 0.542. Ground Truth를 루프 측정으로 입력하지 않았습니다.
- 전체 Python: 1,813개 실행, 실패 24·오류 424·건너뜀 22. **전체 통과 아님.**
  같은 Windows/Python 환경에서 변경 전 HEAD 소스를 별도 복사하여 1,800개를 실행한 결과도
  실패 24·오류 426·건너뜀 22였습니다. 최종 실행의 실패 테스트 식별자는 모두 변경 전
  실패 집합에 포함됐습니다. Unix `resource` 모듈 부재, ROS 명령 부재, POSIX 파일
  권한/하드링크 전제 등 기존 환경 제한이 포함되어 있습니다.
- ROS live 기록, 실제 bag 변환, 실장비 성능과 지도 주행 검증: 미실행.
- 배포·로봇 서비스 재시작·운영 지도 변경: 수행하지 않음.

상세 실행 로그와 합성 화면 캡처는 Git에서 제외되는 `runtime/offline-validation/`에
보관합니다. 별도 작업에서 변경 중인 navigation 코드와 해당 테스트는 이번 변경에
포함하지 않습니다.

### 2026-11-16 수치 스트레스 검증 (합성 전용)

기존 전체 랜드마크 가시성 예제 외에 XY 가시 거리 3.4 m, 프레임별 18% 무작위 누락,
XYZ 15 mm Gaussian 잡음을 추가했습니다. 같은 생성식의 정답 자세는 평가에만 사용하며
루프 측정·optimizer 입력에는 넣지 않았습니다. 시작 자세를 고정한 절대 병진 RMSE를
전체 21개 자세에서 계산합니다. 설정은 후보 반경 1.2 m, 프레임 간격 10,
correspondence 0.35 m이며 나머지는 기본값입니다.

| 난수 seed | 채택 루프 | 같은 그래프 비용 전 → 후 | 끝점 거리 전 → 후 (m) | 정답 병진 RMSE 전 → 후 (m) |
|---|---:|---:|---:|---:|
| 21 | 2 | 79.360351 → 0.543285 | 0.498899 → 0.022637 | 0.252511 → 0.084891 |
| 182 | 2 | 79.580086 → 0.545959 | 0.498899 → 0.019270 | 0.252511 → 0.086965 |
| 909 | 1 | 38.275813 → 0.526518 | 0.498899 → 0.030081 | 0.252511 → 0.081630 |

- 기본 correspondence 0.6 m로 seed 182를 실행하면 모든 후보가 `HIGH_RESIDUAL`로
  기각되어 `NO_LOOP`입니다. 합성 입력에 맞춘 0.35 m 결과를 기본 설정의 보장으로
  일반화하지 않습니다. 끝점 거리 감소만으로 정확도를 판정하지 않습니다.
- 변형 오인식: 원본 200점에 Z축 0.35 m 이동 복제층을 더한 400점 target은 양방향
  중첩 1.0, forward RMSE 약 0 m여서 이전 검사에서 채택됐습니다. reverse RMSE
  0.212683 m도 검사하도록 수정하여 `HIGH_RESIDUAL`로 기각합니다. 반대 정합 방향도
  0.182686 m로 기각합니다. 이 후보만 있는 그래프는 `NO_LOOP`이며 수정 자세가 없습니다.
- 공간적으로 겹치는 독립 난수 점군도 잔차로 기각합니다. 동일한 반복 구조의 장소를
  구별하는 정답 기반 검사는 아니며, 실제 반복 선반 오인식 방지를 입증하지 않습니다.
- 2D 지도 경계에 사용하지 않는 `[500,0,100]` 상층점 또는 `[500,0,1]` 원거리점이
  이전에는 작은 지도도 `GRID_TOO_LARGE`로 만들 수 있었습니다. 수정 후 이 점들을
  추가해도 PGM/YAML 바이트는 같고, PCD에는 원래대로 추가 점이 보존됩니다.
- Python 기존 13개 + 신규 10개 = **23개 통과**, JavaScript **2개 통과**.
  새 검사는 비대칭 변형/거짓 루프·잡음과 부분 가시성·알려진 3D 정합·회전 전용
  키프레임·PCD 수정 자세·교정 센서 원점·PGM 상하 방향·빈 높이 구간도 포함합니다.
- 실제 bag 제공/검증, ROS live, 실장비 정확도, 운영 지도 적용: **NOT_RUN**.

참고: [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html),
[FAST-LIO 입력/출력 개념](https://github.com/hku-mars/FAST_LIO).

## 저장 지도 정합 거부 진단 — 2026-11-16

공개 `docs/replay-fixtures/stage3-20261019`의 실제 스캔 3개와 저장 지도에 대한
**로컬 수치 진단**입니다. 연속 주행 기록이나 적격 루프가 아니므로 포즈 그래프,
새 지도 저장, 운영 위치 적용은 수행하지 않습니다. 원본과 기존 모호성 판정을 보존합니다.

### 확인한 원인과 수정

- 이전 시험은 원래 voxel 처리된 키프레임에 쓰는 ICP를 전체 원시 스캔에 직접 적용했습니다.
  유효 XYZ 약 15,600개 중 서로 다른 좌표는 약 8,280개이며, 표면별 점 밀도도 다릅니다.
  첫 두 결과의 중첩률은 약 83%였지만, `고유 대응 지도점 / 대응 스캔점` 비율이
  약 13%로 35% 기준보다 낮았습니다. 이를 모두 `LOW_OVERLAP`로 표시하던 진단을
  `MANY_TO_ONE_CORRESPONDENCES`와 분리하고, 높은 잔차 등 **모든 동시 실패 사유**를 남깁니다.
  기존 그래프 엣지의 승인 기준과 ICP 계산은 바꾸지 않았습니다.
- 새 `registration_diagnostics`는 명시적인 저장 지도 진단 경로에서만 중복 좌표 제거 후
  8 cm voxel 중심점을 사용합니다. 기존 기록기의 공간 해상도와 같은 크기이며, 거리·잔차·
  중첩·고유 대응 비율 기준을 완화하지 않습니다. raw 무효 원점 행은 fitting에서 제외하되
  원본 16,000점 전체 및 원점 제외 모집단의 전후 점수를 각각 저장합니다. 표본화만으로
  점수가 개선된 것처럼 보이지 않도록 지도 전체 25,666점에 대해 다시 평가합니다.
- 세 번째 기록의 선택 후보는 첫 번째와 병진 약 1.635 m 차이가 납니다. 원래 후보 32개
  전체를 같은 기준으로 시험하면 첫 두 스캔은 각각 2개 후보가 통과하지만 세 번째의
  후보 8개는 모두 실패합니다. 별도 상대 스캔 정합으로 첫 스캔의 **미검증 가설**을
  세 번째에 전달하면 상대 잔차 약 1.38 cm, 지도 fitting 잔차 약 11.11 cm로 수치 기준을
  통과합니다. 이 가설 전달은 새로운 전역 재위치추정이나 위치 정답이 아닙니다.

동일한 원본 16,000점에 대한 거리 상한 0.75 m의 capped nearest-neighbor RMSE입니다.
인라이어 수가 달라져도 분모와 입력을 유지하며, 원점 무효행도 이 표에서는 그대로 포함합니다.

| 스캔 | 기존 ICP 결과 | 밀도 보정만 적용 | 첫 스캔 가설을 상대 정합으로 전달 |
|---|---:|---:|---:|
| 1 | 15.79 cm / 거부 | 15.64 cm / 수치 기준 통과 | 기준 가설 |
| 2 | 15.87 cm / 거부 | 15.76 cm / 수치 기준 통과 | 15.74 cm / 수치 기준 통과 |
| 3 | 30.28 cm / 거부 | 30.18 cm / 높은 잔차로 거부 | 15.81 cm / 수치 기준 통과 |

첫 스캔의 원래 seed 점수는 15.50 cm였으므로 밀도 보정이 모든 시작점보다 잔차를 낮추는
것도 아닙니다. 핵심 개선은 밀도에 민감한 거부의 해석과 초기 가설 일관성 진단입니다.
`AMBIGUOUS_ALTERNATIVES`, clock/body extrinsic 미검증을 계속 보존하며, 모든 결과는
`DIAGNOSTIC_ONLY`, `global_location_verified=false`, `operational_application=NOT_APPLIED`입니다.
실제 절대 위치 정확도, 지도 복원 성공 또는 주행 정확도를 입증하지 않습니다.

### 재현

```bash
python scripts/diagnose_saved_map_registration.py \
  --packet docs/replay-fixtures/stage3-20261019 \
  --output runtime/saved-map-diagnosis-new \
  --all-recorded-candidates --cross-scan-seed-check
python -m unittest discover -s tests -p test_saved_map_registration_diagnostics.py -v
```

`--output`은 새 디렉터리여야 하며 입력 패킷 내부 경로는 거부합니다. 공개 manifest와
지도/스캔/기존 점수 해시를 검증한 뒤 실행하고 종료 시 다시 검사합니다. Windows checkout의
CRLF 변환 때문에 manifest 검증이 실패하면 원본 Git blob과 동일한 패킷 사본을 지정해야
하며, 검증 기준을 완화하거나 원본 파일을 덮어쓰지 않습니다. 결과 JSON에는 코드/입력 해시,
표본 수, 모든 후보와 거부 사유, 양방향 중첩, 대응점 중복도, 원본 전체 점수가 포함됩니다.
실장비, ROS, 네트워크, 저장 지도 채택 코드에 연결되지 않습니다.

검증 결과: 신규 진단 회귀 9개, 기존 오프라인 SLAM 13개, 관련 JavaScript 2개 및
Ruff 검사 통과. 신규 회귀는 중복 배율 불변성, 알려진 합성 6DoF 복원, 다중 거부 사유,
틀린 seed/퇴화 형상 거부, 원본 보존, 상대 변환 방향, 모호성 유지 등을 검사합니다.
전체 Python은 1,836개 중 실패 24·오류 425·건너뜀 22로 **전체 통과가 아닙니다**.
수정 전 `a81ef92` 소스 사본의 동일 환경 검사도 1,827개 중 실패 25·오류 424·건너뜀 22였고,
Unix `resource`, ROS 도구, Windows 파일 권한 전제의 실패가 남습니다. 변동한 기존
파일 이관 테스트는 코드가 동일하며 양쪽 단독 재시험에서도 해시 검사·권한 계열의 오류가
각각 7개 발생했습니다. 실패한 개별 테스트는 실행 간 변동하므로 전체 회귀 통과로 판정하지 않습니다.
Windows 샌드박스의 asyncio 내부 socketpair 대기로 중단된 최초 시도와, 로컬 socket이
허용된 환경에서 완료한 검사 결과를 구분해 로그에 보관했습니다.

공간 표본화의 참고 자료: [Open3D ICP의 voxel 해상도 설명](https://www.open3d.org/docs/release/tutorial/t_pipelines/t_icp_registration.html#voxel-sizes).
이 구현은 기존 NumPy/SciPy ICP를 사용하며 Open3D 의존성을 추가하지 않습니다.
