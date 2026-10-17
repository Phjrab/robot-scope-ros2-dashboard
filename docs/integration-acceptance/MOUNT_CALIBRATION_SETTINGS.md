# 카메라 장착 각도 보정: 설정 화면 통합

## 목적

기존 대시보드의 **설정 → 카메라 장착 각도 보정**에서, 앉은 자세로 정지한 Go2에 장착된 RealSense의 각도별 깊이 샘플을 불러오고 같은 전방 벽의 여러 점을 선택해 기준 샘플 대비 상대 pitch를 비교한다.

독립 시제품 `experiments/realsense_mount_calibration`의 계산 코드를 재사용한다. 이 기능의 통합은 실장비 depth 수집, 몸체 기준 절대각 인증, 운영 TF 변경을 의미하지 않는다.

## UI와 API

- 기존 설정 카드/폰트/테마/반응형 규칙을 사용하는 기본 설정 화면의 패널
- 실제 데이터는 import 방식이며, 합성 데모는 사용자가 명시적으로 선택한 경우에만 로드
- 사용자 확인 조건은 기본 체크 해제: 로봇 정지·같은 벽·pitch만 변경
- 원본 depth 샘플, 선택점, 기준 샘플, 적합 잔차와 상대각 결과를 함께 확인
- 계산 결과는 JSON 파일로 내보내며 실행 중 장착 변환이나 센서 보정값에 쓰지 않음

API:
- GET `/api/v1/settings/mount-calibration/status`
- POST `/api/v1/settings/mount-calibration/estimate`
- POST `/api/v1/settings/mount-calibration/export`

POST는 기존 same-origin 보호를 사용한다. 요청 크기와 JSON 유한값·프로필·좌표계·평면 품질 검증을 유지한다. 결과는 `RELATIVE_ONLY`, `body_extrinsic_validated=false`다. 사용자 checkbox는 독립 센서 검증이 아니다.

## 다른 Codex의 depth 캡처 작업과의 경계

이 설정 패널은 이미 측정된 깊이 JSON을 받는다. 기존 카메라 owner/broker/session을 이용한 실시간 캡처는 별도 작업에서 연결해야 한다. 카메라 모델·profile·영상과 depth 좌표 정합·source timestamp는 실제 캡처에서 검증해야 한다.

- 같은 픽셀 인덱스의 RGB/IR/depth를 무조건 같은 공간점으로 취급하지 않는다.
- 좌표 프레임 이름인 `frame_id`와 노출 식별자인 `frame_number`는 다르다.
- rectified pinhole 좌표의 optical-Z(m)만 현재 계산 경로에 넣는다.
- 기존 stereo VSLAM의 버전 업그레이드나 RGB-D 전환은 필요하지 않다.
- live capture가 없는데 연결됨/보정 완료/적용됨으로 표시하지 않는다.
- 별도 UI를 다시 만들지 말고 이 설정 패널과 계약에 맞춰 캡처 결과를 연결한다.

## 안전 및 해석

앉은 로봇의 몸통이 수평이라는 보장은 없다. 상대 영점과 몸체 기준 절대각을 구분한다. pitch-only 벽 관측으로 translation·전체 6DoF를 복원하지 않는다. 고정 높이 가정과 브래킷 pivot에 따른 광학 중심 이동도 구분한다.

지도 중복 벽, 회전 시 궤적 점프는 별도 native pose/좌표 변환/시간 정합 진단이 필요하다. 이 기능을 추가했다고 해당 문제를 해결했다고 표시하지 않는다.

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
