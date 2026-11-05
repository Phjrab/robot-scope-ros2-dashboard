# A1 주행 인계

마지막 현장 검증은 2026-11-05 14:02 KST다. 대시보드와 브리지의 고정 실행판은 `8c26c3f588f9f7f48e6325f5b5601c5e33d524f3`이며 REPLAY·USABILITY만 ON이다. 실제 메뉴·모바일 진입·로컬 합성 기록 재생/비교와 SOFTWARE STOP 1회를 확인했다. STOP 잠금은 ON, 제어권 없음, 명령·관측 속도 0, 배터리 63%로 종료했다. 센서 시작·초기 위치·goal·주행은 이번 후속 배포에서 각각 0회다.

앞선 `dce1e889` 정지 관측 1회에서 FAST-LIO pose/점군 갱신과 세션 종료를 확인한 기록은 유지한다. 새 배포가 지도 기반 초기화·P1/P2·경사로 검증을 추가하지는 않는다. MULTIMAP·SCENE·RUNTIME은 OFF이며 HTTPS·검토 입력 연결은 별도다.

| 행 | 이번 회차 종료 판정 |
|---|---|
| D00 | DEVICE_STATIONARY PASS · 후속 고정판 적용·양 실행본/flags 확인. 후속 전환 중 `8c26c3f`→`dce1e889` 복구와 재적용 확인. |
| D01 | 센서·계보 읽기 PASS. 현재 장소가 지도와 달라 초안·geometry 적용 INPUT_REQUIRED. |
| D02 | exact-session 관측 종료·작업 정리 PASS. geometry-bound handoff·Nav2·INITIAL POSE·match BLOCKED_DEPENDENCY. |
| D03 | REAL_CORE/UNIT PASS. 실제 지속 보정·Nav2 TF 소비와 화면 연속성 BLOCKED_DEPENDENCY. |
| D04–05 | 시험 녹색 early/double/stale·한 번당 다음 goal 1개 소프트웨어 PASS. P1 실측 정지·dwell, P2 출발·종료 BLOCKED_DEPENDENCY. |
| D06 | 상승/정상/하강 운영 위치추정 BLOCKED_OPERATOR. |
| D07 | 실제 정지 센서 graph + 로컬 재생 PASS. 격리 C4 native·새 장애물 costmap/planner/actuator BLOCKED_DEPENDENCY. |
| D08 | 정지 세션 정리와 후속 배포 자산 보존 PASS. 지도 140파일·navigation 4파일·기타 설정 6파일 보존. SOFTWARE STOP 잠금 ON. 주행 후 측정 NOT_RUN. |

**다음 한 가지** · 보존한 `map1`/`map1_2D`의 실제 장소에서 현재 현장 범위와 X/Y/yaw 초안·정지 가정을 운영자가 확인한다. 현재 STOP 잠금의 해제는 다음 현장 절차에서 명시적으로 다룬다. 그다음 geometry → 정확한 관측 종료 → Nav2 → 명시 INITIAL POSE → 별도 match·지속 보정을 검증한다. 실제 이동 직전에 운영자·충전선 분리·배터리(20% 이하면 중단)·통로·회수/정지 수단·제어권·목표·횟수·시간을 새로 확인한다. 후속 main을 자동 배포하지 않는다.

[첫 결과표](ROUND1_RESULTS.md) · [후속 진단](POST_ROUND1_DIAGNOSIS.md) · [현장 관측·복구](FIELD_SESSION.md) · [A2 입력](A2_INPUT_HANDOFF.md) · [소스 고정](SOURCE_LOCK.json)
