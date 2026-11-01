# 2026-11-01 C0 초기 가설 전달 구현·검증

이 문서는 정보성 초기 위치 제안을 새 Nav2 실행에 명시적으로 전달하는 후속 변경이다. 저장 지도 위치추정이나 실제 이동 성공 보고가 아니다. 기존 `review/20261030-c0-3d-field-sweep`에서 구현·테스트 19파일을 `99d5681a50c2322f4a326d7f2d4bc59e66e0e43e`로 통합했다. 소프트웨어 회귀와 표적 수리를 완료했으며 배포는 하지 않았다. 마지막 확인 장비 코드는 `c414a519bd18ece9ecf46469074046bb94dac33e`다.

## 기능별 현재 결과

| 항목 | 구현 | 소프트웨어 검사 | 배포 / 장비 비이동 / 실제 이동 |
|---|---|---|---|
| 명시적인 제안 확인과 지도 기준 본체 초기 가설 | 로컬 구현 | backend 자체 검사 및 최종 독립 21 PASS에 포함 | 모두 NOT_RUN |
| 정확 관측 세션의 정상 stop 수락·inactive receipt 및 한 번의 새 실행 결합 | 로컬 구현·결함 수정 | 최종 독립 21 PASS에 포함 | 모두 NOT_RUN |
| source 변경·복원 검출, 실패해도 기존 정상 stop 유지 | 로컬 구현·결함 수정 | 합성 source/실제 owner/async 경로 최종 독립 PASS | 모두 NOT_RUN |
| 현재 runtime·초기 위치·match receipt와 과거 이력 구분 | 로컬 구현·결함 수정 | 최종 판독 시각까지 신선도 검사 수리 후 독립 PASS | 모두 NOT_RUN |
| 명시 확인 UI·서버 복원·단계 상태 및 영구 무효와 일시 상태 구분 | 로컬 구현·수정 후 동결 | 표적 경계 7 PASS 뒤 최종 전체 Playwright 253 PASS에 포함; 중복 합산하지 않음 | 모두 NOT_RUN |
| 전체 통합 회귀와 Git 코드 통합 | 코드 99d5681 통합 | 주 브라우저 253, Node 715, 문법 113, pinned 통합 270, API 브라우저 10 PASS. Python 최초 오류와 표적 18 PASS는 아래 구분 | 미배포 |
| 현재 센서의 정보성 global 제안 한 번 | 별도 배포 c414a519 | 이전 소프트웨어 검사는 상위 보고서 참조 | W05 현재 정지 확인 대기; 이번 실기 NOT_RUN |
| 운영 저장 지도 보정·TF·Nav2 → P1 정지 → 녹색 버튼 → P2 | 기존 구현 보존 | 이 표의 합성 검사를 실제 연결 증거로 사용하지 않음 | 이번 실행 BLOCKED/NOT_RUN |
| 경사로 운영 위치추정 연속성·후방/측면 후보 | 기존 결과 보존 | 이번 연결 작업에서 가중치 변경 없음 | 새 실기 NOT_RUN; ALL_DIRECTION_BASELINE 유지 |

최신 backend 자체 검사는 120건 PASS로 보고됐다. handoff 28, operator bundle 20, proposal 16, preparation 16, operational quality 19, 초기 cycle 6, API 9, 기존 stop 6이다. 마지막 stop 6건은 테스트 안에서만 executor 문제를 피하려 `asyncio.to_thread`를 동기 대체했으므로 실제 async/thread의 독립 검사와 구분한다. 이것은 전체 저장소 검사나 실제 센서/정합/주행 증거가 아니다.

## 연결과 차단의 의미

정보성 proposal을 명시적으로 확인하면 서버가 지도·revision·교정·관측 세션·source와 본체 좌표 변환을 확인하고 `proposal_confirmed` 출처의 초기 가설을 기록한다. 확인만으로 관측 종료, Nav2 시작, INITIAL POSE, 정합, TF 또는 goal을 전송하지 않는다. 사용자 초기 위치 점, 정합 후 실제 추정 아이콘, 목표 표시는 별개로 유지한다.

정상 관측 stop의 dispatch 수락과 이후 inactive 확인은 구분한다. 정확한 세션·시작 시각·nonce·dispatch 경계를 확인하고 이전 실행의 `T_map_odom`을 새 실행에 복사하지 않는다. source 감시는 실제 관측한 변경만 판별하며 샘플 사이의 변화나 물리적으로 계속 정지했음을 증명하지 않는다. 관측과 새 runtime 사이의 감독 구간도 `SUPERVISED_GAP_UNMEASURED`로 표시한다.

로컬 후보 정책 TTL 120초, 초기 XY 차이 0.25m, yaw 차이 0.20rad는 실기 적합성이 미검증이다. Nav2 도착 오차·속도·progress·운영 품질 기준을 변경한 것이 아니다. TTL은 새 명시 정합 수락까지의 초기 사용 권한이며, 이미 수락한 같은 정상 runtime을 TTL 경과만으로 중단하지 않는다. 새로운 초기화에는 다시 유효한 조건이 필요하다.

`MATCH_ARMED`는 현재 실행의 정합 요청 수락 상태이며 정합 품질 통과나 주행 성공을 뜻하지 않는다. 실제 runtime instance·localization generation·INITIAL POSE stamp·match receipt가 신선한 health와 일치해야 한다. 과거 이력만 남거나 최신 상태를 확인할 수 없으면 geometry/reference를 준비 완료로 제공하지 않는다. 기존 정지/dwell/source/3스캔·품질/TF gate는 유지한다.

## 독립적으로 발견한 결함과 수리 상태

| 발견 | 최초 증거 | 수정·재검증 상태 |
|---|---|---|
| 같은 세션 stop 중복 dispatch, 다른 start 수락, receipt 문맥 손상 | 독립 최초 8건 중 3 FAIL | 수리 후 후속 독립 PASS에 포함 |
| 같은 job ID의 다른 map으로 이전 가설 복원 | 독립 복원 검사 1 FAIL 추가 | map·revision·phase 조건 수리 후 PASS |
| 확인 뒤 source 변경·복원 미검출 | owner 합성 재현 FAIL | stop 경계까지 bounded 감시; 최종 이전 독립 19 PASS에 포함 |
| 과거 MATCH_ARMED와 새 runtime 혼합 | owner 합성 재현 FAIL | 현재 세대·실제 receipt 결합 및 이력 분리; 이전 독립 PASS |
| UI가 일시 `HANDOFF_JOB_NOT_RUNNING` 뒤 같은 정상 실행에도 영구 무효 유지 | UI 재현 1 FAIL | 그 사유만 일시 표시로 분리; 후속 7 PASS. 영구 source/receipt/세대 무효·만료는 유지 |
| health 취득 뒤 대기 시간을 빼고 최신 MATCH_ARMED 표시 | direct/preparation GET 0.953/0.952초 지연 재현 FAIL | 내부 취득 경계와 원래 age를 결합해 0.75초 기준 적용; 최종 독립 재검증 PASS |
| confirm의 2.2초 manager 잠금 때문에 정상 source 감시를 유실로 오인 | 입력을 50ms마다 갱신해도 독립 FAIL | 느린 검증과 감시 잠금 분리·재진입 문맥 비교; 최종 독립 재검증 PASS |

이전 최종 독립 19/19 PASS 뒤 두 지연 경계에서 별도로 실패했다. 두 수리 후 실제 asyncio/to_thread와 원래 지연·차단 기대값을 유지한 독립 21/21 PASS(6.949초)를 확인했다. 관련 12개 파일 전후 hash가 같고 C0가 현재 핵심 파일을 다시 대조했다. 개발 중 서로 다른 snapshot의 검사 수를 합쳐 한 번의 전체 성공으로 표시하지 않는다. 위 지연 재현은 과거 실제 장비의 간헐 지연 원인이나 이동 gate 우회를 입증하지 않는다.

신선도 수리는 서버 내부 `capture_runtime_health(agent)`가 `RuntimeHealthSample`과 monotonic 취득 시각을 함께 만든다. raw dict나 외부 요청 시각을 신뢰하지 않는다. 원래 gateway age와 이후 실제 경과·rounding 0.001초를 한 번만 합산한다. 지도 검증 중 selection·교정·geometry가 바뀌면 재진입 검사에서 차단한다. 검증 시간을 줄이거나 기준을 완화한 것으로 보고하지 않는다. 실제 장비의 end-to-end 응답 시간은 미측정이며 느린 조회가 불확정으로 표시될 수 있다.

## 배포·복구 및 남은 증거

이번 로컬 변경으로 장비 서비스·지도·교정·source·주행 설정을 변경하지 않았다. 13:51:03 KST에 확인한 배포 c414a519, PID82325, Nav2/goal idle·lease inactive·명령0·관측 STOPPED는 그 시점의 읽기 결과다. 현재 상태를 새 관측 없이 단정하지 않는다. 기존 release와 백업을 보존하며 복구는 검증된 정상 selector/restart 절차로 수행한다. 지도·교정·설정을 옛 백업으로 덮어쓰지 않는다.

C1.4의 W05는 새 정지 확인 뒤 최대5분 관측 한 번·정보성 proposal 한 번과 정상 정리·복구만 허용한다. 운영 가설 채택·Nav2·정합·goal·실제 이동은 이 창에 포함하지 않는다. 그 결과와 독립/전체 소프트웨어 검사 후 C0가 다음 배포 및 비이동 연결 검증을 결정한다. 실제 이동에는 현재 현장 준비·정지 수단과 새 범위를 담당 채팅에서 확인한다.

코드 hash 및 원본 증거는 비공개 orchestration 상태와 각 담당 STATUS에 보존한다. 지연 재현 로그는 `/tmp/c1_3_delay_20261101.log`, fresh 입력 보완 재현은 `/tmp/c1_3_delay_b_fresh_20261101.log`다. 수리 후 독립 로그는 `/tmp/c1_3_delay_fix_20261101.log`다. 통합 코드 SHA는 `99d5681a50c2322f4a326d7f2d4bc59e66e0e43e`, 실제 장비 적용 정책은 기존 ALL_DIRECTION_BASELINE이며 이번 초기 가설 전달 코드는 미배포다. 로봇 지도·센서 원본·인증 정보는 Git 보고서에 포함하지 않는다.


## 전체 회귀 원본·표적 수리·통합 판정

`C13-HANDOFF-FULL-REGRESSION-20261101-01`을 C0가 로그와 파일 hash로 확인했다.

| 검사 | 실제 결과 | 구분 |
|---|---|---|
| 최초 Python unittest discover | 3,286건 중 3,283 PASS, 오류 1, skip 2; 129.874초 | 단일 전체 PASS가 아님 |
| 유일 오류의 API 모듈 표적 재검증 | 테스트 대역 보완 후 18/18 PASS; 실제 asyncio/to_thread | production 변경 없이 별도 실행 |
| Node 20 | 715/715 PASS | 최초 잘못된 Node 18 실행과 별도 |
| 프런트 문법 | 113개 PASS | 지정 Node 20 |
| 주 Playwright | 253/253 PASS; 8.6분 | 로컬 합성 HTTP fixture |
| 별도 실제 API mission 브라우저 | 10/10 PASS; 41.1초 | localhost 합성 실행이며 실제 로봇이 아님 |
| 기존 pinned competition | native 117 + traffic 97 + integration 56 = 270 PASS | C2_CROSS_REQUIRED=1, 확장 브랜치 통합이 아님 |
| Python에서 호출하는 Node geometry parity | 최초 전체 PASS 및 지정 Node 20 표적 1 PASS | 두 실행을 하나로 합산하지 않음 |

유일 Python 오류는 기존 `SelectionManager` 테스트 대역에 새 `check_match` 인터페이스가 없어 발생했다. `record_match_armed`도 함께 명시적인 spy로 보완하고 정확한 지도·세대, 내부 health sample, 거절 시 dispatch 0, 정상 match 1/goal 0을 검사했다. 실제 manager나 안전 gate를 테스트에 맞춰 완화하지 않았다. 전체 Python을 재실행하지 않았으며 최초 오류와 수리 후 모듈 PASS를 그대로 구분한다.

최초 Node 실행은 PATH에 Node20 디렉터리의 `/bin`이 빠져 Node18.19.1이 선택된 실행 설정 오류다. 그 실행의 686건 중 672 PASS/14 FAIL, 문법 모듈 오류, Playwright 시작 전 Node20 요구를 원본 로그에 보존했다. 올바른 환경에서 수행한 위 결과로 검증했으며 최초 결과를 지우지 않는다. 별도 Python 표적의 잘못된 클래스명 loader 오류와 owner 표적 실행 중단130도 미완료 이력으로 남긴다.

시작 HEAD `2ff4f84a77d421b8bf3cd93b10e96bca16793cf0`와 branch는 검사 중 같았다. 시작 변경·신규 20파일의 내용 hash는 전후 모두 같았다. 추가된 유일 변경은 `tests/test_operational_navigation_api.py`로 14:33:55.677830493 KST에 적용됐으며 원본 `cc2da06b2645118c4f1e90078212d6d5ce869223d9946c4d7aa580e6b035a285`에서 `3a7049ff87d62845ca64b723ec6b2af651fbf928b233eac3ba33b5825b526335`로 바뀌었다. 그 파일을 포함한 표적 검사 전후 hash도 같았다. 따라서 전체 실행이 단일 무변경 snapshot이었다고 주장하지 않는다. C0가 통합 직전 최종 21파일을 다시 대조했고 구현·테스트 19파일을 정확히 커밋했다. 이후 보고서 2파일만 최종 검사 결과를 반영했다.

비공개 원본은 `/tmp/c1_3_handoff_freeze_20261101/`의 `before.*`, `after.*`, `python.log`, `api-target.log`, `node20.log`, `syntax-node20.log`, `playwright-node20.log`, `competition-e2e.log`, `competition_*.log` 및 최초 환경 오류 로그다. 알려진 로컬 실패의 원인과 표적 수리 증거를 검토해 코드 통합을 진행했다. GitHub OS matrix/coverage/audit는 별도 결과를 확인해야 하며 실제 장비 검증을 대체하지 않는다.
