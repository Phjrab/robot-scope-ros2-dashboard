# C0 후속 1차 결과 — 현장 입력 대기

**OPEN_REQUIRED_FIELD_INPUT. 전체 실기 완료가 아니다.** 실행 가능한 비이동 항목을 먼저 확인했고, 현재 source 선택·새 P1/P2·새 시험창이 없어 이동 의존 항목을 BLOCKED로 남긴다. 가중치 구현 전에 동결한 1차 snapshot SHA256은 `530d0e3bba0591cf511b1d4c9a4a6c5a9ceae69009ed5e5b88948dcae71ddb42`다. 기존 [진행표](../20261030/CONTINUE_PROGRESS_20261031.md)의 C00~C06을 이번 지시서의 F00~F06에 대응시켰다. 과거 V00~V09 결과는 바꾸지 않는다.

첨부 후속 지시서를 실제 파일로 읽었다. 정합은 **USER_CONFIRMED_USABLE / 재조사 제외**로 인수하며 C0 정확도 PASS로 바꾸지 않는다. 뒤에 받은 명시적인 후방·측면 구현 지시는 기존 기록을 사용한 2차 후보 비교만 허용한다. 과거 HIGH_RESIDUAL 원인·원점·구/신 지도 비교는 재조사하지 않는다.

| ID | 항목 | 인수·실제 구현/배포 | 이번 방식·결과 | 근거·남은 일 |
|---|---|---|---|---|
| F00 | 현재 source·배포·제어 인수 | 기존 실행15706c4 / 변경0 | readback PASS, source 선택 BLOCKED | 입력/TF 갱신, selected=null/LEGACY_2D, gateway idle. 사용자 준비 source 선택 필요 |
| F01 | 3D Nav2 정지점 도착·측정 정지 | 기존 구현·배포 | BLOCKED_DEPENDENCY | source·새 P1/P2·현장 창 없음. 이번 goal0, 정밀 오차 미측정 |
| F02 | 정지/dwell→시험 녹색→다음 goal·출발·종료 | 기존 gate·배포 | BLOCKED_DEPENDENCY | 실제 success·3D source·정지/dwell 부재. 가짜 허가/상태 변경0 |
| F03 | 현재 운영 위치추정의 경사로 연속성 | 기존 matcher·배포 / 현재 비활성 | BLOCKED_DEPENDENCY | 기존3회 MANUAL_LIO_ONLY 자료 인수. 현재 운영 지도 관측과 구분 |
| F04 | 현재/목표 URDF·상태 | 기존 구현·배포 | 현재 표시 PASS, 새 목표 NOT_RUN | 현재 Go2 pose+12관절 신선도/화면 확인. 실제 새 goal 미발행 |
| F05 | 종료·제어권·자료·복구 | 기존 stop 경로 보존 | 자체 비이동 정리 PASS, 이동 종료 NOT_RUN | 임시 탭·2초 recorder 정상 종료. 타 소유 runtime 보존, lease inactive·명령0 |
| F06 | 전체 결과표 | 기존 결과 보존 | OPEN_REQUIRED_FIELD_INPUT | 실행 가능한 행 결과 기록 완료, 실제 이동 sweep 미완료 |

08:14:05 UTC 재조회에서도 입력 약10Hz, TF age 약1.3ms, bridge ready, lease inactive, 명령 전축0이었다. pipeline running과 gateway 주행 활성화는 다르며, 과거 canceled action을 이번 실패로 세지 않는다. 현재 지도/source·실제 파라미터·배포 경로는 기존 [진행표](../20261030/CONTINUE_PROGRESS_20261031.md)와 [집계 JSON](CONTINUATION_RESULTS.json)에 연결했다. 생성 YAML·교정·FAST-LIO 설정의 private 백업을 유지했다.

PCD 편집·저장, 기존2D Nav2와 보행 자체·기존 수동 기록은 INHERITED_EVIDENCE이며 이번 PASS 수에 중복 계산하지 않는다. yaw/속도/progress/rear 정책을 바꾼 1차 반복 주행은0건이다. 현장 의존 항목이 준비되면 이 표에 새 실행 근거를 추가하며, 기존 BLOCKED 시점의 근거를 삭제하지 않는다.

## 추가 R01~R04 — 1차와 분리한 후방·측면 후보

| 항목 | 구현 | 배포 | 동일 입력 비교 | 실기 |
|---|---|---|---|---|
| REAR_SIDE_QUALITY_V1 | PASS·18 새 회귀 | CODE_DEPLOYED_DISABLED |1,616쌍 완료·혼합/회귀·NOT_ADOPTED | NOT_RUN |

현재 기본 ALL_DIRECTION_BASELINE을 유지한다. [별도 비교와 한계](REAR_SIDE_COMPARISON.md). 사용자 추가 준비 이후 실제 지도/source·P1/P2 readback은 기존 snapshot과 구분해 인수한다.


## 후속 인수와 연결 보완 (18:16 KST 이후)

위 F00~F06은 가중치 구현 전 동결한 1차 시점의 결과다. 이후 사용자가 원래 지도와 P1/P2를 준비했고, 17:37 KST readback에서 기존 2D Nav2 READY와 저장된 두 점을 확인했다. 그러나 selected=null/LEGACY_2D였으므로 이를 3D Nav2 성공으로 세지 않았다. 정상 STOP 후 기존 map-family 증거를 이용한 최소 source 연결을 시도했으나 HTTP 응답이 20초 내 오지 않았다. 임시 map binding 교정을 즉시 원복했고 hash 보존·selected=null·idle·명령0을 확인했다. 시간 초과의 원인은 아직 확정하지 않았다. 이전 P1/P2는 그때의 2D revision에 속한다.

사용자는 이후 실제 편집 PCD `map1`을 선택했다. 편집본은 18,166개의 실제 점을 가진 불변 복사본이다. 변경 불가 표식이 2D 변환까지 막는 결함을 수정·배포했다. 사용자가 18:16:17 KST 변환 버튼을 누른 작업은 18:16:23 KST 성공했고 `map1_2d`가 생성됐다. 화면은 이전 idle snapshot을 재렌더하면서 TRACKING LOST를 표시했다. 실제 지도 생성 성공과 UI 추적 실패를 구분한다. [수정·배포·복구 기록](EDITED_PCD_CONVERSION.md).

후보 가중치 코드도 배포 release에 포함됐지만 기본 비활성이다. 활성 정책은 ALL_DIRECTION_BASELINE이며 운영 matcher는 선택되지 않았다. 실제 3D Nav2 이동, stop/dwell/녹색 버튼, 현재 운영 위치추정 경사로 실기는 여전히 미실행이다. 새 map1/map1_2d source 연결·P1/P2 적용 확인·현재 현장 창이 의존 조건이다. 기존 품질·stop·dwell·source 검사는 보존한다.
