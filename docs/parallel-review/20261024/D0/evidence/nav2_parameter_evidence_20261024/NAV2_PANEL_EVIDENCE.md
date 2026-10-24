# Go2 Nav2 패널: 유지·변경 후보에 대한 읽기 전용 근거 검토

작성: 2026-10-24 UTC. 조사 HEAD: `7ef47dc249e4dba83865e78dc283f40013ea92de` (13:10 UTC 원격 main 확인).

## 결론

현재 패널은 그대로 보존하고, **제어기별 프로필과 실행값 관측을 먼저 구분하는 설계**를 검토하는 것이 타당하다. 기존 수치를 몇 개 바꾸는 것만으로 Go2의 자연스러운 대각선 우회·발 디딤·경사로 대응이 구현되지는 않는다. UI/설정/서비스/로봇에는 아무 변경도 하지 않았다. 아래 숫자는 저장소 기본값과 허용 범위이지, 현재 온보드 실행값이나 안전 보증이 아니다.

### 확인한 사실

1. 패널은 27개 키를 표시하며 5개는 고정값이다. 기본 경로는 NavFn A* → Rotation Shim → RPP이다. 플러그인 클래스는 서버에서 고정되므로 UI의 값 조정으로 MPPI로 전환할 수 없다.
2. APPLY는 ROS의 즉시 파라미터 변경이 아니다. 실행 중에는 저장을 거부하고, 검증된 YAML과 revision을 저장한 뒤 **다음 Nav2 시작**에 사용한다. 프리셋 LOAD와 RESET은 draft 작업이며 이미 저장된 서버 설정을 롤백하는 기능과 다르다.
3. 서버는 이전 YAML을 백업하지만, 조사한 API에는 이 파일로 즉시 롤백하는 전용 명령이 없다. 이전 프리셋/값을 선택해 다시 저장하는 절차와 런타임 확인이 필요하다.
4. 별도 collision-mask 프로필 생성기는 직접 RPP로 전환하고 polygon footprint를 거부한다. 그 프로필이 실제 사용되는지는 이번 조사에서 확인하지 않았다. UI 기본 plugin을 현재 로봇의 실제 plugin이라고 단정할 수 없다.
5. GetParameters/GetState 기반 readback은 이미 존재한다. 다만 정책·플러그인·costmap 검증용 목록이며, 패널의 속도·lookahead 등 27개 값 전체를 readback하지는 않는다. 저장 성공과 실제 런타임 적용 확인을 구분해야 한다.

## 기존 항목 분류 및 판단

| 묶음 | 현재값 / 허용범위 | 적용 지점 | 판단 / 검증 근거 |
|---|---|---|---|
| `desired_linear_vel` | .25 / .05–1.0 m/s | RPP FollowPath | KEEP, 명칭 CLARIFY. 전후진 전체 속도 제한이 아니라 RPP 목표 선속도. 실제 명령은 bridge 제한·보행 응답의 영향을 받음. |
| `controller_frequency` | 10 / 10–20 Hz | controller_server | KEEP. 계산 지연·명령 도착 간격·watchdog을 함께 측정해야 하며 20Hz 숫자만으로 안정성 입증 불가. |
| `lookahead_time`, `min_lookahead_dist`, 속도연동 | .8s(.2–2), .25m(.1–.6), true | RPP | KEEP for RPP. 최대거리 .9m, 고정거리 .6m는 base YAML에 있으나 패널에서 바뀌지 않음. 속도연동 false이면 time/min만 바꿔도 기대 효과가 없을 수 있음. |
| `rotate_to_heading_angular_vel`, `max_angular_accel`, `angular_dist_threshold` | .5rad/s(.1–.5), 1.2rad/s²(.1–1.2), .785rad(.1–π) | Rotation Shim / 일부 RPP 이름 공유 | CLARIFY. 일반 회전 속도·모든 출력의 가속도 제한과 동일하지 않음. Shim 진입/탈출, 신경질적 회전, 좁은 폭에서 full footprint 검사 필요. |
| `transform_tolerance` | .3 / .05–1s | controller FollowPath | KEEP. localization 오류나 잘못된 timestamp를 덮기 위해 늘리지 말 것. source age·수신 TTL·TF 허용시간은 서로 다른 계약. |
| `robot_radius` | .22 / .15–.40m | 양 costmap 원형 근사 | 우선 재검토 후보. 원형 반경은 길쭉한 Go2와 움직이는 다리 외피를 나타내지 못함. 작은 원은 길이 방향을 놓치고 외접원은 좁은 통로를 과도하게 막을 수 있음. 숫자 축소로 해결 금지. |
| `inflation_radius`, `cost_scaling_factor` | .25m(.16–1), 5(1–20) | 양 costmap inflation | KEEP but controller/footprint별 조합 검증. inflation_radius≥robot_radius가 현재 서버 제약. footprint+padding+inflation을 이중 물리 반경으로 계산하지 말고 lethal/soft-cost 역할을 구분. |
| 높이 slice min/max | -.5m(-1–1), 2m(.1–3) | runtime PointCloud2→LaserScan | KEEP, 프레임·장착 높이·roll/pitch 의존성 명시. Nav2 LaserScan layer의 높이 gate는 고정 -1..3m임. 단순 2D 투영은 발 디딤/턱/계단 통행가능성 판정이 아님. |
| 장애물/광선 범위 | 8m(.5–12), 10m(.5–15) | projection + 양 obstacle layer | KEEP. raytrace≥obstacle 제약 유지. 미관측·가림을 자유공간으로 지우지 않는지 센서 시험 필요. |
| `always_send_full_costmap` | true | 양 costmap 발행 방식 | KEEP. 지도 전송/관측 완전성 항목이지 로봇 clearance 증가 기능 아님. |
| `track_unknown_space` | true | global costmap | CLARIFY. base NavFn `allow_unknown=true`와는 다른 값. mask 프로필은 false/tolerance0으로 강제. 프로필별 unknown 정책을 명시해야 함. |
| XY/yaw goal tolerance | .35m(.05–1), .45rad(.05–π/2) | SimpleGoalChecker | 일반 Nav2 goal용으로 KEEP. 대회 정지선 두 앞발·P 전신 포함·앉기·2/5초·OUT 완전통과 판정을 대체하지 못함. |
| `required_movement_radius` | .20m(.05–1) | SimpleProgressChecker | KEEP. base movement_time_allowance10s는 비노출. 저속·옆걸음·정지 미션과 정체 판정 충돌을 별도로 시험. |
| `use_astar` | true | NavFn | KEEP. 격자 검색 방식을 바꿀 뿐 orientation-aware/footstep planner가 되지는 않음. |
| 고정 5개 | RPP rotate false, Shim true, goal rotate true, closed_loop false, stamped false | profile/호환성 | 현재값 유지. 바꾸려면 해당 controller profile·Humble 버전·bridge 메시지 호환 검증을 먼저 수행. |

정확한 27개 키·기본값·범위·잠금값은 동봉 `parameter_inventory.json`에 소스 AST에서 추출했다(프로젝트 코드 실행/설정 변경 없음).

## 4족 특화 추가 후보: 지금 적용하지 않음

### A. 먼저 보이게 해야 할 상태
- 선택한 controller/primary_controller/설치된 Nav2 버전, 저장 revision과 실제 적용 revision, STOP 후 적용 필요 여부.
- 요청값 / bridge 허용값 / 실제 적용값 / 관측된 몸체 속도를 별도로 표시.
- 현재 프로필의 원형·polygon footprint, padding, unknown 허용 정책, 실제 readback freshness.

### B. 별도 검증 후 선택할 제어기 프로필
- 기존 RPP는 비교 기준으로 유지한다. 부드러운 곡선 추종 자체가 반드시 MPPI 교체를 요구하지는 않는다.
- MPPI Omni는 `vx/vy/wz`를 함께 고려하는 후보지만 설치된 **Humble** 버전에 맞는 파라미터, polygon 충돌 옵션, 최적화 지연을 시험해야 한다. 4족 발 디딤·접촉·보행 안정성 모델을 제공하는 것으로 오해하지 않는다.
- `vy_max`, `vx_max/vx_min`, `wz_max`, horizon(`time_steps×model_dt`), critic/footprint 설정은 **MPPI 프로필 전용** 후보다. RPP의 lookahead에 이름만 대응시켜 복사하지 않는다. Ackermann의 최소 회전반경을 4족의 기계적 제약으로 도입하지 않는다.

### C. 바디 명령과 실제 보행의 경계
- 저장소 bridge hard cap: x≤1.0m/s, |y|≤.20m/s, |yaw rate|≤.50rad/s, 명령 timeout≤.20s. 이것은 프로젝트의 제한이며 Unitree의 실물 안전 동작 범위를 인증하는 숫자가 아니다.
- onboard config의 선형/측면/각 가속도 .8/.6/1.2는 control 계층 값이다. 패널의 같은 이름 `max_angular_accel`과 별개다. controller가 낸 값이 clamp/slew된 뒤 어느 궤적이 되는지 확인해야 한다.
- Go2 SDK Move는 vx/vy/vyaw를 받는다. 이것이 보행 컨트롤러가 어떤 지형에서도 동일 속도를 정확히 실현한다는 뜻은 아니다. 경사·계단·미끄럼·발 디딤은 별도 관측/자격시험이 필요하다.
- 실측 전 후보 값을 실장비 기본값으로 추천하지 않는다. VM의 IK 관절 애니메이션은 보행 제어기로 배포할 산출물이 아니다.

## 설정 변경 여부를 결정하기 위한 근거 수집 순서

1. 현재 프로필과 설치 패키지/런타임 readback을 명시적으로 승인된 하드웨어 세션에서 수집한다. 이번에는 로봇에 접속하지 않았다.
2. 동일 지도·footprint·정지/지연 정책으로 RPP 현행 / 곡선 추종 후보 / MPPI Omni 후보를 격리 시뮬레이션에서 비교한다. wheel model을 임의로 legged dynamics라고 부르지 않는다.
3. 도착률만 아니라 full-body 최소 여유, 회전 중 swept collision, vx/vy/wz 및 변화율, 제어주기 p95/max, watchdog 여유, localization 오차와 센서 dropout 시 정지 성능을 기록한다.
4. 좁은 슬라럼의 성공과 전 코스 경사·계단·정지선·앉기 성공을 분리한다. 저속·경사·발 디딤 실패 조건을 포함한다.
5. 근거가 갖춰지면 패널 변경안만 먼저 검토하고, 사용자의 별도 승인을 받은 뒤 C1 공용 UI/API/profile 연결 작업으로 넘긴다. 현재는 제안만 작성했다.

## 소스 근거: 고정 HEAD 링크

- [패널 27개 필드·단위·범위](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/static/navigation.js#L8-L64)
- [서버 allowlist와 범위/기본값](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/navigation_jobs.py#L184-L274)
- [STOP-only 저장·revision·requires_restart](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/navigation_jobs.py#L576-L625)
- [고정 플러그인·파라미터 매핑](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/navigation_jobs.py#L1033-L1160)
- [원자적 저장과 previous YAML](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/navigation_jobs.py#L1327-L1360)
- [APPLY 동작](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/static/app.js#L4369-L4417)
- [공식 base YAML](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/config/nav2_params_go2_humble.yaml#L64-L113)
- [collision-mask 별도 프로필](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/navigation_collision_profile.py#L162-L244)
- [ROS 정책 readback 범위](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/ros/policy_readback.py#L1-L36)
- [bridge hard caps](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/go2_bridge.py#L602-L635)
- [onboard control 설정](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/config/go2-onboard.json#L70-L89)
- [control 계층의 제한/가속도](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/7ef47dc249e4dba83865e78dc283f40013ea92de/robot_dashboard/control.py#L289-L365)

## 공개 1차 자료

- [Nav2 Humble RPP](https://api.nav2.org/nav2-humble/html/md_nav2_regulated_pure_pursuit_controller_README.html): 경로 추종과 속도/충돌 규제이며, 횡방향 자유도를 충분히 활용하지 않는다고 명시. 이 특성 때문에 파라미터 튜닝만으로 holonomic 최적화를 기대할 수 없다.
- [Nav2 Humble MPPI](https://api.nav2.org/nav2-humble/html/md_nav2_mppi_controller_README.html): Omni 모델과 vx/vy/wz 한계, prediction horizon과 critics를 제공한다. 여기의 desktop 성능 수치를 Orin 실측으로 전용하지 않았다.
- [Nav2 Humble Rotation Shim](https://github.com/ros-navigation/navigation2/blob/humble/nav2_rotation_shim_controller/README.md): 새로운 경로의 방향 차이가 크면 제자리 정렬한 뒤 primary controller로 넘기는 목적. 자연스러운 연속 회전을 원한다면 Shim 동작 자체도 비교해야 한다.
- [Unitree Go2 SportClient](https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/robot/go2/sport/sport_client.hpp): Move(vx,vy,vyaw) 인터페이스 근거. 안전 최대속도·가속도의 현장 검증을 대신하지 않는다.

## 검증 범위

PASS: 독립 읽기 전용 clone, HEAD/clean status, UI↔서버 27개키 정적 대조, 저장/매핑/readback/bridge 코드 추적, 공식 Humble 자료 확인.
NOT_RUN: 온보드 readback, ROS 실행·Native Nav2 벤치마크, 실제 보행·접촉·브레이크 거리·제어주기·슬립 측정.
설정 적용·코드 수정·commit/push·PR·장비 접속: 없음. 문서와 JSON만 clone 바깥에 작성했다.

## 별도 C3 제출과의 관계 (추가 확인)

[C3 REVIEW, 고정 2495f7b](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/2495f7bdbad5ff83d1b4c8ff7171260618f4e5bd/docs/parallel-review/20261024/C3/REVIEW.md)를 직접 읽었다. 문서상 144 native 비교를 계획했으나 실제 실행은 **0회**이며, 38개 offline 하네스 검사 통과와 구분된다. 차동 평면 plant와 0.716×0.324m 기존 envelope이므로, 현재 관절 포함 holonomic VM 사례와 조건도 같지 않다. 이 결과로 RPP/MPPI의 성능 우열이나 Go2 실물 권장값을 결정할 수 없다. 해당 브랜치를 병합하거나 실행하지 않았으며, 문서의 실행 주장도 독립 재실행 결과로 표현하지 않는다.

이번 조사에서 upstream Humble 코드 기준과 로봇에 설치된 버전은 동일하다고 가정하지 않았다. 실제 package/plugin 버전을 확정하고 해당 버전이 파라미터를 소비하는지 확인하는 절차가 필요하다.
