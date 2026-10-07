# 인수 기준 · UI 범위

`PASS`는 명시된 소프트웨어/fixture 범위의 판정이다. 실장비 항목은 [VALIDATION](VALIDATION.md)의 NEEDS_HARDWARE이며 합격으로 처리하지 않는다.

| 기준 | 판정 | 증거 |
|---|---|---|
| 센서 workspace 중심·통계 홈 대체 | PASS | 기본 Cockpit, 실제 after Observation, geometry scene 폭 ≥60% |
| Safety HUD/STOP·ownership/readiness 보존 | PASS | 기존 control/Cockpit E2E, 새 모든 route 단절·mock STOP 테스트 |
| 초기화/reload/preset 무제어 | PASS | ui_redesign preset/migration/capture의 forbidden mutation 0 assertion |
| layout·camera demand·singleton·renderer resize | PASS | Cockpit 21개, 신규 20회 preset·reconnect·cleanup·migration |
| Go2 off 격리 실행 | PASS | static-only loopback·외부 hostname 차단·fixture E2E |
| FIXTURE/REPLAY/STALE·map/ROS 의미 구분 | PASS | provenance unit·browser stale, 기존 revision/CAS/route validation 회귀 |
| checkout/지침/user changes/baseline 조사 | PASS | INVENTORY, BASELINE; 원본 HEAD clean |
| 모든 기존 기능 접근 경로 유지 | PASS | INVENTORY route 매핑; Advanced·dedicated·offline experiments 유지 |
| 실제 기존 앱 수정 | PASS | index/app/workspace·새 module/CSS·실제 Chromium screenshots |
| loading/empty/error/stale/disabled | PASS | 기존 상태 및 신규 disconnected/denied/mock STOP/긴 텍스트·fallback fixture |
| keyboard/focus/대비/모바일/확대 | PASS · 검사 범위 한정 | Chromium 320~1920 clipping, 5개 geometry viewport·token 대비; 전체 screen reader audit 미실행 |
| 테스트와 한계 구분 | PASS | VALIDATION: 기존 Python error 1·skip 1 별도 기록 |
| 실제 before/after 직접 확인·manifest | PASS | 28 PNG, 29행 CSV, 동일 fixture, 실제 view_image 확인 |
| 데이터/secret/운영 프로세스 보호 | PASS | synthetic only, static server, 지정 경로 diff/stage 검토 |
| 소스/테스트/문서·rollback/handoff·로컬 커밋 범위 | PASS | FINAL_REPORT, ROLLBACK, HANDOFF, feature branch의 UI 변경 커밋 |
| 원격 publication/배포 | NOT_RUN · 요청 범위 준수 | push/PR/merge/release/deploy 실행 없음 |
