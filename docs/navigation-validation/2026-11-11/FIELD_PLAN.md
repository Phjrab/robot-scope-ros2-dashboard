# 후보와 현장 검증·복구 계획 — 2026-11-11

이 문서는 실행 순서이며 현재 장비가 정지했거나 특정 단계에 있다는 증거가 아니다.
현재 세션의 승인 범위는 저장소 수정·오프라인 검증·문서화·main 커밋/push다.
장비 접속 경로/현재 실행본과 배포·서비스 전환·관측·INITIAL POSE·이동의 현재 승인은 확인되지 않았다. 장비 명령은 실행하지 않았다.

## 후보 릴리스 준비

- 후보 내용: preparation refresh 직렬화와 관측 시작 UI/handler 차단, 정확한 관측 종료 후 조회. 서버 admission과 ROS/control 동작은 변경 없음.
- 원격 exact 후보 commit, CI, source archive hash는 [HANDOFF.md](HANDOFF.md)의 게시 영수증을 사용한다. 가변 main을 배포 대상으로 사용하지 않는다.
- `git archive --format=tar <candidate-sha>`로 tracked source 후보를 생성·목록/hash 검증한다. 이는 소스 후보이며 Jetson venv/native 라이브러리 호환성·장비 배포 완료는 아니다.
- 진행률 위험은 미해결이다. 이 후보를 주행 완료판으로 표시하지 않는다. baseline/timeout 변경은 없다.
- 지도·PCD·rosbag·인증/환경파일은 공개 Git과 소스 후보에 새로 포함하지 않는다. 실제 장비 보호 자료는 장비의 비공개 저장소에서 hash만 대조한다.

## A. 첫 작업: 현재 실행본을 읽기 전용으로 인수

현재 접속 주소/인증 경로가 제공되면 다음을 읽는다. 비밀번호/키를 채팅이나 Git에 복사하지 않는다.

1. dashboard/bridge의 systemd unit, PID, `/proc/<pid>/cwd`와 모듈 경로, selector/release 경로 및 실제 import 파일 hash. bridge의 서명된 release readback과 HTTP 정적 자산 hash를 대조한다. Git HEAD 하나로 실제 실행본을 대체하지 않는다.
2. `GET /api/v1/navigation`, `/api/v1/control`, `/api/v1/system/ownership-readback`, `/api/v1/observations/fastlio`, `/api/v1/navigation/operational-3d/preparation-inputs`, `/api/v1/navigation/parameters`, `/api/v1/navigation/presets`를 읽는다. 읽기 API가 작업을 시작하지 않는 현재 코드를 먼저 확인한다.
3. 실제 mode/profile/source·pipeline job·goal·STOP·lease·watchdog·bridge capability/신선도·배터리·관측 invocation을 기록한다. busy/unknown이면 이전 시험의 idle로 덮지 않는다.
4. 사용 중인 2D/3D 지도 ID/revision, calibration hash, 저장/생성/live parameter revision을 고정한다. 보호 대상 지도/교정/프리셋/selector/환경/네이티브 라이브러리 목록과 hash를 비공개 보존한다. 과거 파일 수/지도명을 현재 값으로 가정하지 않는다.
5. 정지 판정은 신선한 본체 자세/odom의 연속 창과 명령/소유권 상태를 함께 본다. HTTP 200·제로 명령·STOP latch만으로 실제 정지를 판정하지 않는다. 관측 불가면 UNKNOWN으로 남긴다.

## B. 승인 후 후보 적용과 복구

요청할 배포 범위: 확인된 현재 장비의 dashboard/bridge에 exact 후보를 별도 불변 release로 준비하고, 유휴·정지·보호 hash를 재확인한 뒤 서비스 전환 1회. 실패 시 같은 작업 범위에서 아래 복구. 자동 goal·이동 없음.

1. 기존 release/selector/서비스 환경과 네이티브 overlay를 보존한다. 현재 실행본과 후보의 source 차이를 비교해 장비의 후속 기능이 후보에 포함됐는지 확인한다. 장비판이 더 새롭거나 미통합 변경이 있으면 덮어쓰지 않고 main 인수·후보 검증으로 돌아간다. 장비 checkout의 사용자 변경은 건드리지 않는다. 후보 디렉터리에서 현재 장비 venv/라이브러리로 ROS 초기화 없는 import와 파일 hash를 먼저 검사한다.
2. STOP·lease 없음·소유권 유휴·관측 정확한 종료를 확인한다. bridge 종료의 실제 job 완료를 확인한 뒤 dashboard 종료를 진행한다. 종료 불명확/타 작업 발생이면 selector 교체 전에 중단한다.
3. 승인받은 release selector만 원자적으로 전환하고 기존 서비스 구성을 사용한다. 재시작 후 새 PID/import 경로·서명된 bridge release·HTTP 자산·mode/profile·시작 STOP·명령 0·보호 hash를 대조한다. 설정/프리셋 자동 초기화 금지.
4. 첫 실패 원문과 exact SHA를 비공개 기록한다. 이전 selector를 복원하되 두 서비스의 정확한 종료와 유휴를 먼저 확인한다. 이전판 재시작 후 같은 readback·STOP·유휴·보호 hash 검사를 반복한다. 복구 확인 실패이면 두 서비스를 정지한 상태로 남기고 보고하며 이동하지 않는다.

현재 장비 경로·unit·복구판 SHA는 A에서 확인해야 한다. 과거 문서의 private 배포 도구나 과거 selector를 그대로 실행하지 않는다. 이번 소스 archive 검증을 실제 전환/복구 실증으로 표시하지 않는다.

## C. 별도 승인된 정지 상태 검증

제안 범위: 현장 감독 하 10분 이내, 센서 관측 1세션, 그 정확한 session 종료 1회, Nav2 시작 1회, 사용자가 현재 확인한 INITIAL POSE 1회, 별도 match 1회. 목표 전송 0건. 실제 좌표·정지 가정은 A의 현재 지도에서 확인하며 임의 0/과거 초안을 사용하지 않는다.

1. ① 실제 mode/profile과 지도/교정 pins를 확인한다. 저장 3D 모드이면 지도 연결은 좌표관계의 사용자 선언으로만 기록한다.
2. ② 기존 STOP·lease/watchdog/Safe mode 유지. 이 정지 창은 STOP CLEAR나 제어권 획득을 승인하지 않으며 필요해지면 그 경계에서 멈춘다. 명시 관측 시작 후 signed inhibit, exact invocation, sensor epoch·시각·frame·publisher 유일성·신선도를 확인한다. unsupported bridge이면 UI 차단과 서버 거절로 끝내며 bridge를 자동 재시작하거나 모드를 바꾸지 않는다.
3. ② 초기값/조건부 가설의 provenance와 품질을 확인한 후 exact observation session으로 종료한다. dispatch 수락과 실제 inactive/owner 해제/receipt를 구분한다. UNKNOWN이면 Nav2로 넘기지 않는다.
4. ③ Nav2 job/source가 준비 pins와 일치하는지, 실제 노드 active·scan/odom·TF를 확인한다. 모의 TF/대체 odometry를 주입하지 않는다.
5. ④ 명시 INITIAL POSE의 이번 job/runtime/localization generation·stamp 접수와 별도 match receipt를 기록한다. 품질 기준과 잔차·겹침 검사를 그대로 적용한다.
6. ⑤ 연속 correction sequence·age, 안정된 위치, Nav2가 소비하는 동일 TF/source를 확인한다. freshness/source/owner가 유실되면 첫 실패를 기록하고 기존 STOP/정확한 종료로 마친다.
7. 종료 영수증: pipeline/goal/lease, 관측 invocation 종료, bridge guard 해제, 측정 정지 여부, 보호 hash, 다음 작업. 다음 세션에 쓸 수 없는 오래된 초안은 폐기한다.

기존 2D mode/profile이면 그 실행 흐름을 명시적으로 기록하며 저장 3D 통과로 보고하지 않는다. A3로 자동 전환하지 않는다.

## D. 기본 흐름 후 별도 이동 창

C를 통과한 뒤 현재 장비·현장 감독·통로·충전선 분리·배터리·회수/STOP 수단·제어권과 **실제 좌표, 최대 거리/속도, 횟수, 시간**을 고정하여 이동 승인을 받는다. 과거 두 목표 창은 소진된 이력이다.

검증 순서: 주행 탭의 짧은 단일 목표 → 취소/STOP → 신선한 본체 자세의 실제 정지 → 정지 후 XY/yaw → 다음 **명시** 목표의 진행률. 목표는 자동 재전송하지 않는다. action 성공/취소 응답과 물리 정지를 별개로 측정한다. 진행률·저속 접근 정체·정지 yaw 잔차를 별도 결과로 기록한다.

단일 목표 기본 흐름 뒤에만 기존 장애물 회피·곡선 추종·사용자 프리셋 재현성을 동일 pins/generated/live readback으로 비교한다. 현재 프리셋을 과거 값으로 덮거나 자동 미션/다른 모드를 선행 조건으로 추가하지 않는다.
