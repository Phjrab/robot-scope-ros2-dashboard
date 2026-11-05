# A1 주행 인계

**추가 준비 · 아직 미적용** · HTTPS·실지도 검토 연결을 `7092851dca9561ca240462eaefc8282f2f892b80`로 게시하고 별도 장비 release를 준비했다. 원본과 동일한 실지도 사본 2개·검토 저장소·Mac 인증서 신뢰 설정을 준비했지만, 전환 전에 운영자가 장비 연결 불가를 알렸다. selector 변경·서비스 재시작·실제 정합·수락·저장은 아직 하지 않았다. 마지막 확인 실행판은 아래 `8c26c3f`이며 현재 장비 상태는 재조회 전 UNKNOWN이다. 재연결 후 정지·배터리·소유권·보호 해시를 먼저 읽고, 완료된 고정 후보의 두 CI 성공 영수증을 대조한 뒤 승인된 비이동 범위만 이어간다.

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

## 후속 여러 지도 검토 연결 준비

사용자가 승인한 추가 범위는 직접 HTTPS·ReviewAccess·별도 사본 catalogue를 연결하고 실지도 2개 정합→후보 검토→리뷰 PCD 저장·재조회까지 확인하는 것이다. 두 지도는 동일 장소를 겹쳐 촬영한 실지도라고 운영자가 확인했다. 센서 수집 epoch와 최초 capture session은 확인되지 않아 null로 유지한다. REPLAY의 `source_epoch`는 원본 저장 파일 revision이며 센서 epoch라는 뜻이 아니다. frame은 보존된 map-family 선언, m 단위는 기존 mapping 산출 규약에 근거한다. 복사본은 자기 ID/revision을 사용하고 원본 ID/revision/내용 SHA를 acquisition에 따로 보존한다.

직접 HTTPS는 `ROBOT_SCOPE_HTTPS_HOST/PORT/CERTFILE/KEYFILE` 4개를 함께 설정할 때만 켜진다. 사설 주소를 명시하고 별도의 비특권 포트 및 해당 주소와 일치하는 `ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN`이 필요하다. HTTP와 HTTPS는 하나의 event loop와 앱 lifespan을 공유하며 forwarded 헤더를 신뢰하지 않는다. 공개 인터넷·프록시·인증서 경고 우회는 이번 범위에 없다. 현재 Mac에는 서버 인증서 한 장을 해당 호스트의 SSL 용도로 신뢰 등록한다.

`ROBOT_SCOPE_EXPANSION_REVIEW_DB`는 사전에 발급한 700 폴더 안 600 SQLite 파일이다. `python -m robot_dashboard.expansion_integration.review_access <private-db> issue review --ttl 900`은 15분 일회용 검토 코드를 발급한다. `read`는 조회 전용이며 `revoke <grant-id>`로 회수한다. 코드·쿠키·DB·TLS 개인키는 공개 저장소에 넣지 않는다. 브라우저 로그인은 HTTPS 확장 페이지의 일회용 코드 입력란을 사용한다.

`ROBOT_SCOPE_EXPANSION_REVIEW_WORKSPACE`는 700 폴더 안 600 JSON이다. schema `robot-scope.review-workspace.v1`, `catalogue_root=<동일 폴더>/sources`, `bundle_root=<동일 폴더>/bundles`, map ID별 `metadata`를 명시한다. sources도 700이며 운영 catalogue·수정 권한·지도 활성화 callback을 연결하지 않는다. 전체 점 저장은 기존 C1 exporter를 사용한다. MULTIMAP/REPLAY/USABILITY만 켜고 SCENE/RUNTIME은 끈다.

이번 정지 배포는 `ROBOT_SCOPE_CONTROL_START_STOPPED=1`로 첫 제어 객체부터 STOP을 잠근다. 기본값은 기존과 같고 해제는 별도 명시 절차다. 새 TLS 구성 실패 시 같은 검증판에서 HTTPS와 MULTIMAP만 끄는 복구가 가능하다. STOP 시작 기능이 없는 과거판을 자동 재시작하지 않는다. 그보다 이른 실패에서는 두 서비스를 정지한 상태로 selector를 복원하고 결과를 보고한다. 배포 성공 여부와 실지도 정합 결과는 실행 후 FIELD_SESSION에 별도로 기록한다.

## A3 수동 2D 주행 격리 검증

`4cebeed`를 ROS 2 Humble 격리 환경에서 실행했다. 비영점 odom 시드·직선 목표·이동 중 취소·비용지도 장애물 우회·odom 중단 후 정지·새 작업의 명시 재시드를 확인했다. 이 SHA는 초기값 수락 직후 Nav2 활성화가 끝나기 전에 목표가 거부될 수 있다. 별도 승인된 A3 현장 시험에서 `bt_navigator`의 `active` 상태를 읽은 뒤 목표를 명시 전송한다. A3 실장비 검증 상태는 `DEVICE_NOT_RUN`이다. [A3 절차와 측정값](../a3/HANDOFF.md) · [격리 실행 결과](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41983696807)
