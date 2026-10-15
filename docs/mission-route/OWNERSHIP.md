# MR / MS 소유권과 작업 창

기록 UTC: 2026-10-15T06:45:34.358571+00:00. checkout `/Users/hajoonpark/자율설계/robot-scope-ros2-dashboard`, 기존 `main`을 공유한다. MR source `22c7913c879afcca536a78d552dcdf98f0f53098`, 적용 전 origin/main `7747ef7`. 이 문서는 프로세스 잠금이 아니다.

사용자는 두 채팅에 직접 조율 메시지를 허용했다. MS 채팅은 `01a13df0-6b59-70b0-a4f8-8c82ea8ae269`이며 최종 상태 idle/read-only다. MS가 쓰기·전체 검사·Git 창을 반환한 뒤 MR만 순차 진행했다. 전체 fixture/test server 종료 후 source commit 완료, 현재 MR docs/Git 창이다.

| 소유자 | 파일/영역 | 처리 |
|---|---|---|
| MR 전용 | mission_routes/*, api/routers/mission_routes.py, static/features/mission_route/*, MR tests, docs/mission-route/* | MR 창에서 적용·검증 |
| MR 기존 미션 접점 | application/mission_coordinator.py, cockpit/mission_client.js·mission_page.js·panels/mission_panel.js, 관련 미션/E1 E2E | MS가 담당 유지 확인; 기존 owner 재사용 |
| MS 공유 통합 담당 | app.py, application/runtime.py, tests/test_api_contract_phase8.py, tests/test_application_workflow_wiring.py | MS 단독 통합 창에서 적용; MR source commit에 함께 포함하도록 명시 인계 |
| MS 전용 | SLAM modules/router/UI/tests, docs/multi-slam/*, camera/native map/feature lifecycle | MR 수정 없음 |
| 공유 미수락 | navigation/gateway/Nav2 config/CI/common CSS/index.html 등 | MR 임의 수정 없음, 요청 PROPOSED 유지 |
| 사용자/운영 데이터 | 지도·annotation 원본·bag·영상·runtime root·서비스 | MR 변경 없음 |

인계 순서: MS 쓰기 중 MR 저장소 밖 초안 → MS 반납 → MR whitelist 적용 → MR 중지 → MS shared source4+MS 문서 적용/검사 → MS 반납 → MR UI·전체 검사 → MS exact 게시 단독 창 → MS 반납 → MR 최종 UI 회귀·source commit·문서/Git. MS의 d866a3b/7747ef7 게시 및 CI는 MS 책임으로 완료됐으며 MR CI로 계산하지 않는다.

MR 최종 인계 시 source30개 staged whitelist·secrets/diff 검사를 마쳤다. MS docs는 MS의 7747ef7에 포함돼 MR commit에서 제외했다. 기존 untracked MR docs만 후속 커밋한다. 새 branch/worktree/PR, force push/reset, 타 작업 lock 삭제는 없었다.

장비/서비스/성능 자원 창 없음. 실제 native·실이동 NOT_RUN. 운영 서비스·카메라·SLAM에 MR이 가한 변경 없음. 다음 쓰기 창은 최종 Git 상태와 새 상호 인계 확인 뒤 열어야 한다.
