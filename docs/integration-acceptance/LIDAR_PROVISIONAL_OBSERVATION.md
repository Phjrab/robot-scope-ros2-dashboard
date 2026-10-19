# LiDAR 관측 잠정 잔차 정책 — 2026-10-19

## 변경 범위

실시간 저장 지도 관측 API와 기존 Maps 관측 패널에 명시적인 **inlier RMSE ≤ 0.10m 잠정 잔차 정책**을 연결했다. `0.10`은 만족, 그 다음 표현 가능한 값은 거부한다. 반올림·epsilon·입력 제거·평가 모집단 변경은 없다. 원본 offline `experimental_se3`의 5cm 기준과 validator는 그대로이며, live wrapper가 원본 결과와 새 판정을 별도로 보존한다.

- `residual_policy.py`: 고정된 원본/잠정 정책과 저장된 단일 잔차 평가. 전체 후보 승인 여부는 이 함수에서 미평가(false/null).
- `observation_policy.py`: 기존 단일 지역 정합의 수렴, 최종 대응점 60개, overlap 0.60, reference/matched geometry 0.002를 독립적으로 검사한다. 원래 HIGH_RESIDUAL 뒤에 가려진 비수렴을 통과시키지 않고 새/알 수 없는 solver 실패도 거부한다.
- API: `original_assessment`, `residual_evaluation`, `gate_reasons`, `provisional`, `candidate_kind`, `body_pose=null`, `tracking_verified=false`를 추가한다. source/map 재확인 이후에만 결과를 반환한다.
- UI: 정책 ID·단위·한계·두 판정값·원본 결과와 모든 기존 source/시간/좌표 조건을 검사한다. 새 정책이 없는 기존 응답은 5cm로만 허용한다. 잔차와 원본 판정을 실패 상태에서도 표시한다. JSON도 같은 구분을 유지한다.

기존 최대 512 query sample, catalogue 전체 normalized reference, 0.75m 대응반경, 단일 요청, 1Hz, 600ms 계산 한도, 1초 입력 신선도, 150ms receipt pairing, map revision/epoch/generation/늦은 응답/점프 검사는 유지한다. 현재 모델 표시는 기존의 **미검증 외부변환과 odometry를 이용한 관측 가설**이며 검증된 본체 pose가 아니다. 운영 TF·initialpose·goal·제어 경로는 추가하지 않았다.

## 실제 실행·프레임 근거

2026-10-19 읽기 점검의 로컬/로봇 HEAD는 `fe5bc2b20ed2d87b3380a134130ec721b1c57f69`, tree는 `b04eb72b58055cb64a6442acf27a2934918db4c0`이었다. 로봇 저장소는 clean, `robot-scope.service` active, control bridge inactive/disabled. 기존 dashboard 소유 XT16 preview만 실행 중이며 FAST-LIO/Nav2는 관측되지 않았다. ROS Humble/domain 0/CycloneDDS 환경을 변경하지 않았다.

8초 subscription 관측에서 `/lidar_points` 64,000점, `/velodyne_points` 16,000점, `/imu/body`의 `body_imu`, `/utlidar/robot_odom`의 `odom→base_link`를 수신했다. `/Odometry`와 TF는 수신되지 않았다. raw stamp epoch와 bridge stamp epoch가 달랐다. bridge는 초기 수신 시각 offset을 이용하므로 restamp된 age만으로 native freshness·센서 간 시계 동기를 검증할 수 없다. 수신 개수를 정밀 주파수나 물리 정지 증거로 해석하지 않는다.

실제 driver YAML은 `transform_flag=false`, frame `hesai_lidar`; bridge 소스는 XYZ를 그대로 복사하고 stride로 점 수를 줄인다. 배포 config/source hash는 로컬과 대조했다. 실제 executable hash도 별도 보존했으나 source와 binary의 재현 빌드 일치를 입증한 것은 아니다.

WeGo 매뉴얼의 명목 `T_IMU_LiDAR`는 R=I, t=(0.171,0,0.0908)m이다. 제품 FAST-LIO 설정은 Rz(+90°), t=(0.25,0,0)m, `extrinsic_est_en=true`이다. 배포 FAST-LIO 소스의 `p_world = R_world_imu*(R_imu_lidar*p_lidar+t_imu_lidar)+p_world_imu` 식은 확인했지만 현재 FAST-LIO는 미실행이며 추정 중 extrinsic은 미확인이다. vendor URDF의 base→imu 명목 이동은 (-0.02557,0,0.04232)m이고, 실제 LowState `body_imu`와 그 URDF `imu`의 동일성은 입증되지 않았다. 어떤 값을 실측 본체 보정으로 승격하거나 자동 적용하지 않았다.

private 근거: `robot-scope-hardware-validation-private/lidar-integration-20261019/`의 `runtime-inventory.json`, `ros-frames-and-config.json`, `native-source-readback.json`, `FRAME_RUNTIME_AUDIT.md` 및 근거 JSON. 장비 식별·raw map 자료는 Git에 넣지 않는다.

## 과거 실제 점군과 v0.3.1의 구분

기존 v0.3 raw879 최선 기록은 **0.07044731830991433m**, 15,200/16,000 inlier, overlap 0.95다. 새 기준의 **잔차만 통과**한다. 원본 `RMSE_ABOVE_0.05M`, `REFINEMENT_NOT_STATIONARY`, selected_candidate=null을 그대로 보존했다. 새 `RAW879_RESIDUAL_COMPARISON.json`은 저장된 scalar를 비교한 sidecar이며 재정합은 0회다.

v0.3.1은 별도 source copy에서 import와 합성 회귀 50개를 통과했다. 원본 파일과 이전 결과를 보존했고 실제 raw879 재실행은 하지 않았다. source-only raw 전역 SE3의 출력은 `T_map_sensor`이며 live wrapper의 `T_map_odom`과 다른 계약이다. 기존 raw 전역 실행은 8.3초로 실시간 600ms/신선도 1초와 호환되지 않는다. 이를 live solver로 교체하거나 historical stamp를 현재 시각으로 바꾸지 않았다.

또한 원본 전역 worker는 5cm gate를 기준으로 대안을 보존하므로 저장된 대표 후보에서 잔차 이유만 제거해 10cm 전체 후보 선택/ambiguity를 재판정할 수 없다. 전역 통합에는 새 정책을 명시한 별도 버전, 모든 후보의 동일 원본 채점·ambiguity 검증, immutable map/source/job 계약, 취소·timeout·완료 재확인, sensor pose 전용 표시가 필요하다. 확인되지 않은 sensor↔body 변환을 넣지 않는다.

## 검증·배포와 다음 최소 작업

합성 회귀는 정확한 경계, 단위/비유한값/반올림, 원본 결과 보존, 수렴 실패 은폐 방지, geometry/support, malformed UI 정책, source/map/epoch 변경, stale/늦은 응답과 별도 잔차 표시를 다룬다. 실제 정합 잔차 감소·절대 위치 정확도·본체 pose·연속 추적·주행은 이번 변경의 검증 결과가 아니다. 정확한 시험 결과와 candidate commit은 private `LOCAL_VALIDATION.json`에 기록한다.

장비 배포는 Git 반영과 별도다. 현재 installed source는 위 `fe5bc2b`이며 새 변경은 로컬 검증 대상이다. 배포하려면 source bundle·설정/지도/런타임 보존 manifest·복구점을 준비하고, 현재 소유권과 미저장 세션을 다시 읽어 확인한 뒤 dashboard와 그 소유 기존 XT16 preview의 재시작 범위를 사용자에게 제시한다. 카메라·broker·새 FAST-LIO/Nav2·control bridge는 변경 대상이 아니다. 실제 현재 입력으로 정합할 때도 18일 시작 위치·방향과 같다는 사용자 설명은 근사 초기 추정이며 독립 정답이 아니다.
