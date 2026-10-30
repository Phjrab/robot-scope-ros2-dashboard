# C0 연결 복구·최소 정지 보완·비이동 인계

현재 실제 배포는 **15706c48c5e6df28be105b6f5bde825dce7c4b1f**, dashboard PID43956 / release robot-scope-15706c48c5e6다. 기존 main846121b와 최초 실행5154761을 구분한다. 다음 내용은 저장 지도에서 현재 위치·방향을 확인하기 전까지의 결과다. 실제 이동은0건이다.

## 1차 결과와 별도 비교

[실장비 1차 표](LIVE_ROUND1_RESULTS.md)의 bridge stop FAIL과 의존 BLOCKED를 보존했다. 그 뒤 [별도 진단](POST_LIVE_STOP_DIAGNOSIS.md)과 최소 두 Python 파일 보완을 거쳐 **이동 없는 정지 비교1회**를 수행했다. yaw/속도/progress/후방 가중치를 탐색하지 않았다.

| 항목 | 실장비 1차 | 보완 뒤/현재 |
|---|---|---|
| 실행 source/배포 | 5154761 source2200/2200 일치 | C0 15706c4 source2216/2216 일치, actual PID/cwd 확인 |
| 영역/Z·undo/redo·전체 PCD 저장 | PASS | 13,546→12,619점 사본1개, 927제외. intensity 포함 전체 record bytes/order·부모 hash 보존 |
| bridge stop | API succeeded / systemd failed(timeout/SIGKILL), FAIL | inactive / Result success / ExecMainStatus0, PASS. HTTP 확인1.836초, 기존 TimeoutStopSec2s 유지 |
| 물리 이동 중 정지/robot ACK | NOT_RUN | NOT_RUN. 위 PASS는 idle 프로세스 안전 종료 비교 범위 |
| 독립 FAST-LIO 관측 경로 | bridge inactive gate 미충족 | 기존 gate 그대로 start1회, READY. 제어 브리지는 inactive 유지 |
| 저장 지도 correction→TF→Nav2 | BLOCKED | 현재 실제 map 위치·방향 seed 확인 필요; 아직 source 선택/초기 정합/소비 미실행 |
| 실제 stop→버튼→next goal | BLOCKED | 실제 success/정지/dwell/source와 새 시험창 부재. 강제 통과 안 함 |
| 수동 경사로 | BLOCKED | 관측 경로 READY. 정밀 도착 성공과 독립; 현장·새 시험창 확인 전 NOT_RUN |
| rear/side 동일 입력 A/B | INPUT_REQUIRED | 실제 ramp 기록 없음. 미구현/미채택, ALL_DIRECTION baseline 보존 |

## 최소 보완·검사·배포

신호 handler의 예외가 Python finalizer에서 무시되지 않도록 플래그와 0.1초 bounded spin_once를 사용했다. 기존 최종 StopMove→executor/node→ROS 종료 순서, watchdog과 2초 systemd 제한을 보존했다. lifecycle은 failed를 stop 성공으로 보고하지 않는다. 실패 상태를 inactive로 바꾸거나 source/dwell gate를 우회하지 않았다.

관련62개, 전체 Python3137개 실행·실패0·선택 의존성 skip2, JS700, Ruff/mypy/secret scan을 통과했다. Jetson Python3.10에서도 실제 main을 실행하는 ROS 없는 종료 회귀3개가 통과했다. C4 b7242fc의 해당 core 경로 변경이 없음을 읽기 비교했고 확장 브랜치를 merge하지 않았다.

기존 selector·control.env·프로필·source-selection·calibration·프리셋 등6개 파일과 사용자 dirty 목록을 장비의 private 증분 백업에 보존했다. 검증된 기존 immutable 파일2196개를 재사용하고 차이20파일/54,507bytes만 별도 release에 적용했다. selector의 ROBOT_SCOPE_DIR 한 행만 바꾸고 기존 restart API를1회 사용했다. 첫 준비 wrapper는 구문 오류로 변경 전에 종료됐고, 구문 검사 후1회 실제 전환했다. 이 인프라 사건을 실기 stop 결과와 섞지 않는다.

사용자 checkout dirty 상태, control.env, operational profile, source-selection 파일, calibration, presets는 byte hash가 보존됐다. 원본 /opt/ros 및 기존 Shim overlay hash도 유지했다. map/PCD/DB를 덮어쓰거나 새 사본을 운영에 선택하지 않았다. 기존5154761/5c1ffe3 release와 백업 selector가 복구 지점이다. 이번 정상 비교 뒤 rollback하지 않았으며, 구버전으로 복귀하면 관측한 stop 결함도 돌아갈 수 있다.

## 실제 입력과 남겨진 상태

관측 전용 session176c1f39da8e445aae4a29d1cefe3faf가 READY다. 12개 정지 입력 표본에서 pose/cloud의 원래 source stamp가 각각 증가했고, 같은 stamp snapshot6개를 확인했다. 최대 pose age .124초, 마지막 cloud10Hz / odom19.93Hz다. 이는 FAST-LIO 입력 증거이며 stored-map correction·운영 TF·Nav2 소비의 PASS가 아니다. 센서 좌표나 odometry를 독립 ground truth로 취급하지 않는다.

Nav2/goal/mission idle, lease inactive, 명령0, SOFTWARE STOP latch=false다. bridge는 정상 inactive/PID0이며 관측 서비스만 active다. 관측은 기존 프로그램의 최대30분 제한을 따른다. generated job/실제 controller .so 로드는 현재 Nav2 idle이므로 없다. 현재 source selector는 LEGACY_2D/selected=null이다.

실제 saved revision71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387, .10m/.10rad, .25m/s, 10Hz를 새 실행본에서 재조회했다. 현재 generated/live 값으로 승격하지 않는다.

다음 필요한 입력은 **로봇이 마지막 시험 종료 위치에 그대로 있는지, 옮겼다면 현재 지도상 위치·방향**이다. 새 seed로 정지 정합·reference pin·actual consumer를 확인한 다음, 실제 움직임 직전에 현재 운영자·케이블·공간·정지/수동 회수·소유권과 새 시험창을 한 번 확인한다. 이전 두 목표 승인은 재사용하지 않는다.

실행 source15706c4의 CI는 [run41042751838](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41042751838)에서 조회 시 진행 중이다. 옛 source 또는 로컬 통과를 exact-SHA CI 성공으로 표시하지 않는다. 최종 문서 commit과 실제 배포 SHA도 구분한다.

[전체 JSON/증거 hash](LIVE_FOLLOWUP_AND_HANDOFF.json), [후보 software 검사](STOP_CANDIDATE_VALIDATION.json). 인증 정보·환경 원문·endpoint·raw PCD/센서·사용자 dirty 원문·진단 ZIP은 private에만 보존한다.
