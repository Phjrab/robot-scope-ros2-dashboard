# A1 1차 결과 · 2026-11-05 KST

소스 dce1e88995e5, 장비 4ff0e47467f9. 아래 대표 검사의 PASS와 현장 완료를 따로 기록했다. 실장비 명령은 조회에 한정했다. A1 goal 전송 0회, 시험 버튼 0회, 주행 구간 0회. 위치 오차·정지 ACK·경사로 품질은 미측정이다.

| ID | 검증 | 대표 검증과 결과 | 현장 판정과 다음 조건 |
|---|---|---|---|
| D00 | 실행본·복구 | PASS · SOURCE / DEVICE_STATIONARY. 두 서비스 모두 4ff0e474. 실행 경로·모듈, 559개 파일, HTTP 자산 3개, bridge release 일치. 고정 후보 2,655개 Git blob 검증. | BLOCKED_OPERATOR. 조회 범위에서 배포·복구 rehearsal 미실행. |
| D01 | 초안·센서·geometry | PASS · UNIT / HTTP / BROWSER. 준비 입력 unit 25. Linux 준비 패널 37건 인수. 실제 map1→map1_2D 계보 및 P1/P2 주석 revision 일치. | INPUT_REQUIRED. 장비 선택 쌍 없음, OBSERVATION_INACTIVE. 현재 위치·방향과 정지 감독 확인 필요. |
| D02 | 관측 종료·Nav2·초기값·match | INHERITED · HTTP / BROWSER. Linux 전체 앱 8개 assertion. exact stop INACTIVE_CONFIRMED, 명시 POST 각 1회, goal POST 0. 준비 API MATCH_ARMED, 진단 GET OUTCOME_UNKNOWN. | BLOCKED_DEPENDENCY. 실제 세션·STOP receipt·release ACK·Nav2 시작·초기값 접수·별도 match 없음. |
| D03 | 지속 위치추정·TF·화면 | PASS · REAL_CORE / UNIT. 운영 코어 19, runtime binding 9, TF authority 12 통과. 보정 만료·세대 교체·기존 TF/odom 소비와 지연 결과를 검사했다. | BLOCKED_DEPENDENCY. 장비 Nav2 idle, 위치·TF 비활성. 현재/목표 화면 연속성 미측정. |
| D04 | P1·정지·dwell | PASS · UNIT. 명령 타이밍 23, 합성 route 36. 2초 미달 거부는 OPERATOR_TEST suite에서 확인. | BLOCKED_DEPENDENCY. P1 전송·결과·ZERO·matching ACK·도착 후 실측 정지·XY/yaw 미측정. |
| D05 | 시험 녹색·P2 | PASS · UNIT. OPERATOR_TEST 23건. 이른 클릭·중복·이전 token 거부/멱등, 정상 P1 release 뒤 다음 목표 1개. P2 도착 후 현재 계약의 별도 완료 확인은 goal 0개. | BLOCKED_DEPENDENCY. P1 실제 성공·정지/dwell 전. 버튼·실제 출발·P2 정지 미실행. |
| D06 | 경사로 연속성 | INHERITED · SOURCE / UNIT. 기존 수동 기록 3건 인수. staged runtime 8건은 초기 tilt·명시 초기화 등 소프트웨어 검사다. | BLOCKED_OPERATOR. 현재 운영 보정·pitch·점 분포·TF/scan/costmap의 상승/정상/하강 동시 구간 없음. |
| D07 | 장애물 입력·우회/정지 | PASS · UNIT. identity 호환 8 + binding 4. graph와 메시지별 출처 구분. C4 과거 native 62 callbacks, ingress 0, publish 0. D3 독립 baseline 5건. | BLOCKED_DEPENDENCY. 격리 native 재실행 환경 없음. 새 C4 costmap marking/clearing·path·actuator 미검증, 기존 경로 분리. |
| D08 | 종료·보존·복구 | PASS · DEVICE_STATIONARY. 읽기 두 시점, 지도 트리 133개·navigation 설정 4개 해시 일치. Nav2·goal idle, lease/deadman 해제, 명령 0. | NOT_RUN. 주행 후 정지·ACK, 실제 release rollback은 시험 전이므로 미실행. |

이번 macOS 전체 Python은 3,652개 실행, 실패 7·오류 192·skip 40으로 종료했다. 별도 handoff 포함 묶음 157개도 실패 5·오류 52였다. 이 결과를 그대로 보존했다. 전체 JS 750/750, syntax 133개를 확인했다. 동일 소스의 Ubuntu 22.04/24.04에서 각각 Python 3,685개(skip 35), 브라우저 333개, 미션 10개를 인수했다. 합성 ASGI 관측·Nav2 transport와 실제 ROS 동작을 별도로 집계한다. 로그 hash·조회 시각은 [JSON](ROUND1_RESULTS.json)에 있다. [기준 Linux CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41494400313) · [제품 CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41494400406)
