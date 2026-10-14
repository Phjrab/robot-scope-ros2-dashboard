# 03 — 실데이터 SE3 qualification과 오프라인 도구

2026-10-14. Run ID: `run-20261014T041650Z`. [02단계](02_sensor_tf_and_capture.md)에서 실제 registered cloud 후보 6개와 원본 timestamp를 확보했다.

**실제 독립 입력의 6DoF 평가·절대 정확도·Jetson 성능은 BLOCKED다.** 실제 데이터가 생겼다는 이유로 sparse FAST-LIO 출력을 바로 적격 `REGISTERED_QUERY`로 바꾸지 않았다. synthetic 회귀와 recorded 입력 qualification 도구를 완료했다.

## 확보한 입력의 한계

- 현재 query는 FAST-LIO 세션의 `camera_init` sparse cloud다. 기존 PCD reference와 세션 원점이 동일하다는 증거·근접 seed가 없다. 같은 frame 문자열은 같은 원점을 의미하지 않는다.
- sensor/body 외부 파라미터의 독립 확인이 없고 `extrinsic_est_en=true`다. 원시 장치 clock 동기화도 미검증이다.
- 기존 PCD·occupancy hash와 lineage는 읽었다. 파일명이나 두 지도 간 정합만으로 독립 query·정답·현재 로봇 위치를 만들지 않았다. reference와 현재 query의 적격 map-family/revision 연결은 확정되지 않았다.
- 독립 위치·각도 정답이 없다. position/rotation error, ATE/RPE는 전부 `null`이다. 운영 pose 입력은 만들지 않았다.

실제 query 하나를 변환 없이 numeric `.npy`로 옮기고 부적격 manifest를 [recorded CLI](../../scripts/evaluate_recorded_se3.py)에 입력했다. 출력은 `BLOCKED`, 최초 reason은 `unqualified provenance: calibration_verified`, exit 2였다. 나머지 clock/frame/independence/seed 공백도 private manifest에 명시했다. 이 결과는 정합 알고리즘의 정확도 실패가 아니라 실행 전 qualification 실패다.

## 새 recorded CLI 계약

`scripts/evaluate_recorded_se3.py`는 synthetic CLI와 UI를 변경하지 않고 offline JSON만 생성한다. 입력 schema는 `robot-scope.recorded-se3-input.v1`이다. qualified manifest는 다음을 명시해야 한다.

- `evidence_type=recorded_real`, calibration/clock/frame 연결·독립 수집의 검증과 calibration/sensor config hash.
- reference/query의 서로 다른 session, map-family/revision, frame, metre unit, file hash, 정확한 kind; query 원본 source stamp.
- `reference_contains_query=false`, `T_target_source`, query registration application count가 정수 1. raw를 재명명하거나 이미 등록된 cloud에 odometry/extrinsic을 재적용하지 않는다.
- 사전에 고정한 1–5개 seed와 출처. 평가 ground truth는 seed로 허용하지 않는다.
- float32/float64 `.npy`, 기존 60–4000 points/좌표/finite/반복 상한. 자동 ground 제거·SE2 필터·숨은 전처리는 없다. 대형 PCD 전처리가 필요하면 별도로 출처와 파라미터를 검증해야 한다.

raw kind, 시간 누락, hash 불일치, 같은 session 또는 byte-identical reference/query, revision 불일치, 미검증 calibration/clock, truth seed, point 상한 초과와 nonfinite 입력은 거부한다. declaration 자체를 센서 교정의 실측 증거로 취급하지 않는다. 통과한 manifest도 외부 provenance 근거의 검토가 필요하다.

출력은 per-seed/repeat SE3 pose·status·overlap·residual·기하 지표, 표본 수를 포함한 p50/p95/max, native RSS 단위, source/CLI/module hash와 dirty 상태를 보존한다. 최초 호출과 같은 프로세스 warm 호출을 구분한다. 전처리는 시간에 포함하지 않는다. 독립 truth 평가·전역 탐색·운영 적용은 구현하지 않아 정확도는 계속 null이며 운영 적용/전역 재위치추정은 NOT_RUN이다. 출력 파일은 새 경로에 mode 0600으로 만들고 기존 파일은 덮어쓰지 않는다.

## 실제 실행한 회귀와 판정

Mac의 기존 synthetic benchmark 11 cases: 기대 status mismatch 0, false candidate 0, repeated structure seed ambiguity 확인. 기존 SE3 테스트 9개와 새 recorded qualification 테스트 4개를 수행했다. synthetic 결과를 실데이터 정확도나 Jetson 속도로 옮기지 않았다. NumPy SE3와 C++ SE2의 속도 비교도 새로 수행하지 않았다.

| 판정 대상 | 상태 | 다음 최소 조건 |
| --- | --- | --- |
| recorded 입력 qualification 도구 | PASS — 소프트웨어 계약 | 실제 provenance를 채운 독립 입력 |
| 적격 실제 입력 처리 | BLOCKED | 교정·clock·frame·세션·seed 증거 |
| 실제 지역 6DoF 정합 | BLOCKED | 위 입력 qualification |
| 독립 정답 기반 정확도 | BLOCKED | 측정 기준과 불확실성 |
| Jetson 동일 실제 입력 성능 | BLOCKED | 적격 입력과 전용 부하 창 |
| 전역 재위치추정 / 운영 적용 | NOT_RUN | 별도 구현·운영 검증 범위 |

독립 query/정답이 없으므로 정확도 gate를 사후 제작하지 않았다. private 결과는 `recorded-input-unqualified.json`, `recorded-se3-blocked.json`, `synthetic-se3-regression.json`이다. [매트릭스](02_04_validation_matrix.json)와 [04단계](04_d2_localization_planner.md)에서 별도 상태로 이어진다.
