# Robot Scope — 포트폴리오 근거·화면 계획 (2026-09-24)

기준 소스: `main` `d81c59e726e26e0e4bc33d288a33a389b1565a81`.
이 문서는 저장소 코드와 기존 기록을 읽은 결과입니다. 이번 작업에서 로봇,
Jetson, ROS, Nav2, Mission을 실행하거나 실장비를 재검증하지 않았습니다.

## 작품 설명

Robot Scope는 ROS 2 로봇의 카메라·센서·점군·저장 지도·수동 제어·경로 계획을
한 웹 작업창으로 묶습니다. 현장 운영자는 Cockpit에서 상태를 관찰하고 지도를
관리하며, 지도 기반 경로 또는 도식 수동 안내를 작성할 수 있습니다. 별도
Go2 command bridge와 lease/deadman/watchdog은 제어 경계를 좁힙니다. 테스트,
정지 관찰, 실제 목표 도달은 서로 다른 결과이므로 자율주행 완주를 현재 결과로
주장하지 않습니다.

| 영역 | 코드·기록 근거 | 완료 범위와 제한 |
|---|---|---|
| 센서/Cockpit | [Cockpit acceptance](COCKPIT_ACCEPTANCE.md), [camera persistence](COCKPIT_CAMERA_PERSISTENCE_20260913.md) | 화면·패널 구현과 시점별 관측; 모든 현장 조합 검증 아님 |
| 지도·경로 | [Architecture](ARCHITECTURE.md), [E1 공간 편집](TRACK_E1_SPATIAL_EDITOR.md) | 지도 저장/편집과 경로 작성·검사; 공간 경로 Mission export 미구현 |
| 도식 안내 | [도식 acceptance](COMPETITION_SCHEMATIC_ACCEPTANCE.md) | DEMO/FIELD 수동 구간·픽업·배달 기록; 운영자 마커는 ROS pose 아님 |
| 음식 보드 | [식당별 생산](FOOD_PRODUCTION_20260912.md), [`orders.py`](../robot_dashboard/route_planner/orders.py) | 최대 8장 주문서, 장당 최대 5 line, 식당별 20초 추정; 적재 5개와 별개 |
| Nav2 | [정지 관찰](NAV2_STATIONARY_20260911_FOLLOWUP.md), [goal 취소](NAV2_COMMAND_TIMEOUT_20260912.md), [replay](NAV2_OFFLINE_TIMING_REPLAY_20260912.md) | 정지 관찰 READY와 합성 300 ms 계약; 실제 goal 도달 미입증 |
| Perception | [shadow runtime](PERCEPTION_SHADOW_RUNTIME.md), [result integration](PERCEPTION_RESULT_INTEGRATION.md) | 수집·입력/출력·표시 경계; 승인 모델 artifact와 현장 성능 근거 부재 |

## 구별해야 할 시간·단위

- 2026-09-08~09 odometry callback arrival gap의 `0.25 s` gate 실패와
  2026-09-11 정지 상태 두 번의 180초 관찰은 다른 시점입니다. 후자의 READY는
  formal C4 경로나 목표 성공을 뜻하지 않습니다. 이전 goal의 `0.305144 s`
  실패와 cleanup 후속도 남습니다.
- 2026-09-12 goal의 `command_timeout` 취소 때 비영점 bridge publication이
  보고됐지만 이동 거리나 도착을 증명하지 않습니다. `0.30 s` Nav2 입력
  freshness는 합성 replay로 확인됐고 이전 live 지연 원인을 확정하지 않습니다.
- Go2 프로필 상한 `1.0 m/s`와 `default_speed_scale=0.35`는 설정값입니다.
  수동 입력 200 ms, bridge receive watchdog 200 ms, Nav2 input 300 ms,
  C4 odometry arrival 250 ms는 각각 다른 계약입니다.
- 도식 상대 비용은 m/s나 ETA가 아니고, 신호가 UNKNOWN이면 임의로 안전 판정을
  만들지 않습니다. `SAVED_OCCUPANCY`의 좌표/검사와 도식 DEMO/FIELD는 별개입니다.

## AI의 역할과 개인 기여

제품 내부에는 데이터셋 수집, perception 결과의 제한된 수신·표시, shadow
runtime과 replay가 있습니다. 승인된 Lane/Object 모델과 target engine이 없으므로
실제 YOLO/UFLD 현장 FPS·정확도·성공률은 제시하지 않습니다. Route Planner의
Dijkstra, 규칙 기반 advisory, 생산 시간 추정은 학습 AI 추론이 아닙니다.

저장소의 [AI team handoff](ROUTE_PLANNER_AI_TEAM_HANDOFF.md), 설계/acceptance 문서와
커밋은 AI 보조 개발의 검토 지점을 보여 줄 수 있으나, 특정 모델 사용이나 개인별
작성 비율을 증명하지 않습니다. 지원서 1인칭 문장을 위해 사용자가 정한 제약,
AI에 맡긴 구체적 작업, 본인이 검토·수정한 테스트/현장 판단, 공동 작업 범위를
당시 기록과 연결해야 합니다.

| 사례 후보 | 확인할 판단·증거 |
|---|---|
| Nav2 지연 진단 | 250 ms odometry gate와 300 ms command freshness를 분리한 이유, 현장 로그·replay, 본인 판단 |
| 도식 수동 안내 | pose 없는 경로와 ROS 경로를 분리한 요구·검증, 실제 기여 담당 |
| 식당별 생산 | 순차 추정에서 식당별 병렬 추정으로 바꾼 규칙, 사용자 확인·테스트 담당 |

## 공개 화면 촬영 목록

공개 가능한 제품 캡처는 아직 이 저장소에 연결되지 않았습니다. 아래 화면을
촬영할 때 원본 날짜/commit, 실제 장비·기록·fixture 분류를 함께 적습니다.
사설 IP, 사람·번호판, 비공개 지도/도식/모델 자료는 공개 사본에서 제외합니다.

| 화면 | 보여 줄 내용 | 캡션 필수 표기 |
|---|---|---|
| Cockpit | 카메라·지도·상태의 통합 | 실제/fixture telemetry와 접속 범위 |
| Route Planner 또는 E1 | 수동 안내 또는 지도 위 경로 작성 | 실행·도착 성공 증거가 아님 |
| Saved Maps | 2D/3D 지도 관리 | 지도 공개 권한, 기록/fixture 구분 |
| diagnostics/replay | 실패 관측과 검증 과정 | 합성 여부, 시점, 성공/실패 결과 |

로컬 Playwright와 `node_modules`가 없는 현재 환경에서는 신규 캡처를 만들지
않았습니다. 기존 `tests/e2e/spatial_editor.spec.mjs`는 격리된 fixture 화면을
`spatial-editor.png`로 출력하도록 되어 있습니다. 실행 전 의존성 설치와
공개 자산 권한을 확인해야 하며, 그 그림은 `UI 데모 / fixture 데이터 / 성능
증거 아님`으로 표기해야 합니다.

GitHub About 후보: `ROS 2 dashboard for robot telemetry, mapping, safe control, and route authoring`.
Topics 후보: `ros2`, `robotics`, `dashboard`, `mapping`, `nav2`, `fastapi`.
원격 메타데이터는 변경하지 않았습니다.
