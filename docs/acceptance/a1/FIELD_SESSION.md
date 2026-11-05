# A1 실장비 기록 · 2026-11-05 KST

**최신 종료 상태 · 14:02 KST** · 아래 후속 배포에서 양 실행판 `8c26c3f588f9f7f48e6325f5b5601c5e33d524f3`, REPLAY·USABILITY ON, 나머지 확장 flags OFF를 확인했다. SOFTWARE STOP 잠금 ON, 배터리 63%, Nav2·goal idle, lease inactive, deadman false, 명령·관측 속도 0, 관측 서비스 inactive, 제어 브리지 active/authenticated로 종료했다.

**앞선 정지 센서 회차 · 11:15 KST** · 고정판 `dce1e88995e5989d63fab257ea55b8d7d2ab8e24`로 대시보드와 브리지 실행을 검증했다. 정지 FAST-LIO 관측 1회를 종료했다. 배터리 84%, Nav2·goal idle, lease inactive, deadman false, 명령 전축 0, 관측 서비스 inactive, 제어 브리지 active/authenticated였다. 이번 A1의 초기 위치·goal 전송, P1/P2 주행, 시험 녹색 클릭은 각각 0회다.

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

## REPLAY·사용 안내 후속 배포 · 13:54–14:02 KST

사용자가 A2 채팅에서 요청한 `8c26c3f` 배포·메뉴·재생·기존 대시보드·STOP 검증 원문을 A1이 확인했다. 장비 작업은 A1 상위만 수행했다. 실제 이동·goal·관측 시작·지도/프리셋 변경·HTTPS/provider 연결은 추가하지 않았다. 기존 자동 preview는 서비스 재시작의 영향 범위였으며 별도 관측·mapping 세션을 시작하지 않았다. 후보의 정확한 SHA에 대한 표준 CI `41967399703`과 I0/C0 CI `41967399665` 성공 영수증을 인수했다.

| 항목 | 결과와 범위 |
|---|---|
| 고정판·flags | DEVICE_STATIONARY PASS. archive SHA256 `88adf92758a15a7235efda030c5013467d7ee9469c11b5f8a9be41d017d1165b`, 2,690파일 검증. 장비 venv에서 ROS 초기화를 차단한 앱·브리지 import 후 양 프로세스·서명된 bridge release·HTTP 자산과 렌더 HTML을 대조했다. REPLAY=1, USABILITY=1, MULTIMAP=0, SCENE=0, RUNTIME=0. |
| 확장 진입 | 실제 장비 HTTP에서 데스크톱 상단 링크, 모바일 390px 더 보기→확장 기능, Robot Scope 복귀 PASS. Navigation 화면과 기존 STOP 표시 확인. |
| 로컬 재생·비교 | 장비가 제공한 제품 화면에서 로컬 합성 C6 파일 A/B를 선택했다. 원본 ns 시각, 조건 불일치 안내, 재생·일시정지·seek 및 관측 표시 PASS. 파일 업로드·재생 경로의 제어 요청 0. 실제 주행 기록 수집 성공을 뜻하지 않는다. |
| 비활성 기능·안내 | 다섯 안내, 지도·Scene·콘의 FEATURE_DISABLED, private 지도/Scene/session GET 404 PASS. 인증서 신뢰·실측 producer·native 보호 검증은 미실행. |
| SOFTWARE STOP | 실제 버튼 POST 1회, HTTP 200, latch=true, dashboard와 일치하는 bridge stop ACK(age 10 ms), SportModeState 속도 전축 0(age 5 ms) PASS. 이동 중 제동·P1 정밀 정지는 미실행. 잠금을 해제하지 않았다. |
| 보존·종료·복구 | 직전 기준 지도 140파일·navigation 4파일·기타 설정 6파일 해시 일치. 앞선 회차 이후 늘어난 지도도 그대로 보존했다. 새 bridge 프로세스 nonzero_move/action 각각 0, 활성 목표·lease 없음, 관측 inactive. 직전판과 설정 백업 유지. |

첫 전환은 변경 전에 OWNERSHIP 검사에서 중단됐고 두 PID와 selector는 그대로였다. 첫 거절 원문을 수집하지 못해 원인 미확정으로 남겼다. 진단 원문을 보존한 두 번째 전환에서는 새 프로세스 시작 직후 `pipeline_coordination / owners_not_sampled`가 관측돼 원복했다. 이전판을 재시작한 직후 같은 조회 거절로 복구 완료 판정도 중단됐지만, 별도 조회에서 이전판 양 실행본·인증·유휴·속도 0을 확인했고 다음 preflight에서 원래 selector 해시를 대조했다.

이 API는 공유 잠금 또는 대기자가 있으면 소유권을 읽지 않는다는 소스로 원인을 확인했다. 비공개 배포 도구에서 그 정확한 미조회 응답만 최대 15초간 GET으로 기다리도록 최소 수정했다. 실제 busy/unknown 결과와 lifecycle·제어·보호파일 검사는 유지했다. 세 번째 전환에서는 미조회 표본 뒤 0.54초 만에 정상 유휴 표본을 얻었고 14:01:42 KST에 새 양 실행본을 검증했다. 제품 코드 수정은 0건이다. 브라우저 대표 검사 여섯 행은 모두 통과했고 최초 실패와 모든 전환·복구 원문은 비공개 영수증에 남겼다.

**문서 게시 전 검사** · 실제 장비 브라우저 여섯 행 PASS, 관련 JavaScript 133개 PASS. macOS 전체 Python은 3,668개 실행, 실패 12·오류 112·skip 40이었다. 추가 오류 51개는 로컬 소켓 bind 권한 거절이었고 해당 51개만 통신이 가능한 환경에서 재검사해 전부 통과했다. 남은 실패·오류 73개의 이름은 이전 A1 macOS 회차와 정확히 같았다(`/proc` 및 교정 파일 소유권 가정 등). 전체 로컬 PASS로 표시하지 않는다. 지원 Linux 검증은 위 고정 코드 SHA의 CI 성공으로 구분한다. 이번 게시 변경은 A1 문서 네 파일뿐이다.
