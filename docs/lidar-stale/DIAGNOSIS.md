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

## 2026-10-27 재개: 정합 버튼 깜빡임과 현재 로봇 미표시 분석

사용자가 Maps 정합 중 STALE 재발과 현재 로봇 아이콘 미표시를 보고했다. 깜빡인 대상은
**정합 시작 버튼**이라고 확인했다. 이번 요청은 원인 분석이며, 장비 설정·서비스·정합
후보·지도 데이터는 변경하지 않았다. 이전 USB 원인을 이번 현상에 그대로 적용하지 않는다.

### 조사 실행본과 범위

- 분석 소스/실행 release: `c98afbc9db6a07697dc9909286ed68356cf98149`.
  읽기 시작 시 로컬 I1 HEAD는 문서 추가 커밋 `ca6e999639ad0f7d267f62b44a366de4975be3f7`.
  최신 origin/main은 `a79dc18b50a0cddee2056fe4748781cdca03aec9`였다.
- 실제 dashboard PID 1032, cwd `/home/unitree/robot-scope-releases/robot-scope-c98afbc9db6a`.
  이번 부팅에서 서비스는 19:32:40 KST에 시작됐다. 이번 진단이 재시작한 것은 아니다.
  Hesai 2875, C++ bridge 2832, FAST-LIO 6252. 별도 정합 worker는 조회 시 inactive.
- 선택 cloud `/cloud_registered`, pose `/Odometry`, `camera_init → body` (FAST-LIO IMU).
  메시지별 GID 미제공, subscription/단일 publisher graph 대체 관측 계약 사용.
  센서 설정은 표시 30,000점 / 0.18초 간격, 실제 registered 스캔은 약 190점이었다.
- 다른 장비 채팅 `C4 YOLO 통합 인수`는 활성 실행 상태가 아니었다. 원본 checkout의
  사용자 CSS 두 파일은 보존했다. 새 ROS 구독·부하 시험·이동 명령은 실행하지 않았다.
- 이 추가 기록만 기존 L1 브랜치에 남긴다. L1의 과거 코드가 현재 실행본이라는 뜻이
  아니며 I1/main 이력을 이 브랜치에 합치거나 배포를 되돌리지 않았다.

### 확인 1: 신선한 입력에서도 정합 버튼과 현재 pose 표시가 흔들림

19:48:01~19:48:31 KST에 기존 pointcloud/pose WebSocket 한 쌍과 기존 state API(목표
2Hz)를 30초 읽었다. 신규 ROS subscriber 없이 현재 수신 경로를 관측했다. 원문은
비공개 `robot-scope-hardware-validation-private/l1-20261027/streams.json`에 보관했다.
초기 수집기의 metadata padding 파싱 오류로 pose만 기록된 `streams-pose-only.json`은
아래 비교에서 제외했다. padding 수정 후 수집에는 오류가 없었다.

| 동일 30초 구간 | 표본 / 중앙값 / p95 / 최대 |
| --- | --- |
| 수신 pointcloud | 145개; 도착 간격 205.33 / 345.16 / 452.41ms |
| 수신 pose | 272개; 도착 간격 101.76 / 212.23 / 337.80ms |
| state API 응답 | 59개; 268.23 / 616.21 / 625.83ms |
| 서버 pose age | 59개; 78 / 133 / 151ms |
| 화면 모델의 pose age | 최대 352.38ms |
| 화면 모델의 cloud age | 최대 383.00ms |
| bridge 5초 집계 | 6개 모두 cloud 50 / reject 0, 합계 300 / 0 |
| 해당 시간 kernel journal | 추가 항목 없음; USB 이탈 미관측 |

서버 API cloud seq는 146, pose seq는 297 증가했다. WebSocket은 최신 snapshot을 별도로
샘플링하므로 seq 증가량과 수신 표본 수가 같을 필요가 없다. **145개 cloud 중 20개는
30초 전체 pose 스트림에도 같은 source stamp가 없었다.** 이를 원본 LiDAR 패킷 손실로
세지 않는다. 이번 자료만으로 그 pose가 ROS callback 이전/이후 어느 경계에서 생략됐는지
모두 확정할 수는 없다.

실제 `LiveMapObservation`에 원래 입력·순서·도착 간격을 그대로 재생하고, 기존 UI와
같이 100ms마다 snapshot했다. 지도 참조와 근사 anchor는 로컬 모델에만 주었으며 서버
정합/장비 기준점은 변경하지 않았다. 0.5~29.9초 295회 확인 결과:

| 같은 실측 입력의 로컬 재생 | 기본 모드 | 기존 근사 연속 관측 모드 |
| --- | --- | --- |
| 초기 입력 대기 | 3회 | 3회 |
| WAITING_PAIRED_POSE | 55회 | 0회 |
| 현재 pose 표시 가능 | 237회 | 292회 |
| canAnchor 변화 | 63회 | 1회 (초기 준비) |
| STALE | 0회 | 0회 |

원인은 기본 `live_observation_contract.js::pair()`가 FAST-LIO의 **같은 source stamp**를
브라우저 history에서 요구하고, `ready()/snapshot()`의 이 결과를 `canAnchor`와 현재
pose 표시 양쪽에 사용하기 때문이다. `map_seed.js::draw()`는 `canAnchor`에 따라 시작
버튼을 켰다 끄고, `live_observation.js::render()`는 pose가 없으면 현재 모델을 지운다.
따라서 입력이 1초보다 신선해도 버튼과 현재 모델은 흔들릴 수 있다. 이것은 수치 정합을
반복 실행했다는 증거가 아니다.

기존 연속 모드는 이미 registered cloud의 고정 frame과 독립적인 신선한 pose를 사용한다.
위 표는 **기존 두 표시 정책의 동일 입력 비교**이며 이번에 수정·배포한 성능 개선이 아니다.
서버에서 정합 입력을 확보할 때의 정확한 cloud/pose pairing은 별도 조건으로 유지해야 한다.

### 확인 2: 한 번의 공백 뒤 현재 로봇은 사라지고 STALE 상태가 남음

같은 기록의 12.0~13.5초 이벤트만 전달하지 않는 로컬 재생을 추가했다. 실제 장비나
네트워크를 끊지 않았으며, 해당 공백이 현장에서 발생했다고 주장하지 않는다.

- 기본 모드는 첫 stale에서 `suspendStaleConnection()` → `invalidate()`가 anchor를
  지운다. 새 입력이 돌아와 `canAnchor=true`가 되어도 anchor가 없으므로 pose는 복원되지
  않는다. 14~29.9초의 160회 확인에서 현재 pose 표시 **0회**, anchor 없음이었다.
- 이때 `snapshot()`의 신선한 입력/anchor 없음 경로가 기존 `this.reason='STALE'`을
  그대로 반환한다. **수신은 회복됐는데 표시 상태가 STALE로 남는 구분 문제**를 확인했다.
- 기존 연속 모드 + 같은 세션 복구는 실제 공백 중 7회 숨김을 유지했고, 새 cloud/pose가
  모두 진행한 뒤 복구했다. 같은 160회 확인에서 현재 pose 표시 **160회**였다. 오래된
  프레임의 시각을 갱신하거나 공백 중 LIVE를 유지한 결과가 아니다.
- 주황 draft와 파란 candidate는 `scene3d.js::_drawInitializationPreview()`의 별도
  레이어다. 위 live anchor 무효화로 자동 삭제되지 않는다. 따라서 **두 후보 로봇은 남고
  현재 관측 로봇만 사라지는 현상**이 코드 경로와 일치한다.
- 추가로 preview가 현재 모델보다 나중에 그려져 위치가 가까우면 겹칠 수 있다. 당시
  화면에서 가려짐이 직접 원인이었는지는 미확정이다. 관절 freshness도 현재 모델의 조건이지만
  조회 시 관절은 신선했고 그 소실을 원인으로 확인하지 않았다.

### 당시 정합 결과와 아직 확정하지 않은 것

최근 서버 job `e8ee030a7c66c3c8f6ee541c`는 map `f9892bac9cc1d59328601dc6` /
revision `13eea513dad4b7bdbe8638e5063bb3cb3ca94ad899465b1f844defa86da41520`에서 끝났다.
220점, 수치 처리 479.56ms, 생성→완료 **5.297초**, 19회 반복으로 수렴했으나
RMSE .355260m / overlap .713636 / `HIGH_RESIDUAL`, `admissible=false`였다.
해당 요청에는 5cm 제한 해제가 전달되지 않아 `enforced=true`였고 course weighting도 없었다.
이전 확정 코스 지도와 다른 지도이며, 현재 Codex 브라우저의 체크 해제 상태와도 다르다.
과거 요청 결과가 이후 체크 변경으로 소급 변경되지는 않는다. 어떤 브라우저/당시 선택이
이 요청을 만들었는지 단정하지 않는다. 전체 5.297초 중 수치 계산 밖의 약 4.8초는 이번
기록만으로 단계별 분해할 수 없으며 반복 worker 실행 시간으로 해석하지 않는다.

이 rejected 후보는 현재 관측 위치로 적용될 수 없다. 사용자가 보았던 두 아이콘이 이
job인지는 미확정이다. 후속 답변에서 사용자는 **“정합 후보만 계산했음”**이라고 확인했다.
따라서 당시 현재 관측 로봇 미표시는 후보가 아직 활성 관측 기준점으로 적용되지 않은
흐름으로 해석해야 한다. 후보 계산만으로 현재 위치를 자동 적용하지 않는 동작은 의도된
분리다. 위 공백 주입에서 재현한 anchor 소실을 당시 미표시의 확인된 원인으로 주장하지
않는다. 실제 화면에는 “후보 미적용 / 현재 관측 위치 미설정” 안내가 명확해야 한다.
이 확인은 별도로 재현한 정합 버튼 깜빡임과 회복 뒤 STALE 문구 잔류 결과를 바꾸지 않는다.
조회 중 Codex 탭은
`map_20261027_125427_edited`의 SAVED 2D 상태였고 3D live cloud demand가 꺼져 있었다.
그 탭의 오래된 cloud 수신 요약 STALE은 **표시 구독 중단**과 구분해야 하며 서버 입력
단절의 증거가 아니다. 임의로 지도를 바꾸거나 초기값을 적용하지 않았다.

### 이번 검증·수정 경계와 다음 한 가지

- 실행본과 같은 소스에서 기존 집중 JS 회귀 43개 모두 통과
  (`test_live_observation.mjs`, `test_map_seed.mjs`, `test_observed_joints.mjs`).
  실측 재생과 공백 주입 재생은 로컬 검사이며 실제 브라우저의 렌더 성능 시험은 아니다.
- 이번 30초에는 실제 STALE/변환 거부/USB 이탈을 재현하지 못했다. 과거 정합 중의
  브리지 backlog, callback 대기, CPU 경쟁, 브라우저 렌더 지연은 이번 자료로 배제하지 않는다.
- 이번 커밋은 분석 기록만이다. 표시 정책·수치 정합·신선도·주행 watchdog 수정이나
  서비스 재시작·배포를 하지 않았다. 원본 점군·pose·지도 데이터는 Git에 포함하지 않는다.
- **다음 한 가지:** 초기값 정합 시작의 준비 조건과 현재 관측 표시를 브라우저의 우연한
  exact-pair 수신 여부에서 분리한다. 기존 연속 관측 경로를 재사용하고, 명시적 후보 적용
  이후의 같은 세션 복구·실제 단절 시 숨김·새 지도/출처 시 무효화·계산 중 기존 anchor 보존을
  함께 검증한다. 회복된 입력의 “기준점 재연결 필요”와 실제 입력 STALE도 구분한다.
  서버의 수치 정합용 정확한 pairing이나 1초 신선도 검사를 단순히 제거하는 수정은 아니다.
