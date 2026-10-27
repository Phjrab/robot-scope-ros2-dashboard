# PR #3 통합·Jetson 배포·정지 관측 검증

검사일: 2026-10-26 KST. 공개 기록 추가일: 2026-10-27 KST.
이 문서는 10월 26일에 확인한 결과를 보존한다. 공개 기록 추가 작업에서
장비에 다시 접속하거나 서비스·코드 배포를 변경하지 않았다.

**코드 병합·장비 배포·이전 실행본 복구 시험은 완료했다. 실장비 인수 검증은
부분 성공이며, Stereo 입력과 최종 브라우저 재연결 문제는 미해결이다.**

이 문서와 [공개 검증 요약 JSON](MERGE_DEPLOY_VERIFY_20261026.json)은
로컬 원본 보고서 및 영수증에서 공개 가능한 결과만 옮겼다. private 환경 파일,
키, 전체 장비 백업, 생성 지도/PCD, 원본 실내 영상·캡처, 센서 원본 로그는
저장소에 포함하지 않는다. 로컬 증거 파일의 SHA-256은 JSON에 기록했다.

## Git에 반영된 코드

| 항목 | 값 |
| --- | --- |
| PR | [#3](https://github.com/Phjrab/robot-scope-ros2-dashboard/pull/3), MERGED |
| 충돌 해결 commit | `7777f471654d6da0afd3580a870d80b7b0b3eb4d` |
| GitHub 합성 병합 SHA | `fbc1550abff1d93b938ebb7ccc51a13092267341` |
| 최종 main / 배포 source SHA | `d6e3fe9675f31e436f5236b390e36e188934f473` |
| 검증 source tree | `4979cc43072a5e424fa8c8cfdf966a8206f7a3d4` |
| 합성 병합 CI | [40295719304](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40295719304), SUCCESS |
| main push CI | [40298136083](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40298136083), SUCCESS |

두 source tree는 일치한다. GitHub의 main merge는 2026-10-26 09:15:20 UTC에
완료됐고, 10월 27일 원격 조회에서도 해당 SHA와 CI 성공을 확인했다.
이후 추가하는 문서 commit과 실제 장비 source SHA는 구분한다.

실제 충돌은 다음 두 파일의 네 구간이었다. 나머지 교집합 열 개 경로는
이미 양쪽에 같은 내용이 있었다.

- `robot_dashboard/static/features/maps/live_observation.js`: source 변경과 reset
  시 오래된 proposal geometry/초기값을 지우는 helper 및 연결 상실 fence 보존.
- `tests/e2e/live_observation.spec.mjs`: IMU 제안 뒤 연결 단절 시 오래된 입력이
  지워지고 `AGENT_CONNECTION_LOST` 이유가 유지되는 회귀 시험 보존.

전체 파일을 일괄 ours/theirs로 선택하지 않았다. 전수 시험 중 발견한 기존
worker 정리 race는 `tests/test_stationary_relocalization.py`의 대기 helper에서
terminal 상태와 active job 해제를 함께 확인하도록 수정했다.
원래 C1 checkout과 장비의 dirty/untracked 파일은 덮어쓰지 않았다.

C1이 채택한 C2/C4/Dots 변경은 보존했다. 미완료 C3 Nav2 제어기, 실패 emitter,
실제 신호등 자동 출발을 활성화하지 않았다. C3의 기존 feasible1 실패와
missed-20Hz 경고 121건은 운영 성공 증거로 바꾸지 않았다.

## 소프트웨어 검사

| 검사 | 결과 |
| --- | --- |
| Python 전수 | 2,963건, 2,961 PASS / 선택 SVG·rosbags 의존성 2 SKIP |
| JavaScript unit | CI 각 환경 666 PASS |
| 브라우저 E2E | 198/198 PASS |
| 미션 실제 Python API fixture E2E | 10/10 PASS; 실제 로봇 시험과 구분 |
| Ruff / mypy / source secret scan / JS syntax | PASS |
| D0 별도 subtree / C3 offline | PASS; C3 offline 58건, native 재실행 아님 |
| 합성 병합 및 main CI | 각 3개 job 모두 SUCCESS |

초기 로컬 환경의 소켓 sandbox·Chromium 누락을 해결하고 재실행했다.
시험 실패와 수정 내역은 보존했으며 선택 의존성 skip을 기능 성공으로
해석하지 않았다. 10월 27일 공개 문서 추가 전 전체 Python 2,963건은 실패 없이 끝났다
(2,960 PASS / 3 SKIP). Node 경로 미설정으로 skip된 parity를 명시적 Node 경로로
다시 실행한 PCD codec 24건은 모두 통과했다. 남은 optional skip은 SVG·rosbags다.
JavaScript 72개 test file, 108개 모듈 구문, tracked-source secret scan, 공개 문서
링크/JSON/private 경로/공백 검사도 통과했다. 새 문서 commit CI는 별도 기록을 따른다.

## 실제 배포와 복구

기존 장비 checkout HEAD는 `d7807de8f15fb457942039bb90ab41cf68d384c6`였고,
dirty/untracked 소스와 혼합 static 실행 상태가 있었다. Git HEAD 하나로
실행본을 단정하지 않고 실제 PID/cwd/환경 파일·static/source hash를 조사했다.

새 release 이름은 `robot-scope-d6e3fe9675f3`다. 정확한 main source 2,116개
파일을 별도 읽기 전용 경로에 설치하고 모든 파일 hash를 검증했다. 기존 venv와
빌드된 ROS workspace를 연결했다. Docker image·JetPack·CUDA·ROS upgrade는 없었다.
기존 service unit/ExecStart는 그대로이며 launcher의 `ROBOT_SCOPE_DIR` 선택을
새 release로 바꿨다. 마지막에 읽는 control 환경 파일은 enabled=0으로 설정했다.

기존 소스와 Git 상태, 지도 28개 ID/revision, 미션 definitions/runs를 보존했다.
이번 조사에서 미션 definitions/runs는 각각 0개였다.

| 백업 | 크기 / 검증 |
| --- | --- |
| 기존 runtime 전체 archive | 3,235,809,280 bytes / 67,293개 항목 |
| Dashboard 정지 중 사용자 데이터 archive | 871,290,880 bytes / 4,356개 파일의 전후·archive hash 일치 |
| 기존 VSLAM 고정 이미지 archive | 13,772,803,584 bytes / OCI config·layer 97개 digest 검증 |
| 관측 service 및 기존 출력 | FAST-LIO 관측 시작 전 별도 보존 |
| PC의 HTTP 지도 export | 28/28 ZIP, 47,534,260 bytes, member hash·revision 검증 |

장비 백업은 기존 source/Git/venv/설정/workspace/VSLAM 설치 패키지와 지도·DB·
미션·dataset을 포함한다. 원본과 장비 내 백업은 같은 디스크에 있으며,
디스크 고장 대비 전체 외부 백업으로 간주하지 않는다. root 전용 camera owner
JSON 현행 원문은 권한상 읽지 못해 원래 설치 패키지 사본만 보존했다.
해당 root 파일은 이 작업에서 변경하지 않았다.

고정 이미지 ID는
`sha256:f9d47c621390b34544de684fea8d62c9bba82f834daa6696733277773f85fdb5`다.
이미지를 새로 load하여 실행하는 복구 시험은 하지 않았다.

실제 Dashboard 복구 시험은 새 PID 139489 → 원래 두 환경 파일 복원 및
기존 cwd/PID 141775 → 새 환경 파일 재적용 및 새 cwd/PID 142080 순서로 진행했다.
기존 app.js hash도 확인했다. 지도/DB를 일괄 복원·덮어쓰지 않았다. 결과는 PASS다.
이후 실패한 관측 세션 표시를 정리하는 진단 재시작으로 최종 PID는 171712가 됐다.
동일한 2,116개 source hash와 지도/미션 보존을 다시 확인했다.

## 정지 실장비 관측 결과

| 항목 | 판정 | 근거와 한계 |
| --- | --- | --- |
| 원시 LiDAR | PASS | 15.075초에 151메시지, frame당 64,000점, 최대 수신 gap 0.107초 |
| 변환 LiDAR | PASS | 같은 구간 150메시지, frame당 16,000점, 최대 gap 0.110초 |
| FAST-LIO 점군 | PASS(관측) | 75.20초 WS 357프레임, 111–114점, 최대 WS gap 0.454초 |
| 3D 위치·자세 | PASS(갱신) | 75.16초 WS 588프레임, 최대 age 0.129초, 최대 WS gap 0.299초, xyz/quaternion 갱신 |
| 궤적 | PARTIAL | trail/pose 입력 갱신 확인. 정지 조건이므로 이동 궤적 정확도 NOT_RUN |
| Go2 카메라 | PASS(초기 화면) | 실제 1280×720 영상 약 14.3FPS, decode FAIL 0 / DROP 0 관측 |
| 저장 지도 | PASS(읽기·표시·보존) | 28개 revision 보존, native 7개 목록, 24,895점 PCD 및 160×310 occupancy 표시 |
| 미션 UI | PASS(초기 읽기·편집 화면) | 실제 저장 지도/canvas, server connected, 실행 불가 이유 확인. 실제 저장/실행 NOT_RUN |
| Stereo 시작·영상·특징점 | FAIL | 실제 broker 시작 뒤 USB open 실패. 영상·현재/지도 특징점·trajectory 및 성공 세션 stop NOT_RUN |
| RGB 색 진단 UI | PASS(합성만) | 8/8 fixture, raw GREEN / canonical·stable UNKNOWN / DETECTION_ONLY 표시 |
| 실제 신호등 모델 성능 | INPUT_REQUIRED | 커스텀 모델·실제 연속 영상·실측 보정 미제공 |
| 최종 UI 재연결 | FAIL_UNRESOLVED | 재시작 뒤 앱 브라우저 reload/새 탭 모두 연결 끊김·0 POINTS 표시, 서버 API 입력은 정상 |
| 제어 상태 | PASS(관측 범위) | 65개 sample에 lease 없음/command 0; ROS cmd_vel publisher 0, planner/controller/bt_navigator 없음 |

FAST-LIO는 기존 관측 전용 service로 시작·종료했으며 TF는 관측 namespace로
분리됐다. 운영 TF/initialpose/지도 정합으로 적용하지 않았다. 시험 후에는
변환 LiDAR와 기존 Go2 odometry를 화면 입력으로 선택했다.

원시·변환 메시지의 시간 기준이 달라 source-to-browser 절대 지연은 UNKNOWN이다.
WS gap은 전체 ROS message gap과 다르다. 절대 위치 정확도·실측 extrinsic·저장
지도 정합은 검증하지 않았다. 원시 좌표나 공간 이미지로 공개 결과를 확대하지 않는다.

## 미해결 문제와 준비 상태

### Stereo USB 경로 불일치

실제 D435i는 USB `001/008`로 열거됐지만 기존 container·managed scope·root owner
probe는 `001/004`를 고정했다. 기존 부팅 로그에 이미 있던 불일치다. native
runtime은 GPU warmup 뒤 USB NO_DEVICE/전원 상태/serial 미발견으로 실패했다.

동일 이미지·보안 설정·카메라 범위를 유지해 장치 pin을 맞추는 복구 스크립트를
로컬과 장비 백업 경로에 준비했다. **실행 미완료, 일반 sudo 사용자 인증 대기**다.
실제 root 설정을 먼저 백업하고 기존 container를 보존하며 실패 시 원복하도록
작성했지만, 준비된 스크립트를 실행 완료 증거로 간주하지 않는다.
인증 후 Stereo 60–120초 영상/현재·지도 특징점/trajectory와 정상 stop을 재검증해야 한다.

### 시작 실패 뒤 빈 mapping 세션 잔류

자원 반환 후 IDLE 세션에 unsaved=true가 남아 ownership slam busy가 유지됐다.
UI stop은 비활성이고 API stop도 IDLE을 그대로 반환했다. 이번 실패 세션의
identity, cleanup 완료, operation/scratch/camera 무소유, 외부 broker 무소유,
owner free, 다른 busy/unknown 없음, 제어 비활성을 확인한 뒤 Dashboard만
재시작했다. 최종 active_session=null, ownership busy/unknown=[]를 확인했다.
근본 소스 수정은 미포함이므로 재발 가능성은 남는다.

### 재시작 후 브라우저 재연결

최종 앱 브라우저는 reload와 새 탭에서도 GENERIC ROS 2 / 직접 ROS 연결 끊김 /
0 POINTS를 표시했다. 같은 시각 state API는 agent_ready=true로 0.477–0.673초에
응답했고 점군·pose seq는 갱신됐다. 초기 정상 캡처와 최종 재연결 실패를 구분한다.

1초 state polling이 매 요청마다 generation을 증가시켜 늦은 응답을 버리는
구조는 조사 후보다. 실제 브라우저 요청별 타이밍이 없으므로 근본 원인으로
단정하지 않는다. 추가 수정·회귀 시험·실장비 재검증이 필요하며 USB 인증과 별개다.

### 입력과 승인 범위

- 미제공 학습모델·실제 RED→GREEN→RED 영상·실측 보정은 해당 기능만 INPUT_REQUIRED다.
- VIO IMU qualification, 절대 정확도, 전체 retained feature export는 미검증이다.
- Cockpit 별도 창은 앱 브라우저에서 노출되지 않아 본 화면으로 검사했다.
- 이동·ARM·Nav2 goal·자세 명령은 0회다. C3 제어기와 신호등 자동 출발은 운영 미채택이다.

## 로컬 인계 자료

전체 한국어 보고서, 복구 runbook, 배포/복구 receipt, source manifest,
software/device evidence ZIP, 초기 정상 화면과 최종 실패 화면은 작업 산출물에
보존했다. 전체 source tar는 main과 중복되고 private 의존성을 포함하지 않으므로
Git에 다시 넣지 않았다. 장비별 접속·복구 스크립트와 private 자료도 로컬에 유지한다.
공개 JSON의 artifact hash는 원본 대조용이며 원본 자료가 공개됐다는 뜻이 아니다.
