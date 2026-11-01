# 콘 표시 후속 인계

팀원 validator·콘 외형·scenario·거부/표시 검증을 C1/C3에 선별 통합했다. 결과는 **독립 합성 공간의 관측 표시**다. 장애물 회피, 실제 cone node, 교정, Nav2/costmap/제어 연결 완료가 아니다. 기존 I0 완료는 [CHECKPOINT.json](CHECKPOINT.json), 채택표는 [INTAKE.md](INTAKE.md), 경계는 [CONTRACT_AND_RENDERING.md](CONTRACT_AND_RENDERING.md), 결과는 [VALIDATION.md](VALIDATION.md)와 [RESULTS.json](RESULTS.json)에 있다.

실제 화면은 기존 `/extensions` → **관측 진단 · ADVISORY** → **CONES · 합성 평면 표시**다. 모든 운영 확장 flag는 기본 OFF이고 CONES도 기본 OFF다. 실제 owner 없는 운영 API는 여전히401 BLOCKED_AUTH다.

저장소 root에서 기존 requirements가 설치된 Python으로 아래를 실행하면 실장비 없이 계속 확인할 수 있다.

```bash
python -m experiments.expansion_20261101.cone_display.demo --port 4192
```

브라우저에서 `http://127.0.0.1:4192/`를 연다. 루트는 이 합성 프로세스 전용 session cookie를 발급하고 `/extensions`로 이동한다. CONES를 켜면 committed scenario의 cone5개가 기존 renderer에 표시된다. viewport와 상태행의 SIMULATED/FLAT_DEMO_ONLY/HEIGHT_UNVERIFIED를 확인한다. 생산자/pose/joints/coverage는 실측값이 없으므로 UNKNOWN이다. 이 CLI는 production app, C0 checkout, ROS 환경을 사용하지 않는다. 기존 실행 중인 서비스와 포트가 겹치면 다른 미사용 loopback 포트를 명시한다.

표시를 끄면 cone glyph를 숨기며 별도 poller는 없다. 탭 전환/닫기는 현재 request와 UI handle을 정리한다. 독립 CLI를 Ctrl+C로 종료하면 synthetic task가 cancel/await된다. 운영 flag를 켜거나 기존 서비스를 재시작할 필요가 없다. scenario/map/원본 파일을 변경하거나 삭제하지 않는다.

제거 가능 부분은 cone_input.py/cone_demo.py, 실험용 demo CLI, C3 cone_display.js·draw/index의 선택 스타일 hook, 관련 tests다. C1 원자적 stamp 방어·TTL/no-store, transport timeout/lifecycle 보완은 일반 관측에도 적용되는 보호이므로 단순 삭제 시 회귀가 필요하다. 기존 대시보드 app.py/app.js/scene3d.js/shared backend의 후속 diff는0이다.

추후 C0 결합: 최신 C0의 source/map revision/generation/session owner와 운영 인증 포트를 먼저 고정하고 수동 이식한다. frame 이름만 같다고 허용하지 않는다. 실제 cone node 원문과 측정 base/center XYZ·자세·sensor-to-map transform·3D ground 근거가 확보될 때 새로운 검토된 입력 adapter를 작성한다. detector confidence와 track ID epoch, clock/receipt/TTL, 모델 전체 hash/교정, latency·Jetson 부하를 별도 검증한다. 실제 marking/clearing/planner/actuator와 충돌 보호 검증은 이번 표시 인수와 별도다.

DEVICE_NOT_RUN: 로봇 접속·배포·Nav2/costmap/TF/control 연결·주행 모두0. main과 C0의 브랜치/checkout/실행 환경은 변경하지 않았다.
