# A3 · 2D 수동 초기 위치 주행

## 대시보드 사용법

1. **실험 → 2D 수동 초기 위치 주행**을 연다. 저장된 2D occupancy 지도와 현재 설정 revision, profile을 확인한다. 현재 장소와 일치하는 지도를 선택하고 확인란을 누른다.
2. **실험 준비**를 누른다. 기존 상대 odometry·LiDAR·Nav2·signed bridge 경로를 준비한다. 준비에서 seed와 목표 전송은 발생하지 않는다.
3. 정지 상태에서 **INITIAL POSE / 다시 지정**을 선택한다. 지도 위 실제 본체 위치에서 바라보는 방향으로 드래그하고 **초기 위치 적용**을 누른다. `ready_manual`, seed 수락 시각과 TF 확인을 본다.
4. **GOAL POSE**를 드래그하거나 같은 지도 revision의 저장 위치를 선택한다. 미리보기의 방향을 확인하고 **이동 시작**을 누른다. 한 번에 한 목표를 실행한다.
5. **목표 취소**, **Nav2 STOP / 실험 종료**, **비상정지 (소프트웨어)**는 각각 기존 취소, Nav2 세션 종료, 제어 정지 경로를 사용한다. 목표 결과와 실제 정지를 각각 확인한다.
6. seed를 다시 지정하려면 목표를 취소하고 실제 정지를 확인한 뒤 새 위치를 적용한다. 로봇을 손으로 옮겼거나 지도를 바꾸려면 실험을 종료하고 다시 준비한다. 안전 조건을 잃어 seed 적용이 잠긴 경우에도 같은 절차를 따른다. 페이지 이동·새로고침은 명령을 발행하지 않는다.

## 동작과 제한

- 화면의 `MANUAL_SEEDED_ODOMETRY`는 지도 재보정이 없는 모드다. 실제 위치 정확도는 미검증이다. 상대 odometry의 누적 이동 거리는 추정 오차를 나타내지 않는다.
- 준비 요청은 2D 지도와 파라미터 revision을 고정한다. job별 `manual-navigation.json`에 모드, job ID, 지도 ID/revision을 기록한다. 설정·프리셋·PCD 원본은 기존 저장 위치에 둔다.
- 기존 `/initialpose` 경로의 수동 SE(2) 계산을 재사용한다. 실험은 해당 계산에 job, 지도, runtime instance, odometry epoch 및 seed 세대가 묶인 요청만 받는다. 브라우저와 ROS 수신 사이에 현재 세대가 바뀌면 요청을 거부한다. runtime receipt와 새 TF 발행의 ROS 토픽 echo가 확인되어야 목표가 열린다. A1은 현장에서 Nav2의 TF 조회와 실제 장착 기준을 별도로 확인한다.
- 실제 입력은 FAST-LIO `/Odometry`, LiDAR `/velodyne_points`에서 만든 `/scan`, profile의 controller 속도 odometry다. 컨트롤러 입력과 상대 위치 입력의 실제 토픽은 화면에 표시된다. Nav2, 원시 속도 토픽, signed bridge, watchdog, 취소, recovery 출력 차단은 기존 구성을 사용한다.
- 실험은 `/tf`와 `/tf_static`에 다른 발행자가 없는 ROS 그래프를 요구한다. Humble의 관측 근거로 공유 TF 토픽의 발행자를 프레임별로 확정하기 어렵기 때문에 적용한 보수적 제한이다. FAST-LIO를 새로 시작할 때는 기존 TF 격리 경로와 상대 odometry 전용 준비 검사를 쓴다. 기존 주행·관측 소유자는 운영자가 정상 종료한 뒤 준비한다.
- scan, odometry, TF, source, 제어권 상태가 바뀌면 현재 seed를 무효화한다. 작업이 교체되거나 지도가 바뀌면 새 준비와 seed가 필요하다. 대시보드 지도 수정은 기존 작업 상호 배제로 막는다. 관리 지도 파일이 외부에서 바뀐 경우 명령 경계에서 감지해 기존 실험을 닫는다. 주행 중에는 job의 고정 지도 스냅샷을 사용한다.
- 정상 주행은 기존 3D 사전검사, bundle, geometry와 match 조건을 사용한다. 구성된 3D job의 bundle이 사라지면 실행이 실패한다. 실험 job에는 이 bundle과 PCD가 생성되지 않는다.
- 합성 검증은 오프라인 UI/API와 ROS 콜백 동작을 확인한다. 네이티브 Nav2와 실제 장비 판정은 [검증 기록](ROUND1_RESULTS.md)에 구분했다.

## `4cebeed` 격리 Nav2 검증

2026-11-05 KST. 제품 SHA `4cebeed8f309a1f5e69ade96f21a4f29d2ba93f4`를 Ubuntu 22.04의 ROS 2 Humble과 Nav2 1.1.20에서 실행했다. 시험 컨테이너는 `--network none`, 루프백 인터페이스만 사용했다. 실제 NavigationRosGateway, ControlManager, map_server, planner, controller와 BT를 사용했고, LiDAR·두 odometry·브리지 상태·구동부는 모의 입력으로 연결했다. 모의 위치는 Nav2 명령을 적분해 갱신했다. 아래 좌표 단위는 m, 방향 단위는 rad다. [통과한 실행과 증거](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41983696807)

| 검사 | 네이티브 결과 |
| --- | --- |
| 비영점 odom 시드와 TF | odom의 `(7.00, −3.00, 0.80)`에서 map 시드 `(2.00, 3.00, 0.25)`를 수락했다. 독립 tf2 조회가 위치와 방향을 재현했다. `/tf`·`/tf_static`의 소유자는 위치 런타임 하나였다. |
| 직선 목표 이동 | 목표 `(3.60, 3.00, 0.00)`에 Nav2 `SUCCEEDED`. 실제 모의 위치 오차 0.350 m, 방향 오차 0.0016 rad였다. |
| 이동 중 취소 | Nav2 `CANCELED`. 취소 요청 시점부터 정지 확인까지 추가 이동은 0.000 m였다. |
| 장애물 | `/scan`으로 관측한 장애물 셀의 비용값이 0에서 100으로 바뀌었고, Nav2가 우회 후 목표에 도착했다. 접촉 0회, 모의 로봇 외곽 기준 최소 여유 0.053 m였다. |
| 상대 odom 중단 | 활성 목표가 취소되고 제어권과 이전 시드가 무효화됐다. 정지 확인까지 0.81초, 추가 이동 0.101 m였다. odom 복구 후에도 이전 TF 발행은 재개되지 않았고 이전 시드의 목표 요청은 거부됐다. |
| 새 작업에서 재시드 | 변경된 odom 원점 `(4.70, 5.20, −0.45)`에서 새 초기값을 명시 적용했다. 독립 tf2 조회를 확인했고 다음 목표가 `SUCCEEDED`였다. 위치 오차 0.346 m였다. |

**A1 확인 사항** · 이 SHA에서는 시드가 수락되고 API의 목표 허용 상태가 켜져도 `bt_navigator`가 아직 비활성일 수 있다. 실제 선행 실행에서 초기 시드 및 재시드 직후 첫 목표가 각각 거부됐다. 통과 실행은 `/bt_navigator/get_state`의 `ACTIVE` 확인 뒤 목표를 명시 전송했다. 최초 시드와 재시드에서 그 상태를 기다린 시간은 각각 약 0.91초와 0.86초였다. 현장에서도 `ros2 lifecycle get /bt_navigator`의 `active`를 확인하고, 거부된 목표는 자동 재전송 없이 별도 명시 조작으로 처리한다. [활성화 전 거부를 재현한 실행](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41983058893)

장비 접속·배포·주행은 `DEVICE_NOT_RUN`이다. 실제 FAST-LIO 추정기, signed 하드웨어 브리지, 장비용 시작 검사, 물리 장애물 여유는 이 시험 범위 밖이다. 재현은 [격리 시험 워크플로](../../../.github/workflows/a3-native-nav2.yml)에서 실행하며, 매번 `4cebeed`를 고정한다.

## A1 배포 및 현장 인계

- 배포 후보는 [소스 기록](SOURCE_LOCK.json)의 `implementation_sha`다. A1의 이전 시험에 사용한 고정 배포는 별개다. 현장 시험은 새 승인 범위를 확보한 뒤 A1이 수행한다.
- 배포 전 실제 bridge·control lease·FAST-LIO·controller odometry·scan·TF 및 현재 소유자를 확인한다. 사용 중인 안전 설정과 파라미터 revision을 기록한다. 2D 지도가 실제 평면 주행 구역과 일치하는지 확인한다.
- **실험 준비**만 눌러 무이동 상태, single TF authority, 현재 토픽, fresh scan·odom 및 runtime mode를 확인한다. 정지 관측을 마친 뒤 물리적으로 확인한 위치와 방향을 seed로 지정하고, TF readback과 목표 허용을 확인한다.
- 여유 공간이 충분한 짧은 목표 한 개부터 확인한다. Nav2 결과, zero command, bridge ACK, 실제 정지, 외부 XY/yaw를 각각 기록한다. 이어서 현장 승인 범위에서 목표 취소와 STOP, odom 손실 뒤 재시드, 저장 위치 및 장애물에 대한 정지 또는 우회를 확인한다.
- 비활성화는 Nav2 STOP으로 현재 실험을 끝내는 방식이다. 기존 소유권과 ROS 그래프 정리를 확인한다. 일반 주행 복귀에는 기존 3D 준비와 새 초기화가 필요하다. 릴리스 원복이 필요하면 A1의 마지막 검증된 고정 SHA와 현장 설정을 사용한다.
