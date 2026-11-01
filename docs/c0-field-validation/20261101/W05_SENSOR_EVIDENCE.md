# 2026-11-01 C0-W05 정지 관측 1차 결과

## 전체 결과표

사용자의 15:11 KST 정지 유지 답변을 받은 뒤 새 W05 범위에서 관측 한 번을 수행했다. 이전 수동 지형 기록이나 과거 성공을 이번 실행 결과로 합산하지 않는다. 실제 이동·Nav2·INITIAL POSE·운영 정합·TF·goal 명령은 0회다.

| 항목 | 이번 결과 | 증거와 의존 관계 |
|---|---|---|
| SSH 연결 복구 | PASS | 기존 인증·known_hosts로 복구, 이후 실제 PID/cwd 조회 |
| 실행본 전체 파일 검증 | 최초 FAIL → 정확 캐시 보존 후 PASS | 현재 c414 release 2,268파일의 집합/hash/mode·runtime links·selector·HTTP4; 최종 복구 뒤에도 PASS |
| 현재 지도·교정·선택 세대 | PASS | map1 / map1_2D, 기존 ID/revision·교정 및 선택 세대 일치; geometry는 null |
| 관측 전 정지·소유권 검사 | PASS | Nav2/goal idle, lease/deadman false, 명령0, 관측 STOPPED, busy/unknown 없음; 실제 물리 정지 자체의 센서 증명은 아님 |
| FAST-LIO 관측 세션 시작 | PASS | start 1회, 15:21:28 KST READY |
| 준비 화면의 현재 cloud/pose 증거 | FAIL / 후속 BLOCKED | HTTP200이나 `evidence.valid=false`, `OBSERVATION_STALE_OR_SOURCE_INVALID`, cloud/pose null |
| 현재 센서로 정보성 global 제안 | NOT_RUN | 위 입력 조건 미충족으로 POST0회, scope/계산/잔차·겹침·모호성 미측정 |
| 새 초기 가설·저장 지도 보정·TF/Nav2 연결 | BLOCKED / NOT_RUN | 유효 센서 증거·제안 및 새 코드 적용 이후 비이동 검증에 의존 |
| P1 도달·정지/dwell·녹색 버튼·P2 | BLOCKED / NOT_RUN | 운영 위치·TF·source 조건 및 별도 새 이동 시험창에 의존 |
| 경사로 운영 위치추정 연속성 | BLOCKED / NOT_RUN | 현재 운영 위치추정 연결에 의존; 기존 수동 보행 기록 반복 없음 |
| 관측 종료·source/bridge 복구 | PASS | 정확 세션 stop1회, 원래 source 정책/선택 복원, bridge active 및 최종 idle/명령0 |
| 지도·주석·설정 보존 | PASS | 125 map/annotation + 8 config, 총133개 전후 key/hash 동일 |

## 실제 실행·시각과 적용 상태

실제 배포 SHA는 `c414a519bd18ece9ecf46469074046bb94dac33e`, PID82325, cwd는 해당 c414 release다. 15:20:33 및 15:23:08 KST strict 검사 PASS를 확인했다. 새 handoff 구현 `99d5681a50c2322f4a326d7f2d4bc59e66e0e43e`와 캐시 예방 수정 `f9a1d3c627cf702c90f9153f73165685ace47ae0`는 장비 미배포다.

15:21:08 정상 bridge stop 1회는 HTTP202 뒤 작업 성공과 inactive를 확인했다. 관측 start 1회 뒤 READY가 됐으나 준비 GET은 7.324초, 같은 시간 별도 operational GET은 6.482초였다. 준비 응답에서 유효한 cloud/pose의 정확 stamp·source epoch를 확인할 수 없어 제안 계산으로 진행하지 않았다. 재POST·입력 반복 조회로 성공을 기다리거나 조건을 완화하지 않았다.

15:21:56 같은 관측 세션을 확인하고 15:22:00 정상 stop 1회를 요청했다. HTTP 응답은 1.267초, 반환 상태는 STOPPING이었다. 15:22:08 STOPPED/inactive/job_pending false를 확인했다. 약47초는 **관측 시작 요청부터 STOPPED 확인까지**이며 stop 대기시간이나 로봇 물리 정지 시간으로 표현하지 않는다.

원래 odometry 자동 선택·requested 빈값과 source 정책/선택을 복원했다. pointcloud origin의 메모리 표시만 `persisted`에서 `user`로 바뀌었으며 영구 source 설정 hash는 동일하다. bridge start 1회도 성공했다. 최종 bridge active/ready/authenticated/connected, 상태 age0.093초, Nav2/goal idle, lease/deadman false, 명령0, 관측 STOPPED, busy/unknown 없음, active global job 없음이다. 이는 최종 읽기 시점의 결과다.

정확한 캐시 한 파일의 원본과 receipt는 `c0-w05-single-cache-20261101` 백업에 보존했고 실행 폴더로 되돌리지 않았다. 현재 strict 검사를 다시 통과했고 과거 release는 변경하지 않았다. 자세한 비교·로컬 예방 수정은 [캐시 수리 결과](RUNTIME_CACHE_FIX_RESULTS.md)를 따른다. 기존 지도·교정·주행 설정과 `ALL_DIRECTION_BASELINE`, stop/dwell/source·신선도·품질 기준은 유지한다.

## 실패 분석과 2차 후보

관측 세션의 READY와 준비 응답의 evidence 유효성은 서로 다른 검사 결과다. 이번 증거로 확인된 것은 후자가 거절됐다는 사실이다. 두 느린 GET의 동시성만으로 지연이 원인이라고 확정할 수 없으며 cloud/pose null을 실제 센서 발행 중단으로 단정할 수도 없다.

첫 결과를 보존한 뒤 c414/current 코드의 정확 거절 분기·health/source 취득 시각·지도 검증·최종 신선도 계산과 저장된 W05 타임라인을 독립 분석한다. 필요한 경우 정확 W05 세션의 기존 로그만 읽는다. 새 관측, 과거 지도 정합 문제 재조사, 허용 신선도·품질 기준 완화는 이 분석에 포함하지 않는다. 결정적인 로컬 재현과 최소 수리 후보를 먼저 검토한 뒤 별도 장비 작업창을 결정한다.

원본은 비공개 W05 증거 폴더의 단계별 API JSON, `inputs.json`, `operational.json`, `hashes-before.json`/`hashes-after.json`, `strict-target-after.json`/`strict-target-final.json`과 C1.4 STATUS에 보존했다. 공개 문서에는 원시 지도·점군·실제 좌표·인증정보를 넣지 않았다. C0가 해당 입력 오류, strict 두 결과와 보호파일 전후 일치를 직접 대조했다. W05는 종료됐고 장비 변경 담당은 C0로 반환했다.
