# 2026-10-31 새 매핑 지도 정합 1회

사용자가 다시 매핑한 `map_20261031_150246`의 저장 성공·매핑 정상 종료를 확인하고 새 관측 세션을 복구했다. 사용자가 새 지도에서 현재 위치·방향 지정과 로봇 정지를 확인한 뒤 브라우저에서 정합1회를 제출했다. job `725c89769977d33be483cc99`의 **계산은 완료**, 품질은 **FAIL / HIGH_RESIDUAL / 미적용**이다. 이번 C0의 중복 정합 POST는0건이다.

## 결과

| 항목 | 이번 결과 | 근거·의존 관계 |
|---|---|---|
| 새 지도 저장·종료 | PASS | PCD23,890점 + YAML/PGM/map-family 저장 succeeded; 매핑 stopped/exit0 |
| 새 reference 인수 | PASS | ID `22f75eff7935774b87cfeec4`, revision `9552c16eba5f0cac752b5e307b40b5267ac00d0d16a5058d98e8995aa27377af`; private 원본 백업과 worker PCD SHA 일치 |
| 관측 입력·새 초기값 | PASS | 새 source epoch, 160점 exact-stamp registered XYZ→IMU; 사용자 seed 행렬 전달과 캡처 시각 initial 일치 검증 |
| 정합 계산 | PASS | 수렴 true, 160/160대응점, 실행 약549ms |
| 정합 품질 | **FAIL** | RMSE51.491981mm >50mm, 한도보다1.491981mm 초과 |
| 운영 위치/TF·odom·Nav2 소비 | **BLOCKED_DEPENDENCY** | admissible=false, 운영 지도 선택/후보 적용0건 |
| stop/dwell/button→다음 goal·재출발 | **BLOCKED_DEPENDENCY** | 운영 위치추정 미충족; 이동0건 |

전체1차 sweep의 기능별 구현/배포/실기 판정은 [기존 결과표](FINAL_ROUND1_RESULTS.md)에 보존한다. 이번 결과로 기존 편집·저장·세 지형 기록의 판정을 바꾸지 않는다.

## 이전 결과와 나란히 비교

| 지표 | 이전 지도 최신53db9049… | 새 지도725c8976… |
|---|---:|---:|
| reference 전체 / 이번 query | 49,080 /172점 | 23,890 /160점 |
| 대응점 RMSE | 51.568mm | **51.492mm** |
| overlap | 100% | 100% |
| 초기값 대비 수평 보정 | 33.193cm | **23.425cm** |
| 초기값 대비 높이 보정 | −5.313cm | **−.980cm** |
| 초기값 대비 yaw 보정 | +6.454° | **+6.956°** |
| 품질 / 적용 | FAIL /없음 | FAIL /없음 |

두 열은 지도·관측 epoch·query·초기값이 다르다. 동일 입력 A/B나 절대 정확도 개선률이 아니다. 높이/수평 보정이 작아진 것을 실물 위치가 더 정확해졌다는 증거로 사용하지 않는다. 현재 위치의 독립 정답과 바닥/IMU 높이 실측은 없다. 점군 RMSE와 초기값 보정량도 서로 다른 양이다. 이번 새 지도 한 사례에서도 기존50mm 잔차 기준 통과는 해결되지 않았다는 사실만 확인한다.

## 유지한 설정과 별도 진단

새 지도 PCD SHA256은 `a60d3c52274dfec5dd94d2333fb10e0d788aa5d99d94dd6f50501e4882a7193f`, XYZ array SHA256은 `ee8b5d3fc2fa511404944a465102de24aa0c9fa9773d9bd5fe93285e2a6d8d30`다. worker는 reachable reference23,872점을 사용했다. 다른 지도/이전 observer epoch/이전 seed를 대입하지 않았다.

50mm 잔차 한도와 XY.75m/yaw25°/Z.3m/tilt10° bounds를 그대로 유지했다. 높이 입력은 approximate였으며 사용자 seed 행렬 재구성과 캡처 initial 비교를 각각1e-9/1e-12 이내로 검증했다. 이번 query160점은 현재 cached registered 모집단 전체이며 이미 축소된 점들을 원시 LiDAR 전체로 표현하지 않는다. 정확도 한도·속도·yaw tolerance·progress checker·후방 가중치 변경은 없다.

장비 dashboard PID1016/cwd `robot-scope-15706c48c5e6`를 읽었고 기존 전체 배포 영수증의 코드 SHA는 `15706c48c5e6df28be105b6f5bde825dce7c4b1f`다. 이번에 전체 source hash를 재감사하거나 배포하지 않았다. 현재 FAST-LIO PID80905의 실제 params는 `fastlio_xt16.yaml`, SHA256 `3d3fd83fe14c21d07d0b7108f4818d74c0557d67006aa00bc24295e8d30dd4bd`로 기존 파일과 일치했다. surface/map voxel.5m, dense publish=false, online extrinsic estimation=true를 읽었으며 변경하지 않았다. 이전 매핑 프로세스74037의 실제 런타임 파라미터/추정 extrinsic까지 소급 인증한 것은 아니다.

입력 전달 오류나 옛 지도 혼용은 이번 확인에서 관찰되지 않았다. 성긴 대표점의 point-to-point 대응과 매핑/관측 세션의 실제 IMU/장착 변환 차이는 원인 후보이며 단일 원인은 미확정이다. 같은 시각의 고밀도/축소 점군을 동일 지도·seed·gate로 비교하는 원인 분리는 아직 실행하지 않았다. 상세 계산 구조 분석은 [이전 진단](RETRY_STATIONARY_20261031.md)에 있다. 실패를 통과시키기 위해 다음 정합을 연속 실행하지 않았다.

## 남긴 상태와 증거

관측 READY(30분 제한), goal/pipeline idle, localization inactive, operational selected=null/LEGACY_2D, lease 없음/pending outputs0을 읽었다. 관측 시작/계산 직후 ownership의 navigation unknown이 간헐적으로 있었으며 직접 navigation→ownership 순차 재조회에서는 unknown0·navigation idle이었다. 이를 물리 정지 ACK로 표현하지 않는다. 물리 정지는 사용자가 확인했고 이번에 별도 로봇 ACK를 계측하지 않았다. 후보 적용/goal/ARM/자세/이동 명령0건이다. 사용자의 위치 확인을 위해 관측은 유지한다.

원본 PCD ZIP·map/scan 수치 영수증·절대 좌표·화면은 private에만 보존한다. 공개 제출은 [집계 JSON](REMAPPED_REGISTRATION_20261031.json)과 본 문서뿐이다. 원본 백업/worker hash, 새 epoch, 초기값 변환, 보정량, 유지한 gate, 설정 hash, 종료 상태 및 이전 여섯 보고서 불변을 검사했다. 앱·테스트·CI 코드 변경은 없다. 이 보고서 exact SHA CI는 제출 후 별도 확인하며 이전 CI 통과를 대신 사용하지 않는다.
