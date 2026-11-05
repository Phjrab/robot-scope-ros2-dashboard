# A1 주행 인계

고정 후보 `dce1e88995e5989d63fab257ea55b8d7d2ab8e24`를 현재 대시보드와 브리지에 배포했다. 정지 관측 1회에서 실제 FAST-LIO pose/점군 갱신, 같은 세션의 종료와 브리지 유휴 복귀를 확인했다. 초기 위치·goal 전송과 주행은 0회다.

| 행 | 이번 회차 종료 판정 |
|---|---|
| D00 | DEVICE_STATIONARY PASS · 기존판 복구와 고정판 적용 검증. 전체 post-switch rollback은 NOT_RUN. |
| D01 | 센서·계보 읽기 PASS. 현재 장소가 지도와 달라 초안·geometry 적용 INPUT_REQUIRED. |
| D02 | exact-session 관측 종료·작업 정리 PASS. geometry-bound handoff·Nav2·INITIAL POSE·match BLOCKED_DEPENDENCY. |
| D03 | REAL_CORE/UNIT PASS. 실제 지속 보정·Nav2 TF 소비와 화면 연속성 BLOCKED_DEPENDENCY. |
| D04–05 | 시험 녹색 early/double/stale·한 번당 다음 goal 1개 소프트웨어 PASS. P1 실측 정지·dwell, P2 출발·종료 BLOCKED_DEPENDENCY. |
| D06 | 상승/정상/하강 운영 위치추정 BLOCKED_OPERATOR. |
| D07 | 실제 정지 센서 graph + 로컬 재생 PASS. 격리 C4 native·새 장애물 costmap/planner/actuator BLOCKED_DEPENDENCY. |
| D08 | 해당 정지 세션 정리·보호 해시·유휴 상태 PASS. 주행 후 측정과 전체 역전환 NOT_RUN. |

**다음 한 가지** · 보존한 `map1`/`map1_2D`의 실제 장소에 돌아오면, 같은 고정판에서 현재 위치 X/Y/yaw 초안과 정지 가정을 운영자가 확인한다. 그다음 geometry → 정확한 관측 종료 → Nav2 → 명시 INITIAL POSE → 별도 match·지속 보정을 검증한다. 실제 이동 직전에 운영자·충전선 분리·배터리(20% 이하면 중단)·통로·회수/정지 수단·제어권·목표·횟수·시간을 새로 확인한다.

[첫 결과표](ROUND1_RESULTS.md) · [후속 진단](POST_ROUND1_DIAGNOSIS.md) · [현장 관측·복구](FIELD_SESSION.md) · [A2 입력](A2_INPUT_HANDOFF.md) · [소스 고정](SOURCE_LOCK.json)
