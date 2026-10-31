# 2026-10-31 새 지도 초기 정합 재시도

최신 재확인: 조회 시점 서버 최신 job53db9049…는 **RMSE51.568mm / overlap100% / HIGH_RESIDUAL / FAIL**이며 사용자 초기값과 후보의 수평 차이는33.193cm다. 사용자 초기값의 전달·좌표 변환은 검증했다. 이전 위치297.037mm와 앞선 새 위치54.924mm 결과도 원래 사실로 보존한다. 문서 마지막 재확인 항목을 참조한다.

사용자의 현재 위치·방향 지정값이 서버에 접수됐고, 새 지도로 계산1회가 완료된 것을 확인했다. **결과는 FAIL / HIGH_RESIDUAL**이다. RMSE .297037m가 유지한 .05m 한도를 초과했다. 계산 job의 `succeeded`는 실행 완료이며 품질 통과가 아니다. 이미 완료된 사용자 제출 job을 조회·보존했고 C0가 중복 정합 요청을 보내지 않았다.

## 이번 결과표

| 항목 | 결과 | 근거·의존 관계 |
|---|---|---|
| 재부팅 후 연결·배포 인수 | PASS | dashboard PID1016/cwd `robot-scope-15706c48c5e6`; 이번에는 PID/cwd 재확인, 전체 source hash는 앞선 배포 영수증 |
| 제어 bridge 정지·관측 복구 | PASS | goal/lease 없음 확인 후 기존 lifecycle stop succeeded/inactive; observation-only FAST-LIO READY |
| 새 지도 reference | PASS | 49,080점, ID `4b672f17ec79b96d2d075189`, revision `32123a1b2eb19798d81aa930a6e7f0b02451fb219f9fa164abe99612d191d268` |
| 현재 seed 정합 계산 | PASS | job `f5b1f94a8c426bc30b7ceb67`, 계산 완료, 수치 수렴 true |
| 정합 품질 | **FAIL** | RMSE297.037mm >50mm; HIGH_RESIDUAL; admissible=false |
| 운영 TF/odom·Nav2 소비 | **BLOCKED_DEPENDENCY** | 초기 정합 미통과, 운영 지도 선택/위치 적용 안 함 |
| stop/dwell/시험 버튼→다음 goal·재출발 | **BLOCKED_DEPENDENCY** | 운영 위치추정 선행조건 미충족; gate 강제 통과·이동 없음 |

기존 기능별 구현/배포/실기 상태와 종료한 1차 표는 [FINAL_ROUND1_RESULTS.md](FINAL_ROUND1_RESULTS.md)에 그대로 보존한다. 이번 한 번의 초기 정합 결과로 기존 편집·저장·수동 지형 관측의 판정을 변경하지 않는다. [세 기록의 구·신 지도 오프라인 비교](TERRAIN_MAP_COMPARISON.md)도 그대로 유지한다.

## 수치와 적용 상태

입력은 새 관측 epoch의 cached registered XYZ 전체238점이며 exact-stamp Odometry 역변환 경로를 사용했다. full PCD49,080점을 인수했고 기존 solver가 reachable footprint로49,058점을 선택했다. PCD SHA256 `879cd0335fad8e15272ffcabcafdbf839f82afd19166a8d6ef2c343a96715203`은 전날 비교한 새 지형 지도와 일치한다. 예전 평지 지도 reference로 계산한 결과가 아니다.

| 지표 | 이번 값 | 유지한 기준 |
|---|---:|---:|
| 대응점 RMSE | .297037m | ≤.05m: FAIL |
| overlap | .756303 / 180대응점 | ≥.60: PASS |
| geometry ratio | .028821 | ≥.002: PASS |
| seed 대비 XY 보정 | .279351m | ≤.75m: PASS |
| yaw 보정 | .205572° | ≤25°: PASS |
| Z 보정 | .210342m | ≤.3m: PASS |
| tilt 보정 | 2.254625° | ≤10°: PASS |
| 전체 계산 시간 | 약713ms | 실행 완료 |

RMSE는 대응점 잔차이며 로봇 절대 위치 오차가 아니다. 겹침·수렴·seed 범위가 충족돼도 잔차 한도 미달 후보는 적용하지 않는다. 5cm 오차 한도, correspondence .75m, geometry ratio .002, 기존 bounds 및 Nav2 yaw/속도/progress/rear 정책을 바꾸지 않았다. 관측 기준점과 운영 위치에 적용하지 않았고 신규 goal·ARM·자세·이동 명령0건이다.

## 별도 원인 확인

확인한 사실은 새 지도 reference가 맞고, 지역 정합은 수렴했으나 잔차가 한도보다 크다는 것이다. 지도 축·높이 기준·장착 extrinsic·deskew·source clock·실제 초기 위치 정확도의 독립 검증은 남아 있다. 이 항목들이 잔차의 단일 원인이라고 확정하지 않는다. 반복 seed 변경이나 gate 완화로 통과시키지 않았다.

브라우저에서 보인 빈 초안만으로 미접수라고 안내했으나, 서버의 완료된 현재 seed job을 확인해 그 안내를 정정했다. **클릭 입력 결함은 확인되지 않았다.** 새 job이 없는 것처럼 다시 제출하거나 어제 평지 지도의 seed를 재사용하지 않았다. 정합 접수와 품질 판정의 근거는 서버 job·anchor proposal 영수증이다. 실제 seed 좌표와 원본 화면은 private에만 둔다.

사용자는 현재 로봇이 새 매핑 시작 때와 같은 평지·높이에 있다고 확인했다. 따라서 약21cm 보정값을 실제 바닥 단차로 간주하거나 지도/pose를21cm 이동하지 않았다. 현재 FAST-LIO 실제 프로세스의 params는 `fastlio_xt16.yaml`, SHA256 `3d3fd83fe14c21d07d0b7108f4818d74c0557d67006aa00bc24295e8d30dd4bd`이며 릴리스 파일과 일치한다. 매핑/관측은 같은 launcher의 설정 선택 경로를 공유한다. 현재 surface/map voxel은 각각.5m, online extrinsic estimation은 true다. 관측 모드의 차이는 map/path 저장·publish와 TF remap을 격리하는 것이다. 설정을 변경하지 않았다.

이 파일 일치는 전날 매핑 당시 실제 런타임 파라미터 영수증이나 두 세션의 실제 추정 extrinsic 일치를 증명하지 않는다. 별도 epoch의 장착 변환 추정과 coarse registered 모집단을 원인 후보로 남기되, 둘 중 하나가 이번 잔차의 원인이라고 확정하지 않았다. 현재 추정 extrinsic의 독립 보정값은 미검증이다.

다음 진단은 이 캡처의 입력 계약과 지도/관측 좌표계·높이 관계를 확인하는 작업이다. 이번 job의 입력 hash·captured context·수치 결과·후보를 private에 보존했다. 이 영수증 보존을 raw LiDAR 전체 재처리나 캡처 XYZ bytes 전체 회수로 표현하지 않는다. 독립 정답 없는 절대 정확도 판정은 하지 않는다.

## 남긴 장비 상태와 검증

현재 배포는15706c48c5e6df28be105b6f5bde825dce7c4b1f로 유지했고 신규 배포·설정 변경은 없다. 제어 bridge inactive, 관측 전용 FAST-LIO READY(30분 자동 제한), goal idle/lease 없음/pending output0, 운영3D selected=null/LEGACY_2D 상태를 읽었다. 관측은 사용자의 위치 지정 작업을 위해 유지하며 `관측 종료`를 자동으로 누르지 않았다. 이번 분석의 물리 정지 ACK는 별도로 측정하지 않았다. 이전 이동 승인을 재사용하지 않았고 새 이동창도 시작하지 않았다.

앱·테스트·CI 코드는 변경하지 않았다. 직전 보고서 c882124의 [CI41057038508](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41057038508)는 success를 재확인했다. 이번 문서 SHA의 CI는 별도로 확인하며 과거 통과로 대신하지 않는다. 새 지도 hash·현재 job 일치·유지한 gate·품질 판정·최종 제어 상태·기존 표 불변 검사를 수행했다. [기계 판독 영수증](RETRY_STATIONARY_20261031.json)에 상세 집계와 private 증거 hash가 있다.

## 추가: 로봇 위치 변경 후 새 초기값으로 정합

사용자가 로봇을 옮기고 새 위치·방향을 지정한 뒤 정합 실행을 요청했다. 관측 STOPPED와 bridge inactive를 확인하고 관측 전용 세션을 복구했다. 처음에는 navigation 소유권 충돌 응답409였고, 재조회에서 idle을 확인한 뒤 가드를 유지한 제한된 재시도1회로 READY가 됐다. 다른 작업을 강제 취소하거나 source gate를 우회하지 않았다.

사용자 새 위치 요청 `bb806a5b474e296f019105f6`은 약2초 뒤 CANCELLED였으며 captured_context=null/result=null이었다. 이를 정합 품질 FAIL로 세지 않는다. 사용자의 실행 요청 범위에서 그 요청에 저장된 새 pose·bounds·source_contract를 그대로 사용하고 5cm 제한을 명시한 새 요청1회만 실행했다. 이전 위치의 seed를 가져오거나 출처 계약을 억지로 갱신하지 않았다. 취소의 정확한 주체/원인은 미확정이다.

| 지표 | 새 위치 결과 | 판정 |
|---|---:|---|
| 계산 job | `f2b7ef3a977235a5c28eb75f` succeeded | 계산 완료 |
| query/full reference/reachable reference | 169 / 49,080 / 49,064점 | 기존 처리 경로 |
| RMSE | **54.924mm** | 50mm 한도보다4.924mm 초과: **FAIL** |
| overlap | 100% / 169대응점 | 기준 통과 |
| 수렴 / geometry ratio | true / .028795 | 기준 통과 |
| XY/yaw/Z/tilt 보정 | .242920m / 7.505369° / .085793m / .770782° | 원래 bounds 안 |
| 전체 계산 시간 | 약710ms | 완료 |

admissible=false/HIGH_RESIDUAL을 그대로 유지했다. 실패를 통과로 바꾸려고 5cm 한도를 올리거나 추가 pose/속도/yaw/progress/후방 가중 변경을 하지 않았다. 지도 PCD hash/revision은 위의 새 지형 지도와 일치한다.

이전297.037mm와 이번54.924mm는 물리 배치·observer epoch·query·초기값이 달라 동일 입력의 제어된 개선 비교가 아니다. 이번 수치는 절대 위치 정확도를 의미하지 않는다. 새 위치에서도 gate 미달이므로 관측 기준점/운영 TF·odom 적용, Nav2 goal, stop/dwell/button/다음 goal 재출발은 NOT_RUN/BLOCKED_DEPENDENCY로 유지한다. 관측 READY, goal idle, lease 없음/pending output0, operational selected=null/LEGACY_2D를 재확인했다. 추가 이동 명령은0건이다.

새 pose·bounds·출처 계약이 취소된 사용자 요청과 동일한지, 유지한 threshold와 지도 hash, 결과 미적용, 제어 상태를 검사했다. 이번 추가도 앱·테스트·CI 코드를 변경하지 않은 집계 문서 제출이다. 프레임별 실제 pose와 원본 수치 영수증은 private에 보존한다.

## 추가: 사용자 초기값과 정합 후보의 일치 여부 재확인

새 계산 없이 서버 결과를 다시 읽는 동안 최신 job이 직전 보고한 `f2b7ef3a977235a5c28eb75f`에서 이미 완료된 `53db9049c009bbacb11b6b3d`로 바뀌어 있었다. 이 재확인은 조회 시점 최신53db9049…/seed revision225를 기준으로 고정했다. 이전 수치54.924mm와 이번51.568mm를 같은 job의 변경으로 표현하지 않는다. 이 요청에서 새 정합 POST0건이다.

사용자 seed를 degree 단위로 구성한 행렬이 captured seed binding의 `T_map_odom_seed × T_odom_imu`와 1e-9 이내로 일치했다. 캡처 시각의 prior도 solver에 들어간 initial_map_from_scan과 일치했다. 사용자 초기값이 다른 위치로 잘못 전달되거나 degree/radian 변환 때문에 달라진 증거는 없다.

| 비교 항목 | 동일 캡처 시각의 후보−초기값 |
|---|---:|
| map X | −30.604cm |
| map Y | +12.852cm |
| 수평 거리 | **33.193cm** |
| map Z | −5.313cm |
| yaw | **+6.454°** |

둘 다 camera_init / FASTLIO_IMU 기준으로, 클릭 시각에서 캡처까지 약.100099초의 Odometry 전달을 반영한 뒤 비교했다. 조회 시점의 새 anchor-proposal pose는 Odometry가 이후 반영된 별도 값이므로 과거 캡처 초기값과 직접 섞지 않았다.

따라서 **초기값은 올바르게 전달됐지만 두 좌표는 일치하지 않는다.** 지도–점군 대응 잔차51.568mm와 초기값–후보의 위치 차이33.193cm는 서로 다른 지표다. 같은 ROI 안의 수치 후보라 해도 그 후보가 실제 물리 위치에 더 가깝다는 독립 검증은 없다. 현장 기준점/독립 측정 없이 어느 좌표가 실물에 맞다고 확정하지 않는다.

최신 결과도 수렴·겹침100%·local bounds는 충족하나 50mm 한도를 초과해 admissible=false/HIGH_RESIDUAL이다. 초기값/지도/기준 변경, 후보 적용, TF·Nav2·이동 명령은0건이다. 주황 prior와 파랑 rejected 후보를 같은 시각/좌표계로 겹친 PNG/SVG와 전체 좌표 비교는 private에 저장했다. 그림의 배경은 저장 지도 전체 높이 점들의 XY 투영이며 벽/바닥 분류나 새 정확도 증거가 아니다. 공개 Git에는 절대 좌표·점군 그림을 넣지 않는다.

## 추가: 높이5cm와 수평33cm 차이의 원인 구분

확인 대상은 위53db9049…의 동일 캡처 비교다. **높이 보정−5.313cm**, **수평 보정33.193cm**, **점군 대응 잔차RMSE5.157cm**는 서로 다른 양이다. 이 중 어느 것도 독립 실측한 로봇 절대 위치 오차가 아니다. 높이 보정값이 품질 한도5cm 때문에 만들어진 것도 아니다.

확인한 계산 구조는 다음과 같다. `experimental_se3.register_se3`는 6DoF point-to-point ICP로 가까운 지도 점에 대한 거리를 줄인다. 사용자 초기값은 반복 계산의 시작값이며 초기값 이탈을 억제하는 prior 비용항은 없다. `seeded_initialization.run_seeded_arrays`는 계산 뒤 XY.75m/yaw25°/Z.3m/tilt10° 범위를 검사한다. 이번33.193cm/6.454°/5.313cm는 그 범위 안에 있어 범위 검사로 거부되지 않았고, 최종 잔차로 거부됐다. 따라서 입력이 올바르게 전달돼도 이런 차이가 날 수 있는 구조임은 확인했다. 해당 후보가 실제 물리 위치로 더 정확하다는 뜻은 아니다.

높이 입력은 `height_source=approximate`, Z=0/roll=0/pitch=0이었다. 지도 좌표계에서 IMU 높이를 독립 실측해 고정한 값이 아니므로 6DoF 계산이 높이를 바꿀 수 있다. 같은 바닥이라는 사실만으로 매핑/관측 두 시점의 IMU 원점·로봇 자세·추정 장착 변환까지 같다고 증명되지는 않는다. 이5.313cm를 실제 바닥 단차나 센서 오차로 단정하지 않는다.

현재 실행 프로필의 `filter_size_surf=.5m`, `dense_publish_en=false`와 장비의 FAST-LIO 설치 소스를 함께 확인했다. `laserMapping.cpp`의 surface voxel 축소는 deskew 점군에서 `feats_down_body`를 만들고, `publish_frame_world`는 dense=false일 때 이 축소 점군을 world로 변환해 발행한다. 이번 정합에 들어온 cached registered XYZ 전체는172점이다. exact-stamp Odometry 역변환은 좌표를 되돌리지만 이미 축소된 점들을 복원하지 않는다. 50cm voxel이50cm 위치 오차를 뜻하거나 반 voxel이 오차 상한이라는 뜻은 아니다.

우선 비교할 가설은 이 coarse 대표점의 선택과 point-to-point 대응이 위치·yaw를 편향시키는지, 그리고 세션 간 IMU 원점/실제 추정 extrinsic이 다른지다. online extrinsic estimation=true이지만 두 세션의 실제 추정값은 독립 검증되지 않았다. 점군 축소 하나가33cm 차이의 원인이라고 확정하지 않는다. 새 지형 지도 reference hash는 일치하며, 사용자 초기값 전달/degree 변환 문제도 이번 행렬 검사에서 관찰되지 않았다.

overlap100%는 최종172점 모두가 대응 허용 거리.75m 안의 지도 점을 가졌다는 뜻이다. 위치 정답 또는 오차0을 보증하지 않는다. reference의 spatial covariance 약한 축은 pose uncertainty/Hessian이 아니므로 높이 관측 불가능의 증거로 사용하지 않는다. coarse seed 단계와 최종 단계의 모집단이 다른 잔차를 같은 입력의 개선률로 비교하지도 않는다.

다음 원인 분리는 한 시각의 동결된 원시/고밀도 점군과 현재 축소 점군을 동일 지도·seed·gate로 오프라인 비교하는 것이다. 현재 영수증은 정합 결과와 계약의 보존이며 고밀도 query 원본 회수/이 비교가 이미 완료됐다는 의미는 아니다. 현장 기준점/높이 측정도 남아 있다. 이번 진단에서 새 정합·설정/한도 변경·위치 적용·이동은 없었다.

장비 설치 `laserMapping.cpp` SHA256은 `63fc4d567e3952d4c7a5d08a9d3b15ded6ceb919ae75f463abf25c851c1af1f9`이며 관련 발행/축소/추정 경로 발췌를 private에 보존했다. 이는 설치 소스 읽기 결과이며 이번에 FAST-LIO 바이너리를 재빌드하거나 소스–바이너리 재현성을 새로 인증한 것은 아니다. 앱·테스트·CI 코드 변경은 없다.
