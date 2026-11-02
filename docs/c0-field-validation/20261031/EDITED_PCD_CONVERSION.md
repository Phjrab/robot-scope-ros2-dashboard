# C0 편집 PCD의 2D 변환과 추적 복구

**실제 사용자 변환 성공 / 화면 추적 오류 재현·수정.** `map1`은 기존 지도에 주석만 붙인 항목이 아니라 18,166점의 실제 PCD 복사본이다. 편집 이력에는 입력23,890점에서5,724점을 제거한 기록이 남고 원본은 보존된다. `manageable=false`는 불변 manifest의 이름 변경·삭제 방지용이다. 기존 UI와 서버가 이 표식을 2D 변환 읽기에도 사용해 `map1`을 제외했다.

## 수정과 실제 결과

변환 수정 SHA `67e6fc5f85a01318c0aa492484356455878878b9`는 이름 변경·삭제 권한을 열지 않고, 관리 루트의 full_source/m 단위 편집 PCD만 manifest/revision/SHA/frame/점 수를 검증해 읽는다. publish 전에도 다시 검증하며 manifest-only race는 실패·정리한다. 원본을 수정하지 않고 새 PGM/YAML·map-family를 생성한다.

| 실제 사용자 작업 | 결과 |
|---|---|
| job | `e3a49a7fa5c94b22b815a50ca5f0de8e` |
| 시작/완료 UTC | 2026-10-31 09:16:17.184522 / 09:16:23.219638 |
| 종료 상태 | succeeded / exit_code0 |
| 출력 | map1_2d.yaml + map1_2d.pgm, 170×166, 0.05m/cell |
| 입력/슬라이스/밀도 필터 후 점 | 18,166 / 9,318 / 9,048 |
| 점유 셀 | 3,292 |
| 변환 설정 | z_min=-0.2m, z_max=0.8m, XY radius0.1m, min_neighbors10, background=unknown |
| 결과 map ID | `17b3e78ac06cc92af38b86f9` |
| 결과 revision | `e220cbbff862ea52ce92dc8c269cca55867a6cb8dbae1fb5f786cbb209dd7912` |
| YAML SHA256 | `c595b3eaaf46c0b34cffa29a0ea61210e79d016fd5d49acd5707fa7bee45a5de` |
| PGM SHA256 | `50a3ad23f6a7eea55dd98a57bd0bae37f4818cb8ea019500c3fb3de9283ec5e2` |
| family SHA256 | `13949e376b4df9d424deb3a5522562e8c1860de678800bb3b1fd070af8c4a5c4` |

map-family는 실제 source map1 ID `49ea555eea2f4ca1adaea223`와 revision `c9ad9bcc4c8b7c02a47a0db5822707853110b60cb4b9ef837e42b0c32e3c823e`를 가리킨다. 출력의 존재만 보고 성공을 추정하지 않고 서버의 동일 job 성공과 파일·metadata를 함께 읽었다. UI에서 저장 2D 지도 선택과 실제 그림을 확인했다. 자동 운전 source 선택·Nav2 실행은 이 동작과 별개다. 버튼을 중복 실행하지 않았다.

TRACKING LOST 원인: `refreshTopics()`가 cached mapping snapshot을 다시 렌더할 때 POST 이전 idle operation이 남아 있어 새 예약 job 추적을 취소할 수 있었다. tracking 판정을 새 mapping HTTP 응답에서만 호출하도록 분리했다. 다른 fresh job/idle이면 중단하는 보호와 request generation 검사는 유지한다. accepted→cached idle topic render→fresh saving→fresh success→fresh mismatched idle 순서의 실제 renderer 회귀를 검사했다. 변환 알고리즘·센서·교정·제어 정책은 이 UI 수정에서 변경0이다.

## 검증과 배포

변환 수정 전체 Python3,159건 통과(skip2), JS701건 통과, 관련 Python60건 통과, 새 Jetson 회귀4건 통과. Ruff·mypy 기존4파일 scope·112 JS module syntax·secret scan 통과. 코드67e6fc5 원격 CI [41187163460 SUCCESS](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41187163460). 후보 c719672 원격 CI [41184320285 SUCCESS](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41184320285).

67e6fc5는 `/home/unitree/robot-scope-releases/robot-scope-67e6fc5f85a0`에 추적 파일2,243개 hash를 검증해 설치했고 18:16 KST PID221740·HTTP·실제 JS asset hash까지 확인했다. 기존 release15706c4는 보존했다. 백업은 `/home/unitree/robot-scope-backups/c0-map-conversion-67e6fc5-20261031`이다. selector의 ROBOT_SCOPE_DIR만 변경했다.

배포 중 실패와 복구: 최초 tracked-only release에 무시된 `.venv`·`workspaces` 링크를 누락해 새 PID/cwd가 보여도 HTTP 시작은 `ModuleNotFoundError: uvicorn`으로 실패했다. PID만으로 완료라고 안내한 것은 잘못이었다. 기존 release와 정확히 같은 두 링크를 연결하고 의존 import를 확인해 정상 HTTP로 복구했다. 새 패키지를 설치하지 않았다. 향후 staging은 링크와 dependency import까지 활성화 전에 확인한다. 최종 HTTP 회복은09:10:27 UTC였다.

설정/지도/기존 dirty checkout 보존을 hash와 상태로 확인했다. 교정5025e83b…·FAST-LIO3d3fd83f…·shim95c6ee9b…·Nav2 preset71933bad…는 동일하다. 기존 yaw/xy0.1rad/0.1m, 속도0.25m/s,10Hz, SimpleProgressChecker는 변경하지 않았다. 생성 YAML69804bc0…는 이전 idle 파일의 보존이며 현재 live 실행 검증을 뜻하지 않는다. 후방·측면 코드는 release에 포함됐지만 기본 ALL_DIRECTION_BASELINE, 후보 비활성/NOT_ADOPTED다.

## 복구 경로와 제한

지도·설정은 이 변경에서 원복할 필요가 없었다. rollback이 필요하면 먼저 정상 idle·lease inactive·명령0·lifecycle blockers 없음 확인 후, private backup의 이전 selector를 원자 복원하고 정상 service restart API를 사용한다. 이전 release15706c4와67e6fc5, 기존 가상환경/overlay는 보존한다. 성공은 PID/cwd뿐 아니라 HTTP·코드/asset hash·source·control readback까지 확인한다. 실행 중 정책 파일을 hot edit하지 않는다.

이 기록은 지도 변환·UI 연결 보완이다. 현재 3D Nav2 도착·정지/dwell·녹색 버튼·운영 경사로 연속성은 [전체 표](CONTINUATION_RESULTS.md)의 미완료 항목이다. 기존 gate를 우회하거나 이동/자세 명령을 보낸 일은0건이다. raw map·위치 좌표·교정 전체·화면/로그는 private이며 공개 파일에는 요약과 hash만 남긴다.


## 최종 readback — UI 추적 수정 후

코드 `8dd087243ecc6ca12146e07cc2b6b8ca5d56e298`, 실제 release `/home/unitree/robot-scope-releases/robot-scope-8dd087243ecc`, PID **241880**, UTC **2026-10-31T09:28:33.371224+00:00**. 추적 파일2243개 검증 및 HTTP의 app.js hash `57fa417bca00ae5c1bda39cb8d368fe8f8fd5792754a65fd1d2a39e877cbdc14`가 release와 일치했다. `.venv`와 `workspaces`는 이전 target을 활성화 전에 연결·검증했다. 정상 idle lifecycle restart 뒤 HTTP까지 성공했으며 이번 staging에는 의존성 오류가 없었다. map1/기존 지도·새 map1_2d PGM/YAML/family·교정·source 선택·control/preset 설정 byte hash가 동일했다. selector의 release 한 줄만 바뀌었다.

최종 pipeline/goal idle, lease inactive, deadman=false, 전축 명령0, selected=null/LEGACY_2D다. 이는 물리 정지 측정이나 현재3D Nav2 성공이 아니다. 후보 코드는 포함됐지만 비활성·NOT_ADOPTED다. 바로 이전67e6fc5 release는 보존했고 selector 백업은 `/home/unitree/robot-scope-backups/c0-conversion-tracking-8dd087243ecc-20261031`에 있다.

UI 추적 수정 재검증: Python3,159건/102.490초 PASS(skip2), 직접 JS assertion701개 PASS 및 파일 runner77개 PASS, 새 cached-topic race 검사 PASS,112모듈 syntax·Ruff·mypy·secret scan·diff check PASS. 첫 전체 Python 실행은 제한 환경에서 진행이 멈춰 이번 전용 PID만143으로 종료하고 기존 호스트 환경에서 전체를 다시 통과했다. 이 종료를 로봇/기능 실패로 세지 않는다. [공개 집계 영수증](EDITED_PCD_CONVERSION.json). 새 센서 기록·자동 goal·자세 명령0건.


최종 UI 확인: 기존 사용자 탭에서 map1_2d를 선택했고 실제 2D 그림·170×166·FRAME map·SAVED2D 표시를 확인했다. 사적 화면을 로컬 증거로 저장했다. 재기동 후 agent 임시 탭은 초기 화면 로딩에 머물러 닫았고, 정상 동작하는 사용자 탭은 보존했다. 새 변환을 추가 실행하지 않았으므로 화면 수정 이후의 두 번째 실제 변환 end-to-end는 NOT_RUN이다. 재현 회귀와 served code hash 확인을 실제 새 변환 성공으로 대체하지 않는다. 추적 수정8dd0872의 원격 CI [41188793754](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41188793754)는 보고 시점 IN_PROGRESS이며 완료 성공으로 세지 않는다.
