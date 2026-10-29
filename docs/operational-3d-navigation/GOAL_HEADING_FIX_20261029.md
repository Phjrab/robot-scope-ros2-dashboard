# 최종 방향 정렬: 재현·수정 후보와 배포 상태

2026-10-29 KST. 기존 두 시험의 결과는
[원본 보고서](GOAL_PRECISION_TWO_TRIALS_20261029.md)를 보존한다.
이번에는 설치된 Nav2 1.1.20의 TF 시각 결함을 실제 C++ 라이브러리로 재현하고
수정 후보를 빌드했다. **후보의 실제 정밀 도착은 아직 미검증**이다.
새 현장 시험·Nav2 시작·goal 전송은 하지 않았다.

## 현재 배포와 설정

| 구분 | 확인 결과 |
| --- | --- |
| 이전 Goal URDF UI | `f469155c2b0c505f3e472e878f75029d7b8d39df`, 장비 배포 확인 |
| 현재 실제 대시보드 배포 | `47ae383fff5bfa12c20d523d2851a952dbb60f4b` |
| 현재 PID / 실행 폴더 | 확인 당시 65464 / `robot-scope-47ae383fff5b` |
| 방향 수정 소스 | 이 보고서와 함께 게시한 main commit; 최종 응답에 전체 SHA 기록 |
| 방향 수정 바이너리 | private 디렉터리에 빌드·검사 완료, 운영 선택 **안 됨** |
| 현재 주행 | idle, active lease=false, command ZERO |
| 제어 브리지 | 사용자 요청으로 기본 자동 시작 활성화, 연결·인증·ready 확인 |
| 지도·파라미터 | 배포 전후 동일; 사용자 checkout/CSS/프리셋 보존 |

제어 브리지는 부팅 시 시작되는 대시보드가 준비 조건을 최대 30초 기다린 후 기존
preflight/start 경로로 한 번 시작한다. 수동 start/stop이 있으면 대기 중인 자동 시작은
취소한다. STOP·리모컨 양도 뒤 무조건 재기동하는 루프가 아니다. 기존 서비스의
실패 재시작 정책은 그대로다. 브리지 전용 unit의 직접 boot enable은 사용하지 않으며,
대시보드 boot enable + `ROBOT_SCOPE_CONTROL_BRIDGE_AUTOSTART=1` 경로를 사용한다.
배포 뒤 브리지 프로세스 관측에서 nonzero move 0회였다. 로봇 재부팅 시험은 하지 않았다.

| 설정 | 과거 두 시험 saved/generated/live | 현재 saved / 이번 후보 |
| --- | --- | --- |
| XY / yaw | .10m / .10rad | 동일, 변경 안 함 |
| controller | RotationShim + RPP | 동일 plugin, 별도 Shim 소스 패치 후보 |
| 선속도 / 주기 | .25m/s / 10Hz | 동일 |
| stateful goal checker | true | 동일 |
| rotate_to_goal_heading / RPP use_rotate_to_heading | true / false | 동일 |
| 회전속도 / 각가속도 / closed_loop | .50rad/s / 1.20rad/s² / false | 동일 |
| 진행 검사 | SimpleProgressChecker, .20m / 10s | 동일; Pose 후보는 격리 비교만 함 |
| NavFn tolerance / 반경 / inflation | .50m / .22m / .25m | 동일 |

현재 저장 revision은
`71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387`이다.
장비가 종료됐던 과거 시점의 baseline 복원은 여전히 수행하지 않았다.
사용자 `홍재`, `정밀시험 전 복구 20261029`, 정밀 후보 프리셋을 보존했다.
이번에는 Nav2 세션을 시작하지 않았으므로 **새 generated YAML/live ROS 값은 없다**.
과거 readback을 현재 실행 중 readback으로 표현하지 않는다.

지도 묶음도 그대로다. 3D `map_20261027_125427_course_localization_20261028`
(ID `e1dd40cc6911404dbdfc073b`, revision
`c7d7ce7e04b2fb80519854cc71465f61af9fff210ac72e299105502497401ad5`)와
2D `map_20261027_125427_operator_free_20261028`
(ID `9a382e3eb990fb02fe1a3569`, revision
`d5733a293effbd9567cdb9165472e15c2be8ab0adef7cf05f99ec39f19578552`)의
identity 관계를 유지한다. 과거 위치 source는 STORED_PCD_FASTLIO,
정합 정책은 ALL_DIRECTION_BASELINE이다. 현재 idle을 활성 위치추정으로 표시하지 않는다.

## 원인과 단계 구분

1. 원본 Shim은 고정 goal의 조회 시각을 `now()`로 만들고 controller pose frame으로
   변환한다. source stamp를 보존하는 map/odom TF가 10~60ms 늦으면 0.1초 대기 뒤
   실패하며 primary로 넘어갈 수 있다. 같은 설치 라이브러리에서 이 경로를 재현했다.
2. SimpleProgressChecker는 정상 yaw 변화만으로 .20m/10초 병진 기준을 갱신하지
   않는다. 과거 시험 2에서는 XY .071m/.045m 부근에도 progress abort가 있었다.
   이 문제는 TF 수정 이후에도 남을 수 있으며 이번 설정에서 숨기지 않았다.
3. 추가로 원본의 초기 회전 handoff threshold가 작은 최종 회전의 footprint 검사를
   건너뛰는 결함을 격리 검사에서 발견했다. 별도 패치로 수정했다. 충돌 오류가 없었던
   시험 2의 과거 원인이라고 소급 판단하지 않는다.

기존 private 증거를 다시 사용했다. 시험 2의 TF 오류 68개를 가장 가까운 pose source
시각과 ±300ms 범위에서 연결하면 XY 10cm 밖 15개, 안 25개, 연결 불가 28개다.
Shim의 TF 조회는 XY 검사 **이전**이므로 68개를 전부 최종 회전 실패로 세지 않는다.
각 오류 뒤 150ms 이내에 병진 raw command가 관측됐지만 이는 시간상 연관이다.
원본에 branch 로그/action UUID가 없어 fallback·recovery를 확정적으로 재구성할 수 없다.
접근/최종 회전은 격리 검사에서 입력으로 분리했고, 실제 recovery 결과는 기존 보고서의
action/FollowPath 결과로만 인용한다.

센서 처리·TF 발행·callback 대기별 지연 기여율, 실제 제어주기 p50/p95/max,
첫 시험 costmap의 원인 셀, raw 회전 명령 대비 bridge/몸체 반응은 아직 미확정이다.
요청과 endpoint가 일치한 시험 2를 goal 전달 오류로 설명하지 않는다.

## 수정과 재현 결과

[버전 고정 패치](../../ros2/nav2_goal_heading_fix/README.md)는 controller pose 시각에
두 TF chain이 모두 유효한지 확인한다. 그렇지 않으면 최신 공통 시각을 구하고 동일
시각의 robot/goal을 함께 복원한다. input 시각과 기존 transform freshness 경계를
넘지 않는다. sensor stamp 변경, future-date, stale 허용 증가, 전역 timeout 증가는 없다.
유효 시각을 얻지 못하면 기존 ControllerServer의 예외/정지 경로로 전달한다.
정상 접근과 초기 회전은 기존 primary/알고리즘을 유지한다.

실제 Humble C++ Shim, TF buffer, goal/progress checker를 사용한 5개 suite,
**44개 검사 통과**. official 원본 7, 설치 원본 7, TF 단독 10,
TF+충돌 수정 10, 실제 production 후보 라이브러리 10이다.
정상/10·40·60ms 지연, 서로 다른 두 edge 시각, 누락/stale/future, 시계 역행,
새 path/goal, 기존 접근, 양방향 최종 회전 충돌을 검사했다.

| 지연 입력 | 설치 원본 | TF 수정 단독 | 실제 후보 라이브러리 |
| --- | --- | --- | --- |
| 10ms | primary fallback, 101.799ms | 회전 명령, .096ms | 회전 명령, .068ms |
| 40ms | primary fallback, 101.924ms | 회전 명령, .031ms | 회전 명령, .018ms |
| 60ms | primary fallback, 101.922ms | 회전 명령, .027ms | 회전 명령, .016ms |

표의 시간은 조건별 단일 native 호출 측정이며 현장 제어루프의 latency 분포가 아니다.
RPP를 설정하되 fallback 관측에는 spy primary를 사용했다. 전체 RPP closed-loop나
ControllerServer action Cancel/ZERO를 native 통합 실행한 것으로 주장하지 않는다.
후보 예외의 ZERO 경로는 설치 ControllerServer 소스와 기존 Cancel/STOP 회귀로
확인했으며, 실제 장비 명령 응답은 다음 승인 시험의 확인 대상이다.

초기 fixture의 frozen clock이 원본 timeout을 끝내지 못해 TF 대기용 clock을 진행하는
system clock으로 분리했다. production 검사가 LD_LIBRARY_PATH 우선순위 때문에
원본 .so를 읽던 문제도 고쳤다. 최종 검사는 `/proc/self/maps`의 로드 경로까지 확인한다.
앞선 실패한 검사들을 통과 기록에 섞지 않았다.

PoseProgressChecker는 실제 설치/export를 확인해 .20m/10s를 유지하고 각도 .20rad로
비교했다. 정상 느린 회전을 인정하고 완전 정지/작은 .04rad 흔들림은 거부했지만,
큰 좌우 반복과 무한 회전은 계속 인정했다. **따라서 운영 선택·설정 통합은 하지 않았다.**
무한 반복을 종료한다고 주장하거나 병진/시간 기준을 완화하지 않는다.

## 계측·취소 보완

- INFO logger에 의존하던 기록을 명시적 private JSONL sink로 연결했다. callback은
  대기 없는 queue64에 넣고 별도 worker가 저장한다. record≤256KiB,
  file≤8MiB×4, 권한 dir0700/file0600, drop/error/pending을 API에 드러낸다.
  종료 flush는 control/ROS shutdown 뒤 최대 .5초만 기다린다.
- declared parameter를 먼저 읽고 활성 plugin/filter 기준으로 미사용 필드만
  NOT_APPLICABLE 처리한다. 활성 필수값 누락은 계속 실패한다. 일부 costmap 값이
  빠져도 controller/planner의 유효 관측을 따로 보존한다. 기존 freshness와 admission
  기준을 늘리지 않는다.
- operator Cancel helper는 현재 goal_id를 한 번 읽어 같은 ID로 기존 API에 전송한다.
  HTTP 422/409를 성공으로 바꾸거나 새 goal을 자동 재시도하지 않는다.

로컬 writer 저장/오류/크기 제한, 파라미터 적용성, Cancel 경쟁과 기존 STOP 회귀는
통과했다. **새 sink와 readback은 현재 배포 47ae383에는 아직 포함되지 않았다.**
실제 서비스에서 브라우저 없이 기록되는지는 다음 정지 상태 배포 검사 대상이다.

## SHA·검증 증거

설치 package: controller `1.1.20-1jammy.20260916.131334`,
Shim `1.1.20-1jammy.20260916.132139`, util `1.1.20-1jammy.20260916.052614`.

| artifact | SHA256 |
| --- | --- |
| 설치 원본 Shim .so | `1cd261a56261e20b10e1d3cc6da3ff14423b467bef23238c8dbc84235f6f0965` |
| 비활성 후보 Shim .so | `95c6ee9b0294651c182092031eb4926291946eb8e72be5cf1bfb976219f1754d` |
| 설치 PoseProgressChecker .so | `0ab4a70804528de9f8f198a44916340e36eef5fb94a736791fe15e66ddb645b7` |
| private 후보 receipt | `853700a444f3cd93b038180fb2e0cbcc543f648eeae8e66faed1aa954a3b24d5` |
| private production native XML | `0acee4cd01398cacd01bf83500b4167819513bc7ddbc1a04771668cdfb8c397a` |
| private phase analysis | `d009b049f33c0690b5558d4c9f2725b957b453c08960e9bbcf1954b12dc79e1c` |

최종 코드 회귀: Python 3,132개 실행, 실패 0, skip 3; JavaScript 699개 통과.
Ruff/Mypy/frontend syntax 통과. 완전한 의존성과 writable Unix socket temp 환경에서
확인했으며, 앞선 누락 의존성·temp 권한 실패를 waive하지 않았다.
원격 CI는 commit별 결과를 최종 응답에서 별도 확인한다. GitHub CI는 비ROS 검사이며
위 native 검사는 격리된 장비 빌드 결과다. private 로그/지도/PCD/환경파일은 게시하지 않는다.

## 현장 결과·복구·다음 한 작업

수정 후 성공 순간·정지 후 오차, 정지 유지, recovery 횟수, 물리적 부작용은 **새 표본 없음**.
과거 시험 2는 CANCELED, 결과 부근 3.18cm/-43.70°, 첫 측정 정지 후 4.60cm/-45.00°다.
이 값을 수정 후 결과나 SUCCEEDED로 바꾸지 않는다.

다음 한 작업은 후보 배포 후 정지 상태에서 library/source SHA·새 generated/live
설정·private sink를 확인하고, 현재 현장 승인 아래 새 단거리 목표 한 건을 비교하는 것이다.
필요하면 반대 yaw 방향 한 건까지, goal당 최대 30초, 첫 반복 progress/TF abort 또는
개선 없는 recovery에서 기존 Cancel로 종료한다. 과거 목표와 잠긴 STOP은 재사용/해제하지 않는다.
최종 통과는 요청 목표 기준 SUCCEEDED + 정지 후 XY≤.10m, |yaw|≤.10rad + 기존 2초
측정 정지 조건을 모두 요구한다. 이 조건이 없으면 미통과다.

복구는 현재 goal-ID Cancel·측정 정지·Nav2 stop 후 overlay 선택을 비우고 이전 immutable
release로 되돌리는 방식이다. `/opt/ros` 원본은 보존됐다. 지도와 저장 preset은
변경하지 않았으므로 자동 복원하지 않는다. baseline 복원이 필요하면 idle에서 최신
revision으로 기존 복구 프리셋을 CAS 적용하고 readback한다.
