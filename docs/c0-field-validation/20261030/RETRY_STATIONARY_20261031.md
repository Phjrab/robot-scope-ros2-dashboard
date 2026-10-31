# 2026-10-31 새 지도 초기 정합 재시도

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
