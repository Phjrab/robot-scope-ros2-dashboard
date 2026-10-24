# Go2 사족보행 자율주행: 근거 조사와 단계별 검증 제안

조사일: 2026-10-24 UTC. 목적: 기존 VM 시뮬레이션을 점진적으로 개선하고 Nav2 설정 검토에 필요한 근거를 정리한다. **실제 로봇, 운영 대시보드, 설정은 변경하지 않았다.**

## 1. 결론

이번 과제는 바퀴 로봇 경로를 그대로 이식하는 일이 아니다. Go2의 몸체 전후·좌우 이동 및 회전, 다리의 움직임 범위, 접지와 지형 통과 가능성을 분리해서 다뤄야 한다.

현재 평면 장애물 회피에서는 기존 경로 생성기를 유지하면서 (1) 몸체 전체 충돌 검사, (2) 전후·좌우·회전 속도의 연속 제어, (3) 자세와 이동 방향의 분리, (4) 센서·위치 추정·응답 지연에 대한 여유를 먼저 개선하는 것이 적절하다. 이후 실제 설치된 Nav2 버전에서 MPPI Omni를 비교 후보로 검토한다. 지금 설정을 바로 적용하거나 새 학습 프레임워크로 전면 교체하지 않는다.

현재 VM의 관절 애니메이션은 운동학적 시각화다. 접촉력, 마찰, 균형, 넘어짐, 실제 보행 정책과 지형 주행 성능을 검증한 결과가 아니다.

## 2. 주요 근거와 적용 범위

### Unitree 공식 SDK: 몸체 속도 명령과 실제 동작은 다르다

- [SDK2 SportClient 헤더](https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/robot/go2/sport/sport_client.hpp)는 Move(vx, vy, vyaw)를 제공한다. 따라서 좌우 이동을 무조건 0으로 제한한 차동구동 모델은 Go2 능력의 일부를 사용하지 못한다.
- [공식 Python 구현](https://github.com/unitreerobotics/unitree_sdk2_python/blob/master/unitree_sdk2py/go2/sport/sport_client.py)의 Move는 x/y/z 값을 직렬화하고 _CallNoReply를 호출한다. 호출 성공은 측정된 이동 성공이나 정지 확인이 아니다.
- 헤더와 예제에서 특정 펌웨어·보행 모드·바닥 조건의 안전 속도, 가속도, 제동 거리 보장을 얻을 수 없었다. 예제 명령값을 운영 제한값으로 복사하지 않는다.
- SDK2 라이선스는 BSD-3-Clause. 실제 연동에는 상태 수신, 명령 소유권, 좌표계, 갱신 주기, watchdog와 정지 확인이 필요하다.

### Nav2 MPPI: 몸체 경로 제어 비교 후보

- [Humble MPPI README](https://github.com/ros-navigation/navigation2/blob/humble/nav2_mppi_controller/README.md)는 DiffDrive, Omni, Ackermann 모델을 지원한다. Go2 평면 몸체 이동에는 Omni가 비교 후보지만 사족 접촉 동역학 모델을 의미하지 않는다.
- full SE2 footprint 검사와 장애물 critic을 사용할 수 있다. 장애물 비용을 무조건 높이면 좁은 통로의 진동 또는 불필요한 정지가 커질 수 있으므로 경로 진행·평활성·안전 여유를 함께 평가해야 한다.
- [Humble package.xml](https://github.com/ros-navigation/navigation2/blob/humble/nav2_mppi_controller/package.xml)에서 1.1.20, MIT 라이선스와 ROS2/Nav2, xtensor/xsimd/libomp 의존성을 확인했다. 사용자 장비에 실제 설치된 버전은 이 조사로 확인되지 않는다.
- CPU 실시간 성능에 관한 upstream 설명은 사용자 Orin NX에서의 측정값이 아니다. p50/p95 연산시간과 deadline miss를 별도로 측정한다.
- Humble과 최신 문서의 파라미터 이름 및 critic 동작을 혼용하지 않는다. 운영 패널의 표시, 서버 설정, 실제 로드된 플러그인, 활성 runtime 값을 각각 확인한 뒤 변경 후보를 제시해야 한다.

### Regulated Pure Pursuit: 유용한 기준선, 좌우 이동 활용 한계

[공식 README](https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/README.md)는 legged 플랫폼 적용과 곡률·충돌 기반 속도 조절을 설명하지만 omni의 측면 이동을 충분히 활용하지 않는다고 밝힌다. 기존 추종 기준선으로 비교할 수 있으나, 횡이동을 활용한 자연스러운 우회 과제의 유일한 선택은 아니다. 추종 제어기는 통과 가능한 경로 계획을 대신하지 않는다.

### 공식 Unitree MuJoCo: 물리 검증의 다음 단계

[unitree_mujoco](https://github.com/unitreerobotics/unitree_mujoco)는 BSD-3-Clause이며 MJCF와 C++/Python 시뮬레이터를 제공한다. 현재 README는 low-level 개발과 LowCmd/LowState/SportModeState 지원을 명시한다. 고수준 Move 명령을 보내면 실제 Go2 내장 보행 서비스가 그대로 재현된다고 볼 수 없다. 적절한 low-level 보행 제어기, 모델, 관절·접촉 상태 검증이 추가로 필요하다.

[unitree_rl_lab](https://github.com/unitreerobotics/unitree_rl_lab)는 Apache-2.0, IsaacLab 기반 Go2 등 환경과 학습·sim2sim·sim2real 흐름을 제공한다. 이는 향후 보행 연구의 공식 참고자료이지 현재 평면 경로 개선에 당장 필요한 전면 교체나 검증된 Orin 실행 패키지는 아니다. 이번 조사에서 설치·훈련·정책 실행은 하지 않았다.

### 지형과 발 디딤: 후속 확장

- [elevation_mapping_cupy](https://github.com/leggedrobotics/elevation_mapping_cupy)는 MIT의 GPU 기반 고도·지형 맵 처리 도구다. main은 legacy ROS1이며 최신 ros2 문서는 Ubuntu24.04/Jazzy/CUDA12를 대상으로 한다.
- [릴리스](https://github.com/leggedrobotics/elevation_mapping_cupy/releases)의 v2.0.0은 Ubuntu22.04/Humble, CUDA11/12, Python3.10 후보로 확인했다. 현재 환경과 맞는 tag와 의존성을 고정해야 한다. NVIDIA 데스크톱 GPU 결과를 Jetson 성능으로 해석하지 않는다.
- [Perceptive Locomotion through Nonlinear Model Predictive Control, 2022](https://arxiv.org/abs/2208.08373v1)는 ANYmal에서 지형 표현, 발 디딤 가능 영역과 전신 동역학을 결합한다. 핵심은 몸체 평면 경로가 비어 있어도 발이 안정적으로 디딜 수 있다는 뜻은 아니라는 점이다.
- [OCS2](https://github.com/leggedrobotics/ocs2)는 BSD-3-Clause C++ 최적 제어 도구다. Go2에 바로 배포되는 완성 보행 제어기가 아니라 모델·접촉·상태 추정과 비용함수 통합이 필요한 기반이다.

### 학습된 이동 응답: 아이디어와 사용 허가 구분

[Learned Perceptive Forward Dynamics Model for Safe and Platform-aware Robotic Navigation, RSS2025](https://arxiv.org/abs/2504.19322v2)는 지형과 proprioception 기반 미래 상태 예측을 MPPI와 결합한다. ANYmal 연구 결과이며 Go2 성능 보장은 아니다. [공개 FDM README](https://github.com/leggedrobotics/fdm/blob/main/README.md)는 IsaacLab 및 ROS Noetic/Ubuntu20.04 추론 환경을 설명하고 라이선스를 All rights reserved로 표기한다. 공개 열람 가능하다는 사실을 permissive open-source 재사용 허가로 오해하지 않는다. 여기서는 명령 속도와 실제 응답의 차이를 검증해야 한다는 설계 통찰만 참고한다.

## 3. 지금 VM에서 적용할 설계 원칙

1. 경로 위상은 유지하고 안전 통로 안에서만 곡선을 평활화한다. 보간으로 장애물을 가로지르지 않는지 전체 궤적을 다시 검사한다.
2. 전후 vx, 좌우 vy, 회전 omega를 공동 제어하되 이동 방향과 몸체 yaw를 같게 강제하지 않는다. 좁은 구간에서는 몸체를 통로와 평행하게 유지하면서 대각선 이동할 수 있다.
3. 충돌 검사는 중심점 대신 회전된 몸체 및 다리의 움직임 범위를 사용하고 시간 사이의 swept footprint도 검사한다. 애니메이션 다리 범위와 실제 물리 안전 여유를 구분한다.
4. 지도·위치·센서 시각·명령 응답의 오차 여유를 명시한다. 신선하지 않은 센서나 불명확한 경로에서는 새 운동 명령을 합리화하지 않는다.
5. 금지 영역·경사로·주차 상태·출구 상태는 단순 곡선 추종과 분리해 mission 상태로 검증한다. 실제 경기장 기준 좌표와 치수가 확정되지 않았다면 provisional geometry라고 표시한다.

### 좁은 통로에서 회전을 강제하면 안 되는 이유

이하 숫자는 전달받은 VM 가정이며 실측값이 아니다. 몸체 보수적 외곽 L=0.81m, W=0.56m, 콘 옆 유효 간격 0.69m를 가정하면 yaw 10도에서 투영 폭은 L*sin(10°)+W*cos(10°)=약0.692m다. 안전 여유가 없어도 간격을 초과할 수 있다. 실제 회전 허용 여부는 콘 위치와 전체 footprint 충돌 검사로 결정해야 하며 이 식만으로 전체 경로 가능성을 판단할 수 없다.

## 4. 검증 순서와 비교 지표

### A. 현재 운동학 VM, 작은 변경부터

동일 지도·시작점·목표·콘 배치·random seed로 기존 추종과 개선 추종을 비교한다. 빈 통로, 콘1개, 콘5개 슬라럼, 완전히 차단된 통로, 센서 지연/누락, 위치 편향을 포함한다.

기록: 목표 도달, 충돌 수, 최소 전체외곽 거리, 금지영역 침범, 경로 길이·시간, 전후/좌우 가속도·jerk, yaw rate, 연산시간 p50/p95, 제동 거리와 실패 사유. 경로를 찾지 못했다는 결과만으로 기하학적으로 불가능함을 증명했다고 말하지 않는다.

### B. 실제 버전과 일치하는 제어기 비교

운영 패널과 실제 플러그인 매핑을 먼저 조사한다. 그 뒤 격리된 재생/시뮬레이션에서 MPPI Omni와 기존/RPP 기준선을 비교한다. 샘플 설정의 vx/vy/omega, acceleration, critic weight, inflation 값을 실제 장비 권장값으로 승격하지 않는다. 어떤 개선을 어느 버전에서 확인했는지 기록한다.

### C. 접촉 동역학 및 지형 검증

공식 MuJoCo 모델과 검증 가능한 보행 제어기를 준비한 별도 단계에서 마찰, 발의 미끄러짐, 접촉, 몸체 자세, 발 도달 범위와 지형 통과를 검증한다. 고도 지도와 발 디딤 계획은 그 뒤 필요 구간에 추가한다. 관절 움직임 영상만으로 계단·경사·충돌 안전성을 주장하지 않는다.

### D. 미래 실기 검증 전제

별도 실기 작업 승인 후에만 진행한다. 단일 명령 소유자, 독립 정지 수단, 상태 신선도, 응답 지연·deadband·정지 거리·보행 모드별 속도 추종을 먼저 측정한다. 외부 VM 결과를 로봇의 보행 안정성 보증으로 사용하지 않는다.

## 5. 재현성과 조사 한계

함께 제공된 source_refs.json은 읽기 전용 git ls-remote로 확인한 조사 시점 branch/tag 참조다. branch 링크는 이후 변경될 수 있다. tag 값은 annotated tag object일 수 있으므로 commit과 동일하다고 단정하지 않는다. 이번 조사에서는 SDK, 시뮬레이터, 학습 도구를 설치하거나 실행하지 않았으며 사용자 실기 성능을 측정하지 않았다. 프로젝트의 실제 Nav2 패널/파라미터 매핑 감사 결과와 합쳐 변경 제안서를 작성해야 한다.

## 6. 저장소 감사와 연결할 때의 주의사항

별도 읽기 전용 감사가 main 7ef47dc249e4dba83865e78dc283f40013ea92de에서 확인한 내용은 NAV2_PANEL_EVIDENCE.md 및 parameter_inventory.json에 정리되어 있다. 감사 보고에 따르면 현재 기본 경로는 RotationShim + RPP/NavFn이며 UI 저장값 전체가 실행 중 플러그인에서 확인되는 구조는 아니다. 브리지의 vx/vy/wz 제한과 watchdog는 플래너의 비용함수나 가속도 파라미터와 별도의 계층이다. 따라서 현재 브리지의 측면 명령 한계가 존재한다면 MPPI Omni의 vy 후보도 그보다 넓게 설정해서 실제 성능으로 해석해서는 안 된다. 현재 로봇 runtime 설정을 이 조사에서 확인한 것은 아니다.

동일 감사에서 기존 C3 실험은 오프라인/차동구동 모델과 더 좁은 몸체 가정을 사용했다는 점이 보고되었다. 이 자료는 실험 절차와 비교 지표의 참고자료일 뿐 현재 Go2 애니메이션 외곽이나 실제 사족보행 성능의 순위 근거가 아니다.

진행 중 VM 개선 실험에서 평활화가 최소 여유를 줄일 수 있다는 중간 관찰이 전달되었다. 완성 결과로 인용하지 않으며, 안전 여유를 유지한 조건에서 속도·자세 평활성을 비교해야 한다. 좁은 콘 사이에서는 잠깐의 측면 이동이 기하학적으로 합리적일 수 있으므로 '항상 전진 대각선'을 합격 조건으로 강제하지 않는다.
