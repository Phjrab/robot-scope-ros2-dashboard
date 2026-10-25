# L1 — 이동 중 LiDAR STALE 진단

조사일: 2026-10-25 (KST). 검토 브랜치: `review/20261024-l1-lidar-stale`.

## 결론과 완료 범위

실제 이동 시험에서 처음 확인된 단절은 **온보드 Jetson의 USB Wi-Fi 장치 이탈 → 브라우저 전달 중단**이다. 13:13:00에 USB 장치가 사라졌고 재인식 도중 다시 이탈했다. 같은 시각 점군·pose의 브라우저 수신이 함께 멈췄다. Jetson 내부 대시보드 수신과 C++ 변환 출력은 그동안 계속 진행됐다.

사용자는 USB 연결 확인·고정과 재연결 후 최종적으로 **“아마 지금까지 usb 연결이 불안전해서 그랬나봄 문제 해결”**이라고 현장 결과를 알렸다. 이 확인으로 추가 이동 시험은 종료했다. USB 접촉, 전원, 드라이버 중 **왜 장치가 이탈했는지는 미확정**이다. 두 번째 이동에서도 사용자가 STALE/멈춤을 봤다고 답했으며 그 순간의 브라우저 연속 수신 기록은 없다. 따라서 최종 해결은 **사용자 현장 확인**, 모든 STALE의 원인 확정이나 계측된 무중단 전후 통과는 아니다.

코드에서는 별도로 실측·재현한 오표시를 최소 수정했다. 서버와 통신할 수 없는 상태를 Maps에서 `ROBOT_TARGET_CHANGED`로 표시하던 경로를 `AGENT_CONNECTION_LOST`로 구분했다. 초기 정합 제안값을 사용한 뒤에는 다음 렌더가 이를 `INITIAL_ESTIMATE_SOURCE_CHANGED`로 덮어쓰는 경로도 기존 브라우저 회귀에서 재현하고 수정했다. 이는 물리적인 USB 단절을 고치는 변경이 아니다. 오래된 관측을 지우는 동작과 기존 stale 기준은 유지한다.

## 기준본·사용자 변경·실행본

- 시작 시 GitHub `refs/heads/main`: `104692fa0070ef085eee918913ea05fdb2d88c05`. 참고 SHA로 되돌리지 않았다.
- 해당 L1 원격 브랜치는 시작 시 없었다. 기존 체크아웃의 브랜치/index를 변경하지 않고 별도 일반 clone을 만들었다.
- 기존 체크아웃의 `robot_dashboard/static/dashboard-polish.css`, `robot_dashboard/static/features/map_editor3d/editor.css` 사용자 변경은 그대로 보존했다.
- `AGENTS.md`의 검사 의무를 따른다. 사용자가 명시한 L1 브랜치/push 및 main 병합 금지가 기본 main 작업 규칙에 우선한다.
- 장비 Git HEAD는 `d7807de8f15fb457942039bb90ab41cf68d384c6`. 작업 트리에 다수의 부분 배포·미커밋 파일이 있어 HEAD만으로 실행본을 판단하지 않았다. 체크아웃/reset/배포하지 않았다.
- `/proc/952/cwd`는 `/home/unitree/robot-scope`. 아래 8개 파일의 SHA-256은 장비 파일과 기준 main에서 모두 일치했다: `ros_agent.py`, `ros/observation_subscriptions.py`, `ros/pointcloud.py`, `ros/telemetry.py`, `static/features/maps/live_observation_contract.js`, `static/features/sensors/pointcloud_transport.js`, `ros2/robot_scope_xt16_bridge/src/xt16_fastlio_bridge.cpp`, `config/fastlio_xt16.yaml` (앞 6개는 `robot_dashboard/` 기준).
- 이 대조는 해당 파일들의 디스크 일치 증거다. 프로세스가 로드한 모든 바이트나 C++ 바이너리의 재현 빌드를 증명하지 않는다. 실제 실행 경로와 5초 로그로 C++ 브리지 실행을 별도 확인했다.

## 실제 화면과 활성 경로

사용자 확인 화면: **Maps / 위치 관측**. Codex 브라우저에서 `/#maps`를 열어 기존 저장 3D 지도 `map_20261023_135003`을 선택했다.

- 지도 ID: `b9087113da92a1f2b477e932`.
- revision: `58991300bd1aac8c872fd45cafdda6f3eaf2026e4e578d411a4cdba439d31f6a`.
- 저장 지도 41,073점, 저장 표시 선택 `ALL ≤2M`.
- 실시간 표시 한도 10,000점, 서버 frame interval 0.18초. 실제 registered frame은 약 400점이었다. 저장 지도 표시량과 실시간 처리량은 다르다.
- 처음에는 `/cloud_registered`가 선택돼 있었지만 FAST-LIO는 STOPPED, pose는 `/utlidar/robot_odom`이었다. 이 상태의 입력 대기는 이동 중 장애와 분리했다.
- 사용자가 Codex 창에서 진행하라고 승인한 뒤 13:10:20경 기존 **관측 시작 (30분)** 버튼으로 FAST-LIO 관측 세션을 시작했다. 자동 이동/ARM/Nav2 goal/자세 명령은 수행하지 않았다.
- 시험 시 cloud `/cloud_registered [camera_init]`, pose `/Odometry [camera_init → body]`. 관측 세션 `9f57dfc0612d4167bbcdfe191bef9d74`. cloud epoch `44652f90e0f0657233fe02b22d107c01`은 첫 이동 수집 전체에서 동일했다.
- dashboard PID 952, Hesai PID 2851, C++ bridge PID 2819, FAST-LIO PID 14536. FAST-LIO는 `/tf`, `/tf_static`, map/path가 관측 전용 토픽으로 remap된 실행본이었다.
- 별도 sensor-tracking worker는 WAITING_GLOBAL / inactive. processing budget은 `null`, 0.6초 제한 해제 상태였다. watchdog 60초와 구분했다.
- camera capture/recording은 비활성. 기존 camera-owner/slam broker는 별도 소유자로 남겨 두었다.
- 초기 Safari에 기존 대시보드 탭이 열려 있었고, 새 Codex 탭도 사용했다. 다른 클라이언트의 연결도 있었으므로 단일 브라우저만의 부하로 해석하지 않는다. 두 번째 시험도 기존 탭을 유지했다. 브라우저 표시량 자체의 A/B 부하 시험은 하지 않았다.
- 사용자는 다른 채팅의 장비 작업이 없다고 확인했다. L1은 다른 C1~C4/D0 채팅에 명령을 보내거나 역할 변경을 하지 않았다.

## 첫 이동 구간의 시간 순서

아래 시간은 장비 UTC 로그를 KST로 변환했다. 센서 자체 시계와 브라우저 monotonic을 직접 빼지 않았다.

| KST | 근거 |
| --- | --- |
| 13:12:23.769 | 90초 기존 API/counter 수집 시작. 사용자에게 준비 완료를 알린 후 사용자가 직접 이동·회전 |
| 13:13:00.356 | SSH를 통해 로컬에 즉시 도착한 마지막 상태 표본. cloud seq 756, 선택 입력은 계속 신선함 |
| 13:13:00 | kernel: `usb 2-2: USB disconnect, device number 2` |
| 13:13:03 | Wi-Fi deauthentication, `mt7921u ... timed out waiting for pending tx`, USB device number 3 재인식 |
| 13:13:06 | `usb 2-2: USB disconnect, device number 3` |
| 13:13:09 | `mt7921u ... Message 000008ed (seq 8) timeout`, `chip reset failed`, device number 4 재인식 |
| 약 13:13:09 | Codex DOM: cloud seq 757 age 9,281ms, pose seq 51677 age 9,283ms, 둘 다 `마지막 수신 · STALE`; 관측 상태 GET도 timeout |
| 13:13:17 | Wi-Fi authenticate 시작 |
| 13:13:18 | journal: pointcloud/pose WebSocket 재연결 수락 |
| 13:13:53.434 | 장비 내 수집 종료. 연결 복구 뒤 SSH 버퍼의 나머지 기록을 모두 회수: 180 표본, 로컬 API 오류 0 |

SSH 파일이 73개 표본에서 일시 멈춘 것을 장비 수집 정지로 오판하지 않았다. 최종 회수된 장비 monotonic 기록은 단절 중에도 진행했다. `fastlio_dashboard.log`는 과거 매핑 로그였으므로 이번 FAST-LIO의 증거로 사용하지 않았다. 이번 관측 FAST-LIO stdout은 socket/journal 경로였다.

첫 부팅의 커널 발췌는 이 채팅의 SSH 도구 응답에 남아 있다. 이후 장비가 재부팅됐고 volatile journal의 이전 부팅 원본은 다시 회수하지 못했다. 별도 원본 로그 파일이 보존돼 있다고 주장하지 않는다. 두 번째 부팅의 커널 로그는 로컬 비공개 파일에 보존했다.

## 연결 정비 후 두 번째 이동과 의도적 재연결

- 장비는 13:19:58 새로 부팅됐다. L1이 재부팅·서비스 재시작을 실행하지 않았다. boot ID `86e757ba-8bfe-4fec-af24-189bc08b3705`.
- Wi-Fi 경로가 첫 시험의 USB3 `2-2`에서 USB2 480M 허브 `1-3.2`로 바뀌었다. 연결 고정 외에 재부팅·USB 경로 변화가 있으므로 단일 변수 A/B 시험이 아니다.
- FAST-LIO 관측 세션 `f7f2d982804f4d7facbb7e6e6e9cdd67`, cloud `/cloud_registered`, pose `/Odometry`. dashboard PID 991, C++ bridge 2546, Hesai 2573, FAST-LIO 5626.
- 동일 저장 지도의 초기 위치 자동 추정 제안값을 적용하고 기준점에 연결한 뒤 `SAME_START_ODOMETRY_ESTIMATE` 상태에서 사용자 직접 이동을 관측했다. 초기 제안 RMSE 0.063m, overlap 100%, ambiguity unresolved. 정합 잔차가 실제 위치 정확도라는 뜻은 아니다.
- **반복 지도 정합과 별도 sensor-tracking worker는 꺼져 있었다.** 초기 정합 후보 + 연속 odometry 관측의 결과이며, worker 실행 부하를 검증한 결과가 아니다.
- GID 미제공 환경의 기존 subscription/ROS graph 대체 관측을 명시적으로 사용했다. 실제 publisher·본체 pose 정확도가 검증됐다고 표시하지 않았다.
- 13:24:25.394–13:25:55.301의 90초 수집은 180개 모두 회수했다. 위치 범위 X −0.397~2.807m, Y −3.371~0.102m로 실제 pose 변화가 기록됐다. 장비 내부 cloud/pose 갱신은 지속했다.
- 사용자는 이 이동 구간에서도 STALE/멈춤을 봤다고 답했다. 해당 순간의 브라우저 수신/decode/render 연속 계측이 없어 이 STALE을 USB 또는 브라우저 처리 중 하나로 확정할 수 없다. 이 90초를 화면 정상 통과로 계산하지 않는다.
- **13:25:57, 13:26:23 USB 허브 `1-3` 이탈은 사용자가 직접 케이블·허브를 재연결한 구간**이다. Wi-Fi 외에 하위 허브·USB Ethernet·저장장치도 함께 재인식됐다. 13:26:44 Wi-Fi 재연결. 이를 이동 중 자발적 재발로 집계하지 않는다.
- 이 의도적 조작 중 13:26:25.886 브리지에 `cloud callback backlog residual 0.925s exceeded 0.250s`가 1회 로그됐고, 13:26:30 집계에 reject 2가 기록됐다. 앞선 90초의 reject 0과 구분한다. 이 시점의 `cfg80211` 경고는 허브 이탈 뒤 disconnect call trace에서 나왔으므로 최초 원인을 드라이버 경고로 단정하지 않는다.
- 조회 당시 허브 power/control `auto`, Wi-Fi 장치 `on`, 둘 다 runtime `active`였다. 이 사후 상태만으로 autosuspend가 원인이었다고 단정하지 않았고 설정도 바꾸지 않았다.
- 최종적으로 사용자가 USB 연결 정비 후 문제 해결을 알렸다. 이후 추가 이동·배포·장비 설정 변경은 하지 않았다.

## 같은 시간창의 수치

기존 `/api/v1/state`, 관측 상태/설정/소유권 API, 브리지 5초 집계, Hesai 원래 로그, `/proc` CPU·UDP counter, kernel journal을 사용했다. 새 ROS 구독, rosbag, 영구 계측, 서비스 재시작을 추가하지 않았다.

| 지표 | 정지 기준 | 첫 이동 포함 구간 | 정비 후 두 번째 이동 구간 |
| --- | --- | --- | --- |
| 실제 시각 KST | 13:10:50.454–13:11:44.152 | 13:12:23.769–13:13:53.434 | 13:24:25.394–13:25:55.301 |
| API 표본 수 / 오류 | 150 / 0 | 180 / 0 | 180 / 0 |
| 서버 API 시간 p50 / p95 / max (ms) | 386.2 / 639.7 / 760.8 | 167.7 / 564.8 / 743.7 | 428.4 / 759.0 / 1027.6 |
| selected cloud callback age p50 / p95 / max (ms) | 50.5 / 106 / 159 | 48.5 / 105 / 125 | 46.5 / 100 / 159 |
| 표시 가공 프레임 age, 응답 완료 시 p50 / p95 / max (ms) | 240.7 / 490.3 / 611.2 | 223.2 / 481.9 / 549.2 | 252.7 / 555.6 / 716.2 |
| pose API age p50 / p95 / max (ms) | 66.5 / 124 / 247 | 76.5 / 126 / 191 | 59.5 / 131 / 206 |
| 화면용 cloud seq 증가 | 259 | 432 | 429 |
| pose seq 증가 | 533 | 893 | 884 |
| 관측한 cloud seq 변경 간 최대 간격 (ms) | 886.7 | 999.6 | 1183.1 |
| 관측한 pose seq 변경 간 최대 간격 (ms) | 804.9 | 984.3 | 1183.1 |
| bridge 집계 cloud / reject | 500 / 0 (5초 집계 10개) | 900 / 0 (5초 집계 18개) | 900 / 0 (5초 집계 18개) |
| 브라우저 stale 관측 | 별도 연속 측정 없음 | cloud 9,281ms / pose 9,283ms 동시 관측 | 사용자 STALE 보고, 해당 순간 age 미수집 |

**표본 간 gap은 ROS callback의 실제 최대 gap이 아니다.** API를 2Hz로 표본화했고 정지 구간은 5Hz 목표였으나 응답 지연 때문에 실제 53.7초가 걸렸다. 표본 개수로 제한했던 정지 수집의 길이 문제를 다음 수집에서 monotonic 마감으로 수정했다. 희소 표본의 seq 차이·빠진 frame을 센서 손실로 세지 않았다. 정지/이동의 polling 부하가 달라 API 지연 감소를 개선 성과로 주장하지 않는다.

CPU는 `/proc/<pid>/stat` 프로세스 tick 차이로 볼 때 대시보드 약 110%, 브리지 약 34–35%, Hesai 약 37–38%, FAST-LIO 약 33–35% 수준(한 코어 100%, Linux USER_HZ=100 환산)이었다. 측정 시작 전 swap 0MiB, available RAM 약 14.4GiB. 이 자료로 순간 부하 피크나 throttling을 배제할 수는 없다. UI의 9초 단절과 일치하는 **명시적 USB 이탈**이 우선 증거다.

두 번째 구간 같은 방식의 평균 CPU는 dashboard 110.86%, bridge 35.37%, Hesai 38.92%, FAST-LIO 36.97%였다. API 최대 응답 시간이 1,027.6ms였지만 callback age 최대 159ms와 같지 않다. 이 값 하나로 브라우저 WS 병목이나 센서 입력 정지를 결론내리지 않는다.

실행 PID의 CycloneDDS XML은 8MiB 요청을 포함했다. `ss`가 실제 socket buffer 상세를 제공하지 않아 요청값을 실제 확보값이라고 쓰지 않는다. 이번 정상 bridge 출력에 근거해 과거 DDS buffer 해결책을 재구현하지 않았다.

## 가설 분류

| 후보 | 이번 구간 판정 | 근거·한계 |
| --- | --- | --- |
| A 원본 정상/브리지 시간 검사 거부 | 두 이동 수집 구간의 원인으로 배제 | 각각 18개 5초 집계 모두 cloud 50, reject 0. 의도적 USB 재연결 중에는 별도 reject 2 발생. 이를 감추거나 시간 검사를 완화하지 않음 |
| B 기본 callback group/무거운 가공 | 코드 구조는 확인, 이번 장시간 단절 원인으로 미지지 | 같은 기본 group 사용은 존재하나 장비 cloud age 최대 125ms. 계측 없이 executor/worker를 바꾸지 않음 |
| C LiDAR–IMU 시간 관계/FAST-LIO | 출력 단절 원인으로 미지지, 정확도는 미확정 | `/Odometry`와 registered stamp/seq 진행. deskew·절대 위치 정확도는 이 시험 범위 밖 |
| D 별도 정합 worker 자원 경쟁 | 두 이동 수집 구간에서 배제 | worker inactive, 처리 제한은 해제 상태. 두 번째는 초기 정합 후보를 사용했으나 반복 정합 부하 시험은 아님 |
| E 전달/브라우저 | **첫 시험 네트워크 전달 단절 확인**, 두 번째 STALE 최초 지점은 미확정 | 첫 USB Wi-Fi 이탈 시각과 browser/SSH 정지가 일치, 장비 내 처리 지속. 두 번째는 사용자 STALE 보고만 있어 브라우저 연산·전달 지연을 구분하지 못함 |

## 최소 코드 변경과 회귀

장비 연결 실패 시 `refreshState()` → `renderOverviewUnavailable()` → `resetLiveRobotSessionView()`가 항상 `ROBOT_TARGET_CHANGED`를 보내는 결함을 실제 DOM과 회귀로 확인했다.

- `robot_dashboard/static/app.js`: reset 이유를 전달한다. HTTP 실패는 `AGENT_CONNECTION_LOST`, 서버가 보고한 robot telemetry unavailable은 `ROBOT_TELEMETRY_UNAVAILABLE`, 명시적 대상 변경은 기존 `ROBOT_TARGET_CHANGED`.
- `robot_dashboard/static/features/maps/live_observation.js`: 연결 단절 시 “현재 LiDAR·pose 수신 상태를 확인할 수 없음”을 표시한다. 초기 제안값의 source fence와 입력 필드를 reset 전에 함께 지워 다음 렌더가 원인을 덮어쓰지 않게 한다. 실제 source 변경의 기존 invalidation과 확인 해제 동작은 유지한다. 서버 미응답만으로 센서 고장을 단정하지 않는다.
- `tests/test_overview_offline.mjs`: 실제 앱 함수 경로를 실행해 실패한 HTTP 요청의 이유, 오래된 cloud/pose 삭제, 반복 실패 시 1회 reset, 명시적 대상 변경을 검사한다. 수정 전 실패(`ROBOT_TARGET_CHANGED`), 수정 후 통과했다.
- `tests/test_live_observation.mjs`: 연결 손실과 서버가 보고한 robot unavailable 안내를 구분한다.
- `tests/test_robot_profiles.mjs`: 기존 reset 함수 서명 검사만 갱신했다.
- `tests/e2e/live_observation.spec.mjs`: 기존 합성 브라우저 fixture에서 초기 IMU 정합 후보 적용 → 지도 연결 → API 실패를 재현한다. 추가 수정 전 `INITIAL_ESTIMATE_SOURCE_CHANGED`로 실패, 수정 후 `AGENT_CONNECTION_LOST` 안내·오래된 geometry 제거·기준점 입력 삭제·확인 해제로 통과했다. 장비 접속이나 로봇 명령은 없다.

1초 관측 stale, 0.18초 화면 sampling, 원본 source stamp, 수신 source/epoch 검증 기준, raw one-shot capture, 기존 latest-only/HTTP fallback/socket watchdog은 변경하지 않았다. 주행 control/navigation watchdog과 소유권도 변경하지 않았다. 네트워크 단절 동안 오래된 pose를 LIVE로 유지하거나 프레임을 재전송하지 않는다.

### 검증 상태

- 집중 JavaScript 회귀: 71개 통과.
- 전체 JavaScript: 666개 통과.
- frontend syntax: 106개 모듈 통과.
- Python 필수 전체 unittest: 최종 2,707개 실행, 통과(4개 skip), 100.897초. Python 3.13.2 기존 venv 사용. 앞선 macOS sandbox Unix socket 및 `/var` symlink 경로 실패를 실행 환경으로 분리했고, `/private/tmp`의 gid 0 상속과 테스트 기대 gid 20 불일치도 확인했다. canonical·사용자 gid의 짧은 전용 임시 경로에서 최종 전체 검사를 통과했다. 관련 없는 Python 소스는 변경하지 않았다.
- 기존 합성 브라우저 회귀: 연결 실패·초기 정합·늦은 제안·실제 source 변경 4개 통과(10.5초). 실제 Chromium에서 합성 API를 사용한 로컬 검사이며 장비 적용 시험이 아니다.
- `git diff --check`: 통과.
- 새 UI 수정의 장비 적용: **미적용**. 실장비 시험은 기준 실행본으로 실시했다.
- USB 정비 후 초기 정합된 상태의 이동 비교: **실시**, 장비 내부 입력 진행 확인. 화면 STALE 사용자 보고가 있어 end-to-end 무중단 통과로 취급하지 않는다. 최종 해결은 이후 사용자 현장 확인이며 마지막 연결 정비 이후의 정량 이동 수집은 없다.

## 배포·복구 및 남은 한 가지 작업

코드 배포는 별도 승인 대상이다. 필요하다면 위 static JS 2개만 기존 파일 해시 확인·백업 후 교체하고 브라우저를 새로고침한다. 대시보드 서비스 재시작, ROS 프로세스 변경, 지도/프리셋/원본 데이터 변경은 필요 없다. 복구는 두 파일의 백업 복원과 브라우저 새로고침이다. 장비에 부분 배포 수정이 있으므로 전체 checkout/pull/rollback은 하지 않는다.

**다음 작업 하나(재발 시):** 케이블 조작 없이 같은 초기 정합 상태에서 짧은 이동 한 구간의 브라우저 수신 age와 장비 내부 freshness를 동시에 기록한다. USB 이탈이 없는 STALE의 최초 경계를 확인하는 데만 한정한다. 사용자 해결 확인 이후 추가 시험을 지금의 완료 조건으로 요구하지 않는다.

C1 통합 충돌 지점은 `static/app.js`의 `renderOverviewUnavailable`, `resetLiveRobotSessionView`, `refreshState` 세 함수와 `features/maps/live_observation.js`의 안내 함수와 초기 제안값 정리/reset 경로다. main 병합·자동 배포 없음. `.github/workflows/ci.yml`의 push 작업은 hardware-free CI이며 로봇 배포 단계가 없다.

상세 API/프로세스/브리지 로그와 두 번째 부팅의 커널 로그는 로컬 비공개 `robot-scope-hardware-validation-private/l1-lidar-stale-20261025/`에 보관한다. 핵심 파일은 `baseline.jsonl`, `motion-1.jsonl`, `motion-2.jsonl`, `motion-2-kernel.txt`, `motion-2-after-window.txt`다. 마지막 파일의 service journal 조회는 `No entries`를 반환했으나 조회 원인을 확인하지 않아 서버 로그 부재의 증거로 쓰지 않았으며, 함께 회수한 bridge 로그만 사용했다. 첫 부팅 kernel 원본의 보존 한계는 위에 명시했다. 이 검토 브랜치에는 영상·점군·bag·인증정보·대형 환경 파일을 넣지 않는다.
