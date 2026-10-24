# 곡선 회피·추종 개발 참고자료

작성: 2026-10-24. 범위: VM 오프라인 합성 평면 시뮬레이션. **실로봇 설정값 또는 주행 승인 자료가 아니다.**

## 결론

- 경로를 부드럽게 만들고 전진·횡이동·yaw를 함께 제한하는 구현을 추가했다.
- 기존의 빽빽한 5콘 배치에서는 새 곡선 후보를 채택하지 않았다. 처음 성공한 후보는 최소 여유가 기존 3.50 cm에서 1.63 cm로 감소했고, 3 cm 여유를 명시적으로 강제한 후속 후보들은 SAFE_WAIT였다. 기존 검증된 고정-yaw 경로는 그대로 보존한다.
- 동일 배치가 불가능하다는 뜻이 아니다. 기존 성공 trace가 이미 통과 가능성의 증거다. 새 알고리즘의 추종·회전·관측 격자 보수성이 아직 충분히 해결되지 않았다는 뜻이다.
- 별도의 더 넓은 5콘 진단 배치에서는 새 곡선 후보가 도착·정지했다. 이 결과를 기존 배치 개선으로 바꾸어 주장하지 않는다.

## 공정 비교: 같은 OPEN 진단 배치

콘 좌표는 `(0.18,1.80)`, `(0.18,2.08)`, `(0.18,2.36)`, `(0.82,4.05)`, `(0.82,4.33)` m이다. 각 받침은 26 cm, robot envelope는 0.81×0.56 m로 유지했다. 기존 좁은 배치의 좌표도 그대로 별도 보존했다.

| 항목 | 기존 추종 | 새 곡선 추종 |
|---|---:|---:|
| 실제 합성 종료 상태 | GOAL_REACHED | GOAL_REACHED, 최종 명령 0 |
| 시간 | 26.6 s | 51.7 s |
| 거리 | 4.256 m | 4.248 m |
| 전체 footprint 최소 여유 | 5.360 cm | 4.530 cm |
| 연속 기록 명령 사이 최대 선형 가속도 | 1.069 m/s² | 0.20 m/s² |
| 최초 명령 전 정지 상태를 가정한 최대 가속도 | 1.60 m/s² | 0.20 m/s² |
| body yaw 전체 변화폭 | 0° | 13.70° |
| 전진·횡이동 동시 구간 | 7.1 s | 17.1 s |
| 충돌 | 0 | 0 |

새 후보는 더 느리다. 속도·가속의 급변을 줄이고 yaw도 완만하게 변하도록 했지만, 모든 지표가 개선된 것은 아니다. 여유 또한 기존보다 작지만 이 진단 사례에서는 명시 기준 3 cm 이상이다. 3 cm는 이 실험의 합성 비교 기준이지 실로봇 권장 안전거리로 확정한 수치가 아니다.

## 구현

`simulate_curved.py`:
- `build_path`: 기존 observed-grid A*를 재사용하고 Laplacian smoothing을 적용한다. 원래 configuration-space 통로와 실제 padded rectangle 검사를 함께 통과하는 점만 허용한다.
- 경로 접선과 body yaw를 동일하게 강제하지 않는다. 몸체 yaw는 회전된 전체 사각형 여유에 따라 별도로 제한한다.
- `bounded`: 선형·각속도와 변화율을 제한한다.
- `safe`: 회전까지 포함한 padded footprint를 예측 구간에서 보간 검사한다.
- 제한된 safe-window recovery는 신선한 관측 격자에서만 후보 명령을 검사한다. hidden cone truth는 센서 생성과 사후 평가에만 사용한다.
- goal 근접 시 감속하고, 명령 0인 마지막 frame을 남긴다.
- 지연 입력은 실제 queue에 넣고 acquisition age로 거부한다. receiver TTL과 source age를 별도로 검사한다. 과거 경로를 유지하는 경우에도 매 명령마다 신선도와 swept collision 검사가 필요하다.

## 실제 사용한 VM 파라미터

| 파라미터 | 값 | 의미 |
|---|---:|---|
| 평면 격자 | 0.01 m | 원래 0.02 m 격자와 별도 표시 |
| 제어 주기 | 0.10 s | VM 이산 주기 |
| 이상적 LiDAR 주기 | 0.20 s | 센서 5 Hz |
| source age / receiver TTL | 각각 0.25 s | 같아 보이지만 서로 다른 검사 |
| 선속도 상한 | 0.16 m/s | 합성 실험 값 |
| 선가속도 상한 | 0.20 m/s² | 정상 동작에 적용 |
| 각속도 상한 | 0.18 rad/s | 합성 실험 값 |
| 각가속도 상한 | 0.35 rad/s² | 정상 동작에 적용 |
| lookahead | 0.05 m | 좁은 통로 후보 |
| OPEN 배치 yaw offset | ±0.12 rad | ±6.88°, 국소 여유에 따라 더 제한 |
| 예측 충돌 검사 | 0.25 s | 회전한 padded rectangle 사용 |
| robot envelope | ±0.405 / ±0.280 m | 관절 메쉬까지 보수적으로 포함하는 대상 |
| 추가 여유 | 0.03 m | CHECK_BODY = ±0.435 / ±0.310 m |

센서 만료·위험 정지는 가속도 제한보다 우선한다. 이때 순간적인 명령 0으로 인해 정상 가속도 상한을 초과할 수 있으며 이를 숨기지 않는다. 실제 로봇의 정지 응답·미끄러짐·잔류 이동은 이 모델에 없다.

## 실패·안전 시험

- 완전 차단 5콘: SAFE_WAIT 3.1 s, 이동 0.
- 4 s 이후 센서 dropout: 4.1 s부터 명령 0, SAFE_WAIT 7.2 s.
- 4 s 이후 0.4 s 지연 queue: source age가 0.25 s를 넘는 14개 sample 거부, 동일하게 정지.
- 정상 주행의 emergency slew override는 0. 센서 이상 사례는 안전 우선 override 1회씩.
- `test_curved.py` 14개 검사 PASS. 실제 기록된 경로의 full-footprint 보간 검사 수행.
- 독립 관절 mesh/foot-ground/hull 검사: 새 7,741 + 기존 3,981 보간 자세에서 벽·콘·바닥·envelope·관절 한계 위반 0. 실제 mesh 최소 여유는 새 10.213 cm, 기존 11.617 cm이며 보수적 사각형 여유와 다른 지표다. 접촉 동역학이나 실물 보행 검증은 아니다.

## 실주행을 위한 다음 검증 단계

1. 실제 로봇의 속도·횡이동·yaw 응답 지연, 제동 거리, 명령 watchdog을 계측한 뒤 controller 제약을 식별한다. 이 문서의 수치를 그대로 복사하지 않는다.
2. 실제 관절 자세·gait에 따른 swept envelope와 센서 사각지대를 측정한다. 위치추정 오차와 지연에 대한 여유를 따로 더한다.
3. 실제 ROS/Nav2 환경에서 Omni motion model 및 footprint collision 비교를 수행한다. 현재 Python 구현은 Nav2, RPP 또는 MPPI를 실행한 것이 아니다.
4. 원래 좁은 5콘에서 SE(2) feasibility, 관측 불확실성, 추종 오차를 분리하여 진단한다. 보기 좋은 곡선만을 목표로 여유나 몸체를 줄이지 않는다.
5. 영상에서는 합성 위치 SIM_GT, 완벽한 바닥 가정, 손실 없는 계산을 실제 위치추정·접촉 동역학과 구분한다.

이 자료는 다음 실험 설계를 위한 참고용이다. 로봇 접속·배포·주행은 수행하지 않았다.

## 공개 참고자료

- Unitree Go2 `SportClient::Move(vx, vy, vyaw)` 공식 인터페이스: https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/robot/go2/sport/sport_client.hpp . 전진·횡이동·yaw 입력의 존재를 확인하는 근거이며 안전한 수치나 실제 응답을 보장하지 않는다.
- Nav2 Humble MPPI 공식 설명: https://github.com/ros-navigation/navigation2/blob/humble/nav2_mppi_controller/README.md . Omni motion model과 경로·장애물·제약 비용 분리의 참고다. 이 VM 구현을 MPPI라고 명명하지 않는다.
- Nav2 RPP 공식 설명: https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/README.md . lookahead, 곡률·근접 기반 속도 조절, 전방 충돌 확인을 참고했다. 이 구현은 RPP 재현·비교 실험이 아니다.
- Unitree MuJoCo 공식 지원 범위: https://github.com/unitreerobotics/unitree_mujoco#supported-unitree-sdk2-messages . low-level simulator와 high-level Move 보행을 동일하게 취급하지 않는다.

## 재현

    python3 run_scenarios.py open_normal open_dropout open_delay blocked_5
    python3 analyze.py
    python3 test_curved.py -v

`open_baseline.json`은 이전 revision의 `simulate_slalom.run`에 위 OPEN 배치 좌표를 전달하여 생성했다. 입력·소스·결과 해시는 `SHA256SUMS.txt` 및 `VALIDATION.json`에 기록한다. 원래 좁은 배치의 실패들은 `results/attempt*`, `results/candidate*`에 보존한다. 대형 trace가 배포본에 없으면 먼저 재생성해야 하며 검사를 skip하여 PASS로 만들지 않는다.
