# 2026-10-24 재부팅 후 도착 위치 관측

## 실제 설치와 실행

사용자는 어제 마지막 이동·회전 후의 도착 위치/방향에서 서서 정지했다고
확인했다. 매핑 시작점으로 복귀했다고 해석하지 않았다.

- 시작 Git 기준: 로컬/origin main `c00cc58543fe436d1dd07145137403f13d9cf8d6`.
- 장비 checkout base: `d7807de8f15fb457942039bb90ab41cf68d384c6`와 기존 선택적
  설치 변경. 장비 Git pull/reset 없이 승인된 UI 17개/Python 3개만 적용했다.
- 13:07:49 KST dashboard 재시작 1회, PID 981 → 15776. 소유 LiDAR preview 복구.
- 원본 19파일 백업, 새 capture 파일 1개, 적용 20파일/백업 SHA 검증 완료.
- 관측 FAST-LIO 1개: `robot-scope-observation-resume-20261024.service`,
  13:09:42 KST 시작, RuntimeMaxSec=3600, 14:09:42 KST 자동 종료 확인.
  원래 설정 유지, PCD 저장 OFF, Log/PCD/ROS 로그 별도 경로와 observation TF로 격리.
- 제어 bridge OFF/disabled, 자동 시작 OFF. 로봇 이동·자세 명령, Nav2 및 운영 TF 적용 없음.

지도는 `b9087113da92a1f2b477e932`, revision
`58991300bd1aac8c872fd45cafdda6f3eaf2026e4e578d411a4cdba439d31f6a`로 고정했다.
`map_20261023_135003.pcd`, 저장 2026-10-23 13:50:05 KST, 41,073점,
`camera_init`/m, 원본 SHA
`628653237cc7fb146793a6b970a5636f6562b5b3b73b57cf64fcf9badaead97a`가 유지됐다.
설정 `fastlio_xt16.yaml`의 SHA도 변경되지 않았다.

## 새 세션 초기화와 정합

실제 publisher graph는 `laser_mapping` 1개, `/Odometry`는
`camera_init → body`, `/cloud_registered`는 이미 `camera_init`에 변환된 점군이다.
여기서 `body`는 FAST-LIO IMU 기준이며 Go2 본체 중심 외부변환은 미검증이다.
원본 메시지 publisher identity를 제공하지 않는 runtime이므로 사용자가 허용한
subscription/ROS graph 기반 관측 후보임을 유지한다.

어제 마지막 동일 세대 원본 pose에 과거 유효 지도 연결을 곱해 도착 위치 prior를
복원했다. XYZ `(1.163563, 0.458375, 0.060606)` m, RPY
`(-0.439443, -0.922733, 9.460683)`°는 근사 초기값이다.
어제의 odometry transform/시각을 새 세션의 현재 값으로 재사용하지 않았고,
오늘의 신선한 pose에 연결해 새 `T_map_odom`을 만들었다.

| 실제 입력 | 잔차 RMSE | overlap | inliers | 수렴/반복 | 전체 처리 |
| --- | --- | --- | --- | --- | --- |
| 정지 입력 보존 | 0.074228094 m | 1.0 | 409 | true / 8 | 164.070 ms |
| 수동 이동 도착 입력 보존 | 0.080835490 m | 1.0 | 377 | true / 17 | 158.915 ms |

두 건 모두 `CANDIDATE_SOURCE_UNVERIFIED`. 잠정 10cm 잔차는 통과,
원래 5cm 평가는 `REJECTED/HIGH_RESIDUAL`이다. 잔차는 절대 위치오차가 아니다.
exact reference/query, paired pose, seed, source stamp/epoch/hash를 opt-in
`capture_inputs`로 보존했고 오프라인 재현에서도 수렴/잔차가 일치했다.
실제 센서 시계 관계, deskew, 본체 외부변환, 절대 정확도는 미검증이다.

## 입력 지연과 이동 관측의 한계

사용자는 이동 후 오른쪽 약 30° 회전했다고 보고했다. 동일 epoch의 원본
odometry 기록에는 약 0.49m 이동/오른쪽 약 22° 회전이 나타났다.
이는 odometry 측정이며 독립 정답이 아니다. UI 기준점이 이동 직전에 무효화되어
이번 이동의 연속 화면 궤적은 검증 완료로 표시하지 않는다.

별도 정지 120초 수신은 pose 954개/점군 555개, 최대 간격 0.587/0.628초였다.
수동 이동을 포함한 600초 기록은 pose 4,944개/점군 2,829개, 단일 epoch였다.
최대 수신 간격은 각각 2.176/2.401초였으며, 앞/뒤 100 pose 중앙값의
변위는 0.4922m, yaw 변화는 −21.57°였다.
1초 stale 기준을 넘으면 현재 표시를 숨긴다. 기존에는 새 입력이 돌아와도
지도 연결이 영구 삭제되어 수동으로 다시 연결해야 했다.

## 승인 후 적용한 화면 복구

`live_observation.js`와 `live_observation_contract.js`를 사용자 추가 승인 후
13:30 KST에 적용하고 브라우저를 새로고침했다. 기존 기본 모드의 stale 차단은 유지한다. 기존 연속 관측
선택 문구에 복구 의미를 명시하고, 선택한 모드에서만 다음을 적용한다.

1. stale 상태에서는 현재 pose/점군/궤적/정합 결과를 숨기고 활성 anchor를 해제한다.
2. 같은 map/frame/observer/publisher/subscription 세대의 pose와 점군이 모두
   새 seq 및 새 source stamp로 수신되고 기존 freshness/graph 검사를 통과해야
   과거 transform을 **근사 연결**로만 복원한다.
3. `RECOVERED_APPROXIMATE_ODOMETRY_ESTIMATE`로 표시하고 이전 정합 수용 표시는
   해제한다. 새 실제 정합이 통과해야 지도 보정 상태가 된다.
4. 공백 구간을 잇는 궤적은 만들지 않는다. reset/명시적 해제/지도·세대 변경,
   source 시간 역행/jump/잘못된 입력은 보류한 연결도 제거한다.

실제 35초 DOM 기록에서 STALE → 근사 복구 → 새 지도 정합 보정 전환을
수동 재연결 없이 확인했다. 단, 짧은 표시 공백 자체는 남았다.
설치 SHA는 contract `b641163ec6b66b9070c49e92b0e28f1bcb066f0f6e06501912b316a44f25f838`,
UI `5d26e06efc6410582bb0364bffb3029a1d2533b8443f32f56431aec2a0e4b1e8`이다.

추가 동시 기록에서는 브라우저에 STALE이 표시될 때 별도 WebSocket에는 더 새
seq가 수신된 사례와 두 경로가 함께 지연된 사례가 모두 있었다. 브라우저는
visible 상태였다. 백그라운드 RAF가 원인이라고 단정하지 않는다.

`pointcloud_transport.js`의 OPEN/CONNECTING 상태만으로 HTTP 보조 수신을
차단하는 경로를 수정했다. 새 점군이 400ms 동안 없으면 기존 HTTP GET으로
보충하며, 요청은 한 번에 하나/최대 1초, 중복 seq·늦은 응답 fence는 유지한다.
원본 시각이나 관측 신선도를 갱신하지 않는다. 1파일 추가 승인 후 13:43 KST
배포/새로고침했고 SHA는
`65ec3f8442659f46ff22eeee9c70bb8baacdee44dfd482ecb0797285665d0da4`이다.
백업/원복 리허설과 설치·백업 해시가 일치했다. 이 두 static 배포에서는
서비스/FAST-LIO 재시작 또는 실행 시간 연장이 없었다.

추가 수정 후 45초/210회 화면 표본은 지도 보정 48회, 보정 실패 중 odometry
유지 37회, 근사 복구 100회, STALE 25회였다. 시간 비율/성능 개선율로 해석하지
않는다. 동시에 수집한 120초 원본 수신의 최대 pose/cloud 간격도 1.283/1.344초여서
**끊김 없는 연속 추적은 아직 검증하지 못했다.**

## 서버 공유 잠금 후속

동시 GET 읽기 측정 30초에서 Jetson 내부 pose 응답 중앙값/최대는
258/701ms, Mac에서는 463/1,505ms였다. health도 유사했다. 이 값은 해당
실행의 응답 시간이며 센서→화면 지연 또는 위치 정확도 측정이 아니다.

`RosAgent.state_snapshot()`은 pose/cloud와 공유하는 잠금 안에서
`health_snapshot()`의 네트워크·인터페이스 조회를 호출했다. 느린 health를
고정한 회귀시험은 기존 코드에서 센서 snapshot 차단을 재현했다. 센서 payload
복사를 끝낸 뒤 잠금을 해제하고 health를 조회하도록 최소 수정했으며,
관련 32개 검사가 통과했다. 제어·신선도·잔차 정책과 상태 수집 순서는 유지한다.
실제 관측 공백의 모든 원인이 이 잠금이라고 단정하지 않는다.
사용자 추가 승인 후 `ros_agent.py` 1파일을 적용하고 13:54:45 KST에
`robot-scope.service`를 한 번 재시작했다. 소스는 main
`2c95b7feddc4cda15352ac21d2098ac3f8642244`, 설치 SHA는
`b19fac478634de6028027b6cc6952d38080dba4b363eebac247f371b6028d4ba`다.
원본 SHA `fa91e8e2faf9900d4448b857e836271d697238a6e3a59175e75a606511819026`의
백업/원복 리허설과 실제 설치·백업 해시가 일치했다.

Dashboard PID는 15776 → 67085, 서비스 소유 LiDAR preview는 자동 복구됐고
Hesai PID67237을 확인했다. FAST-LIO MainPID17924/실제 mapping PID17983은
유지됐다. 이번 추가 승인에서는 추정기 재시작/시간 연장이 없으며 기존
14:09:42 KST 종료와 RuntimeMaxSec=3600을 유지했다. 이번 전체 세션의 dashboard
재시작은 최초 20파일 승인 1회와 이 추가 승인 1회, 총 2회다.

새 dashboard observer `16c8b738c3f5fa4f1ceb1271e044d55a`, pose epoch
`17c28f752f3fecb570e587988700295e`, cloud epoch
`8ba00008d57972a27f16ce85b62f11ba`를 확인한 뒤 현재 도착 위치의 근사 prior
XYZ `(1.780526, 0.696874, 0.089251)`m, RPY
`(-2.162301, 1.085484, -8.166322)`°를 신선한 입력에 다시 연결했다.
오래된 dashboard observer identity를 현재 값으로 재사용하지 않았다.

재시작 후 보존한 정확한 실제 입력은 373 inliers, 12회 반복 수렴,
RMSE `0.07884657686306222m`, overlap 1.0, 수치 계산 54.896ms/전체 141.839ms였다.
동일 FAST-LIO 원본 stamp `1792817897242691993`의 pose/cloud를 연결했으며,
오프라인 재현 잔차 `0.07884657686306197m`도 일치했다. 잠정 10cm 통과,
원래 5cm HIGH_RESIDUAL 거절, 출처·본체 변환·절대 정확도 미검증 상태를 유지한다.
화면에서도 지도 보정 적용과 근사 복구 상태의 현재 IMU pose를 확인했다.

**지연 해결 완료로 보고하지 않는다.** 동일 동시 GET 측정에서 pose 응답의
중앙값/최대는 Jetson 304/829ms, Mac 614/1,636ms였고 개선 근거를 얻지 못했다.
측정 요청이 추가된 구간이며 통제된 성능 회귀 비교나 센서→화면 지연 측정은
아니다. 120초 별도 WebSocket 기록은 pose 992개/cloud 561개, 단일 새 epoch,
최대 간격 1.919/1.920초였다. 처음 35초의 HTTP 측정 구간을 제외해도 같은
최대 간격과 각각 15/17회의 1초 초과 공백이 있었다.
45초/214회 UI 표본에서도 지도 보정 37회, 보정 실패 중 odometry 유지 40회,
근사 복구 108회, STALE 29회여서 끊김 없는 연속 이동 추적은 미완료다.
이 120초 기록까지는 수정 이후 추가 수동 이동을 요청하거나 확인하지 않았다.
이후 사용자가 직접 이동·회전했다고 확인한 기록은 다음 절과 구분한다.

## 후속 동시 수신·이동 입력과 자동 종료

14:05경부터 90초 동안 Jetson loopback과 Mac에서 기존 pose/cloud WebSocket을
동시에 읽었다. 두 기록 모두 종료 레코드를 확인했다. 새 센서 구독·서비스
변경이나 추정기 재시작은 없었다.

| 읽기 위치 | pose/점군 수 | 최대 pose/점군 수신 간격 | 1초 초과 |
| --- | --- | --- | --- |
| Jetson loopback | 719 / 423 | 0.386 / 0.601초 | 0 / 0 |
| Mac | 742 / 428 | 0.397 / 0.534초 | 0 / 0 |

Jetson의 동일 호스트 관측 수신→기록기 수신 간격 중앙값/최대는 pose
45.6/126.1ms, 점군 113.3/349.5ms였다. 센서→화면 전체 지연이 아니며,
Mac/Jetson 시계 동기화는 검증하지 않았다. latest-value 수신 경로라 두
클라이언트의 모든 seq가 일치한다고 가정하지 않는다. 이 구간에서 기존
약 1.92초 공백을 재현하지 못했으므로 원인 확정·지연 해결 완료는 아니다.
동시 45초 UI 196표본은 초기값 기반 추정 188회/해제 8회, STALE 0회였다.

사용자는 이 기록 중 로봇을 이동·회전했다고 확인했다. 화면의 기준점 해제와
새 연결도 관찰됐으나 정확한 UI 조작 주체는 확인되지 않았다. pose/cloud
epoch는 각각 `dafd73a84b44bea66edfc38f45da996e` /
`4622eacd8520994589788553adf672bb`로 앞선 정지 캡처와 달랐다. 90초 기록 내부에는
추가 epoch 변화가 없었고, 앞선 전환 순간의 원인은 보존 자료로 확정하지 못했다.
이전 도착 위치 prior를 새 epoch에 다시 연결한 값은 이동 후 실제 위치의
검증된 초기값이 아니다. 이전 epoch의 정합을 현재 연결로 승격하지 않았다.

이동 후 정확한 입력을 별도로 보존했다. RMSE `0.14105859356927658m`, overlap
`0.9975429975`, 406/407 inliers, 40회 반복 미수렴, 수치 계산 197.607ms/전체
268.649ms로 `REJECTED/HIGH_RESIDUAL + NOT_CONVERGED`였다. 원본 pose/cloud
stamp `1792818523330240011`이 일치했고, 오프라인 재현에서도 잔차와 미수렴이
일치했다. 현재 지도 보정이나 연속 이동 추적 성공으로 보고하지 않는다.

초기값 민감도만 확인하려고 같은 저장 점군·지도·40회 반복·잔차 정책을
유지하고 앞선 epoch의 정지 정합 transform을 **오프라인 진단 초기값**으로
대입했다. 잔차는 `0.0721268002m`로 낮아졌지만 여전히 미수렴으로 거절됐다.
낮은 잔차만으로 후보를 통과시키지 않았고 현재 화면·운영 TF에 적용하지 않았다.
이는 초기값의 영향을 보여주며, 정확한 좌표를 사용자에게 요구해야 한다거나
초기값만 바꾸면 문제가 해결된다는 증거는 아니다.

14:09:42 KST journal에서 `Service reached runtime time limit. Stopping`과
FAST-LIO 종료를 확인했다. systemd의 `timeout` 결과는 승인된 RuntimeMaxSec에
도달한 기록이다. 14:11 readback에서 transient unit은 inactive/MainPID0이고
`fastlio_mapping` 프로세스가 없었다. 회수된 unit의 `RuntimeMaxUSec=infinity`를
실행 시간 연장으로 해석하지 않는다. Dashboard PID67085와 Hesai PID67237은
유지됐고, bridge inactive/disabled, 적용·백업 파일 및 지도·설정 해시가 일치했다.

종료 후 `/api/v1/pose`는 제조사 `/utlidar/robot_odom` (`odom → base_link`)으로
전환됐다. 이를 FAST-LIO나 저장 지도 pose로 재사용하지 않았으며, 실제 Maps는
`SOURCE_IDENTITY_UNAVAILABLE`, 지도 정합 `UNAVAILABLE/NOT_RUN`으로 현재 마커와
지도 기준 pose를 숨겼다. 종료 후 화면과 읽기 증거를 private에 보존했다.
추가 배포·재시작·시간 연장은 없었다.

이 기록 직후의 구현 과제는 **저장한 이동 실패 입력으로 근사 초기값 주변의
제한된 탐색/단계별 정합을 비교해 수렴 범위를 넓히는 것**이었다. live 600ms,
1초 freshness와 기존 잔차·수렴 조건을 유지해야 한다. 전역 무초기값 위치찾기나
임의 epoch 간 연결은 검증 완료 기능이 아니다. 수신 공백의 원인은 여전히
미확정이며 다음 승인된 실기 구간에서 재현·송수신 계측이 필요하다.

## 로컬 후속: 거친 초기값의 단계별 정합 — 당시 장비 미적용

사용자는 마지막 위치에서 약 1.35m 규모로 직접 움직인 것이 맞다고 확인했다.
이는 이동 규모의 확인이며 독립 좌표·정확한 방향의 정답은 아니다. 기존
정지 위치를 새 기준점으로 재연결한 영향과 지역 정합의 수렴 한계를 구분했다.

0.2/0.4/0.6m voxel의 초기 정렬과 원본 입력 재정합을 비교했다. 0.4m 방식을
모든 입력에 무조건 사용하면 기존 이동 입력이 미수렴하는 경우가 있어 채택하지
않았다. 구현은 기존 대응점 반경 안에서 초기 잔차가 0.2m를 넘고 overlap이
60% 이상일 때만 0.4m centroid로 한 번 초기 정렬한다. 0.2m는 계산 경로 선택
기준이며 잔차 수용 기준이 아니다. 충분히 가까운 초기값은 기존 경로를 유지한다.

초기 정렬 최대 40회 후 **원본 41,073점 지도와 원래 query 전체**로 최대 40회
정합·잔차·overlap·geometry를 다시 계산한다. 파생 점군의 성공을 채택하지 않으며
기존 5cm 평가/잠정 10cm·수렴 조건을 유지한다. 전체는 기존 한 번의 600ms
deadline 안에서만 실행되고, 최종 입력 freshness·map/epoch 검사는 그대로다.
캐시는 파생 지도와 검색 인덱스만 보관하며 이전 scan/pose/transform은 보관하지
않는다. 응답과 replay의 `seed_refinement`는 `NUMERICAL_SEED_ONLY` 진단이다.

실제 저장 입력 4건의 로컬 수치 재현에서 기존 성공 3건의 수렴·잔차는 유지됐고,
마지막 실패 입력은 RMSE `0.07207172234m`, overlap 1.0, 407/407 inliers,
최종 26회 수렴으로 잠정 기준을 통과했다. 원래 5cm는 여전히 거절이다.
이 실행의 총 수치 계산은 553.1ms(초기 정렬/준비 184.4ms, 최종 ICP 356.4ms),
미리 준비된 full reference index를 사용했다. Mac의 SciPy 없는 RadiusGrid 경로다.
별도 subprocess worker에서도 같은 입력을 600ms deadline으로 재현해 부모의
송신~수신 556.7ms와 같은 수렴·잔차를 확인했다(지도 인덱스 준비는 요청 전).
API·지도 로딩·센서→화면 지연과 Jetson 실시간 예산을 검증한 값은 아니다.
새 장비 실행이나 현재 위치 적용으로 보고하지 않는다.

같은 입력 시각에서 새 후보와 기존 anchor 사이의 pose 차이는 약 1.35m다.
기존 UI의 1m 급변 차단을 넘으므로 수렴만으로 현재 마커에 적용할 수 없다.
새 세션에는 사용자가 마지막 도착 위치·정지 자세를 확인한 경우에만 이 과거
후보의 지도 pose를 **근사 prior**로 사용할 수 있고, 신선한 pose·점군으로
새 연결과 정합이 필요하다. 과거 `T_map_odom`·epoch를 그대로 복원하지 않는다.

3개 Python 배포 후보(`observation_alignment.py`, 새 `observation_seed.py`,
`observation_capture.py`)의 원격 원본 2개/새 파일 부재를 읽어 비교했고,
로컬 설치·원복 리허설에서 해시 복원과 새 파일 제거를 확인했다. Dashboard
PID67085·동일 boot, bridge OFF/disabled, 종료된 관측기, 원본 지도·설정 해시와
소유권 조건 clear를 재확인했다. 로봇 파일 쓰기·서비스 재시작·추정기 실행은
하지 않았다. 별도 승인이 필요한 후보 범위는 3파일 적용, dashboard 재시작
1회, 기존 설정의 관측 FAST-LIO 1개 최대 30분 및 현재 도착 위치의 정지 확인이다.

## 추가 승인 후 단계별 정합 배포와 새 정지 관측

사용자는 3파일 적용·dashboard 재시작 1회·기존 설정의 관측 FAST-LIO 1개
최대 30분·마지막 도착 위치의 정지 검증을 승인했다. 소스는
`cc83ee0474be7c3883b3bfd4d345178462366c4e`이며 장비 Git base
`d7807de8f15fb457942039bb90ab41cf68d384c6`와 기존 선택적 설치를 유지했다.
`observation_alignment.py`, 새 `observation_seed.py`, `observation_capture.py`
3파일만 추가 적용했다. 원본 2파일 백업·설치 해시와 원복 리허설을 확인했고
실제 원복은 필요하지 않았다. 지도·설정·기존 로그를 수정하지 않았다.

- Dashboard: 14:42:48 KST 재시작, PID67085 → 118660. 이번 승인 범위 1회.
- 서비스 소유 Hesai preview 자동 복구, PID118808.
- 새 관측기: `robot-scope-observation-coarse-20261024.service`,
  14:43:51 KST 시작, MainPID120010/FAST-LIO PID120059 한 개.
- `RuntimeMaxSec=1800`, **15:13:51 KST 자동 종료 예정**. 14:49:44 readback에서
  실행 중/30분 제한을 확인했다. 이 기록은 예정 시각의 실제 종료 증거는 아니다.
- TF·map·path를 observation 이름으로 remap, PCD 저장 OFF, Log/PCD bind 및
  ROS 로그 격리. bridge inactive/disabled, 자동 시작 OFF, 소유권 제약 clear.
- 별도 로봇 이동·자세·Nav2·운영 TF·제어 출력은 수행하지 않았다.

새 observer `0ebcb17b05e24ad227ef4657a7457d55`, pose/cloud epoch
`0672aeec036aa4a9c1fd6fe7e9b424f4` / `a8cd74a57ea1f36c8efb868df019687a`를
확인했다. `/Odometry`는 `camera_init → body`의 FAST-LIO IMU,
`/cloud_registered`는 이미 `camera_init`에 있는 점군이며 graph publisher는
각각 `laser_mapping` 한 개다. 메시지별 publisher identity는 여전히 제공되지
않으므로 subscription/graph 관측 허용 모드를 명시적으로 사용했다.

마지막 저장 입력의 수치 후보에서 얻은 지도 XYZ
`(0.386558913, 0.405521097, 0.056802836)`m, RPY
`(-2.611982723, 3.311181897, 6.812771896)`°를 **근사 prior**로 입력했다.
새 신선한 pose에 연결해 새 `T_map_odom`을 계산했으며 이전 세대 transform을
재사용하지 않았다. 화면에서 지도 보정 상태와 IMU 마커를 확인했다.
14:48경 표시값은 대략 XYZ `(0.33, 0.43, 0.05)`m / yaw `10.5°`였다.
이는 관측 추정이며 독립 정답이나 Go2 본체 중심 위치가 아니다.

반복 관측을 잠시 끄고, 이미 화면에서 수락한 새 지도 연결을 seed로 6회
입력 캡처했다. 첫 요청은 `COMPUTE_BUDGET_EXCEEDED`로 거절됐다.
나머지 5회는 모두 수렴/overlap 1.0, 407–414 inliers였으며
`CANDIDATE_SOURCE_UNVERIFIED`였다. RMSE 범위는
`0.0719841603–0.0729496082m`, 수치 계산 47.23–88.01ms,
서버 `total_runtime_ms` 108.49–159.62ms였다. 전체 reference/query를 포함한
캡처 HTTP 왕복은 465–820ms로, 작은 일반 응답이나 센서→화면 지연과 구분한다.
잠정 10cm 잔차는 통과하지만 원래 5cm는 거절이다. 가까운 corrected seed여서
이 5회에는 coarse 단계가 필요하지 않았다. 대표 입력의 오프라인 재현도
같은 잔차·14회 수렴이었다.

반대로 **원래 근사 prior를 유지한 별도 새 입력**은 coarse 단계가 실행됐으나
최종 RMSE `0.2231962948m`, overlap 1.0, 12회 수렴으로 `HIGH_RESIDUAL` 거절이다.
같은 정확한 입력의 오프라인 fine-only 비교도 `0.2242169335m`로 거절됐다.
이 실패를 버리지 않고 보존했으며, 조건부 coarse가 모든 초기값·scan에서
성공한다거나 정확한 초기 위치 정보가 불필요한 전역 위치찾기가 됐다고
보고하지 않는다. 잔차·수렴·600ms·1초 신선도·UI 급변 차단은 변경하지 않았다.

정지 90초 동시 읽기 결과:

| 읽기 위치 | pose/점군 수 | 최대 pose/점군 수신 간격 | 1초 초과 |
| --- | --- | --- | --- |
| Jetson loopback | 643 / 402 | 0.455 / 0.618초 | 0 / 0 |
| Mac | 620 / 394 | 0.451 / 0.640초 | 0 / 0 |

각 스트림은 동일 epoch였다. Jetson 호스트 수신→기록기 수신 중앙값/최대는
pose 52.6/141.7ms, 점군 161.5/386.7ms다. 센서 시계 동기화나 전체 표시 지연은
검증하지 않았다. 동시 30초 UI 73표본은 지도 보정 32회, 보정 실패 중 odometry
계속 41회, STALE 0회였다. `NO_PAIRED_POSE`와 `RATE_LIMIT_1HZ`가 나타났고
유효한 현재 pose는 계속 표시됐다. 이 표본 수를 시간 비율로 해석하지 않는다.

14:44:54–14:46:16 반복 관측 구간(별도 캡처 요청 1회 포함)의 서버 로그는
HTTP200 41건/409 34건이다. HTTP200은 수치 응답 완료이며 후보 수락과 같지 않다.
200 응답의 dispatch→response 중앙값/최대는 280.8/616.3ms,
분리 계산 단계는 74.9/531.9ms였다. 수치 예산과 API 왕복·dispatch 시간은
서로 다른 범위다. 이전 수신 공백 해결 완료나 장시간 무중단 추적 근거는 아니다.

이번 새 세션은 정지 검증만 수행했다. 수동 이동은 앞 절의 별도 세션 결과이며,
새 연결의 연속 이동 궤적까지 완료됐다고 표시하지 않는다. 다음 최소 작업은
같은 기록으로 exact-stamp pose pairing 실패와 1Hz 요청 간격을 재현하는 것이다.
추가 배포·재시작·추정기 재실행/연장은 이번 승인에 포함되지 않는다.

private `resume-20261024/`에 `coarse-*-readback.json`,
`coarse-live-input-capture.json`, `coarse-corrected-capture-1..6.json`,
`coarse-live-replay-comparison.json`, `coarse-paired-{jetson,mac}.ndjson`,
`coarse-ui-samples.json`, `coarse-stationary-summary.json` 및 실제 화면
`coarse-map-screen.png`, `coarse-live-screen.png`를 보존했다.
최종 설치·백업 해시와 지도·설정 SHA는 모두 일치했다.

## 검사와 보존

단계별 정합 후속은 관련 Python 94개, 전체 Python 2,643개(4 skip), JS
650개, 합성 브라우저 10개가 통과했다. 초기 전체 실행에서는 macOS `/var`
심볼릭 링크 경로로 기존 파일 보호 검사 58건이 실패했고, `/private/tmp`를
사용한 실행에서는 파일 그룹 상속 차이와 기존 process PID fixture의 일시적
빈 파일 경합이 발생했다. `TMPDIR`를 사용자 임시 폴더의 실제 경로로 지정한
환경에서 관련 85개/15개와 최종 전체 검사가 통과했다. 보호 조건·테스트 코드는 변경하지
않았고 실패 로그도 private에 보존했다. Ruff, mypy, frontend syntax도 통과했다.

static 수정의 관련 JS 52개, 전체 JS 650개, 브라우저 10개가 통과했다.
잠금 수정 전 전체 Python 2,636개(4 skip), 수정 후 2,637개(4 skip)가
통과했다. 합성 브라우저 검사는 실장비 이동 검증을 대체하지 않는다.
앞선 1시간 관측의 최종 readback에서 최초 20파일, 추가 static 3파일과 Python 1파일의 설치·백업
해시, 지도·설정 SHA가 일치했다. dashboard PID67085, 관측 MainPID17924,
Hesai PID67237, bridge inactive/disabled, ownership 제약 clear,
관측 RuntimeMaxSec=3600이었다. Git main에 소스 커밋을 push했으며 장비 checkout
base는 앞서 적은 d7807de8과 선택적 설치로 구분한다.

실제 입력·원시 기록·스크린샷·백업/복구 리허설·검사 로그는 Git 밖의 private
`resume-20261024/`에 있다. 원본 지도·PCD·인증정보는 저장소에 추가하지 않는다.


## 후속 후보: 서버 시간·관절 모델·상대 높이 (장비 미적용)

서버가 monotonic rate limit의 남은 시간을 응답 헤더로 반환한다. 브라우저는
응답 수신 이후 그 기간을 기다린다. 서로 다른 호스트의 절대시각을 비교하지
않으며 원본 센서 stamp pairing, 1 Hz 제한, 신선도와 계산 예산은 유지한다.
기록된 FAST-LIO callback 순서를 재현해 cloud가 먼저 도착하면 동일 stamp
pose를 기존 150 ms 수신 범위와 600 ms deadline 안에서만 기다리도록 했다.

공식 Go2 URDF에서 생성한 기존 링크·관절·mesh를 별도 근사 관측 레이어로
연결했다. `/lowstate`의 명명된 12관절을 사용하고 같은 seq는 신선도를 연장하지
않는다. 서버 age와 로컬 경과시간이 1.2초를 넘으면 모델을 숨긴다. pose·점군은
기존 1초 제한과 세대 검사를 유지한다. 관절 수신에는 유효한 센서 timestamp가
없어 pose와 정확히 동기화됐다고 표시하지 않는다. IMU→URDF base 보정은
아직 미확인이므로 같은 원점·방향을 가정한 모델이라고 표시하며 body_pose는
계속 null이다. 높이는 현재 지도 IMU Z와 기준점 이후 odometry ΔZ를 구분한다.
정합 보정으로 변환이 바뀌어도 ΔZ 기준은 바뀌지 않으며 새 기준점은 초기화한다.

전체 Python 2,649개(4 skip), JS 654개, 합성 관측 브라우저 12개와 변경 Python
Ruff 검사가 통과했다. 최초 전체 Python 25개 오류는 sandbox의 Unix socket
생성 제한(PermissionError)이며 허용된 로컬 환경의 전체 재실행이 통과했다.
추가 대상 mypy 검사는 기존 mypy 1.13/NumPy stub의 Python 버전·placeholder
오류로 완료되지 않았으며 통과로 집계하지 않는다. 실제 관절 입력은 read-only로
확인했지만 앉기·상하 움직임 실험은 하지 않았다.

15:08:16 KST 설치 읽기에서 Python 2개와 static 7개의 원본이 main의 기존
소스와 일치하고 새 static 1개가 없음을 확인했다. 관측/관절 입력은 fresh,
bridge inactive, ownership clear였다. private `joints-time-bundle`에 10파일,
원본 9파일 사본, SHA manifest와 실패 시 원복 절차를 준비했고 로컬 disposable
checkout에서 check/install/restore/check를 통과했다. 아직 장비에 쓰지 않았다.
기존 관측의 15:13:51 종료 시각을 연장하지 않는다. 추가 적용·재시작 1회와
이전 관측 종료 후 최대 30분 실행은 원래 요청 7항의 추가 승인 대상이다.
