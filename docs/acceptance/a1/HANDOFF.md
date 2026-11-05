# A1 주행 인계

**현장 적용 · 2026-11-05 15:30 KST** · HTTPS·실지도 검토 연결을 고정판 `7092851dca9561ca240462eaefc8282f2f892b80`로 적용했다. 양 서비스 실행본·실제 Mac 브라우저의 정상 HTTPS·읽기/검토 로그인·사본 지도 2개 조회·기존 HTTP/WS·REPLAY·모바일 메뉴와 새로고침을 확인했다. MULTIMAP/REPLAY/USABILITY는 ON, SCENE/RUNTIME은 OFF다. A3 실험 준비·seed·goal은 실행하지 않았다.

첫 실지도 정합 1회는 `DISCONNECTED`로 종료했다. 유효 겹침은 양방향 0.0086667, inlier 13, 거리 p95 5.2533 m였다. 수락·리뷰 PCD 저장은 BLOCKED_DEPENDENCY이며 저장본은 0개다. 운영자는 확인된 상대 배치/대응점이 없다고 답했다. 품질 조건·정합 알고리즘을 바꾸거나 반복 계산하지 않았다.

마지막 15:52 KST 조회에서 SOFTWARE STOP 잠금 ON, lease 없음, 제어 명령 전축 0, nonzero/action 요청 0을 확인했다. 다만 본체 telemetry가 13.297초 오래되어 bridge ready=false였으므로 **현재 물리 정지는 확인되지 않았다**. 원본 지도 140파일·navigation 4파일·기타 설정 6파일과 검토 사본 해시는 동일했다. 활성 goal·선택 운영지도·정지 관측 세션은 없다. 이전 FAST-LIO 정지 관측 기록은 유지하며, 이번 검토 연결은 초기화·P1/P2·경사로 성공을 추가하지 않는다.

| 행 | 이번 회차 종료 판정 |
|---|---|
| D00 | DEVICE_STATIONARY PASS · 후속 고정판 적용·양 실행본/flags 확인. 후속 전환 중 `8c26c3f`→`dce1e889` 복구와 재적용 확인. |
| D01 | 센서·계보 읽기 PASS. 현재 장소가 지도와 달라 초안·geometry 적용 INPUT_REQUIRED. |
| D02 | exact-session 관측 종료·작업 정리 PASS. geometry-bound handoff·Nav2·INITIAL POSE·match BLOCKED_DEPENDENCY. |
| D03 | REAL_CORE/UNIT PASS. 실제 지속 보정·Nav2 TF 소비와 화면 연속성 BLOCKED_DEPENDENCY. |
| D04–05 | 시험 녹색 early/double/stale·한 번당 다음 goal 1개 소프트웨어 PASS. P1 실측 정지·dwell, P2 출발·종료 BLOCKED_DEPENDENCY. |
| D06 | 상승/정상/하강 운영 위치추정 BLOCKED_OPERATOR. |
| D07 | 실제 정지 센서 graph + 로컬 재생 PASS. 격리 C4 native·새 장애물 costmap/planner/actuator BLOCKED_DEPENDENCY. |
| D08 | 정지 세션 정리와 후속 배포 자산 보존 PASS. 지도 140파일·navigation 4파일·기타 설정 6파일 보존. SOFTWARE STOP 잠금 ON. 최종 본체 telemetry stale로 현재 물리 정지 UNKNOWN, 주행 후 측정 NOT_RUN. |

**다음 한 가지** · 보존한 `map1`/`map1_2D`의 실제 장소에서 현재 현장 범위와 X/Y/yaw 초안·정지 가정을 운영자가 확인한다. 현재 STOP 잠금의 해제는 다음 현장 절차에서 명시적으로 다룬다. 그다음 geometry → 정확한 관측 종료 → Nav2 → 명시 INITIAL POSE → 별도 match·지속 보정을 검증한다. 실제 이동 직전에 운영자·충전선 분리·배터리(20% 이하면 중단)·통로·회수/정지 수단·제어권·목표·횟수·시간을 새로 확인한다. 후속 main을 자동 배포하지 않는다.

[첫 결과표](ROUND1_RESULTS.md) · [후속 진단](POST_ROUND1_DIAGNOSIS.md) · [현장 관측·복구](FIELD_SESSION.md) · [A2 입력](A2_INPUT_HANDOFF.md) · [소스 고정](SOURCE_LOCK.json)

## 후속 여러 지도 검토 연결

사용자가 승인한 추가 범위는 직접 HTTPS·ReviewAccess·별도 사본 catalogue를 연결하고 실지도 2개 정합→후보 검토→리뷰 PCD 저장·재조회까지 확인하는 것이다. 두 지도는 동일 장소를 겹쳐 촬영한 실지도라고 운영자가 확인했다. 센서 수집 epoch와 최초 capture session은 확인되지 않아 null로 유지한다. REPLAY의 `source_epoch`는 원본 저장 파일 revision이며 센서 epoch라는 뜻이 아니다. frame은 보존된 map-family 선언, m 단위는 기존 mapping 산출 규약에 근거한다. 복사본은 자기 ID/revision을 사용하고 원본 ID/revision/내용 SHA를 acquisition에 따로 보존한다.

직접 HTTPS는 `ROBOT_SCOPE_HTTPS_HOST/PORT/CERTFILE/KEYFILE` 4개를 함께 설정할 때만 켜진다. 사설 주소를 명시하고 별도의 비특권 포트 및 해당 주소와 일치하는 `ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN`이 필요하다. HTTP와 HTTPS는 하나의 event loop와 앱 lifespan을 공유하며 forwarded 헤더를 신뢰하지 않는다. 공개 인터넷·프록시·인증서 경고 우회는 이번 범위에 없다. 현재 Mac에는 CA:FALSE인 서버 인증서 한 장을 SSL 용도로 신뢰 등록했다. SAN 주소 일치를 유지하며 다른 호스트 이름의 검증은 거부된다. 최초 호스트 policy-string 방식은 Chromium에서 인식되지 않아 같은 인증서의 SSL 신뢰 형식만 교정했다.

`ROBOT_SCOPE_EXPANSION_REVIEW_DB`는 사전에 발급한 700 폴더 안 600 SQLite 파일이다. `python -m robot_dashboard.expansion_integration.review_access <private-db> issue review --ttl 900`은 15분 일회용 검토 코드를 발급한다. `read`는 조회 전용이며 `revoke <grant-id>`로 회수한다. 코드·쿠키·DB·TLS 개인키는 공개 저장소에 넣지 않는다. 브라우저 로그인은 HTTPS 확장 페이지의 일회용 코드 입력란을 사용한다.

`ROBOT_SCOPE_EXPANSION_REVIEW_WORKSPACE`는 700 폴더 안 600 JSON이다. schema `robot-scope.review-workspace.v1`, `catalogue_root=<동일 폴더>/sources`, `bundle_root=<동일 폴더>/bundles`, map ID별 `metadata`를 명시한다. sources도 700이며 운영 catalogue·수정 권한·지도 활성화 callback을 연결하지 않는다. 전체 점 저장은 기존 C1 exporter를 사용한다. MULTIMAP/REPLAY/USABILITY만 켜고 SCENE/RUNTIME은 끈다.

이번 정지 배포는 `ROBOT_SCOPE_CONTROL_START_STOPPED=1`로 첫 제어 객체부터 STOP을 잠근다. 기본값은 기존과 같고 해제는 별도 명시 절차다. 새 TLS 구성 실패 시 같은 검증판에서 HTTPS와 MULTIMAP만 끄는 복구가 가능하다. STOP 시작 기능이 없는 과거판을 자동 재시작하지 않는다. 그보다 이른 실패에서는 두 서비스를 정지한 상태로 selector를 복원하고 결과를 보고한다. 배포·브라우저·정합 실패와 최초 시도는 FIELD_SESSION과 POST_ROUND1_DIAGNOSIS에 분리 기록했다. 로컬 비공개 인계에는 현재 Mac에서 15분 일회용 검토 코드를 발급하고 접속 페이지를 여는 도우미를 제공한다. 테스트 세션은 모두 종료·회수했으며 새 세션은 운영자가 도우미를 실행할 때 발급한다.

## A3 수동 2D 주행 격리 검증

`4cebeed`를 ROS 2 Humble 격리 환경에서 실행했다. 비영점 odom 시드·직선 목표·이동 중 취소·비용지도 장애물 우회·odom 중단 후 정지·새 작업의 명시 재시드를 확인했다. 이 SHA는 초기값 수락 직후 Nav2 활성화가 끝나기 전에 목표가 거부될 수 있다. 별도 승인된 A3 현장 시험에서 `bt_navigator`의 `active` 상태를 읽은 뒤 목표를 명시 전송한다. A3 실장비 검증 상태는 `DEVICE_NOT_RUN`이다. [A3 절차와 측정값](../a3/HANDOFF.md) · [격리 실행 결과](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41983696807)
