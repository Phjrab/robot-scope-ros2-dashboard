# A1 실장비 기록 · 2026-11-05 KST

**이전 회차 종료 상태 · 14:02 KST** · 아래 후속 배포에서 양 실행판 `8c26c3f588f9f7f48e6325f5b5601c5e33d524f3`, REPLAY·USABILITY ON, 나머지 확장 flags OFF를 확인했다. SOFTWARE STOP 잠금 ON, 배터리 63%, Nav2·goal idle, lease inactive, deadman false, 명령·관측 속도 0, 관측 서비스 inactive, 제어 브리지 active/authenticated로 종료했다.

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


## 여러 지도 검토 연결 준비 · 실행판 전환 전 연결 중단

운영자는 두 입력이 같은 장소를 겹쳐 촬영한 실지도임을 확인했고, 현재 Mac 브라우저의 키체인 등록도 직접 승인했다. A1은 인증서 한 장을 해당 호스트 SSL 용도로 등록하고 macOS 신뢰 검증 성공을 확인했다. 장비에 새 비공개 검토 폴더·인증 저장소·읽기 전용 원본 사본 2개를 준비했다. 두 사본은 각각 86,785/127,882점이며 원본 내용 SHA가 일치했다. 새로운 catalogue ID/revision과 원본 ID/revision을 구분했다. 최초 sensor capture session/epoch는 null이다.

최종 게시판 `7092851dca9561ca240462eaefc8282f2f892b80`은 별도 불변 release의 2,709파일, archive SHA256 `2063a9b0dffcca5c60e06444c191ed5b550f02cf9f46e21cd796d25780a6a66a`로 준비했다. 실제 장비 venv에서 ROS 초기화를 차단한 앱·브리지 import, source 경로, 두 검토 사본 조회, HTTPS 인증서/개인키 쌍, 공개 flags와 기존 준비/정지 API를 검증했다. 사전 검사 당시 기존 실행판은 `8c26c3f`, 원본 지도 보존 기준은 140파일이었다. 이 준비는 listener 실행이나 서비스 전환이 아니다.

| 행 | 연결 중단 시 상태 |
|---|---|
| M00 정지·소유권 | 최초 정지·STOP 상태는 확인. 현재 연결 불가로 재조회 필요. |
| M01 HTTPS | Mac 호스트별 인증서 신뢰 PASS, 직접 TLS 실행기 로컬 회귀 PASS. 장비 listener 미활성. |
| M02 검토 세션 | 비공개 DB 준비, 로컬 TLS read/review·회수·만료 검사 PASS. 실제 장비 로그인 NOT_RUN. |
| M03 실지도 catalogue | 사용자 같은 장소 확인, 원본 해시 동일 사본·신원 근거 준비, 장비 venv catalogue 조회 PASS. |
| M04 정합·수락·전체 점 저장·재조회 | DEVICE_NOT_RUN. 계산·수락·저장 요청 0. |
| M05 기존 HTTP/WS·대시보드·REPLAY·STOP | 새 실행판의 실제 장비 브라우저 회귀 NOT_RUN. |
| M06 보존·복구 | 운영 selector·서비스 변경 0. 전환 직전 보존 재조회와 배포/복구는 연결 후 수행. |

연결 불가 통보 이후 장비 접속을 중단했다. 운영 지도 선택·활성화, initial pose, goal, 추가 센서 세션, 실제 이동은 수행하지 않았다. A3 코드가 함께 게시됐지만 실험 준비·seed·goal은 이번 승인 범위가 아니며 실행하지 않았다. 미사용 초기 준비판 `b4998f2`와 실제 게시 후보를 구분해 증거를 남겼다.

최종 결합 소스의 macOS 전체 Python 3,697건은 FAIL 12/ERROR 61/skip 40으로 기존 실패 이름 73개와 동일했다. A3 후속 상대 odometry 준비 보정까지 반영한 관련 100건, JavaScript 765건, 정적 검사 PASS다. 공개 Git에는 사본·인증서 개인키·로그인 코드·장비 주소를 넣지 않았다. 실제 접속 주소와 비공개 증거는 현장 인계 사본에 보존한다.

고정 후보의 최종 [표준 CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41976977598)는 Ubuntu 22.04/Python 3.10, Ubuntu 24.04/Python 3.12, competition-offline 모두 SUCCESS이며 [I0 제품 CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41976977597)도 SUCCESS다. 이 결과는 `7092851` 소프트웨어 검증이고 장비 전환·실지도 정합 성공을 뜻하지 않는다.


## 여러 지도 HTTPS 실제 적용·대표 검사 · 15:26–15:52 KST

운영자의 재연결 통보 후 기존 승인 범위로 재개했다. 고정 `7092851`의 두 CI 성공과 보존 기준을 재확인했다. 첫 전환은 `BASELINE_LIFECYCLE`에서 selector/서비스 변경 전에 거절됐다. 별도 읽기에서 로봇 본체 DDS 수신 중단과 bridge ready=false를 확인했다. 이후 2초 간격의 fresh·속도 0 표본 5개와 정지·소유권·배터리 39%를 확인한 뒤 15:30:22 KST에 전환했고, 15:30:29에 두 서비스의 같은 release·시작 STOP·자산·TLS·보호 해시를 대조했다. 이 회차의 원복 실행은 없었다.

| 행 | 실제 결과 |
|---|---|
| M00 정지·소유권 | 전환 전 PASS. STOP ON으로 시작, lease/goal/추가 센서 세션 없음. 본체 신선도는 간헐적으로 중단됐으며 종료 시 UNKNOWN. 소프트웨어 정지와 물리 정지를 분리한다. |
| M01 HTTPS | 최초 실제 Chromium 접속은 CERT_AUTHORITY_INVALID. 같은 leaf 인증서의 Mac SSL 신뢰 형식만 교정한 후 경고 우회 없이 정상 HTTPS·secureContext PASS. HTTP 확장 링크가 직접 HTTPS로 이동. 잘못된 호스트 이름은 거부. |
| M02 검토 세션 | 실제 TLS 12항목 PASS: HTTP/forwarded 우회 거부, 미로그인/다른 origin 거부, secure/httponly/samesite cookie, read 조회·쓰기 거부, 코드 1회 사용, 회수·만료. 실제 브라우저 read/review 로그인·로그아웃 PASS. 시험 grant 회수. |
| M03 실지도 catalogue | 사본 2개의 ID/revision·원본 ID/revision/내용 SHA와 사용자 같은 장소 확인을 실제 API/브라우저에서 대조 PASS. 별도 저장 폴더만 연결. 원본 capture epoch/session은 null 유지. |
| M04 정합·수락·전체 점 저장·재조회 | 실지도 계산 정확히 1회. `DISCONNECTED`, accepted edge 0/rejected 1, connected components 2. 수락/저장 요청 0. exports GET 200/빈 목록. 유효 후보가 없어 저장/저장본 재조회 BLOCKED_DEPENDENCY. 사용자는 알려진 상대 배치/대응점 없음으로 확인. |
| M05 기존 화면·재생·모바일 | HTTPS 대시보드 STOP 표시, 실제 WSS/WS joint/pose 수신, 기존 HTTP 대시보드와 메뉴 복귀, 로컬 합성 REPLAY 원본 ns 보존, Scene 404 PASS. 모바일 390px 실제 메뉴 클릭·문서 새로고침·세션 복원·읽기 제한·로그아웃 PASS, 가로 넘침 없음. fragment-only 시험 실패는 별도 보존. |
| M06 보존·종료 | 원본 지도 140·navigation 4·기타 설정 6파일 SHA 동일, 사본 SHA 동일, 새 bundle 0. selector는 승인한 release/HTTPS/review/flags/시작 STOP만 변경. SOFTWARE STOP ON·lease 없음·명령 0·새 bridge nonzero/action 0. final body stale로 물리 정지는 미확인. |

실제 job의 원문에서 유효 겹침 source/target 각각 `0.008666666666666666`, inlier 13, 거리 p50 `1.6452649893162592 m`, p95 `5.253311924918951 m`, inlier RMSE `0.10017842945518989 m`, reason `AMBIGUOUS_OR_LOW_OVERLAP_OR_DEGENERATE`를 확인했다. 낮은 inlier RMSE를 지도 정확도/성공으로 표시하지 않았다. C1이 원본 사본 파일을 D1 solver에 전달하며 160점 화면 preview를 정합 입력으로 넘기지 않는 것을 확인했다. 상세 원인(초기 배치·샘플 분포·형상)은 이번 자료로 확정하지 않는다. 품질 한도·solver·운영 지도·TF 변경 및 추가 정합 실험은 0건이다.

본문과 별도로 최초 접속 실패, 전환 거절, 첫 정합/모바일 시험 실패, 원문 job GET, 마지막 telemetry stale을 비공개 증거에 보존했다. 최초 A1 9행 결과표와 여러 지도 7행 상태표는 수정하지 않았다. 관측 서비스 inactive, Nav2 goal 없음, 운영 지도 미선택을 유지했다. UI 검사를 위한 세션 POST 외 로봇 제어 쓰기는 없었다.

**현장 종료 문서 검사** · 게시 전 원격 main의 A3 격리 workflow/runner 2파일만 fast-forward로 인수했으며 장비는 7092851을 유지한다. A1 기존 Python 3.12.14 가상환경의 전체 3,697건은 FAIL 12/ERROR 61/skip 40, 실패 이름 73개는 앞선 Mac 기준과 동일하고 신규 이름은 없다. JavaScript 765건·secret scan·diff 형식 검사 PASS. 처음 두 검사 시도는 기본 Python 3.13 및 가상환경 밖 Python 3.12에서 의존성 부재로 각각 2,591건(FAIL 1/ERROR 161/skip 46), 2,661건(FAIL 16/ERROR 118/skip 57)이었고 원문을 보존했다. 필수 모듈 import를 확인한 기존 A1 가상환경으로 교정했으며 제품 소스 변경은 없다. 지원 Linux의 장비 코드 검증은 고정 7092851의 두 CI 성공이다.


## 로그인 제거 고정판 적용·읽기 검증 · 2026-11-05 17:08–17:22 KST

사용자의 배포 요청 원문을 확인하고 A1 상위만 장비를 조작했다. 후보 `59714317c5abefca43b25fe8c78015f7843f387c`의 [표준 CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41989057092)와 [I0 CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41989057089)가 모두 SUCCESS였다. 최초 7행 배포 상태표 SHA256 `ff45c8e4addefc1b97b169d2b21bfb2d1f9a204926ee7f92f3a7153c003bd567`을 전환 전에 고정했다.

| 항목 | 실제 결과·한계 |
|---|---|
| U00 정지·소유권 | 첫 z속도 표본은 -0.0304 m/s로 전환하지 않았다. 조건을 유지하고 17:11의 fresh·제로 속도 5표본과 STOP ON·유휴를 확인했다. |
| U01 불변 소스 | 2,711파일, archive 90,788,944 bytes, SHA256 `cad58e80c9acb51a1ad4fc55827760f5103c1cfc6e33b70047db4e31ffc9bd68`. 장비의 실제 의존성 import PASS, 이 단계에서는 ROS 초기화 금지. |
| U02 전환 | 정상 bridge stop 완료 17:12:58, dashboard stop 17:13:01. selector의 release 한 줄만 교체, 17:13:09 양 프로세스의 정확한 새 release 검증. 원복 실행 없음. 기존 release·selector 백업 유지. |
| U03 로그인 없는 확장 | 실제 Mac Chromium 정상 TLS, OWNER_POLICY, 사본 2개 신원·원본 SHA, 새 탭·새로고침·390px 모바일 PASS. session GET 404·cookie 0. 계산/수락/저장 없음. |
| U04 실험·STOP | 실험 메뉴, STOP 안내, 준비·전송 비활성, can_start=false/software_stop_latched 확인 PASS. 현장 일치 checkbox는 선택하지 않았다. 지도 상세 로딩·주행 성공을 포함하지 않는다. |
| U05 회귀·접근 경계 | 실제 HTTP/WS/WSS·합성 REPLAY 원본 ns·Scene 비활성 PASS. HTTP/잘못된 Origin/잘못된 Host는 403. 검사 클라이언트 TLS 오류와 후속 검증은 별도 보존. |
| U06 보존 | 지도 140·navigation 재귀 287·selector 외 설정 6·검토/TLS 6파일 동일. navigation 287은 하위 runtime 자료를 포함해 조사 범위를 넓힌 수치이며 배포로 추가한 수치가 아니다. release 외 환경 설정은 동일. |
| U06 마지막 STOP | 17:15 ON → 17:16:59 OFF. A1 clear 요청 0, 현장 조작 여부 INPUT_REQUIRED. 마지막 표본은 lease/goal 없음·명령 0·본체 속도 0/age 3ms·배터리 51%·nonzero/action 0. 시작 STOP 성공과 이후 상태를 구분한다. |

검사 브라우저는 GET/HEAD 외 요청과 control WebSocket을 차단했다. 초기값·goal·추가 센서 시작·운영지도 교체는 각각 0건이다. A3 초기값 뒤 stale 중단의 원인을 고쳤다는 주장이 아니다. 17:22에 이전 최초 작업의 영구 기록을 읽었으나 조사한 ROS 로그 176개 중 해당 runtime PID 파일이 없었고 해당 job 폴더도 없었다. 지정한 시작 구간의 service journal은 `No entries`였다. 기록 소실 시점/이유는 확정하지 않았다.

**지도 상세 별도 첫 결과와 11월 6일 후속** · 목록 36개가 표시된 뒤 map-info가 5초 동안 `2D 지도 필요`여서 첫 검사는 FAIL이다. 원래 검사를 덮어쓰지 않았다. 11월 6일 09:34 KST GET endpoint/상태/완료 시간/응답 크기를 기록하는 후속 브라우저는 페이지 접속 전에 `ERR_NETWORK_CHANGED`로 중단됐고 지도 GET은 0개였다. 후속은 BLOCKED_DEPENDENCY이며 단순 지연인지 제품 오류인지 아직 구분할 수 없다. 초기 브라우저 실행의 Mac 권한 오류도 별도 보존했다.

**게시 전 검사** · 기존 A1 가상환경 전체 Python 3,698건: FAIL 12/ERROR 61/skip 40. 실패 이름 73개는 앞선 Mac 기준과 정확히 같고 신규 이름은 없다. JavaScript 765건 PASS. 제품 변경은 없으며 이번 게시 범위는 A1 기록 네 파일이다. Linux 제품 검증은 위 고정 SHA의 CI 성공으로 구분한다.
