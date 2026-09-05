# Robot Scope 진행 현황과 향후 작업 계획 — 2026-09-01

## 문서 목적과 판정 기준

이 문서는 repository `main`의 `065161c`까지 반영된 코드, 테스트와 장비 검증 기록을
한곳에 요약한 시점별 진행 보고서다. 대화에서 예상한 상태가 아니라 현재 repository의
문서와 테스트를 근거로 작성했다. 이후 변경으로 수치가 달라질 수 있으므로 세부 증거는
각 링크 문서를 기준으로 하고, 이 문서는 우선순위와 의사결정용 요약으로 사용한다.

상태는 다음 네 값으로 구분한다.

- `PASS`: 같은 범위의 코드 또는 실제 장비에서 기대 조건을 확인했다.
- `BLOCKED`: 필수 입력·공식 절차·장비 증거가 없어 진행하면 안 된다.
- `NOT_RUN`: 의도적으로 뒤로 미뤘거나 아직 실행하지 않았다.
- `PROPOSED`: 아래의 향후 계획이며 아직 승인이나 완료를 뜻하지 않는다.

소프트웨어 테스트 통과를 실제 로봇·센서·네트워크 검증으로 승격하지 않는다. 과거
장비 검증 결과는 그때의 commit과 환경에 대한 기록이며 현재 프로세스가 실행 중이라는
뜻도 아니다.

## 한눈에 보는 현재 상태

| 영역 | 현재 판정 | 핵심 상태 |
|---|---|---|
| 리팩터링과 제품 경계 | `PASS` | Phase 0 이후 구조 분리, SO-101 제거, API/ROS/UI/lifecycle 소유권 정리 완료 |
| Control 안전 경계 | `PASS` | signed Bridge, lease/deadman/watchdog, server clamp, zero/release와 주요 감독 fault 검증 완료 |
| Cockpit와 대시보드 UI | `PASS` 중심 | 전용 전체 작업창, 접이식 HUD, 레이아웃/카메라/점군/STOP 동작 검증; 일부 현장 브라우저 항목 보류 |
| 카메라와 Dataset | `PASS` 중심 | Go2+RealSense 동시 LIVE, demand 정리, relay 복구, 실제 Dataset 저장·finalize·reserve/recovery 검증 |
| 무선 XT16·FAST-LIO Mapping | `MAPPING_STATIONARY_PASS` | HW-1~HW-5와 60초/10분 복합 부하 통과; 60분 soak 미실행 |
| Controller odometry | `BLOCKED` | 전송은 설치됐지만 원본 `/utlidar/robot_odom`이 약 681 ms 미래여서 WNO-2 fail-closed |
| Localization·Nav2·Mission 실장비 | `BLOCKED` | controller odometry source-clock 해결 전에는 시작, initial pose, goal 검증 금지 |
| Shadow perception | `BLOCKED` | 계약과 UI는 준비됐지만 승인된 Lane/YOLO 모델·target TensorRT engine·실장비 soak가 없음 |
| Competition release | `BLOCKED` | WP08 도구/runbook은 준비됐지만 동일 release commit의 완전한 장비 acceptance가 없음 |

## 완료한 핵심 작업

### 1. Architecture와 리팩터링

- `RosAgent`, application/API, mapping, navigation, control transport와 frontend 기능의
  소유권을 단계적으로 분리했다.
- SO-101 전용 integration을 제품 경계에서 제거하면서 Go2, TurtleBot과 Generic mobile
  robot의 공용 기능을 보존했다.
- control, mapping, navigation, map/Dataset filesystem의 fail-closed 경계를 유지했다.
- shell-free 고정 명령, same-origin mutation, private runtime root, symlink/traversal 방어,
  bounded log/export 계약을 유지했다.
- 현재 구조와 남은 기술 부채는 [현재 Architecture](ARCHITECTURE.md)에 기록돼 있다.

### 2. Control과 감독 검증

- 브라우저 속도 이중 적용을 제거하고 normalized axis와 한 번의 `speed_scale`만
  전송하도록 수정했다. 서버 clamp와 watchdog은 유지했다.
- 명시적 zero/release acknowledgement 경합을 bounded wait와 HTTP disarm fallback으로
  정리했다.
- `직접 ROS`와 `원격 Control Bridge` 상태를 분리해 무선 split topology를 정확히
  표시한다.
- 저속 전진·정지, browser disconnect watchdog, Dashboard Software STOP, stale LowState,
  foreign Sport publisher, Bridge process loss의 정지 또는 fail-closed 동작을 감독하에
  확인했다.
- 마지막 기록은 DISARMED, lease 없음, deadman false, exact zero이며, Bridge unit의
  자동 시작 정책을 임의로 변경하지 않았다.

세부 증거는 [2026-08-30 장비 검증](HARDWARE_VALIDATION_2026-08-30.md)의 P0 control
후속 기록을 따른다.

### 3. Cockpit와 운영 UI

- CWP를 기존 작은 패널이 아닌 별도의 전체 작업창으로 열고, popup 차단 시 embedded
  workspace를 유지하도록 구현했다.
- Competition Status와 Control Authority를 기본 접힘 상태로 제공하면서 SOFTWARE STOP은
  항상 접근 가능하게 유지했다.
- status rail과 3D toolbar의 겹침, 좁은 viewport, launcher/panel stacking을 수정하고
  대표 해상도에서 자동화 검증했다.
- 카메라 1/2화면 전환, source별 single demand owner, PointCloud adaptive LOD, XYZ 축
  표시, map/navigation/mission panel lifecycle을 검증했다.
- 전체 UI 결과와 미측정 항목은 [Cockpit Acceptance](COCKPIT_ACCEPTANCE.md)에 분리돼 있다.

### 4. 카메라, Dataset과 장애 복구

- Go2 Front와 RealSense가 동시에 LIVE이며 source별 viewer 한 개만 유지되는 것을
  실제 장비에서 확인했다.
- RealSense/Go2 relay restart 후 STALE에서 LIVE로 자동 복귀하고 중복 producer가
  생기지 않는 것을 확인했다.
- RealSense JPEG 해상도 metadata가 `640×480`으로 표시되도록 보완했다.
- Go2/RealSense 단독·동시 Dataset 저장, atomic sample, finalize, quota, reserve space,
  abrupt interruption recovery와 dashboard stop blocker를 검증했다.
- 실제 카메라 케이블 분리는 별도 감독 fault로 `NOT_RUN` 상태를 유지한다.

### 5. 무선 topology와 XT16·FAST-LIO

- robot-side Jetson은 Go2/XT16 sensor LAN과 Wi-Fi 관리망을 동시에 소유하고, external
  Orin은 유선 관리망에서 dashboard, validation, storage와 navigation authority를
  소유하도록 역할을 확정했다.
- 임의 route/NAT/bridge/DDS Router 대신 fixed peer/port, 최소 권한 firewall, restricted
  lifecycle과 authenticated small transport를 사용한다.
- XT16 relay, Hesai driver, authenticated IMU, cloud-only C++ bridge, stationary FAST-LIO가
  단계별 실제 검증을 통과했다.
- 두 카메라, FAST-LIO, signed Bridge status와 LOW PointCloud를 합친 60초/10분 부하를
  통과했다. 60분 soak는 사용자 요청에 따라 `NOT_RUN`이다.

현재 gate별 수치와 cleanup 증거는 [Wireless Mapping Acceptance](WIRELESS_MAPPING_ACCEPTANCE.md)에
있다.

### 6. Controller odometry와 Nav2 조사

- `/utlidar/robot_odom`만 전달하는 784-byte HMAC 고정 UDP transport를 추가했다. 원본
  stamp, `odom -> base_link`, QoS, publisher cardinality, replay와 freshness를 보존한다.
- WNO-1은 통과했지만 WNO-2는 원본 source stamp가 host realtime보다 220초 이상 오래돼
  zero publish 상태로 fail-closed 됐다.
- sender에도 동일 source-clock guard를 추가해 stale/future sample이 네트워크로 나가지
  않도록 했다. WOC-1은 `sent=0`으로 통과했다.
- Go2 body `v1.1.15` 업데이트 뒤 세 번의 read-only 재측정에서 90개 stamp가 약 150 Hz로
  증가했지만 median이 host NTP보다 약 `681 ms` 미래였다. 고정 허용치는 stale 500 ms,
  future 100 ms이므로 여전히 차단된다.
- 현재 물리 topology에서는 external Orin이 Go2 sensor LAN에 직접 연결될 수 없으므로
  direct wired candidate를 선택하지 않는다. 기존 strict wireless path가 유일한 선택이며
  producer clock이 정상 범위에 들어올 때까지 `BLOCKED`다.

관련 문서는 [Controller clock 복구 계획](CONTROLLER_ODOMETRY_CLOCK_RECOVERY_PLAN.md),
[Unitree 지원 요청서](UNITREE_CONTROLLER_ODOMETRY_CLOCK_SUPPORT_REQUEST.md),
[Nav2 Track B 결정](NAV2_TRACK_B_PARALLEL_PATH_PLAN.md)이다.

### 7. Perception과 Competition 준비

- dual-Jetson workload split, fixed HTTP pull result contract, source epoch/sequence와
  cross-host clock-domain 처리, stale result UI와 Dataset reference를 구현했다.
- model registry의 atomic active/previous rollback, target engine hash 재검증, Dataset/model
  lifecycle 계약을 보강했다.
- WP07 read-only recorder와 fixed supervised scenario catalog, WP08 offline release/lock/
  rollback 도구와 runbook을 준비했다.
- 승인된 ONNX/model package와 target-built TensorRT engine이 없어 shadow service의 실제
  설치, Lane/YOLO inference, 자원/온도 soak, activation/rollback은 아직 `BLOCKED`다.

## 현재 보류 또는 차단된 작업

### P0 — Nav2를 여는 필수 전제

1. Unitree에서 공식 producer-clock 절차, 적용 body/L1/app 버전, timestamp domain,
   persistence와 rollback 답신을 받는다.
2. 답신을 repository safety invariant와 대조한다. undocumented endpoint, guessed
   `ConfigClient`, host `date -s`, legacy `lidar-timesync.service` 재실행 또는 transport
   timestamp rebasing이면 거부한다.
3. 지원되는 절차가 확인된 경우에만 별도 실행 계획과 rollback을 작성하고 새로운 명시적
   승인을 받는다.
4. 변경 후 read-only source stamp를 먼저 재측정한다. 500 ms stale/100 ms future 범위와
   strict advancement를 통과하기 전에는 sender/receiver를 시작하지 않는다.
5. WNO-2를 stationary/no-goal 상태로 재실행하고 cleanup을 확인한다.

현재 이 항목은 `BLOCKED PENDING UNITREE SUPPORT`이며, 다른 작업으로 우회해 green으로
만들지 않는다.

### P1 — WNO-2 통과 후 Navigation 검증

아래 순서는 모두 `PROPOSED`이며 WNO-2 통과와 각 감독 승인이 선행돼야 한다.

1. WNO-3: Wi-Fi loss, wrong/replayed packet, sender/receiver loss와 재연결 시 no-auto-resume.
2. WNO-4: 저장 지도 revision을 고정한 stationary Nav2 no-goal 시작·정리.
3. TF, `/scan`, FAST-LIO `/Odometry`, controller odometry와 localization readiness 확인.
4. known-free 셀의 initial pose 설정과 costmap 안정화.
5. 물리 E-stop/리모컨, 저속 제한과 안전 담당자가 있는 짧은 goal.
6. Nav2 child crash, XT16/IMU interruption, Manual Takeover와 Mission
   pause/skip/retry/abort를 한 시나리오씩 검증.

실패 시 freshness나 timeout을 늘리지 않고 전체 navigation process group을 정리한다.

### P2 — 미완료 hardware acceptance

- 60분 Wi-Fi/XT16/FAST-LIO/Cockpit compound soak와 interference 관찰.
- 실제 Xbox Controller 연결/분리와 held-button replay 차단.
- reference PC에서 native fullscreen, background-tab 정책, 해상도별 FPS/heap/RSS.
- 감독된 RealSense cable/source stall fault.
- full RTT p50/p95/p99, loss와 minimum throughput interval.
- WP07에 남은 formal supervised scenario를 현재 release commit에서 다시 기록.

이 작업들은 서로 묶어 한 번에 승인하지 않고, 로봇 동작·네트워크 장애·케이블 fault를
각각 독립 시나리오로 수행한다.

### P3 — Shadow perception 실장비 경로

1. 공개 benchmark가 아닌 승인된 Lane/YOLO ONNX package와 immutable manifest 준비.
2. robot-side target에서 TensorRT engine을 빌드하고 JetPack/TensorRT/hash를 기록.
3. `SHADOW` only로 relay+Lane+YOLO 단독/동시 FPS, p50/p95 latency, input age를 측정.
4. CPU/GPU/RAM/swap, thermal/throttling과 camera/LowState/Bridge coexistence를 측정.
5. process stop/result freeze/model mismatch/rollback 및 최소 30분 soak를 검증.
6. external validator, overlay와 Dataset reference를 실제 result로 확인.

Perception은 관측만 제공하며 control, navigation 또는 Mission authority를 얻지 않는다.

### P4 — Competition release

- 두 Jetson을 동일한 검증 commit과 redacted configuration fingerprint로 고정한다.
- 같은 commit에서 WP07 read-only와 필수 supervised rows를 PASS로 수집한다.
- Competition Lock 상태에서 offline bundle을 만들고 checksum과 target engine을 검증한다.
- Internet 제거 boot, cold boot, laptop/browser disconnect, storage reserve, model rollback,
  soak와 field checklist dry run을 완료한다.
- FAIL/BLOCKED/NOT_RUN을 삭제하거나 assertion을 약화해 release하지 않는다.

### P5 — 기능 완료 뒤 기술 부채

- `app.js`의 camera, mapping/maps, overview, control/navigation UI 소유권을 vertical feature
  단위로 계속 추출한다.
- external caller deprecation 뒤 `RosAgent` forwarding property를 제거한다.
- ROS-stubbed 경계부터 strict typing과 hardware-aware coverage baseline을 확대한다.
- trusted private LAN을 넘어서는 배포가 필요할 때만 별도 threat model로 authentication/TLS를
  설계한다.

## 내가 앞으로 진행할 방식

1. 매 작업 시작 시 `AGENTS.md`, `git status --short --branch`, 현재 HEAD와 관련 acceptance를
   다시 확인한다.
2. 승인 범위를 software-only, read-only hardware, deployment, supervised fault, motion으로
   구분하고 이전 승인을 다음 단계에 재사용하지 않는다.
3. 구현 전 source of truth와 실제 owner를 조사하고, shared code나 기존 기능을 사용 관계
   없이 제거하지 않는다.
4. robot motion, service restart, network fault, firmware/clock, map 삭제는 정확한 계획과
   승인 없이는 실행하지 않는다.
5. 실패를 baseline, 환경 의존성, 이번 변경 regression으로 분리하며 테스트 삭제나 assertion
   약화로 통과시키지 않는다.
6. 변경 후 targeted test, 전체 repository test, relevant JavaScript/browser/static check와
   `git diff`를 검토한다.
7. 진도 보고서에 활용할 수 있도록 책임·동작·안전 경계·검증 결과를 상세 커밋 메시지로
   남기고 `origin/main`에 push한다.
8. 장비 작업 종료 시 DISARMED, no lease, deadman false, zero command, owned child/process/socket
   cleanup과 boot enable 정책을 확인해 보고한다.

## 이번 보고서 작성 시점의 검증 기준선

- repository branch: `main`
- report input HEAD: `065161c`
- project virtualenv Python: `925/925 PASS`
- JavaScript unit: `267/267 PASS`
- frontend syntax: `53/53 PASS`
- system Python: `921`개 중 `920 PASS`, `fastapi`가 없는 macOS 시스템 Python의 기존
  import error `1`; repository virtualenv에서는 동일 영역 포함 전체 PASS
- targeted wireless odometry/document contract: `16/16 PASS`
- `git diff --check`: `PASS`

이 기준선은 새 기능의 hardware readiness를 뜻하지 않는다. 다음 실제 기능 게이트는
Unitree 답신 검토와 controller odometry source-clock 정상화다.

## 2026-09-02 Track C2 우선순위 전환

위의 source-clock 지원 요청과 Track A/B 작업은 삭제하지 않고 `DEFERRED`로 보존한다.
Track C direct-Humble 조사에서 확인한 물리/배포 제약을 바탕으로, 현재 external Humble
Orin에서 이미 검증된 wireless XT16·인증 IMU·FAST-LIO 경로를 재사용하는 별도 opt-in
profile을 구현했다.

- profile: `go2-xt16-wireless-competition-fastlio`
- localization odometry: `/Odometry` (`camera_init -> body`)
- controller odometry: `/robot_scope/nav/controller_odom_fastlio`
  (`odom -> base_link`)
- strict `/utlidar/robot_odom` profile, 500 ms/100 ms guard와
  `competition-pdf-direct` profile은 변경하지 않았다.
- NG0는 initial pose 이전 단계로 분리해 `map -> base_link` 없이도 명시적으로
  `WAITING_FOR_INITIAL_POSE`를 판정한다. NG1만 해당 TF와 costmap을 요구한다.
- C2에서는 initial pose, goal, lease, ARM, deadman과 robot motion을 실행하지 않는다.

원본 교육 PDF 01–12를 새로 확인했고, 특히 09 p4/p10–18, 10 p4–6/p9,
11 p4–7을 repository ownership과 page 단위로 대조했다. 결과는
`TRACK_C_COMPETITION_DIRECT_NAV2_PLAN.md` 후속 section에 기록했다. 설계 결정은
`ADR_COMPETITION_FASTLIO_CONTROLLER_ODOM.md`, 실행 결과는
`TRACK_C2_COMPETITION_FASTLIO_NO_GOAL_ACCEPTANCE.md`가 기준이다.

같은 배포 코드에서 stationary sensor/controller-odometry를 30초 이상 확인했고,
command-isolated NG0 60초를 12/12 반복 PASS한 뒤 reverse cleanup을 증명했다.
canonical odometry는 약 10 Hz, `odom -> base_link`, source/output stamp 동일,
final host offset 약 36 ms였으며 jump/error는 없었다. raw command는 60초간 0 byte,
Sport topic은 없었고 lease/deadman/속도는 계속 false/false/zero였다.

다음 단계는 `TRACK_C3_STATIONARY_INITIAL_POSE_NO_GOAL_PROMPT.md`에 따라 exact map
revision을 다시 고정하고, known-free initial pose 한 번과 localized no-goal을 별도 감독
승인으로 수행하는 것이다. C3에서도 goal과 motion은 금지된다.

## 2026-09-04 Track G Competition Route Planner

`feature/competition-route-planner`에서 software-only Route Planner를 구현했다. 주문서
규칙과 20초 순차 준비 시간, exact map/annotation revision에 고정된 그래프,
BALANCED/FASTEST/SAFEST 최적화, 단일 Cockpit 3D renderer의 경로 overlay, 수동
guidance, 픽업·배송 운영자 확인, Mission `ready` draft export를 추가했다.

Route Planner는 control/lease/ARM/deadman/이동 명령을 소유하지 않는다. 기존 gateway에
goal 전송과 분리된 안전한 plan-only Nav2 계약이 없으므로 live Nav2 path preview는
`SAFE_PLAN_ONLY_NAV2_INTERFACE_NOT_AVAILABLE`로 명시적으로 차단했다. 로봇,
Jetson, ROS, 서비스, initial pose, Navigation goal, Mission start와 물리 움직임은
실행하지 않았다. 실장비/Nav2 통합은 승인된 별도 후속 트랙으로 남긴다.
