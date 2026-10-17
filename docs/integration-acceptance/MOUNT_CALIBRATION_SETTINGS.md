# 카메라 장착 각도 보정: 설정 화면 통합

## 목적

기존 대시보드의 **설정 → 카메라 장착 각도 보정**에서, 앉은 자세로 정지한 Go2에 장착된 RealSense의 각도별 깊이 샘플을 불러오고 같은 전방 벽의 여러 점을 선택해 기준 샘플 대비 상대 pitch를 비교한다.

독립 시제품 `experiments/realsense_mount_calibration`의 계산 코드를 재사용한다. 이 기능의 통합은 실장비 depth 수집, 몸체 기준 절대각 인증, 운영 TF 변경을 의미하지 않는다.

## UI와 API

- 기존 설정 카드/폰트/테마/반응형 규칙을 사용하는 기본 설정 화면의 패널
- 실제 데이터는 저장 샘플 목록 또는 JSON 파일로 가져오며, 합성 데모는 사용자가 명시적으로 선택한 경우에만 로드
- 사용자 확인 조건은 기본 체크 해제: 로봇 정지·같은 벽·pitch만 변경
- 원본 depth 샘플, 선택점, 기준 샘플, 적합 잔차와 상대각 결과를 함께 확인
- 계산 결과는 JSON 파일로 내보내며 실행 중 장착 변환이나 센서 보정값에 쓰지 않음

API:
- GET `/api/v1/settings/mount-calibration/status`
- POST `/api/v1/settings/mount-calibration/estimate`
- POST `/api/v1/settings/mount-calibration/export`
- GET `/api/v1/slam/depth/samples` 및 샘플별 `compatibility`, `image`, `export` 경로

POST는 기존 same-origin 보호를 사용한다. 요청 크기와 JSON 유한값·프로필·좌표계·평면 품질 검증을 유지한다. 결과는 `RELATIVE_ONLY`, `body_extrinsic_validated=false`다. 사용자 checkbox는 독립 센서 검증이 아니다.

## 저장 샘플 가져오기와 수집 경계

Mapping의 **정지 Depth 캡처**가 기존 broker/session/camera lock을 통해 수집·저장한다. Settings에는 카메라 시작·중지를 추가하지 않는다. 설정에서 **목록 새로고침 → 저장 샘플 선택 → 선택한 저장 샘플 가져오기**를 누르면 기존 분석 목록이 교체된다. 사용자 확인과 이전 결과는 초기화된다. 이후 각 촬영의 같은 벽에 넓게 퍼진 6개 이상의 유효한 점을 선택하고 기준 촬영을 지정한다. 두 촬영 이상과 촬영 조건 확인이 있어야 상대각 계산·JSON 내보내기를 할 수 있다.

보관 IR1 PNG는 원본 크기의 canvas에 표시한다. 화면 축소 배율은 표시용이며, 선택 좌표와 intrinsics는 원본 픽셀 기준이다. 대응 영상이 실패하면 이유를 표시하고 깊이 히트맵으로 전환하며 정상 깊이 데이터는 유지한다. 전체 원본 ZIP 링크는 변환하지 않은 원본 증거를 내보낸다. 파일 가져오기와 합성 데모도 그대로 유지한다.

목록·JSON·영상은 GET만 사용한다. 목록은 `no-store`; 저장소가 무결성을 확인한 **원본 bytes**를 제공하고 `X-Robot-Scope-Artifact-SHA256`/`X-Robot-Scope-Artifact-Bytes` 응답 헤더가 목록의 파일 정보와 일치해야 한다. 다운로드 후 목록을 다시 대조한다. 이는 보관 파일 간 대응 검사이며 HTTP의 네트워크 인증을 제공하지 않는다. 오래된 목록·다른 파일·프레임/시각/단위/프로파일/왜곡/정렬 불일치는 실패한다. 늦게 도착한 가져오기나 계산 응답은 새 입력의 결과로 나타날 수 없다.

과거에 저장된 샘플은 나이만으로 거부하지 않는다. 원래 촬영 시각·clock domain을 보존해 **보관 촬영**으로 표시하고 현재 센서 readiness로 사용하지 않는다. 같은 source exposure를 다른 ID로 복제한 입력은 새 각도로 인정하지 않는다. hardware clock은 세션별 epoch로 구분하며 세션 정보가 없는 이전 파일은 epoch 미확인 경고를 남긴다. 실제 정지·같은 벽·pitch만 변경했는지는 현장 확인이 필요하다.

- 같은 픽셀 인덱스의 RGB/IR/depth를 무조건 같은 공간점으로 취급하지 않는다.
- 좌표 프레임 이름인 `frame_id`와 노출 식별자인 `frame_number`는 다르다.
- rectified pinhole 좌표의 optical-Z(m)만 현재 계산 경로에 넣는다.
- 기존 stereo VSLAM의 버전 업그레이드나 RGB-D 전환은 필요하지 않다.
- 저장 파일을 읽었다는 이유로 현재 카메라 연결됨/보정 완료/적용됨으로 표시하지 않는다.
- 별도 UI를 다시 만들지 말고 이 설정 패널과 계약에 맞춰 캡처 결과를 연결한다.

## 안전 및 해석

앉은 로봇의 몸통이 수평이라는 보장은 없다. 상대 영점과 몸체 기준 절대각을 구분한다. pitch-only 벽 관측으로 translation·전체 6DoF를 복원하지 않는다. 고정 높이 가정과 브래킷 pivot에 따른 광학 중심 이동도 구분한다.

지도 중복 벽, 회전 시 궤적 점프는 별도 native pose/좌표 변환/시간 정합 진단이 필요하다. 이 기능을 추가했다고 해당 문제를 해결했다고 표시하지 않는다.

## 실제 파일 계약

호환 JSON의 `id`, `width`, `height`, `intrinsics.{fx,fy,cx,cy}`, `depth_m`(행 우선 optical-Z, m), `points`를 그대로 소비한다. 수집 직후 `points=[]`이며 0 depth는 null이다. `metadata`에는 `serial`, `frame_id`, `profile_id`, `rectified`, `synthetic=false`, 원본 시각/단위/도메인, IR1·depth 각각의 frame number와 timestamp, synchronization 및 실제 alignment 증거가 보존된다. 새 캡처는 `capture_session_id`도 포함한다. 이전 정상 export의 필드 부재는 허용한다.

동일 픽셀 계약은 원본 두 스트림의 크기·pinhole intrinsics·0 왜곡 계수·identity depth→IR1 외부파라미터로 검사한다. 이름만 rectified로 바꾸지 않으며 시각 차이 제한은 기존 1 ms를 유지한다. 내보낸 분석의 `input.samples[].metadata.saved_capture`는 보관 세션·generation·촬영 시각·파일 SHA256/크기를 추가 보존한다. 파일에서 가져온 신고값과 서버 보관 파일의 대응 검증은 출처 표시가 다르며 어느 쪽도 절대 보정을 인증하지 않는다.

## 2026-10-17 배포 전 저장 샘플 연결 검증

시작 기준은 당시 최신 main `316b1a4`(로컬 clean), 기존 Settings 통합 `eb0a9c6`와 수집 `78e23ce`를 보존했다. 장비의 10:15:02Z 읽기 전용 확인에서는 clean `78e23ce9edb59790a665055dfd23f230be018b43`가 실행 중이었다. 아래 loopback 검증은 Settings 통합 배포 전 기록이며, 이후의 실제 배포·수집 결과는 다음 절에 구분한다.

`REALSENSE_SDK_UNAVAILABLE`는 과거 초기 상태다. 이 읽기 전용 확인에서 broker 전용 Python 경로의 SDK 2.55.1 pipeline/context/config binding과 원래 native library SHA256이 정상임을 확인했다. 이때 장치 context/pipeline은 열지 않았으며 USB에는 D435i가 인식됐다. 이 시점의 모델·serial·펌웨어·지원 107 profiles와 실제 640×480×30 IR1/Z16 근거는 이전 승인 캡처였다. 이번 소프트웨어 변경에는 SDK 설치·Isaac 업그레이드·운영 DDS 변경이 없다.

실제 저장 샘플 `a58f3549f327424f8b6241d89783974f`는 로봇의
`/home/unitree/robot-scope-data/runtime/state/navigation/multi-slam/depth-samples/` 아래에 있다.
원본 ZIP을 로컬 private store에 복사하고 **제품 Settings 패널/JS + 실제 수집 GET router/store + 실제 분석 API**만 사용하는 loopback 검증 서버에서 확인했다. 센서·ROS·broker·실제 대시보드는 연결하지 않았다.

- 실제 데이터: 원본 IR 영상, 640×480 native 좌표, metadata, 6개 픽셀 선택 및 최소 2개 촬영 부족 시 계산·내보내기 차단을 확인했다. 선택점은 UI 확인용이며 실제 평면 품질이나 상대각 검증이 아니다.
- 실제 파일의 consumer 계약 통과. 원본 timestamp/global_time·IR1 55/depth 56·0 ms skew·95.4655% 유효 depth를 보존했다. 원본 전체 픽셀·ZIP 검사는 기존 [DEPTH_CAPTURE.md](DEPTH_CAPTURE.md)의 증거를 재사용한다.
- 합성 데이터: 같은 로컬 제품 패널에서 실제 Python API로 0°, +9.999446°, −8.000435°를 계산하고 `RELATIVE_ONLY`, `synthetic=true` 분석 JSON을 생성했다. HTTP 응답과 UI 다운로드 시작을 확인했으며 native 브라우저의 파일 저장 완료까지는 주장하지 않는다.
- 새 입력으로 바꾸면 이전 분석이 사라지고 조건 체크가 초기화됨을 확인했다. 브라우저 fixture 시험은 별도의 합성 데이터이며 실기 정확도 근거가 아니다.

Private evidence: `robot-scope-hardware-validation-private/mount-settings-20261017/`의
`current-runtime.json`, `mount-consumer-contract-report.json`, `settings-real-sample.png`,
`local-api-events.jsonl`, `local-export-response.json`. 원본 센서 파일은 Git에 올리지 않는다.
반복 가능한 읽기 전용 검사는 해당 폴더의 `check_mount_consumer_contract.py --help`와
`serve_saved_sample.py`에 있다. 후자는 제품 패널을 그대로 사용하는 검증 harness이며 별도 제품 UI가 아니다.

전체 Python 2,266개(2 skip), JavaScript 434개와 정적 검사(ruff/mypy/secret scan/diff)가 통과했다.
최종 관련 브라우저 18개(Settings 14 + 기존 Depth 4)가 통과했다. 제품 커밋 `40276a51b2e08c77732317a856cc879cc23e1ef6`의 [GitHub CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/39024766108)도 성공했다. 합성 회귀·CI와 아래의 실제 장비 검증은 서로 다른 근거다.

## 2026-10-17 실제 배포·동일 각도 반복 수집·품질 차단

현재 승인 범위에서 `40276a51b2e08c77732317a856cc879cc23e1ef6`를 clean fast-forward로 배포했고 1,345개 소스 파일 hash가 일치했다. 기존 dashboard와 user broker만 재시작했다. 보존한 SDK 2.55.1 binding/native library, broker entry, 환경 및 Stereo/depth 설정을 바꾸지 않았다. 배포 receipt의 서비스 준비 완료 시각은 10:35:54Z다. SDK/Isaac 업그레이드, factory calibration/CameraInfo/운영 TF/base frame 변경이나 로봇 명령은 없었다.

사용자가 이번 각도 조절을 건너뛰어, 앉은 고정 자세·정지한 카메라에서 **같은 각도의 두 독립 세션**을 수집했다. 각도를 달리한 실험이나 정확한 0° 차이를 측정한 실험은 아니다.

| 실제 샘플 | 수집 시각 (UTC) | 세션 / generation | 유효 depth | IR1–depth skew |
| --- | --- | --- | ---: | ---: |
| `0f301ed2870243e5bb0a6bac68dc5b94` | 10:36:36.616828 | `b697a8eaa06b4e9ea88cb00285f33241` / 1 | 95.1712% | 0 ms |
| `c92c6700bc5a4125b9bf3d9408d5fe8e` | 10:37:03.575887 | `67b0f9f0172d42178dd3c01fffbd1617` / 2 | 95.2738% | 0 ms |

두 샘플 모두 로봇의 `/home/unitree/robot-scope-data/runtime/state/navigation/multi-slam/depth-samples/<sample_id>/`에 보존된다. 각각 307,200개의 raw depth→optical-Z(m)/null 대응, lossless PNG 원본 픽셀, ZIP 멤버 hash와 재조회 계약이 통과했다. `synthetic=false`이며 새 `capture_session_id`와 원래 timestamp를 보존했다. 원본 ZIP·compatibility JSON 내보내기는 통과했다.

`camera_info.json`은 실제 SDK intrinsics 관측에서 파생한 기록이다. ROS CameraInfo 토픽 전체 메시지나 R/P 행렬을 이번에 관측한 것으로 해석하지 않는다.

실제 배포된 Settings에서 GET 목록/가져오기, 원본 IR 표시, native 픽셀 좌표의 6개 점 선택까지 확인했다. 그러나 상대각 분석은 실제 데이터 품질 조건에서 차단됐다.

- 첫 점 `(300,85), (345,85), (390,85), (340,115), (365,140), (390,165)`는 분석 API에서 유효한 주변 depth가 1개뿐이라는 HTTP 422를 반환했다. 전체 영상의 높은 유효 depth 비율이 선택한 벽 주변의 품질을 보장하지 않는다.
- 같은 후보 부근에서 0–2.83 px 이내의 안정적인 depth 주변으로 옮긴 `(300,86), (343,85), (390,85), (340,114), (363,138), (391,164)`도 HTTP 422 `no reliable planar consensus`로 거부됐다. 분석 JSON export 역시 HTTP 422이며 Settings 내보내기 버튼은 비활성 상태다.
- 이 점 이동은 선택 주변의 품질 확인이며, 실제 같은 평면·기준점 인증이 아니다. 품질·동기화 임계값을 완화하거나 실패한 결과를 상대각으로 표시하지 않았다. **실제 상대각 및 분석 결과 JSON 내보내기는 미완료**다. 원본 수집 파일의 성공적인 내보내기와 구분한다.

이후 고정된 카메라로 기존 Stereo를 순차적으로 시작·중지했다. 세션 `8c083c88e3914bf78c804efd227e6b40`, generation 3은 10:42:02.302Z 시작, 10:42:09.730Z TRACKING, 세션 경과 60.546초에 중지 요청, 10:43:08.102Z 정리를 완료했다(약 65.81초). 이 관측은 기존 native VO, IMU=false, TF publish=false 경로의 순차 복귀 확인이다. 이번에 새 WebSocket/FPS/CPU 성능 측정이나 Depth+Stereo 동시 실행을 검증하지 않았다. 이전 창의 성능 수치를 이번 결과로 재사용하지 않는다.

최종 10:45:54.953551Z 확인에서 설치 소스는 clean `40276a5`, 세션 IDLE, camera reserved=false/unknown=false였다. root owner probe도 10:45:53.819Z에 실제 장치 free를 확인했고 bridge는 PID 0·inactive·disabled다. 환경/설정/broker entry/binding, 기존 지도·패키지·샘플은 그대로이며 새 depth 샘플 두 개만 추가됐다. 주행·자세·ARM·initialpose·goal 명령은 없었다.

새 private evidence는 같은 `mount-settings-20261017/` 아래의 `deployment-result.json`, `depth-repeat-1/`, `depth-repeat-2/`, `actual-depth-contract-report.json`, `actual-analysis-api-report.json`, `settings-actual-wall-quality-blocked.png`, `final-runtime.json`이다. 원본 센서 자료는 Git에 올리지 않는다.

다음 최소 작업은 사용자가 더 가깝고 가려지지 않은 질감 있는 같은 벽을 정하는 것이다. 로봇 위치 변경이 필요하면 사용자가 별도로 안전을 확인한 뒤 수행하며 자동 이동은 하지 않는다. 현재 정지·현장 대응 조건을 확인하고 **같은 각도의 반복 촬영에서 평면 품질을 먼저 통과**시킨 뒤, 카메라 pitch를 조절할 때마다 정지 확인을 새로 받아 여러 각도를 비교한다. 실제 각도 정답·독립 정확도·몸체 외부파라미터는 미확보이며 결과를 자동 적용하지 않는다.

## 검증 범위

오프라인 수학·API·UI 회귀, 설정 라우트 통합, 합성 입력·잘못된 데이터·새 입력 시 stale 결과 취소를 검증한다. 하드웨어 없는 브라우저 시험의 API fixture는 명시적으로 synthetic이며 실제 카메라 성능 근거가 아니다. 실제 장비 배포/캡처는 별도 현재 허용과 현장 확인 후 진행한다.

### 2026-10-17 로컬 통합 검증
- 신규 계산/API root 테스트 39개, API inventory/security 계약 8개 통과
- 기존 독립 시제품 테스트 30개 통과; canonical 계산 소스는 이전 공개본과 바이트 동일
- root JavaScript 전체 406개 통과(신규 설정 UI 13개 포함)
- 실제 HTTP router와 native 설정 DOM을 연결한 9개 검사 통과. canvas는 stub이므로 브라우저 픽셀 렌더링 검증은 아님
- 신규 Playwright synthetic 통합/반응형 시험 10개 작성 및 discovery 확인; 실제 실행은 해당 통합 커밋의 CI에서 확인
- JavaScript 85개 모듈 구문 검사 및 diff/compile 검사 통과
- root Python 전체 2205개 실행 중 기존 baseline과 동일한 24개 AF_UNIX PermissionError, 1개 skip. 새 오류 식별자는 없음. 로컬 전체 PASS로 표기하지 않음
- 이전 독립 시제품 커밋 98ef9e1의 GitHub CI는 두 Ubuntu/Python 환경에서 통과했지만, 그 결과를 이번 통합본의 CI 결과로 재사용하지 않음

### 동시 depth 캡처 변경과의 통합

- 게시 직전 원격 main에 78e23ce의 depth 수집 기능이 추가되어, app.py/index.html/API inventory의 겹치는 변경을 보존해 병합했다.
- depth capture router·frontend script와 테스트는 유지했다. 최종 inventory는 HTTP 173 / v1 172, GET 76 / POST 85 / PUT 1 / PATCH 6 / DELETE 5다.
- 기존 수집기의 compatibility export 소비자가 사용하는 `_validate_sample`을 실험 shim에서 그대로 재노출했다. 계산/검증 규칙은 변경하지 않았다.
- 수집 export→사용자 포인트 선택→보정 validator 계약 시험 1개, 계산/API 40개, 병합된 API 계약 9개, 원래 시제품 30개가 통과했다.
- 병합 후 root JavaScript 전체 428개가 통과했다.
- 실시간 수집 기능의 존재와 이 설정 패널의 파일 가져오기 방식은 별개다. 이 변경에서 센서 수집·서비스·운영 TF를 실행하거나 적용하지 않았다.
