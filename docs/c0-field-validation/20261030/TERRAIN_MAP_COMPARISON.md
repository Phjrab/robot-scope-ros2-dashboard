# 새 경사로·계단 지도와 세 수동 기록의 오프라인 비교

새 지도 `map_20261030_205128`을 인수해 세 기록을 실제 비교했다. **같은 관측 좌표계를 유지한 진단 가정에서 정합 잔차 중앙값은 A 231→63mm, B 206→60mm, C 203→56mm로 감소했다.** 다만 기존 50mm 기준을 대부분 충족하지 못했으며 실제 Nav2 위치추정 성공으로 판정하지 않는다. 원시 자료 인수·동일 입력 비교 실행은 PASS, 대표 프레임의 전 구간 품질은 FAIL, 검증된 좌표계·보정·시계가 필요한 운영/절대 정확도 평가는 BLOCKED다.

이는 [종료된 전체 1차 결과](FINAL_ROUND1_RESULTS.md) 이후의 별도 분석이다. 당시 FAIL/BLOCKED나 원래 정지 정합의 HIGH_RESIDUAL을 소급 변경하지 않았다. [준비 보고](MAP_COMPARISON_PREP.md)의 새 지도 대기 상태는 당시 기록으로 보존한다. 이번 실행 결과·입력 hash·집계는 [JSON 영수증](TERRAIN_MAP_COMPARISON.json)에 있다.

## 경로와 입력 인수

사용자 설명을 다음과 같이 적용했다. 좌우는 진입 시 로봇 기준이며, 각도를 데이터에 강제로 적용하지 않았다.

| 기록 | 경로 분류 | 정확한 점군–Odometry 쌍 | IMU 표본 | 정합 대표 프레임 |
|---|---|---:|---:|---:|
| A | 경사로 진입·상승 → 왼쪽 약90° → 계단식 하강 | 3,006 | 150,288 | 11 |
| B | 계단 진입·상승 → 오른쪽 약90° → 경사로 하강 | 2,941 | 147,042 | 12 |
| C | 경사로 진입·상승 → 왼쪽 약90° → 계단식 하강 반복 | 2,607 | 130,354 | 20 |
| 합계 | 세 기록을 합치거나 한 경로로 재분류하지 않음 | **8,554** | **427,684** | **43** |

장비에 보존된 종료된 bag만 read-only로 읽어 전체 registered XYZ/Odometry/IMU 수치 배열과 일부 full body 점군을 PC로 회수했다. ROS 메시지 역직렬화만 사용했으며 ROS node·publisher·subscription을 만들지 않았다. 원시78DB/20,362,293,248B 전체를 PC로 복제하거나 raw LiDAR 전체를 재처리한 것은 아니다.

기존 준비에서 고정한 대표45개 중 A/B 각1개는 정확히 같은 source stamp가 bag에 없어 제외했다. 근접 시각이나 임의 점군으로 대체하지 않았다. 존재하는43개는 모두 exact-stamp Odometry와 결합했다. 전체8,554프레임에는 초기 prior를 고정한 지도 최근접 거리 진단을 추가했으며, 이것은 전체 프레임의 ICP/연속 localization 재생 결과와 구분했다.

기존 cached `/cloud_registered` 입력 경로를 유지했다. 프레임당 전체129~446개의 registered 점을 정확한 Odometry로 한 번만 역변환했고 왕복 변환을 검증했다. 별도 `/cloud_registered_body`는 약1.0만~1.6만점으로 처리 모집단이 달라 registered 배열과 점 순서별 동일성을 가정하지 않았다. full body/raw 모집단으로 교체해 점수를 비교하지 않았다.

## 지도와 초기 좌표계 가정

| reference | ID | revision | 전체 점수 |
|---|---|---|---:|
| 기존 평지 edited PCD | `e1dd40cc6911404dbdfc073b` | `c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5` | 13,546 |
| 새 경사로·계단 PCD | `4b672f17ec79b96d2d075189` | `32123a1b2eb19798d81aa930a6e7f0b02451fb219f9fa164abe99612d191d268` | 49,080 |

기존 full PCD SHA256은 `6ec38aa876ffcfe505ee81204d94fa84e1c3cb438ae706a6a6b7fc0048970b5a`, 새 PCD는 `879cd0335fad8e15272ffcabcafdbf839f82afd19166a8d6ef2c343a96715203`이다. 새 지도는 binary x/y/z/intensity, frame `camera_init`, 785,437B다. 다운로드 manifest/hash 및 분석 후 catalog의 동일 revision을 확인했다. 사용자 지형 포함 보고는 인수했으나 계단 치수·경사·지도 재구성 정확도를 독립 측량한 것은 아니다.

사용자가 새 매핑 시작 위치·방향을 세 기록 시작 때와 같다고 확인했다. 이를 근사 초기 prior로 사용했다. 새 매핑 `camera_init` 원점이 실제 시작 IMU 원점이라는 가정, 기존 수동 seed와의 관계는 아직 검증된 TF가 아니다. 동일한 물리 prior를 구·신 지도 좌표로 각각 표현했으며 숫자가 같은 transform을 두 지도에 복사하지 않았다.

A는 별도 관측 epoch, B/C는 같은 epoch다. A/B 시작 prior를 고정하고 C에는 B의 map-from-odom 관계를 유지한 표를 아래에 제시한다. 이 구조 규칙은 점수로 선택하는 새 seed가 아니다. 별도로 사용자의 시작점 답변을 각 기록의 첫 Odometry에 적용한 민감도 결과도 보존했다. 실제 배치 순간과 각 bag의 첫 표본이 일치한다는 증거는 없다.

같은 B/C epoch인데 두 기록의 첫 위치 추정값은 2.617m, 상대 자세는39.318° 다르다. 이를 물리적 시작점 차이나 실제 drift라고 확정할 수 없다. **C를 첫 표본 기준으로 다시 원점화하면 새 지도 잔차 중앙값321.3mm/수치 후보0개, B 좌표계를 유지하면55.6mm/후보3개**였다. 좋은 점수만 남기지 않고 두 결과를 함께 보존했다. “같은 시작점” 보고가 숫자 좌표 초기화를 정당화하지 않음을 보여준다.

앞서 계산한 coarse map/frame 후보도 private에 남겼다. old→new coarse 정합은 잔차 약248mm인 추정이며 검증된 지도 TF로 채택하지 않았다. 이전 worker 실행 오류 결과 역시 성능 실패 표에 섞지 않았다.

## 동일 입력 수치 비교 결과

기존 `run_seeded_arrays`/격리 SE3 worker를 그대로 실행했다. 같은 query hash/source stamp·처리 경로·초기 prior 근거를 유지하고 reference만 비교했다. full PCD를 입력하되 기존 solver의 reachable-reference 선택은 유지했다.

RMSE 한도 .05m, overlap .60, correspondence .75m, geometry ratio .002, seed bounds XY .75m/yaw25°/Z .3m/tilt10°, 프레임당3초를 변경하지 않았다. rear/side 가중치·속도·yaw tolerance·progress checker 변경은0건이다. 이 제한을 풀어 통과시키지 않았다.

| 기록 | 비교 수 | 기존→새 RMSE 중앙값 | 기존→새 overlap 중앙값 | 기존→새 수치 후보 | 판정 |
|---|---:|---:|---:|---:|---|
| A | 11쌍 | 230.7→63.1mm | .782→1.000 | 0→0 | FAIL: 새 지도11/11 HIGH_RESIDUAL |
| B | 12쌍 | 205.5→60.2mm | .689→1.000 | 0→2 | FAIL: 분류 전2개만 후보, 나머지 잔차/seed 범위 미달 |
| C: B/C epoch 유지 | 20쌍 | 203.3→55.6mm | .745→1.000 | 0→3 | FAIL: 후보3개 외17개 HIGH_RESIDUAL |

RMSE는 .75m 안의 대응점 잔차이며 로봇 절대 위치 오차가 아니다. overlap1.0도 넓은 대응 거리 안에 모든 query 점이 있다는 뜻이다. 계단 형상·정확한 로봇 위치의 검증을 의미하지 않는다. 새 지도가 더 크고 밀도·관측 시점도 달라 지형 포함만의 순수한 인과 효과라고 단정하지 않는다.

| 기록·표시 구간 | 대표 수 | 기존→새 RMSE 중앙값(mm) | 새 수치 후보 |
|---|---:|---:|---:|
| A 분류 전 | 2 | 199.0→58.3 | 0/2 |
| A 상승 | 3 | 230.7→63.1 | 0/3 |
| A 정상부 | 3 | 236.8→115.0 | 0/3 |
| A 계단 하강 | 3 | 181.4→50.6 | 0/3 |
| B 분류 전 | 2 | 224.2→46.5 | 2/2 |
| B 계단 상승 | 3 | 199.2→52.5 | 0/3 |
| B 정상부 | 3 | 164.2→66.3 | 0/3 |
| B 경사로 하강 | 3 | 232.5→58.7 | 0/3 |
| B 정지 | 1 | 220.9→65.7 | 0/1 |
| C 분류 전 | 3 | 228.2→57.4 | 0/3 |
| C 진입 | 3 | 225.6→58.3 | 0/3 |
| C 경사로 상승 | 3 | 227.3→74.3 | 0/3 |
| C 정상부 | 3 | 210.5→62.1 | 0/3 |
| C 계단 하강 | 3 | 202.8→48.8 | 2/3 |
| C 하강 완료 후 | 3 | 202.1→53.5 | 0/3 |
| C 정지 | 2 | 200.3→51.1 | 1/2 |

A/B 진입 표시는 상승과 같은 시각으로 기록된 길이0 구간이므로 별도 수치를 만들지 않았다. A 최종 정지 보고는 캡처 밖이다. 새 지도 후보5/43은 B 분류 전2개·C 하강 표시2개·C 정지1개다. **5개를 이동 중 지형 위치추정 성공률이나 실제 Nav2 성공률로 쓰지 않는다.**

## 전체 시계열에서 확인한 사실과 한계

점군 source stamp의 비증가/중복은 세 기록 모두0건이다. 최대 간격은 A102.75ms/B101.32ms/C101.04ms, IMU는13.28/12.17/13.36ms다. 회수한 registered/Odometry 기록의 큰 입력 중단이 대표 실패의 첫 원인이라는 증거는 찾지 못했다. source clock의 물리적 보정·deskew·장착 extrinsic 검증까지 통과했다는 뜻은 아니다.

전체 LIO 높이·yaw/pitch·IMU 자세·각속도/가속도와16개 사용자 표시를 그렸다. 실제 운동 burst가 채팅 경계보다 앞서 나타나는 구간이 있으며, 특히 C의 “하강” 표시15.905초 구간은 LIO 시작–끝 위치차 약1.47cm, IMU 각속도 p95 약.02645rad/s였다. 단계 경계가 지연됐거나 구간에 정지가 포함됐을 가능성을 남긴다. C의 수치 후보를 “계단을 내려가는 동안 통과”로 승격하지 않는다.

단계 receipt 기준 C의 진입→하강 yaw 변화는 약+87°로 사용자의 왼쪽90° 관계와 부합하는 추정이다. A/B에서는 해당 표시 경계 사이가 각각 약+.6°/−13°라 동일한90° 실측으로 인정할 수 없다. 전체 기록에는 배치·회수·다른 회전도 들어 있다. 채팅 지연과 좌표계 문제를 구분하기 전에 사용자 경로 설명이 틀렸다고 판정하거나 궤적을 회전 보정하지 않는다.

원시 LiDAR→deskew→LIO→map matching 중 첫 악화 지점을 확정하려면 동일 처리 계약의 raw 재처리와 독립 보정/시각 확인이 더 필요하다. 이번에는 기존 registered 경로의 수치 진단과 원시 IMU 시계열을 비교했고 전체 raw LiDAR 재처리·연속 TF/scan/costmap/Nav2 재생은 하지 않았다. calibration/clock/map axes/독립 map lineage qualification을 임의로 true로 채우지 않았다. strict recorded-real evaluator 및 ATE/RPE/절대 정확도 판정은 BLOCKED다. 처리 시간은 프레임별 영수증에 남겼으며 peak memory는 미측정이다.

PNG/SVG 그래프, 전체 시계열 CSV/NPZ, 좌표계 후보, 프레임별 정합 결과, 실패한 인프라 시도는 private 증거에 보존했다. 공개 Git에는 점군·bag·사용자 화면·실제 절대 좌표를 넣지 않는다. JSON에 파일 hash와 재현 입력 식별만 남긴다.

## 실행 복구와 실제 장비 상태

첫 수치 실행은 child Python의 cwd/PYTHONPATH와 로컬 샌드박스의 Unix 소켓 차단으로 `NUMERICAL_WORKER_UNAVAILABLE`였다. 그 결과를 별도 인프라 실패로 보존하고 private runner 실행 환경만 수정했다. 기존 worker로 실제 결과가 나오는지 확인한 뒤 고정된 sweep을 실행했다. 최종126개 결과(공통 시작 가정86개와 C 연속 좌표 민감도40개)는 worker 오류0건이다. 그중 B/C epoch 유지 표의 구·신 지도 결과는86개다. 모델·품질 gate·시간 한도를 바꾼 재시도가 아니다.

2026-10-30 21:32:28 KST SSH readback에서 `robot-scope.service` active/PID43956, cwd release `robot-scope-15706c48c5e6`를 재확인했다. 실제 배포 code는 **15706c48c5e6df28be105b6f5bde825dce7c4b1f**이며 전체 source hash 검증은 앞선 C0 배포 영수증, 이번 재확인은 PID/cwd/service다. 보고서 커밋을 장비 code SHA로 혼동하지 않는다.

분석 후 읽기 전용 API에서는 mapping pipeline stopped/exit0(21:09:44 KST), 저장 succeeded, preview running이었다. 분석 시작 때 running이던 매핑을 C0가 중단한 것은 아니다. busy/unknown 모두[], lease 없음·pending output0·goal idle, observation STOPPED, 3D selected=null/LEGACY_2D다. 이는 소프트웨어 관측 상태이며 이번 분석에서 물리 정지를 새로 확인한 것은 아니다.

새 지도는 운영 source로 선택하지 않았다. 배포·서비스 변경·goal/자세/이동 명령0건이며 복구할 장비 변경도 없다. 이전 설정 영수증의 XY/yaw .10m/.10rad·.25m/s·10Hz·saved revision71933bad…를 수정하지 않았다. 현재 Nav2 idle이므로 실행 중 controller 파라미터 값이 있는 것처럼 보고하지 않는다. 기존 백업·5154761 복구 release·지도를 보존했다. 구현/배포/실기 E/N/G/R 상태는 [기존 전체 표](FINAL_ROUND1_RESULTS.md)에 그대로 있으며 실제 Nav2·녹색 버튼→다음 goal은 선행 저장 지도 정합/운영 qualification 의존 BLOCKED다.

## 별도 수정·2차 비교 후보

1. 지도 원점/축과 A·B/C epoch의 TF를 점수와 독립적인 근거로 먼저 확정한다. 같은 시작점 보고를 첫 bag 표본의 숫자 초기화로 대체하지 않는다.
2. 전체 시계열의 실제 운동 구간과 operator receipt 경계를 연결해 상승/정상/하강 라벨을 확정한다. 현재0초·캡처 밖·정지 포함 구간을 지형 성능 판정에서 구분한다.
3. 보정·source clock·지도 수집 lineage 확인 후 같은 기록/같은 gate의 단일 baseline을 다시 평가한다. 그 전에 yaw/속도/progress/rear 정책을 차례로 변경하지 않는다.

앱·테스트·CI 코드는15706c4 이후 변경하지 않았다. 해당 code의 Python3137·JS700 및 code CI41042751838 통과는 기존 영수증을 유지한다. 이전 결과 커밋47f4082의 [CI41050588194](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41050588194)는 이번 조회에서 success를 확인했다. 직전 준비 커밋65ea839의 [CI41051773748](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41051773748)도 success다. 이번 문서 SHA의 CI는 별도이며 과거 통과로 대신하지 않는다.
