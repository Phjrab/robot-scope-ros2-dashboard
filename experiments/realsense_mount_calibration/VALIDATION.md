# 검증 기록 — 2026-10-17

## 이 시제품
- `python -m unittest discover -s tests -v`: **30개 통과**
- Python py_compile 및 `node --check static/app.js`: 통과
- `NODE_PATH=<jsdom 설치 경로>/node_modules node tests/ui_dom_smoke.cjs`: **통과**
  - 실제 loopback HTTP 서버의 health/static 제공
  - 처음에는 촬영 조건 미확인으로 계산 불가
  - UI 합성 데이터 → HTTP API → 결과 테이블
  - 기준 0°, 합성 +10°와 -8°를 각각 9.999446°, -8.000435°로 추정
  - 보기용 샘플 전환은 결과 유지, 점 수정·조건 해제는 결과 무효화
  - 양의 pitch 도식 방향, 재계산 후 JSON 내보내기
- 검토에서 발견한 coordinate frame_id 의미, 큰 숫자/Infinity 입력·export 오류, 포인트 개수 상한, 도식 부호, 늦게 끝나는 import 상태 덮어쓰기 문제 수정

위 수치는 합성 데이터의 소프트웨어 검증이다. 실제 RealSense 각도 오차 수치가 아니다.

## 검증하지 못한 범위
- 브라우저 실제 픽셀 렌더링/반응형 화면의 시각 검수: **미완료**. VM sandbox의 AF_UNIX 제한으로 로컬 Chromium 실행이 실패했고, cloud browser에서는 해당 loopback 서버에 접근할 수 없었다. DOM 시험은 canvas drawing을 stub 처리한 논리/HTTP 통합 검사이며 실제 렌더링 검사로 표시하지 않는다.
- 실제 카메라·depth 캡처·USB/IR FPS 영향·로봇 자세·몸체 기준 절대각·VSLAM/TF 연동: **미실행**
- 수동 사용자 확인은 센서로 검증한 정지/동기화 증거가 아니다.

## 기존 저장소 회귀
변경 전 baseline `c6fedc05e5086fa755cc92b1a2cf2daa56ffc41a`의 root Python 전체 검사는 2166개 실행, 24개 오류, 1개 skip이었다. 24개는 기존 slam_broker 시험의 AF_UNIX socket 생성이 VM sandbox에서 PermissionError로 거부된 환경 제약이었다. 전체 통과라고 주장하지 않는다.

기존 root JavaScript 단위시험은 **393개 통과**했다. 이 실험은 운영 모듈·카메라·TF·Nav2를 변경하지 않는다. GitHub의 실제 commit CI는 별도 결과로 확인한다. root 테스트가 별도 실험 폴더의 모든 테스트를 자동 수집한다고 가정하지 않는다.
