# A1 실장비 기록 · 2026-11-05 KST

**종료 상태** · 고정판 `dce1e88995e5989d63fab257ea55b8d7d2ab8e24`로 대시보드와 브리지 실행을 검증했다. 정지 FAST-LIO 관측 1회를 종료했다. 배터리 84%, Nav2·goal idle, lease inactive, deadman false, 명령 전축 0, 관측 서비스 inactive, 제어 브리지 active/authenticated였다. 이번 A1의 초기 위치·goal 전송, P1/P2 주행, 시험 녹색 클릭은 각각 0회다.

| KST | 장비에서 확인한 근거 |
|---|---|
| 10:56 | 읽기 승인. 대시보드와 브리지 각각의 systemd PID, /proc cwd, 정확한 `-m` 인자, 기존판 `4ff0e47467f9d049706cd70ca49af6e3da805457`의 소스 및 bridge release readback 대조. 배터리 89%, goal idle. |
| 11:02~11:04 | 재연결 후 지도 트리 133파일 및 navigation 설정 4개 해시 비교. 운영 교정 파일과 preset, 디스크의 generated/previous YAML을 분리했다. Nav2가 유휴여서 현재 job의 generated evidence=null, live ROS 정책 unavailable. 저장 설정 0.20 m/s, 10 Hz, XY 0.05 m, yaw 0.10 rad. |
| 1차 마감 후 | 운영자가 현재 장소와 기존 지도가 다름을 확인. 고정판 배포·필요 시 원복·지도와 독립적인 정지 관측 1회만 승인했다. 지도를 선택하거나 초안/geometry를 적용하지 않았다. |
| 11:11~11:13 | 구판에서 앱·브리지·스크립트·설정 559개 파일 및 HTTP 자산 3개 일치. 새 Git archive의 2,655개 파일과 장비 전송 SHA256 일치. 새 디렉터리에서 기존 venv/workspaces 링크와 서비스 환경으로 실제 앱·브리지 import, 준비/정지 API·선택 bounds·기본 확장 OFF 확인. 기존 selector를 비공개 백업했다. |
| 11:11:39 | 첫 전환은 브리지 프로세스 종료 직후 dashboard stop 금지로 중단. selector 교체 전이었다. 정확한 bridge stop 작업 성공과 유휴 확인 후 기존판 브리지 정상 재가동. 11:13:12 같은 기존판·인증·제로 명령·보호 해시 확인. |
| 11:13:53 | 두 번째 전환은 같은 작업 ID의 종료 완료까지 확인한 뒤 두 서비스가 모두 내려간 상태에서 selector의 release 한 줄만 교체했다. 대시보드 정상 기동과 기존 자동 브리지 시작, 각각의 새 PID/cwd/모듈·서명된 release와 HTTP 자산 해시를 확인했다. |
| 11:15:45~11:15:52 | 배터리 84%, 활성 goal·lease·관측 없음. 관측 시작 1회. signed control bridge HELD → FAST-LIO READY. 점군 353점/347점과 자세 2회, source stamp·sequence 증가. 2번째 cloud/pose header stamp 일치. 동일 시각·같은 좌표로서의 자격을 별도로 검증할 geometry/TF bundle은 없었다. |
| 11:15:52~11:15:55 | 해당 systemd InvocationID와 대조한 세션에 stop POST 1회, STOPPING/HELD → STOPPED, active/busy/job_pending=false, bridge_guard=null. 관측 PID 0·inactive, 양 서비스 PID 유지. 최종 Nav2·제어·보호파일 재확인. |

**지도·교정 인계** · 보관 지도 51개(2D 34·3D 17). `map1`의 3D revision `c9ad9bcc4c8b…`에서 파생된 2D 지도 중 P1/P2 주석은 대문자 D인 `map1_2D` revision `f691b8e98e81…`, annotation revision `c639ebe083cd…`에 결속되어 있다. 소문자 `map1_2d`는 revision `e220cbbff862…`인 별도 지도다. 교정 파일 SHA256 `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226`, 저장 파라미터 revision `8362ba4fbae6812ee8a619d74466fd297d72588b52bbe9db1461d8e23a8300fa`. 133개 지도·4개 설정은 전환·관측 종료 때 기준 해시와 일치했다.

**증거 경계** · 실측 그래프는 두 topic 모두 endpoint 1개, publisher RELIABLE/VOLATILE/KEEP_LAST depth 20, subscriber depth 1. 각 메시지의 publisher GID는 null, source clock은 ROS_HEADER_UNVERIFIED다. 준비 API는 MAP_PAIR_REQUIRED를 반환했다. 서비스 stop 수락과 실제 종료·작업 정리·bridge hold 해제를 관측했다. 제품 코드는 동일 토큰의 RELEASED를 확인한 뒤 guard를 제거한다. 이 조회에서 별도 raw 서명 ACK 또는 proposal에 결속된 handoff journal/nonce를 수집하지 않았다. P1 정지 ACK 및 도착 후 실측 오차는 미측정이다. 종료 시 SportModeState 속도 전축 0, age 3 ms, error_code 1001과 기존 vendor-local position INVALID는 별도 기록이며 지도상의 정밀 정지를 입증하지 않는다.

**복구** · 기존 release와 selector 백업은 장비에 남겼다. 첫 시도에서 구판 브리지 복구를 실증했다. 새 selector를 적용한 뒤의 전체 역전환은 미실행이다. 필요 시 운영자가 정지·제어권과 새 작업 부재를 확인하고 두 서비스의 정상 종료를 거친 뒤 정확한 기존 selector를 복원해 양쪽 source·HTTP·유휴·보호 해시를 다시 읽는다. A2 push 자동 배포는 설정하지 않았다.

원본 현장 영수증 SHA256은 `17a8939e7288ebe2a95dac937e8a96f57fd1ae7487522e60450c85d332fc9b06`이다. 비공개 사본에 두 전환 시도, 시간·세션·서비스 영수증을 분리 보존했다.
