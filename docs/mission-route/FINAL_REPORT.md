# MR 소프트웨어 구현 보고

기록 UTC: 2026-10-15T06:45:34.358571+00:00. source `22c7913c879afcca536a78d552dcdf98f0f53098`. **전체 인수 PARTIAL**: 제품 backend/API/planner adapter·기존 coordinator와 UI 연결 및 소프트웨어 회귀 완료. effective runtime 정책 제공자(MR-MS-003)는 미연결이라 새 실행 시작은 차단된다. 실제 native·실기는 NOT_RUN이다.

## 사용 흐름

1. 미션 페이지에서 occupancy 지도를 선택하고 **지도 불러오기 / 새 미션**을 누른다. 지도 또는 주석에서 방문을 추가하고 목록에서 순서·복제·삭제·되돌리기를 조작한다.
2. 방문 설정에서 좌표/heading, 기본 도착 정책, 0~300초 대기, 출발 전·도착 후 확인을 정한다. 같은 POI를 여러 번 방문해도 각 visit ID와 작업 순서는 독립이다.
3. **미션 저장 → 작성 검사**로 저장/검사를 수행한다. CAS 충돌/오래된 지도 pin은 조용히 덮어쓰지 않고 재연결·복사 등 명시 조작을 요구한다. active 정의는 새 미션으로 복사해 편집한다.
4. **Nav2 계획 미리보기**는 실제 native 자원 창과 유효 context가 있어야 성공한다. 기본 설정은 비활성이다. 현재 환경에서 그려진 작성선이나 fixture 결과를 실제 Nav2 계획으로 표시하지 않는다.
5. **FLEXIBLE compile → 새 실행 만들기**는 방문 순서를 기존 coordinator 실행 구조로 변환하고 run snapshot을 만든다. 두 조작은 이동 명령을 보내지 않는다. **실행 시작**은 별도 admission을 거치며 현재 runtime proof가 없어 차단된다.
6. 실행 이력은 선택·조회·읽기 전용 export할 수 있다. revision/시각/outcome/attempts와 같은 지도 관측 궤적을 비교할 수 있다. maintenance/archive API는 없다.

E1 경로는 **E1 → 미션 초안**으로 가져와 검토·저장한다. 원본 geometry/revision을 유지하면서 기존 selector로 최대32 STOP 후보를 만든다. 원본 geometry의 모든 점을 필수 방문으로 해석하지 않으며 주문/pickup/delivery 작업 의미를 자동 변환하지 않는다. 명시적으로 작성한 반복 방문·작업은 보존한다.

최종 Chromium96개와 Node381개가 통과했다. 캡처의 responsive/CSS zoom/테마 검토는 synthetic UI 범위이며 실제 browser zoom·touch hardware는 미검증이다.

## 무엇이 실제 경로인가

| 표시/데이터 | 의미 |
|---|---|
| 파랑 점선 작성선 | 사용자가 작성한 방문 연결선. 충돌 없는 Nav2 계획이라는 증거가 아님 |
| 초록 native preview | 실제 ComputePathToPose 응답을 검증한 계획. synthetic 응답은 fixture로 표시 |
| 보라 dispatch 계획 | 각 leg 전 현재 pose에서 새로 확인한 계획. 이후 내부 재계획 경로와 같음을 보장하지 않음 |
| 주황 관측 궤적 | 운영 pose 관측을 epoch별로 기록. 위치 정확도 truth나 계획선이 아님 |
| `live_plan` | 현재 unavailable: `NAV2_RUNTIME_PATH_WITH_PROVENANCE_UNAVAILABLE` |

native adapter는 고정 `/compute_path_to_pose`, `GridBased`, `map`을 호출하고 timeout/자기 요청 cancel/응답 frame·quaternion·유한값을 검사한다. 실제 native 서버 호출은 이번 작업에서 NOT_RUN이다. live runtime path, 경로 기반 ETA/잔여거리·편차 증거는 제공하지 않는다. run의 `source_sha`/`runtime_sha`는 null이며 Git HEAD로 임의 보충하지 않았다.

## 저장 설정의 실행 반영

실제 MissionCoordinator code와 synthetic navigation fixture에서 annotation heading override의 goal 전달, 마지막 hold 유지, monotonic 대기·pause 잔여시간, 출발 전/도착 후 별도 확인 token을 검증했다. 따라서 이 설정들은 저장만 하는 필드가 아니다. 상세 설정의 HTTP 요청/저장/compile/실제 coordinator dispatch는 Python synthetic integration으로, UI 입력/polling/저장·조회는 browser fixture로 각각 검증했다. 브라우저 fixture 성공이 실제 장비 명령 성공은 아니다.

지원되는 실행은 순차 STOP/TASK와 NAV2_DEFAULT 도착 판정이다. action SUCCEEDED는 물리 정지 관측과 구분한다. photo/sit_then_rise/dock, 비기본 speed/arrival tolerance, PASS_THROUGH, CORRIDOR/STRICT, SLOW_ZONE/WAIT_ZONE runtime 적용은 지원하지 않으며 실행 가능한 것처럼 통과시키지 않는다.

각 leg는 fresh 운영 pose로 preflight하고 최신 context pin을 검사한다. `policy_provider` 연결은 아직 없고 기본 `{}`이므로 effective planner/footprint·runtime unknown/KEEP_OUT 적용 증거가 부족하면 실행을 거부한다. MR-MS-003은 **소프트웨어 연결 의존성**이며 단순 장비 확인 대기가 아니다. 실제 runtime 정책을 약화하거나 fixture를 production 증거로 사용하지 않았다.

## 기존 기능·실행·복구

legacy mission API/기존 coordinator/annotation 원본을 재사용하고 자유좌표 방문이 원본 annotation을 생성하지 않도록 분리했다. MR CSS는 `.mr-workspace` 범위다. 기존 advanced 주문/도식과 공유 client를 유지하는 접점을 구현했으며 최종 legacy/테마/MS CSS 전체 browser 회귀도 PASS했다. MS 전용 기능·사용자 지도·영상·bag·실험·서비스를 임의 수정하지 않았다.

MR↔MS는 같은 coordination lock과 기존 ownership gate를 사용한다. running/paused/canceling 동안 MS engine/map 변경, MS active 동안 MR/legacy 시작이 서로 차단되는 실제 code 교차 fixture8개가 PASS했다. 앱 hook MR-MS-001/002는 실제 앱 wiring·교차·전체 suite 근거로 software VERIFIED다. 실제 runtime 검증으로 확대하지 않는다. MR-MS-004의 source 분리 consumer는 적용/fixture 검증됐고 추가 공유 요청 상태는 PROPOSED다.

마지막 대기·사후 확인을 마쳐야 완료한다. skip/failed/uncertain을 정상 완료로 숨기지 않는다. goal ID/세대가 다른 결과는 현재 방문을 완료시키지 못한다. 취소가 불확실하면 ownership을 유지하고 새 goal을 막는다. paused를 포함한 재시작은 interrupted이며 자동 resume/ARM/재전송이 없다. 외부 작업의 generic exactly-once executor는 구현하지 않았다.

정의와 run 이력은 분리하고 export는 token 없이 `executable=false`다. 상한은 정의64/run32/request receipt256/JSON512KiB/events·logs200/trajectory256이다. maintenance/archive API가 없어 장기간 운용의 정리 절차는 남아 있다. 포화·저장 실패가 pause/abort를 막지 않으며 durable audit를 남기지 못하면 `audit_warning`을 반환한다. 자동 이력 삭제·기존 데이터 migration은 수행하지 않았다.

## 검증·게시·장비 상태

| 범위 | 결과 |
|---|---|
| source / 파일 | `22c7913c879afcca536a78d552dcdf98f0f53098`, source/tests30개. SOURCE_MANIFEST.json에 모든 경로·SHA256 |
| focused Python | 83 PASS / skip0 / fail0,2.557초. MR/MS actual code 교차8·NativePlanner synthetic transport4 포함 |
| 전체 Python | 1939 발견 / 1937 PASS / skip2 / fail0,81.974초 |
| 전체 Node | 381 PASS / skip0 / fail0 |
| Ruff / configured mypy / syntax / diff / secrets | PASS. mypy는 설정된4 modules 범위 |
| 전체 Chromium | 96 PASS / skip0 / fail0 / flaky0,151.110초. local synthetic HTTP fixture |
| 화면 | dark/light,1440/1280/1024/portrait/mobile,CSS200% zoom fixture 검토 |
| 실제 native / 실기 / 배포 | NOT_RUN |
| exact MR 게시/CI | b42b28f push, CI38694446361 두 Linux 환경 success |

Python skip은 optional rosbags 미설치와 macOS에서 Linux /proc 전용 검사 불가다. 실제 browser200% zoom·touch hardware는 NOT_RUN이다. 실제 실행 명령·시각·원본 log hashes·fixture 종류는 VALIDATION.json, 인수45개 행은 ACCEPTANCE_MATRIX.md에 있다. MS 이전 단독 CI 결과를 MR 결과로 사용하지 않는다.

MR source30개 중 합의된 shared source/tests4개는 MS 단독 창에서 적용하고 coherent MR commit 포함을 확인했다. MS 문서는 MR이 고치지 않았다. docs/evidence는 MR 별도 commit으로 보존한다.

source rollback은 MR source commit의 변경만 검토해 정상 revert한다. 새 coordinator 저장 필드와 이전 strict reader의 호환성은 별도 data rollback 검토가 필요하다. 운영 데이터 root를 reset하지 않는다. 서비스 복구/재시작도 별도 장비 창이며 source/data/service rollback은 이번에 수행하지 않았다.

다음 최소 작업은 MR-MS-003 read-only policy 계약의 소유권 수락/연결과 영향 검증이다. run/receipt 포화 maintenance 절차도 남아 있다. 단계27 별도 조건 전 배포·서비스 재시작·초기 위치·ARM·motion goal·실이동은 하지 않는다. CORRIDOR/STRICT/무정차/teach-repeat는 후속 범위다.

## 원격 게시·CI 확정 기록

기록: 2026-10-15T06:57:10.887581+00:00 / KST 2026-10-15T15:57:10.887581+09:00. source `22c7913`와 문서 `b42b28f`를 origin/main에 정상 push했다. exact tip `b42b28f9a4fdbb98a60692e90c677aaf5f9ddf34`의 [CI 38694446361](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38694446361)는 **success**, UTC 2026-10-15T06:46:31Z → 2026-10-15T06:55:01Z다. Ubuntu24.04/Python3.12와 Ubuntu22.04/Python3.10 각각 Python1939(1938 PASS/skip1/fail0), JS381 PASS, Chromium96 PASS, 정적·secrets·의존성 감사·coverage74% 검사를 통과했다. skip은 optional rosbags backend 미설치다. 상세 job 시각·log hash는 CI.json, 로컬 dirty tree 실행과 원격 clean commit 검증의 구분은 VALIDATION.json에 있다.

이 기록은 source 변경 없는 문서 후속 commit으로 보존한다. 이후 문서 tip의 CI는 별도 확인하며, 위 run은 명시한 b42b28f만 검증한다. 전체 인수 PARTIAL과 MR-MS-003 software BLOCKED/native·실기 NOT_RUN은 그대로다. 장비/서비스 변경 없음. 다음은 소유권 수락 뒤 runtime policy provider 연결·실제 증거 검증이다.
