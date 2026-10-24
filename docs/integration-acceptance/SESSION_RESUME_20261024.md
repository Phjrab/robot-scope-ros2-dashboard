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

다음 한 가지 구현 과제는 **저장한 이동 실패 입력으로 근사 초기값 주변의
제한된 탐색/단계별 정합을 비교해 수렴 범위를 넓히는 것**이다. live 600ms,
1초 freshness와 기존 잔차·수렴 조건을 유지해야 한다. 전역 무초기값 위치찾기나
임의 epoch 간 연결은 검증 완료 기능이 아니다. 수신 공백의 원인은 여전히
미확정이며 다음 승인된 실기 구간에서 재현·송수신 계측이 필요하다.

## 검사와 보존

static 수정의 관련 JS 52개, 전체 JS 650개, 브라우저 10개가 통과했다.
잠금 수정 전 전체 Python 2,636개(4 skip), 수정 후 2,637개(4 skip)가
통과했다. 합성 브라우저 검사는 실장비 이동 검증을 대체하지 않는다.
최종 readback에서 최초 20파일, 추가 static 3파일과 Python 1파일의 설치·백업
해시, 지도·설정 SHA가 일치했다. dashboard PID67085, 관측 MainPID17924,
Hesai PID67237, bridge inactive/disabled, ownership 제약 clear,
관측 RuntimeMaxSec=3600이었다. Git main에 소스 커밋을 push했으며 장비 checkout
base는 앞서 적은 d7807de8과 선택적 설치로 구분한다.

실제 입력·원시 기록·스크린샷·백업/복구 리허설·검사 로그는 Git 밖의 private
`resume-20261024/`에 있다. 원본 지도·PCD·인증정보는 저장소에 추가하지 않는다.
