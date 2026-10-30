# C0 연결 복구 뒤 실장비 1차 결과

2026-10-30T19:33:18.408318+09:00 KST. 기존 ROUND1_RESULTS.json은 보존한다. 연결 복구 후 가능한 실제 비이동 항목을 한 번씩 검증했고, 새 stop 실패를 분석하기 전에 이 표를 마감했다.

| ID | 기능 | 이번 결과 | 증거 수준 | 사실·의존성 |
|---|---|---|---|---|
| V00 | 현재 인수·실행 기준 | **PASS** | STATIONARY_DEVICE | SSH/API 복구; PID995/cwd, source5154761 2200/2200 hash 일치; saved71933bade 유지 |
| V01 | 대표 software/UI | **PASS** | STATIONARY_DEVICE + SOFTWARE | 기존 software3132/JS700/browser18 인수; 실제 editor에서 영역/Z·undo/redo 확인 |
| V02 | E1/E2 편집·전체 저장·재조회 | **PASS** | STATIONARY_DEVICE | 13,546→12,619점 사본1개; 927점 제외, XYZ/intensity layout·retained record bytes/order·부모 hash 보존. E3 실제 worker는 V03에 의존 |
| V03 | N1~N4 실제 source·TF·consumer | **BLOCKED_DEPENDENCY** | STATIONARY_DEVICE | 부팅 뒤 LEGACY_2D/source null. 독립 관측 준비 중 bridge stop이 failed여서 관측 시작하지 않음. 실제 seed·정합·Nav2 소비 미실행 |
| V04 | N5/G2 stop 접근 | **BLOCKED_DEPENDENCY** | SOURCE_REVIEW | V03+V08 안전 gate 미충족, 새 시험창 미확인. 신규 goal0 |
| V05 | G1~G4 실제 버튼 재출발 | **BLOCKED_DEPENDENCY** | SOFTWARE | actual stop/success/dwell/source 불충족. GREEN·arrival 강제 안 함 |
| V06 | R1/R4 독립 수동 경사로 관측 | **BLOCKED_DEPENDENCY** | STATIONARY_DEVICE | 정밀 도착과 독립적으로 관측 경로를 준비했으나 bridge inactive gate가 충족되지 않음; 관측 서비스 STOPPED |
| V07 | R2/R3 원인 경계·동일입력 A/B | **BLOCKED_DEPENDENCY** | SOURCE_REVIEW | 실제 ramp raw/LIO/match 입력 없음(INPUT_REQUIRED); rear policy 미적용 |
| V08 | 정지·복구·보존 | **FAIL** | STATIONARY_DEVICE | 기존 stop API succeeded와 systemd failed/Result=timeout 불일치. MainPID0, TimeoutStopUSec2s, ExecMainCode2/Status9. 물리 정지는 미확인 |
| V09 | 표 마감·진단 분리 | **PASS** | SOURCE_REVIEW | 이번 표를 새 stop 원인 분석보다 먼저 생성; 첫 ROUND1 원본 JSON 보존 |

## 배포·설정·지도

- 현재 대시보드 PID995/cwd와 bridge PID2544의 초기 cwd는 모두 robot-scope-5154761bba6f였다. 실행 source SHA **5154761bba6fa4f171881e61f986901e2b415ed9**의 2,200개 Git 파일을 실제 release와 비교해 전부 일치했다. 감사 전후 PID/cwd도 동일했다.
- main846121b와 C0b790aa0는 장비 실행 SHA와 구분한다. 사용자 dirty checkout은 main ahead35 및 dirty/untracked 목록을 private에 보존했고 수정하지 않았다.
- 선택된 Shim overlay .so SHA256은 95c6ee9b0294651c182092031eb4926291946eb8e72be5cf1bfb976219f1754d, /opt/ros 원본은 1cd261a56261e20b10e1d3cc6da3ff14423b467bef23238c8dbc84235f6f0965로 기존 보고와 일치했다. 현재 Nav2가 idle이므로 controller 로드 검사는 NOT_RUN이다.
- 현재 saved revision71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387, XY/yaw .10/.10, .25m/s, 10Hz, required_movement_radius .20m를 재조회했다. 새 generated YAML은 없고 live readback은 unavailable이다. 현재 live 값이라고 주장하지 않는다.
- 기존 원본22,529점 ID f9892bac9cc1d59328601dc6와 기존 localization13,546점 ID e1dd40cc6911404dbdfc073b, 2D operator_free9a382e3eb990fb02fe1a3569의 revision/hash가 기존 공개 보고와 일치했다.
- 새 C0 사본: f4f819b45cb145bb826c3e8d, revision c7e296aa6a81fd9548b5b6375ef059235228b7e5bca0f12b909d746008a7c017, SHA25653668ab834e77ca38a79103add1918f82e0ecad15dd807fef480ba505fbbedaa. 이름 C0_20261030_ROUND1_EDIT, 12,619점. 원본/부모는 immutable 보존; 새 사본은 운영에 선택하지 않았다.

## 실제 수행·중단

실제 화면에서 사각형 localization 영역(Z −.5~1.2m)을 1개 추가했고 UNDO0/REDO927점을 확인한 뒤 새 전체 PCD 사본1개만 저장했다. 실제 parent/copy zip을 private로 읽어 16-byte XYZ/intensity record layout과 보존 record 전체 바이트·순서가 일치함을 확인했다. 운영 source는 저장 전후 selected=null, LEGACY_2D였다.

독립적인 관측 경로를 준비하기 전 goal·mission·lease·command·mapping 등 상태를 다시 읽고 idle을 확인했다. 기존 bridge-service/stop을 1회 요청했고, 6초의 제한 readback에서 inactive를 확인하지 못해 관측 시작 요청을 보내지 않았다. 이후 API와 systemd를 읽어 API operation succeeded / systemd failed(Result timeout, PID0, 종료signal9)를 확인했다. 재시도·reset-failed·강제 inactive 처리·새 publisher·source gate 우회는 하지 않았다.

관측 전용 FastlioObservationSession은 control bridge ActiveState가 정확히 inactive일 것을 요구한다. failed를 inactive로 간주하지 않았다. V06은 정밀 도착 성공에 묶지 않았지만 이 별도 안전/관측 의존성 때문에 차단됐다.

## 남겨진 상태와 권한

Nav2/goal/mission은 idle, lease inactive, 명령0. SOFTWARE STOP latch는 false로 읽혔다. 이를 물리 정지 ACK/현장 확인으로 승격하지 않는다. bridge는 PID0·failed, 관측은 STOPPED다. dashboard·persistent preview는 유지한다. 신규 goal·ARM·자세 명령·GREEN·배포·주행 파라미터 변경은0이다. 원래 두 목표 승인은 재사용하지 않는다.

원격 C0 exact SHA b790aa0의 CI run41029362811은 FAILURE로 완료됐다. Ubuntu24.04 browser의 합성 mount_calibration import 결과 표시 timeout1건/226PASS이며, Ubuntu22.04 및 competition integration은 PASS다. main846121b의 URDF timeout과 다른 실패 위치다. 이를 flaky나 같은 실패라고 단정하지 않는다.

[JSON 결과](LIVE_ROUND1_RESULTS.json). raw PCD·센서·진단 ZIP·endpoint·SSH 인증 정보·사용자 dirty 원문은 공개 Git에 넣지 않는다. 이후 stop 원인과 최소 복구 후보는 별도 문서에 기록한다.
