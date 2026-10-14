# 01 — 현재 실행본 조사와 검증 공백

2026-10-14 KST. Run ID: `robot-scope-hw-validation-20261014T033609Z`.

**01단계의 접근 가능한 조사와 항목별 판정은 완료했다. 실장비 acceptance와 주행은 승인하지 않는다.** 현재 API 관측은 확보했지만 SSH 인증이 거부돼 장비 checkout, 실제 서비스 PID/cwd/release와 실행 파일·설정 hash를 확정하지 못했다. D2는 현재 소스의 `go2-onboard` 연결이 미지원이다. 과거 PASS를 이번 실행본의 PASS로 옮기지 않았다.

구조화 결과: [01_validation_matrix.json](01_validation_matrix.json). 31개 검사: PASS 14, FAIL 2, BLOCKED 10, NOT_RUN 5. FAIL은 D2 onboard 구현 연결과 시스템 Python의 의존성 부족이다. PASS는 각 행에 명시한 제한된 조건의 확인이며 전체 하드웨어 정상 판정이 아니다.

## 측정 대상과 조사 범위

| 대상 | 이번 확인 | 판정/한계 |
| --- | --- | --- |
| 개발 checkout 시작 | `main@416d25c6e1c98b0c51097c9d6576b6ae34a690e9`, clean | 로컬 미커밋·staged 변경 없음 |
| 최신 origin/main | 실제 fetch로 `15d27bd8e4ba44126b24894961a69d011e1a44b3` 확인 | fetch 시점의 최신 값; 기존 main을 ff-only 갱신 |
| 조사·회귀 소스 | `15d27bd8e4ba44126b24894961a69d011e1a44b3`, clean | 아래 보고서 추가 전의 측정 SHA. 문서 publication SHA와 분리 |
| 장비 checkout | SHA/dirty/hash 모두 `null` | BLOCKED — SSH 인증 거부 |
| 실제 서비스 실행본 | cwd/release/interpreter/executable/config hash `null` | BLOCKED — HTTP 응답과 개발 SHA의 동일성은 미확인 |
| HTTP 현재 관측 | 03:36:31–03:38:05 UTC 및 종료 03:47:47–03:47:49 UTC / KST 각각 +9시간 | 서로 다른 endpoint의 세 번의 순차 snapshot, 원자적 snapshot이나 연속 soak가 아님 |
| 플랫폼/workload | API: `ubuntu`, aarch64, Humble, domain 0, CycloneDDS; preview running, mapping/Nav2 idle, 카메라 viewer 0 | 추가 ROS 구독·카메라 소비·파이프라인 기동 없음 |
| 사전 원본 저장소 | `/private/tmp/robot-scope-hw-validation-20261014T033609Z/` | Git 밖, 새 디렉터리 0700/파일 0600, 생성 전 경로·쓰기 권한·약 15 GiB 여유 확인 |

첨부 팩의 배경·예시·과거 명령은 현재 실행 결과나 현장 승인으로 취급하지 않았다. 적용 범위는 사용자 요청의 공통 지침과 01단계다. 저장소 `AGENTS.md`에 따라 main에서 문서만 추가하며 별도 branch/worktree/PR은 만들지 않는다.

첫 GitHub fetch는 sandbox DNS 실패였고 네트워크 허용 실행으로 성공했다. SSH는 sandbox와 네트워크 허용 실행 모두 `Permission denied (publickey,password).`/exit 255였다. 로컬 관리 경로는 `en0`, 기존 SSH agent 접근은 확인했다. 키 내용·비밀번호는 읽지 않았고 동일 조건 인증을 반복하지 않았다. 관리 HTTP가 응답하므로 이를 장비 고장이나 전원 꺼짐으로 분류하지 않는다.

## 기준 SHA와 현재 소스의 차이

기준 `2c267785a85e18f4c3daacec902961c9da60b9c8`과 현재 소스의 필수 문서·D2/SE3 경로를 비교했다. 파일별 SHA-256과 기준 비교는 매트릭스의 `source_hashes`에 있다.

- D2 observer, `ros_agent.py`, manager/runtime wiring/models, SE3, onboard profile/env 예시, FAST-LIO launcher/config, 기존 세 검증 도구는 기준과 byte 동일하다.
- `app.py`와 `application/runtime.py`에는 이미 게시된 resource router/ResourceMonitor 연결이 추가됐다. 이번 채팅은 이 파일을 수정하지 않았다.
- 최신 `15d27bd`는 VSLAM 실험 도구·테스트·증거·문서를 통합한다. 운영 서비스 배포나 실행본 변경을 의미하지 않는다. 실험 도구는 기동하지 않았다.
- migration 문서에는 10월 14일 camera handback이 추가됐다. [ADR](../ADR_GO2_ONBOARD_OPERATION.md)의 마지막 “카메라 인계 중” 문구는 이 후속 증거보다 오래된 기록이다.

## 현재 플랫폼·통신·저장공간

| 항목 | 현재 API 관측 | 아직 필요한 확인 |
| --- | --- | --- |
| host/model/L4T | `ubuntu`, aarch64, Jetson Orin NX model, L4T R36 revision 5.2 | Ubuntu release, kernel, JetPack/CUDA/native ABI는 SSH BLOCKED |
| ROS | Humble / `ROS_DOMAIN_ID=0` / `rmw_cyclonedds_cpp` | 실행 PID의 safe env key·overlay·Python 확인 |
| 센서 NIC | `enP8p1s0`, up, reported 1000 Mbps | 실제 CIDR/routes/XT16 packet tuple 확인 |
| 관리망 | HTTP `.50.30:8088` 응답; host interface `wlx289401c9eb9b` up | host IP·default route는 미확인 |
| 메모리 | total 16,402,857,984 B; available 15,165,976,576 B; swap used 0 | 한 시점 값이며 부하 여유·장시간 안정성 미검증 |
| GPU/CPU/열 | sampled GPU 0%; 첫 resources sample CPU `null`; 최고 zone 56.843°C | throttling과 CPU interval 사용률 미측정; VSLAM 여유 근거가 아님 |
| Dataset 저장 | free 394,545,008,640 B; reserve 5,368,709,120 B; capture idle | 실제 mount·권한·전체 저장 경로와 기록기 소유 확인 |

과거 Ubuntu 22.04.5/kernel 5.15.199-tegra와 메모리·NIC·PID를 현재 값으로 복사하지 않았다. API에 노출된 값은 현재 API 관측이라고 명시했다.

## 프로세스·자원 소유 관계

현재 PID/세대를 확정할 수 없는 칸은 비워 두고 근거 수준을 구분한다. process API의 top 목록에서 `hesai_ros_drive` PID 2801, `dockerd` 1467, `containerd` 1037이 관측됐지만 실행 경로/세대/소유자를 확인한 PID가 아니다. 목록에 없는 프로세스의 부재도 증명하지 않는다.

| 자원 | 현재 실행/출력 관측 | PID/세대와 소유 작업 | 충돌·다음 조건 |
| --- | --- | --- | --- |
| dashboard | 상태 API HTTP 200; onboard_local; instance 관측 | MainPID/cwd/release BLOCKED; 소유 채팅 미확인 | 배포·재시작 금지, 실행 파일 식별 필요 |
| control bridge | systemd API active/running; signed ready/authenticated; own 1/foreign named 0/vendor bare 10 | invocation `f4d1f72ddd1942a1a37d67599f92a9de`; MainPID/cwd BLOCKED | 기존 제어 소유 보존; vendor bare와 own publisher 구분 |
| XT16 driver | `/lidar_points` publisher 1; raw dashboard samples 0/hz null | 위 PID 2801은 이름 기반 힌트만 | raw 정상 출력은 미검증, 새 driver 금지 |
| cloud 변환 | `/velodyne_points` publisher 1, 10.0 Hz, receipt age 42 ms | PID/세대/소유 BLOCKED | 기존 preview 관측만; source stamp/frame/QoS는 별도 |
| IMU 변환 | `/imu/body` publisher 1, 132.5 Hz, receipt age 8 ms | PID/세대/소유 BLOCKED | 과거 500 Hz를 현재 rate로 복사하지 않음 |
| FAST-LIO | mapping pipeline idle, `/Odometry` publisher 0 | OS 프로세스 부재까지는 미확인 | 새 관측 기동에는 현장 정지·창 필요 |
| localization/Nav2 | pipeline/session/goal idle, localization uninitialized | worker PID 확인 BLOCKED | initial pose·planner/goal 미실행 |
| Go2 camera | waiting/live false, viewer 0; decoder process_running false | device/process owner BLOCKED | viewer 연결은 on-demand 기동; 이번에는 연결 안 함 |
| RealSense | waiting/live false, viewer 0 | 현재 service PID/열린 device owner BLOCKED | 최신 handback 기록은 아래 역사 증거; 현재 재확인 필요 |
| VSLAM container | 현재 API로 running container 수는 미확인 | docker daemon은 container 실행 증거가 아님 | 창과 owner 확인 전 기동/성능 측정 금지 |
| 데이터 기록기 | Dataset capture idle | 별도 rosbag/외부 기록기 유무 BLOCKED | 중복 기록 방지에 전체 프로세스 조사 필요 |
| 리소스 모니터 | `/api/v1/system/resources` 현재 응답 | dashboard runtime 소유 구현 확인; 두 jtop PID도 이름만 관측 | 기존 sampler 보존, 전용 채팅·부하 창 미확인 |

## 제어·센서·카메라 판정의 한계

두 control snapshot은 lease inactive, deadman false, command x/y/yaw exact zero, action inactive, goal idle, bridge ready/authenticated였다. bridge process scope의 Move/nonzero Move/action 카운트는 모두 0이다. 기존 bridge의 STOP 카운트가 627→799로 증가했으며 이 채팅은 STOP 명령도 전송하지 않았다.

이것은 **소프트웨어 상태 관측 PASS**다. 현장 물리 정지 관찰은 `null`/BLOCKED다. Sport velocity는 zero였지만 `error_code=1001`, position motion-observation은 `INVALID`/`SportModeState position is invalid`였다. 이 값을 정답 위치나 현장 안전 확인으로 쓰지 않는다. 원인은 이번 조사에서 확정하지 않았다.

`/lowstate`는 두 번째 snapshot에서 publisher 1, 144.05 Hz, receipt age 11 ms였다. IMU/LiDAR 변환도 현재 rate·receipt age가 관측됐다. raw `/lidar_points`는 publisher 존재만 확인했으므로 정상 cloud PASS로 확대하지 않았다. `/cloud_registered`, `/tf`, `/tf_static`은 반환 catalogue에 없었으며 catalogue 부재를 전체 ROS graph의 publisher 부재로 단정하지 않는다. source timestamp/QoS/frame/TF authority/3D pose 연속성과 정확도는 미측정이다.

`/api/v1/resources` 초기 요청은 404였고 소스의 정확한 `/api/v1/system/resources`로 확인하니 200이었다. 최초 요청 오류도 원본에 보존했다. D2 status의 정확한 경로 `/api/v1/relocalization`은 503이었다. 이를 하드웨어 고장으로 해석하지 않는다.

두 카메라의 waiting/zero viewer 상태는 on-demand 설계와 양립한다. stream/FPS 검증을 위해 viewer를 새로 열면 장치 점유가 발생하므로 이번 단계에서 실행하지 않았다. 이전 상태를 임의로 복구하거나 RealSense 서비스를 재시작하지 않았다.

## 역사 증거와 이번 검증 공백

| 영역 | 보존된 과거 근거 | 이번 재확인/남은 공백 |
| --- | --- | --- |
| 내부 단독 운영 | migration `093600f`: 600.016초/58 resource 표본; `92ff609`: 별도 post-UI 30초 기능 관측 | 현 실행 byte/새 600초 부하는 미확인; 과거 PASS는 현재 acceptance가 아님 |
| D2 실센서 | 9/7 source qualification; 9/8 dense collection/지도 검증·거부·수정 기록 | onboard FEATURE_GAP; 현재 live candidate 없음 |
| D2 후속 최종 결과 | 문서 726행의 finite-JSON 실기: 25 frames/375332 raw/1340 filtered, NDT2D 유효 JSON, leading overlap 0.49254/fitness 0.18698, quality rejected | 상단 “map not eligible”나 초반 “PCL 없음”만으로 현재 상태를 단정하지 않음; 후보 acceptance 미달 |
| D2 실패 보존 | zero known-free → free-review drift → PCL qualification fail → fixed-grid corpus pass → IMU input gap/추정기 발산 → invalid JSON 수정/실기 strict parse | 각 실패·후속 수정은 별개; free-review 지도는 주행 지도 승인 근거가 아님 |
| SE3/WP03 | synthetic local 6DoF ICP; 글로벌 탐색 미구현, pose 미적용 | 독립 실query/정답/Jetson 성능은 BLOCKED; 정확도 `null` |
| WP04/WP05 | 격자 연결성은 Nav2가 아님; viewer는 synthetic-only | 실제 planner/운영 위치/TF/도달은 NOT_RUN |
| VSLAM handback | [followup-final-restoration](../experiments/isaac-vslam/evidence/followup-final-restoration.json): 10/14 02:15:35 UTC, camera active PID 34571, running Docker 0, operational domain lab nodes 0, RGB 소비 NOT_RUN | 그 시점 인계 종료 기록 확인. 현재 PID/장치 owner로 재사용하지 않음 |
| VSLAM 성능/한계 | 정지 VO 18018 outputs/600.026초, VIO zero IMU, map reuse code3 실패 | 이번 작업에서 재실행/운영 TF·Nav2 연결 없음; 현재 동시 실행 여유 미검증 |

보유 오프라인 자료도 현재 읽었다. migration archive에서 PCD 두 개의 header/bytes/SHA-256과 12개 Dataset manifest(합계 1225 samples, 모두 completed)를 확인했다. Dataset sources는 Go2/RealSense RGB camera이며 3D query bag이 아니다. PCD는 각각 1,101,439 / 1,494,830 points, binary x/y/z/intensity다. archive의 두 파일은 지도이며 독립 timestamp query가 아니다. 두 지도 간 정합·자체 변환으로 실측 정확도를 만들지 않았다. API map revision과 archive 파일 hash의 동일성/lineage도 filename으로 추정하지 않는다.

검색 범위는 해당 migration archive, 개발 저장소, 별도 VSLAM checkout이다. 그 범위에서 원본 `.db3`/`.mcap` query bag은 발견하지 못했고, Git에는 VSLAM bag inventory/분석 요약만 있다. 원격 archive의 bag 존재·내용은 SSH BLOCKED다. 독립 정답·position/rotation error는 전부 `null`이며 residual이나 FAST-LIO 일치도로 대체하지 않았다.

## D2 onboard FEATURE_GAP 추적

| 연결 | 현재 소스 조건 | onboard 영향 |
| --- | --- | --- |
| Evidence PROFILE | `ros/relocalization_evidence.py:24` = wireless competition FAST-LIO | onboard 프로필을 표시/지원하지 않음 |
| observer 활성화 | `ros_agent.py:165`: 요청 opt-in **그리고** `navigation_profile == RELOCALIZATION_PROFILE` | observer flag만 켜도 onboard에서는 disabled |
| runtime 생성 | `application/runtime.py` delegate → `relocalization/runtime_wiring.py:78` | enabled 시 profile 불일치 RuntimeError, observer enabled도 필수 |
| stationary preflight | `relocalization/manager.py`의 PROFILE/exact preflight | factory만 고쳐도 manager gate에 막힘 |
| backend | runtime: `bounded-se2-icp`, `pcl-ndt2d`; result schema: 추가 `pcl-gicp` | GICP는 schema 지원과 live 허용이 다름; SE3는 allowlist에 없음 |
| dense-query | wireless wrapper만 opt-in=1에서 `fastlio_xt16_d2_relocalization.yaml` 선택 | onboard mapping factory는 direct `start_hesai_mapping_humble.sh`→generic FAST-LIO로 실행; 자동 dense opt-in 경로 없음 |
| 기본 설정 | onboard example D2 observer=0/manager=0; 일반 FAST-LIO dense=false, D2 config dense=true | 예시는 실제 env가 아님; 실제 onboard env/hash는 BLOCKED |

최소 후속 변경 제안은 프로필 지원을 shared contract로 명시해 observer/factory/preflight를 함께 확장하고, onboard direct DDS를 보존하면서 고정된 D2 dense config 선택을 연결하는 것이다. 관련 범위는 `ros/relocalization_evidence.py`, `ros_agent.py`, `relocalization/manager.py`, `runtime_wiring.py`, direct FAST-LIO launcher 및 opt-in config 계약이다. `app.py`/resource monitor/UI 변경은 필요 범위에 넣지 않는다.

회귀는 onboard/기존 competition/disabled/unknown-profile, source freshness·future·continuity/generation/QoS/cardinality, stationary bound·exact map fence·backend allowlist, dense 선택/default 불변, zero publisher/no pose apply를 확인해야 한다. 관련 기존 테스트는 `test_stationary_relocalization.py`, `test_ros_agent_target.py`, `test_wireless_mapping_profile.py`, onboard/mapping artifact tests다. 이번 01단계에서는 설계·공백 확인까지만 수행했다. flag 우회나 wireless 프로필 위장, 장비 env 수정·배포를 하지 않았다. 향후 구현 회귀 PASS와 실장비 candidate PASS는 별개다.

## 기존 읽기 전용 도구 재사용 준비

세 도구의 소스와 현재 `.venv/bin/python ... --help`를 실제 확인했다. 장비 CLI 실행은 올바른 서비스 interpreter/config 식별이 선행돼야 하므로 BLOCKED다. Mac에서 실행한 진단을 Jetson 결과로 기록하지 않았다.

| 도구 | 확인한 계약 | SSH 확보 후 읽기 전용 사용 |
| --- | --- | --- |
| `robot_scope_doctor.py` | mode-aware 설치/ABI/설정 조사, hardware 변경 없음 | live interpreter로 `--mode go2-nav --project-dir <실제 root> --env-file <실제 private env> --json` |
| `robot_scope_onboard_diagnostics.py` | `snapshot`/`sample`, fixed systemd/process-name/sysfs, argv/env dump 없음, 새 private output만 허용 | 확인한 새 evidence root에 `snapshot --output <새 파일> --disk-path <실제 data root>` |
| `robot_scope_acceptance.py` | fixed loopback GET/systemd/doctor, private `runtime/reports`, `--onboard`, physical scenarios recorder | `--mode go2-nav --onboard --project-dir <실제 root> --env-file <실제 private env>`; 결과 행과 NOT_RUN/BLOCKED를 해석 |

위 placeholder는 실행 명령의 확정값이 아니다. 먼저 systemd의 MainPID/invocation/WorkingDirectory를 읽고 `/proc/<현재 PID>/cwd`, `/proc/<현재 PID>/exe`, PID 시작시각/boot ID로 세대를 연결한다. 전체 `Environment`/`ExecStart`/`ps args`는 공유 출력하지 않는다. safe env key는 ROS/RMW/domain/interface/profile/D2 flag/config 경로만 추출하고 실제 파일 hash를 별도로 기록한다. 그 root의 Git status/HEAD와 로딩 대상 module/config를 비교한다. 설치 interpreter와 서비스 interpreter가 다르면 둘을 분리해 기록한다.

원격 evidence root 생성 전 실제 경로·권한·여유 용량·reserve를 확인하고 Git 밖 새 0700 디렉터리를 만든다. 이 단계는 센서 데이터 기록이 아니다. 기존 도구 파일이 장비에 있는지도 hash로 확인한다. missing이면 배포 승인 없이 파일을 덮어쓰지 않는다. acceptance가 loopback 고정이라는 이유로 host 제한을 변경하지 않는다. exit 0은 NOT_RUN을 포함할 수 있으며 camera 미소비나 optional 기능을 전체 PASS로 바꾸지 않는다.

## 02단계에서 즉시 가능한 작업과 조건이 필요한 작업

| 작업 | 상태/조건 |
| --- | --- |
| 기존 API의 bounded GET, 현재 map-family/revision/annotation catalogue 조사 | 바로 가능. 인증/ROS source hash 미확인 한계 유지; lifecycle POST 없음 |
| 보유 PCD/occupancy/manifest의 hash·frame/lineage·세션·정답 출처 분석 | 바로 가능. 현재 API revision과 archive equality는 별도 검증; reference/query 독립성을 만들지 않음 |
| 기존 fixture의 timestamp/future/gap/quaternion/TF/SE3 계약 회귀 | 바로 가능, 개발 PC synthetic 증거로만 분류 |
| 실제 publisher 정체/QoS/frame/source stamp/use_sim_time/clock/TF authority 읽기 | SSH 확보 후 read-only 진행 가능; 설치 환경과 owner 식별 우선 |
| 짧은 추가 구독 부하 시험 → 180초 정지 관측/제한된 bag 기록 | 현장 실제 정지, DISARMED/no lease/no goal, 유일한 owner, 자원 창·개별 범위 필요. 현재 BLOCKED |
| 카메라 실제 영상 소비/RealSense 인수 | 현재 열린 device owner와 camera/window 계약 필요. 역사 handback만으로 재점유하지 않음 |
| 운영자가 직접 수행하는 직선·회전·복귀 기록 | 현장 운영자·물리 정지 수단·제한 구역·속도/거리/이번 기록 범위 확인 필요. 자동 이동 없음 |
| D2 candidate | onboard 지원 구현·회귀·개별 배포·fresh physical-safety·정확한 D0 lineage·source 조건 필요; 04단계 항목 |
| 운영 초기 위치/실제 Nav2 planner/goal | 실제 위치·지도 revision·단일 TF authority 및 각각의 실행 조건 필요; 04/05단계 항목 |

02단계 임계값은 현재 실행 byte와 source를 대조해야 한다. 이번에 확인한 개발 소스의 D2 age/gap 0.50 s·future 0.10 s, manual/bridge 0.20 s, Nav2 command 0.30 s는 서로 다른 지표다. **C4 gap 0.25 s 정책은 현재 코드에서 competition FAST-LIO 프로필 전용이다.** 현재 onboard API의 `rate_gate.enabled=false`, `max_gap_s=null`을 보존하며 onboard에 0.25 s가 적용됐다고 주장하지 않는다. onboard localization health에는 별도 age/rate gate가 있다. 180초는 새 측정 구간이며 timeout 변경값이 아니다.

## 검증·종료

| 개발 소프트웨어 검사 | 실제 결과 |
| --- | --- |
| 요구된 plain `python3 -m unittest discover -s tests -v` | 1625 run, errors 6, skips 2 — FastAPI/Starlette/Pydantic 누락. 실패 원본 보존 |
| 기존 `.venv/bin/python -m unittest discover -s tests -v` | 1667 run, failures/errors 0, skips 2 |
| `npm run test:unit` | 360/360 PASS |
| `node scripts/check_frontend_syntax.mjs` | 79 modules PASS |

이 회귀는 소프트웨어 증거이며 live DDS·Jetson native imports·정확도·주행을 검증하지 않는다. 새 기능 코드를 추가하지 않았으므로 새 implementation-mirror 테스트는 만들지 않았다. 보고서/JSON 구조·증거 hash·상태/필수 필드·Markdown 링크·diff를 확인했다. 매트릭스 행의 시각은 판정을 기록한 시각이며 실제 API 관측 시각은 `api_observed_utc`와 원본에 별도로 있다. 원본 참조는 파일명은 private root, 저장소 상대 경로는 repo root에서 해석한다.

생성한 공유 파일은 이 보고서와 `01_validation_matrix.json` 두 개다. 원본 HTTP JSON, source/baseline hash inventory, local data metadata, connection 결과, 최초 실패/완료 테스트 로그는 위 private root에 남긴다. shared matrix는 명시적 필드만 포함하고 token/전체 env/argv/센서 payload는 포함하지 않는다. private root는 임시 디렉터리여서 장기 보관 시 별도 private archive로 복사해야 한다.

이 채팅이 만든 장비 process/ROS subscriber/camera viewer/remote temporary file은 0개다. 서비스 재시작·배포·카메라 인수·초기 위치·ARM·lease·goal·실이동·장애 주입을 하지 않았다. 기존 지도·bag·설정과 별도 채팅의 자원을 보존했다. 03:47:47 UTC 종료 snapshot에서도 control zero/no lease/deadman false/action 없음/goal idle, mapping/Nav2 idle, preview running, 두 카메라 viewer 0이 유지됐다. dashboard instance ID와 bridge invocation도 시작과 동일했다. 이는 API 범위의 관측이며 물리 정지·장치 owner·전체 서비스 PID 상태의 동일성은 확인 불가다. 정상 물리 종료를 추정하지 않는다.

Git 게시는 별도 **BLOCKED**다. 보고서 두 파일은 로컬 main에 커밋했지만 자동 승인 검토가 `git push origin main`을 거부했다. 이유는 장비 운영 정보가 들어 있는 문서를 공개 범위가 확인되지 않은 GitHub 대상으로 게시할 위험이다. 이 거부를 우회하지 않았고 원격 push/장비 배포는 수행하지 않았다. 대상 `Phjrab/robot-scope-ros2-dashboard`의 `origin/main`에 이 두 문서를 게시할 명시적 사용자 승인이 다음 조건이다. 이 게시 상태는 31개 조사 검사의 판정과 별도로 JSON의 `publication`에 기록한다.
