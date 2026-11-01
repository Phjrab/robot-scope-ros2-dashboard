# C0 후속: CI fixture와 Nav2 전 위치 초안

## 기준과 최초 결과

- 기준 브랜치: `review/20261030-c0-3d-field-sweep`, 수정 전 HEAD `94a48bc4b98846d8dbf119c166f0cc2365281a8f`.
- 장비는 N1에서 검증한 `e24c52181fc4c1146fe42fcc7318a8dbd16903ee`에 남아 있다. 이 후속 작업은 로컬 구현·검증이며 신규 배포·관측·INITIAL POSE 전송·Nav2 시작·goal·이동은 수행하지 않았다.
- N1은 종료됐다. 당시 유효 센서 증거와 `GLOBAL_AMBIGUOUS` 거절을 현재 위치나 새로운 승인으로 사용하지 않는다.

| 검사 | 최초 결과 | 의미 |
|---|---|---|
| 94a48bc CI `41289128981`, Ubuntu 22.04/Python 3.10 | Python 3319건: 3316 PASS, 1 ERROR, 2 SKIP | 신규 scoped worker 테스트의 `SCOPE_PRIVATE_WORKDIR_REQUIRED` |
| 같은 CI, Ubuntu 24.04/Python 3.12 | Python 3319건: 3316 PASS, 1 ERROR, 2 SKIP | 같은 테스트·같은 workdir 복합 검사에서 오류 |
| 두 OS의 후속 Node/문법/browser/mission 단계 | SKIPPED | 앞선 오류로 실행되지 않았으며 성공이 아님 |
| competition-offline-integration | PASS | 별도 job 결과이며 두 OS 실패를 상쇄하지 않음 |
| CI artifact 목록 | 0개 | metadata와 기존 실패 로그를 별도 보존 |

이 CI를 재실행하지 않았다. GitHub job 시작·종료 metadata와 step/log 시각의 한 시간 차이는 원문 그대로 보존하며 추측으로 보정하지 않는다. 과거 49ed9e7의 카메라 browser timeout, e24의 CI 성공과도 구분한다.

## 테스트 fixture 수리

기존 테스트는 프로세스 UID만 1000으로 모의하면서 임시 작업 폴더의 실제 소유 UID는 실행 환경에 맡겼다. 실제 admission은 경로·디렉터리 종류·0700 mode·소유 UID 1000을 확인한다. 임시 폴더 소유 UID만 1001로 모의하면 동일 오류가 재현됐다. 원본 CI 로그에는 당시 UID와 각 predicate 값이 없으므로 두 CI job의 정확한 실패 predicate가 소유권이었다고 단정하지 않는다.

수정은 테스트의 해당 작업 폴더 소유 UID를 명시적으로 제어한다. UID 1001은 proof/exec 전에 거절되고 UID 1000은 기존 `-I -B` 명령으로 exec되는지 함께 확인한다. 실제 mode와 다른 파일의 metadata는 보존하며 제품 코드의 UID·scope·worker hash·bytecode 방지 조건은 변경하지 않는다. 미수정 임시본의 합성 재현은 1 ERROR, 수정 임시본의 관련 검사는 20 PASS였다.

## ②와 사전 위치 지정의 경계

현재 staged 3D/2D 경로는 작업 snapshot을 만들기 전에 지도 기준 본체 z·roll·pitch를 요구한다. 별도 센서 관측은 실행 중인 Nav2 및 제어 bridge와 소유권이 충돌하지 않아야 한다. 이는 해당 모드의 구현 계약이며 모든 Nav2 모드의 보편 필수 순서는 아니다.

기존 주행 지도는 위치를 그리는 도구와 실제 전송을 같은 runtime gate로 잠그므로 Nav2 전에 사용자 XY/yaw 의도를 표시할 수 없다. 전송과 별개인 로컬 초안을 기존 INITIAL POSE 도구에 허용하는 것이 후속 후보의 범위다. 이 초안은 높이·기울기를 생성하지 않는다. 현재 initialization proposal API는 XY/yaw 검색 힌트를 받지 않으며 자동 proposal이 모호하면 수동값으로 옮겨 gate를 우회하지 않는다.

새 현재 준비 조회에서는 Nav2/goal idle, 소유권 busy/unknown 없음, seed_geometry null, `INITIAL_HEIGHT_TILT_REQUIRED`가 확인됐다. pair generation은 N1과 달라졌으며 과거 generation을 재사용하지 않는다. 이 조회는 물리 정지 측정이나 새로운 관측 창이 아니다.

## 구현과 독립 검토 수리

기존 아래 INITIAL POSE 도구를 재사용해 Nav2 idle에서 미전송 XY/yaw 초안을 그릴 수 있도록 했다. 유효한 지도 조합·catalog·로드된 지도의 ID/revision과 generation을 비교하며 방향은 실제 드래그를 요구한다. 초안은 실제 위치·높이·기울기의 확인이 아니라고 표시하고 SEND handler에서도 거부한다. GOAL 및 기존 실행 중 INITIAL POSE 전송 조건은 유지한다. reload·지도/구성/실행 문맥 변경은 초안을 폐기하며 Nav2를 시작한 뒤에는 현재 위치를 다시 지정해야 한다.

C1.4가 발견한 구성 변경 요청 중 초안 유지 문제를 수리했다. 변경 시작 즉시 초안을 폐기하며 변경 후 새 준비 조회가 성공할 때까지 다시 그릴 수 없다. 추가로 기존 공통 준비 상태가 늦은 GET에 덮이는 경합을 C0의 합성 검사에서 1 FAIL로 재현했다. 성공·실패 응답 모두 요청 세대와 busy 상태를 검사해 이전 응답을 버리고, 현재 변경 후 조회를 수행하도록 수리했다. 마지막 두 조건은 독립 코드 재검토를 받았다. 이 검토는 실기 검증이 아니다.

초안과 기존 지도 helper는 별도 모듈로 분리했다. 이 과정에서 기존 Node 검사의 소스 파일 위치 의존 assertion은 실제 ID/revision 불일치 거절 검증으로 바꾸고 앱의 호출 연결 검사는 유지했다. `app.js`는 6898행으로 기존 6900행 미만 조건을 충족한다.

## 통합 검증 및 한계

| 순서와 snapshot | 결과 |
|---|---|
| CI fixture 수리 후 전체 Python | 3319건: 3317 PASS / 2 SKIP, 126.671초 |
| 최초 UI 통합 Node | 80개 파일 단위 결과 중 79 PASS / 1 FAIL. app.js 크기 제한 초과이며 개별 테스트 건수로 환산하지 않음 |
| 최초 UI 통합 browser | 51건: 45 PASS / 6 FAIL. C0 실행 PATH가 시스템 Python을 선택해 실제 API fixture의 fastapi import 실패; 원본 로그/아티팩트 보존 |
| 모듈 분리 후 전체 Node | 722건: 721 PASS / 1 FAIL. 기존 검사가 옛 파일 위치를 요구했음 |
| 해당 검사를 실제 helper 동작 검사로 갱신한 전체 Node | 722 PASS, 1.414초 |
| 수정 모듈·준비 문맥 수리를 포함한 전체 Python | 3319건: 3317 PASS / 2 SKIP, 127.121초 |
| 올바른 Python PATH 및 준비 문맥 수리 후 navigation browser | 53 PASS, 약 1.2분. 아래 공통 상태 fence 추가 전 snapshot |
| 공통 준비 상태의 늦은 응답 재현 | 새 경계 검사 1 FAIL. 오래된 generation으로 되돌아간 결과 보존 |
| 성공·실패 응답 fence 수리 후 관련 preparation/draft browser | 43 PASS, 53.8초. 이전 53건과 합산해 전체 browser 결과로 주장하지 않음 |
| 마지막 fence 후 관련 Node | 13 PASS |
| 문법·정적 검사 | 114개 dashboard JS module 문법 PASS, 변경 Python ruff PASS, diff check PASS |

Python skip 2건은 optional SVG plotting 및 rosbags 의존성 부재다. 전체 Python은 마지막 JavaScript 응답 fence 추가 전 결과이며 이후 그 변경의 관련 Node/browser 검사를 수행했다. 기존 성공 검사와 이후 변경의 검사를 구분한다. 신규 exact-commit CI는 게시 후 별도로 확인하며 94a48bc 실패나 e24 성공을 신규 커밋의 결과로 바꾸지 않는다.

실제 서버는 조회만 했으며 새 배포·관측·pose/goal 전송·Nav2 시작·이동은 NOT_RUN이다. 실기 복구 경로는 N1 문서의 e24/c414 보존 및 검증된 selector/lifecycle 경로를 따른다. 새 배포 시 현재 base와 정지·소유권·백업을 다시 확인해야 한다.

## 다음 의존

②의 지도 기준 본체 높이·기울기 근거는 여전히 미확인이다. 현 기능은 독립적으로 확인한 operator z/roll/pitch 또는 새 유효 관측에서 모호하지 않은 proposal과 명시 확인/handoff를 요구한다. 새 관측을 같은 조건으로 성공할 때까지 반복하지 않는다. 사용자 XY/yaw를 정합 prior로 사용해 나머지 자유도를 구하려면 별도 API·좌표 변환·출처·신선도·모호성 검증 계약이 필요하며 이번 UI 초안은 그것을 구현하지 않는다. 기존 seeded_local은 완전한 6DOF 입력을 요구하고 모호성이 미해결로 남으므로 이를 대체 경로로 사용하지 않는다.
