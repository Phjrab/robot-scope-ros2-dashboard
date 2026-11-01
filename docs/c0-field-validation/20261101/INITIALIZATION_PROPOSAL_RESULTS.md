# 2026-11-01 C0 초기 위치 제안 및 준비 조회 연결

기존 10월 28일 팩과 10월 30–31일 검증 결과를 이번 새 실기 성공으로 합산하지 않는다. 이 기록은 전체 동결 회귀와 C0-W04C 배포 완료 및 이후 로컬 연결 구현을 구분한다. 13:51:03 KST의 실제 실행본과 보호 상태를 확인했으며, 센서 기반 global 제안 실기는 별도 W05에서 확인한다. 배포 코드 SHA는 `c414a519bd18ece9ecf46469074046bb94dac33e`다. 이후 미배포 연결 구현과 독립 검사는 [초기 가설 전달 결과](PROPOSAL_HANDOFF_RESULTS.md)에 기록한다.

## 현재 결과

| 항목 | 구현 | 소프트웨어 검사 | 배포·실기 |
|---|---|---|---|
| 현재 스캔과 저장 3D 지도에서 정보성 초기 위치 제안 | 완료·배포 | backend 관련 86건 PASS(독립 proposal 6·단일 조회 7 포함) | c414a519 배포 PASS, 실제 global 계산 NOT_RUN |
| 사용자 클릭에 의한 제안 표시·IMU/본체/운영 위치 구분 | 완료·배포 | UI 20건 PASS 이후 cleanup 보완 4건 PASS; 중복 합산하지 않음 | 실제 HTTP 자산 hash PASS, 관측 중 새 UI 실기 NOT_RUN |
| 동일 요청에서 운영 상태와 센서 준비 조회 | 완료·배포 | 실제 합성 catalog/ASGI 7건 PASS, source 전환·교정/PCD 변조·만료 차단 | 실제 GET 200/2.5251초 1회; 간헐 지연 해결 미확정 |
| 자기 global job의 종료·소유권 관리 | 완료·배포 | source 복원 후 재사용, 교정 경합, 외부 job ID 충돌, 관측 종료 cleanup, session 전 pose 경계 회귀 PASS | 실기 resource scope·cleanup NOT_RUN |
| 전체 통합 회귀 | 검토 완료 | Python 3,237건 OK(2 skip), Node 78 PASS, 문법 113개, 기존 pinned 통합 270 PASS, 로컬 실제 API 합성 E2E 10 PASS. 주 browser 최초 237 PASS/3 환경 FAIL → 해당 3건만 지정 환경에서 3 PASS. 전후 14파일 hash 일치 | 로봇 접근 없는 로컬 검사 |
| 초기 가설의 새 Nav2 실행 전달 | 로컬 구현·수리 후 동결 | 코드 99d5681 통합. 독립 21 PASS, 주 브라우저 253/Node715/pinned270/API브라우저10 PASS. Python 최초 3286건 중 오류1·skip2 → 테스트 대역 보완 후 API모듈18 PASS; 단일 전체 PASS로 합산하지 않음 | 미배포, 실제 가설·정상 전환·TF/Nav2 검증 BLOCKED/NOT_RUN |
| 후속 연결 코드 CI·배포 후보 | 코드 99d5681, 문서 head f336830 CI 완료 | Ubuntu22/Python3.10·Ubuntu24/Python3.12·통합 job PASS, 오프라인 후보 strict 검사 PASS | 실제 새 코드 배포 NOT_RUN, W05 사용자 정지 확인 대기 |
| 저장 지도 지속 보정→TF→Nav2 / P1→버튼→P2 / 경사로 운영 추정 | 기존 코드 보존 | 기존 결과 유지 | 이번 실제 실행 BLOCKED/NOT_RUN, 목표·이동 명령 없음 |

## 구현의 의미와 한계

기존 GlobalObservationCoordinator의 fastlio_imu / subscription_observation 경로를 재사용한다. 명시 POST 한 번으로 현재 스캔을 캡처하고, 결과 GET은 저장 3D 지도 기준 FAST-LIO IMU 가설(m/degree)과 검증된 T_imu_base를 적용한 본체 후보(m/radian)를 분리해 반환한다. 과거 누적 지도점을 새 스캔으로 만들지 않으며 FAST-LIO·장애물 입력·주행 파라미터는 수정하지 않는다.

proposal의 ready는 정보성 표시 가능이다. geometry·TF·Nav2·goal 자동 적용은 없고 operational_application=NOT_RUN, absolute_accuracy_m=null이다. global overlap 기준 0.60과 운영 초기 기준 0.85 및 독립 3스캔·정지/dwell·잔차/TF 검사는 별도다. global residual selection gate가 비활성인 사실, capture 경과와 현재 전파 pose 경과, 미검증 source clock/per-message publisher/deskew를 구분한다. 정합 잔차를 실제 위치 정확도로 보고하지 않는다.

지도 쌍·revision·SHA·교정·관측 세션·observer/source epochs·정확 stamp·각 수신시각을 확인한다. 같은 source가 복원돼도 관측된 문맥 변경으로 무효가 된 기존 제안은 살아나지 않는다. 작은 교정 파일은 반환 직전에 재검증한다. 서버 생성 global request ID로 다른 기능의 job을 채택하지 않고, HTTP 폴링이 없어도 자기 작업만 취소·정리한다. 취소 접수와 worker 종료를 구분해 UI에 표시하며 완료 후 최신 점유 해제를 확인해야 새 요청이 가능하다. 실패·timeout 자동 POST 재시도는 없다.

준비 화면은 기존 상태 GET과 준비 GET의 중복을 없애고 동일 준비 응답의 operational_state를 사용한다. 독립 요청의 지도·교정 재검증은 유지하며 요청 간 증거 캐시는 없다. source/세션/선택이 조회 중 바뀌면 상태·참고값·후보를 함께 폐기한다. 단일 조회가 합성 작업량을 줄인 것은 실제 장비의 5–7초 간헐 지연 해결 증거가 아니다.

## 수정 중 발견한 문제와 검증

독립 검사에서 source 전환 후 operational_state가 남는 문제, source 복원 시 과거 후보 재표시, 반환 전 교정 변경 미검출, 관측 종료 뒤 worker 정리 누락, global request ID 충돌에 의한 외부 job 소유 가능성을 재현했다. 담당 수정 뒤 원래 기대값을 유지한 독립 회귀가 통과했다. 개발 중 snapshot 결과와 최종 동결 전체 검사는 구분한다. 이전 GitHub CI의 ui_consistency 4건 실패는 mock의 새 준비 GET 누락이었으며 404 허용 대신 명시 fixture를 추가했다.

남은 한계: proposal POST/GET이 지도 검증 중 공유 pipeline 잠금을 보유해 관측 stop 응답이 지연될 가능성이 있다. 실제 잠금 대기·global backend 계산·resource admission은 아직 미측정이다. 이를 로봇 물리 정지의 증거로 취급하지 않는다.

## 실제 배포·보존·다음 단계

마지막 확인 배포 코드는 4f90612379705b7b7c8c86cca99941266e3ae611, PID 24983이었다(13:15 KST 읽기). 검사 시작·종료 HEAD는 `7321251f36ede748c73f8252f913b4cf2ac91fbd`였고, 검사한 14개 변경 파일은 C0가 현재 hash까지 대조한 뒤 `c414a519bd18ece9ecf46469074046bb94dac33e`로 commit/push했다. 그 이후 W04C 배포에서 실제 실행 c414a519와 PID82325를 확인했다. 아래 배포 증거를 우선한다.

map1/map1_2D와 P1/P2, 교정 SHA 5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226 및 주행 설정은 기존 보호 대상이다. 마지막 W03에서 133개 보호 파일 집합/hash가 일치했고 source 정책·bridge를 복구했다. 이번 구현은 ALL_DIRECTION_BASELINE과 기존 품질·stop/dwell/source gate를 보존한다.

C0-W04는 현재 확인된 4f90612 release를 BASE로 한 별도 private 도구를 사용하며 기존 bb77/W02 백업을 보존한다. 오프라인 helper 8건 PASS다. C0는 검증된 정확한 c414a519 SHA만 배포하도록 C1.3을 단일 담당으로 지정했다. 이후 W04/W04B는 필수 검사 실패로 변경 없이 중단했고, 해결 후 새 W04C에서 fresh idle·ownership·실행 base 검사, stage/activate/verify가 통과했다. rollback은 실행하지 않았다. source 파일/mode/hash·HTTP 자산과 지도·설정 보호 hash를 확인하고, 불확실 restart는 재시도 없이 읽기 조사한다.

배포 후 새 현재 정지 확인을 담당 채팅의 질문 UI에서 받은 뒤, 최대 5분 관측 한 번과 정보성 global proposal 한 번을 검증한다. 성공 또는 실패 증거를 남기고 정확한 자기 job·세션을 종료해 source/bridge를 복구한다. 기존 W03 승인은 재사용하지 않는다. 초기 가설의 새 Nav2 실행 전달은 별도 최소 계약을 검토 중이며, 그 구현과 새 runtime의 현재 정합/TF/품질 확인 전 실제 주행을 준비 완료로 표시하지 않는다.

## 전체 검사 원본과 판정

전체 Python은 3,237건 중 3,235 통과·2 skip, 114.906초다. 주 browser 최초 240건 중 `map_editor3d_full_source.spec.mjs` 3건은 runner PATH에서 기존 venv가 빠져 시스템 Python의 NumPy import에 실패했다. 나머지 237건은 통과했다. 코드나 기대값을 바꾸지 않고 기존 venv를 지정한 그 3건만 별도 포트에서 재실행해 모두 통과했다. 이 두 실행을 단일 전체 240 PASS로 합산하지 않는다. 이전 CI 문제인 ui_consistency 4건은 최초 전체 실행에서 통과했다.

동결 전후 HEAD·status·diff SHA가 같고 변경/신규 14개 파일 hash도 일치했다. C0가 통합 직전 현재 파일과 다시 대조했다. 원본 로그는 비공개 `/tmp/c1_3_freeze_20261101/`의 python.log, node.log, syntax.log, playwright.log, playwright-retry.log, competition-e2e.log 및 before.json/after.json에 있다. 기존 pinned 통합 270건은 저장소가 이미 사용하는 회귀 검사이며 확장 브랜치 통합을 뜻하지 않는다.

## 다음 연결 설계와 현재 오케스트레이션

초기 가설을 새 Nav2 실행에 전달하는 후속 구현은 `proposal_confirmed` 출처와 지도 기준 본체 가설을 유지하고, 정확 관측 세션의 정상 stop 수락 및 이후 inactive 관측을 별도 receipt로 연결한다. 옛 T_map_odom을 새 odom으로 복사하지 않는다. stop 기록 실패는 handoff만 막고 정상 stop은 계속 사용할 수 있어야 한다. C1.4 독립 문서 검토 후 로컬 구현·회귀 수리를 진행했으며 최신 상태는 별도 결과표를 따른다. 구현·테스트는 `99d5681a50c2322f4a326d7f2d4bc59e66e0e43e`로 통합했고 배포·실기는 NOT_RUN이다. TTL 120초, XY 0.25m, yaw 0.20rad는 로컬 초기 정책 후보이며 실기 적합성은 미검증이고 현재 장비 운영 기준으로 적용하지 않았다.

사용자 지시에 따라 정기 heartbeat는 PAUSED로 전환했다. 하위 채팅은 새 완료·실패·필수 의존 사항을 C0에 직접 한 번 보내고 C0가 근거를 분석해 다음 작업을 배정한다. 단순 수신 확인과 과거 결과 재전송은 하지 않는다. 모델 6.1 Terra/Extra High, 단일 장비 변경 담당, 사용자 질문은 담당 채팅의 질문 UI와 대시보드에서 처리하는 규칙은 유지한다.

## C0-W04C 실제 배포와 복구 상태

W04는 SSH control socket 만료로 인증 단계에서 중단됐다. 이전에 사용자가 승인한 비밀번호 인증을 대화형 입력으로 복구하고 strict host key 확인을 유지했다. W04B는 manifest 밖 `scripts/__pycache__/robot_scope_wireless_mapping_ssh_command.cpython-310.pyc` 1개로 전체 파일 집합 검사에 실패했다. 두 시도 모두 패키지·업로드·서비스·지도 변경을 수행하지 않았다.

캐시는 실행하지 않은 채 Python 3.10.12에서 manifest에 고정된 소스의 compile 결과와 code object 및 헤더 시각·크기를 대조해 일치를 확인했다. 생성자는 미확정이다. W04C에서 이 파일 1개를 동일 inode/bytes/hash/mode/mtime와 원래 경로 기록을 보존해 `/home/unitree/robot-scope-backups/c0-w04c-single-cache-20261101/`로 옮겼다. 캐시 전체 무시나 파일 검사 기준 완화는 없었고 기존 strict 검사로 base 2,261파일이 통과했다. 원본 복구 경로와 receipt를 남겼으며 실제 rollback은 수행하지 않았다.

정확 c414a519 Git archive를 사용한 새 release는 2,268파일, base 대비 변경16/삭제0이다. 보호 tar의 파일 집합·내용 hash, 독립 inode 복사, stage 전후 gate를 검증한 뒤 정상 restart API를 한 번 호출했다. 최종 실행 PID `82325`, cwd `/home/unitree/robot-scope-releases/robot-scope-c414a519bd18`; 새2268·기존2261 파일의 정확한 경로 집합·mode·hash와 runtime links, 실제 HTTP app.js/navigation.js/index.html/preparation.js가 일치했다. 지도·주석125개와 설정8개는 의도한 selector 경로 변경 외 모두 보존했고 교정/P1/P2도 같았다.

백업은 `/home/unitree/robot-scope-backups/c0-navigation-pair-c414a519bd18-20261101/`에 있다. 이전 release/backup을 유지했다. 복구가 필요하면 현재 gate와 실행본을 새로 확인하고 기존 selector-only 정상 restart 경로를 사용한다. 지도·교정·설정을 옛 백업으로 덮어쓰지 않는다.

재시작으로 선택이 null인 것을 확인하고 직전 fresh map1/map1_2D pin·교정을 재검증한 뒤 pair POST를 한 번 수행했다. 새 generation `6d5c7964a413423ea8c95e870aa10955`, pair valid, geometry/seed null, `INITIAL_HEIGHT_TILT_REQUIRED`, can_start=false다. 지도 선택은 운영 위치추정이나 주행 시작이 아니다. preparation GET은 HTTP200/2.5251초 1회이며 지연 해결로 판정하지 않는다.

13:51:03 KST 최종: Nav2/goal idle, lease inactive, deadman false, 명령0, 관측 STOPPED, ownership busy/unknown 없음, bridge active. source는 `/cloud_registered` 및 `/utlidar/robot_odom`, 주행 설정 revision `9a47e9d4a6c0d2b5beb0664cc1370a7bf6b70d647418815c5381f196d335645a` 그대로다. 속도0.5m/s·XY0.05m·yaw0.1rad·progress0.05m·controller10Hz와 ALL_DIRECTION_BASELINE을 보존했다. 관측·Nav2·seed·match·goal·실제 이동은 수행하지 않았다.

C0가 private 원본 `/tmp/c1_3_w04c_` 접두의 preflight/cache_move/strict/stage/before_activate/activate/final_verify/final_state 증거를 읽었다. W05는 별도 현재 정지 확인을 C1.4 질문 UI에서 받은 뒤 최대5분 관측1회·정보성 proposal1회 및 정상 정리·복구만 허용한다. 새 확인 전 장비 변경은 없다. 동시에 C1.1은 후속 handoff를 로컬에서 구현하며 W05의 배포본은 c414a519로 고정한다.
