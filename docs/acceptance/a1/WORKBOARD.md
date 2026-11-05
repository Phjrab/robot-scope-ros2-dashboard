# A1 주행 검증 인수표 · 2026-11-05 KST

현장 조회·첫 대표 검사 전 고정한 시작표다. 기준 main은 dce1e88995e5989d63fab257ea55b8d7d2ab8e24다. A0를 대체하고 I0·C0의 병합 이력을 인수했다. A2는 별도 clone에서 제품 항목을 진행한다.

| ID | 검증 | 시작 시 확보한 근거 | 이번 현장 |
|---|---|---|---|
| D00 | 소스·실행본·지도·복구 | SOURCE PASS, 기준 CI 2개 SUCCESS, 두 통합 조상 확인 | NOT_RUN |
| D01 | 현재 초안·정지 센서·geometry | HTTP/BROWSER INHERITED, Linux 준비 패널 37건 | NOT_RUN |
| D02 | 정확한 관측 종료·handoff·Nav2·명시 INITIAL POSE·match | BROWSER INHERITED, Linux 전체 앱 8건 | NOT_RUN |
| D03 | 지속 보정·TF/odom·표시 | 합성 요청 수락까지 INHERITED | NOT_RUN |
| D04 | P1 결과·실측 정지·dwell | 기존 주행 기준 인수 | NOT_RUN |
| D05 | 시험용 녹색 1회·P2 주행과 종료 | 기존 미션 경로 인수 | NOT_RUN |
| D06 | 경사로 운영 위치추정 | 과거 수동 기록 INHERITED | NOT_RUN |
| D07 | C4 입력·costmap·planner·정지 | 격리 core INHERITED, native identity 미확정 | NOT_RUN |
| D08 | 종료·정지 근거·자산 보존·복구 | 기존 lifecycle 인수 | NOT_RUN |

새 현장 범위는 우선 읽기 전용이다. 실제 이동은 현재 정지/회수 수단, 현장 운영자, 충전선, 통로, 배터리, 제어권, 목표·횟수·시간을 확인한 뒤 진행한다. 모든 행의 첫 근거는 ROUND1_RESULTS에 남기고 이후 진단·수리를 구분한다.
