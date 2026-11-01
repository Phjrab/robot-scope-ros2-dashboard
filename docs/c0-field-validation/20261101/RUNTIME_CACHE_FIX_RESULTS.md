# 2026-11-01 C0 실행 폴더 캐시 불일치와 최소 수리

## 1차 결과

W05 정지 관측 전에 현재 `c414a519bd18ece9ecf46469074046bb94dac33e` release의 엄격한 파일 목록 검사에서 manifest 밖 Python 캐시 1개가 발견됐다. 등록된 2,268개 파일의 hash/mode 검사 뒤 추가 파일 때문에 차단됐으며, 이 실행을 전체 배포 검사 PASS로 보고하지 않는다. bridge stop·관측 시작·proposal POST는 모두 0회였다. 사용자 정지 확인은 15:11 KST에 이미 받았으며 입력 미수신 상태가 아니다.

| 항목 | 결과 | 한계 |
|---|---|---|
| SSH 복구와 HTTP 9종 | PASS, HTTP 모두 200 / 0.476–1.625초 | 각 시점의 표본이며 물리 정지 증명이 아님 |
| 현재 PID/cwd·지도 쌍·교정 | PID82325, c414 release, 기존 선택 세대·map ID/revision·교정 일치 | 이 단계의 보호 133파일 hash는 별도 보존; strict 이후 검사는 차단됨 |
| 배포 파일 전체 집합 | FAIL: manifest 밖 캐시 1개 | 목록·mode·hash 검사를 완화하지 않음 |
| 캐시와 고정 원본 코드 비교 | PASS: CPython3.10.12에서 optimize0/1의 code object와 재귀 필드 일치 | marshal 재직렬화 bytes는 다름. 생성자 미상, 캐시 실행 없음 |
| 해당 import 경로의 캐시 기록 방지 | 로컬 구현 완료, 관련 28건 PASS | 실장비 미배포; 기존 캐시 제거 또는 다른 producer 차단이 아님 |
| 전체 Python 회귀 | 3,287건 중 3,285 PASS·2 skip, 실패/오류0, 123.097초 | 관련28건 및 과거 검사와 중복 합산하지 않음 |
| 정보성 제안·운영 위치추정·TF/Nav2·실제 이동 | 이번 차단 시점 NOT_RUN | 이 캐시 수리 검사는 위치 정확도나 주행 성공의 증거가 아님 |

## 실패 분석과 수리 범위

추가 파일은 `scripts/__pycache__/robot_scope_wireless_mapping_ssh_command.cpython-310.pyc`이며 10,084 bytes, mode0644, SHA-256 `605ff67a3a6825d525a2abe68b2905ac74c71ae33340bd527f29c2bc5a27aeaf`다. 대응 원본 source의 SHA-256 `a5940f93a90b8f901db63def9109ba40a87b4cf9bedd94b21e122a7b6f92d94a`와 manifest pin을 확인했다. 캐시를 import/exec하지 않고 header·code object·중첩 상수/bytecode/이름/파일명/line 정보 및 전후 파일 identity를 읽어 비교했다. 다른 extra와 비예상 symlink는 없었다. 이는 원본과의 코드 동등성 증거이며 raw 캐시 bytes가 재현됐다는 주장은 아니다.

코드에서 확인한 생성 가능 경로는 화면 초기 RealSense profile 조회 → `GET /api/v1/cameras/realsense/profile` → local profile runner → `robot_scope_realsense_local_command.py`의 sibling helper import다. 기존 child argv는 `python3 -I`로, `-B`가 없었다. 부모의 `PYTHONDONTWRITEBYTECODE`만 변경해도 isolated child에는 적용되지 않는다. 실제 파일 생성 당시 이 GET을 실행한 주체나 다른 producer는 확인하지 못했다.

수리는 `FixedLocalRealSenseProfileRunner`의 argv에 명시적 `-B`를 추가한 한 줄이다. `-I`, action allowlist, 고정 환경, timeout, `shell=False`를 유지했다. 회귀 검사는 실제 runner가 임시 benign helper를 자식 프로세스로 실행하고 sibling module을 import하도록 한다. 반환값·action·isolated flag·bytecode 금지와 `.pyc`/`__pycache__` 부재를 확인했다. 장비 helper나 서비스를 실행하지 않았다. 관련 RealSense 12건과 wireless profile 16건, ruff 및 diff 공백 검사가 통과했다.

## 실제 적용과 복구

예방 수정은 `f9a1d3c627cf702c90f9153f73165685ace47ae0`로 통합했으며 아직 장비에 적용하지 않았다. 전체 Python 검사 전후 변경 두 파일 hash가 같았다. 기존 JavaScript 코드는 변경하지 않았고 관련 smoke 28건을 수행했다. 실제 장비 정책은 `ALL_DIRECTION_BASELINE`이며 지도·교정·센서·Nav2 파라미터와 stop/dwell/source·품질 gate를 변경하지 않았다.

C0는 기존 가역 보존 도구를 현재 release의 정확한 cache SHA/inode/mtime/소유자와 PID/source/manifest/선택 세대에 고정해 C1.4에 배정했다. 파일 한 개만 원본 bytes·mode·mtime·경로·before/after receipt와 함께 백업한 뒤, 예외를 추가하지 않은 현재 target 전체 strict 검사와 보호 hash·selector·HTTP 검사를 다시 통과해야 한다. 과거 release의 캐시는 이 변경 범위가 아니다. 15:20:20 KST 해당 캐시를 `c0-w05-single-cache-20261101` 백업에 동일 inode/hash로 보존했다. 15:20:33 및 최종15:23:08 현재 target strict 전체2,268파일과 links/selector/HTTP4·보호 baseline 검사가 통과했다. 이후 관측의 센서 증거 거절과 정상 복구는 [W05 전체 결과](W05_SENSOR_EVIDENCE.md)에 구분해 기록한다. 보호133파일 전후 hash는 모두 동일했다.

예방 수정의 원복은 해당 argv의 `-B` 한 항목을 되돌리는 코드 변경이며 실장비 배포 원복과 구분한다. 캐시 원본의 복구는 기록한 정확 경로와 hash를 대조한 별도 가역 작업이다. 현재 캐시를 자동으로 실행 폴더에 다시 넣거나 지도·설정을 과거 백업으로 덮어쓰지 않는다.
