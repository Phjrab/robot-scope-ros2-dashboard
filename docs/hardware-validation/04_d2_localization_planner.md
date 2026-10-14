# 04 — D2 onboard 연결과 실제 Nav2 planner 검증

2026-10-14. Run ID: `run-20261014T041650Z`.

**D2 onboard의 최소 소프트웨어 연결·회귀와 격리된 실제 Nav2 planner 실행을 완료했다. 운영 localization과 D2 live candidate는 BLOCKED이며 05단계 이동은 미승인이다.** 사용자는 대시보드에서 새로 재매핑한 뒤 초기 위치를 제공하기로 했다. 현재 로봇의 지도 좌표를 임의로 만들지 않았다.

## A — D2 지원 변경과 실제 실행본

기존 01단계 FEATURE_GAP은 현재 장비 실행본에도 존재했다. 장비의 D2 observer/manager opt-in은 각각 0이다. 장비 checkout은 clean `416d25c`; 이번 측정의 FAST-LIO readback도 dense false였다. 이번 소프트웨어 변경을 이 실행본의 실기 PASS로 사용하지 않는다.

개발 base `48d33df`에 다음만 변경했다.

- [공유 지원 계약](../../robot_dashboard/relocalization/profiles.py)에 onboard와 기존 competition FAST-LIO 프로필을 명시한다. observer의 실제 profile 표시, factory의 exact profile 일치, manager preflight가 같은 계약을 사용한다. unsupported profile과 observer/runtime mismatch는 계속 거부한다.
- [query config 선택](../../scripts/select_fastlio_query_config.sh)을 분리했다. onboard D2 명시 opt-in 1일 때만 dense config를 선택한다. 모순된 explicit config·invalid opt-in·allowlist 밖 config를 거부하며 direct DDS·센서 NIC·기존 preview 경로는 보존한다. wireless wrapper의 기존 local DDS 선택은 유지한다.
- source age/future/gap, generation, QoS/cardinality, stationary, query density, known-free/clearance/KEEP_OUT, map-family/revision, backend allowlist와 physical-safety 확인을 느슨하게 하지 않았다. initialpose/apply/control 경로를 추가하지 않았다.

새 테스트는 두 profile의 observer identity와 정지/lease/freshness/QoS/cardinality gate, factory profile mismatch, dense opt-in 및 conflicting config를 확인한다. 기존 구조적 runner 검사 두 개는 selector의 새 위치를 검사하도록 갱신했다. 최초 전체 회귀의 두 structural failure는 private log에 보존했다.

장비 배포·서비스 재시작·D2 live job은 수행하지 않았다. 승인 범위는 확보됐지만 정확한 새 map-family/revision·실제 위치와 적격 입력이 아직 없어 운영 실행본을 교체해도 후보 검증의 선행 조건이 풀리지 않는다. 기존 설치·실행본·타 작업 자원을 보존한다. 새 지도·위치가 전달되면 이미 승인된 04 범위에서 정확한 배포 대상과 복구를 고정하고 이어갈 수 있다. 후보는 자동 적용하지 않는다.

## 지도 조사와 B — 운영 위치

현재 map catalogue와 실제 PCD/PGM/YAML/family 문서의 hash를 읽었다. 13개 occupancy 이미지 중 원래 3D→2D 지도 일부는 known-free 0이며, 일부 편집본은 unknown 0이다. unknown을 free로 변환하거나 편집된 free-background 지도를 검증된 주행 지도로 승인하지 않았다. 세부 지도 identity·revision·conversion·annotations는 private inventory에 보존했다.

현재 실제 위치·방향과 사용할 새 지도 revision이 아직 없다. `(0,0,0)`이나 planner의 실험 시작점을 운영 초기 위치로 넣지 않았다. localization-only·초기 위치 적용·단일 운영 TF authority·실제 구조와의 정렬은 BLOCKED다. 사용자가 새로 재매핑하고 위치를 알려주기 전에는 이 항목을 READY/정확도 PASS로 올리지 않는다.

## C — 실제 planner 실행

내부 장비의 Nav2 1.1.20 `nav2_navfn_planner/NavfnPlanner`를 실제로 실행했다. controller server, behavior server, BT navigator, control bridge 연결은 만들지 않았다. 별도 domain 83 + localhost-only + 실험 namespace + 전용 TF remap을 함께 사용했다. 기동 전 domain이 비었고 graph에서 `cmd_vel`, sport/control, NavigateToPose, FollowPath endpoint가 없음을 확인했다. `ComputePathToPose`만 호출했다. 두 실행의 소유 planner는 모두 exit 0으로 종료했다.

plugin/footprint 설정은 기존 source의 Navfn A*, tolerance 0.5 m, `allow_unknown=true`, radius 0.22 m, inflation 0.25 m, cost scaling 5를 사용했다. 관측 장애물/scan layer는 포함하지 않아 운영 costmap 전체 검증은 아니다. synthetic map 시험과 기존 실측 occupancy 시험을 분리했다.

| 입력·case | 실제 결과 | 해석 |
| --- | --- | --- |
| synthetic 연결 free 목표 | SUCCEEDED, path 27 poses | 실제 Nav2 planner 실행 확인 |
| synthetic occupied | ABORTED, path 0 | 거부 확인 |
| synthetic unknown | SUCCEEDED, path 108 | **FAIL — unknown 거부 요구와 현재 allow_unknown=true 정책의 공백** |
| synthetic 단절 통로 / 지도 밖 / wrong frame | 각각 ABORTED, path 0 | 거부 확인 |
| 기존 실측·편집 occupancy, free 목표 | SUCCEEDED, path 42 | recorded map 입력 처리·계획 성공 |
| 같은 recorded map occupied / 지도 밖 / wrong frame | 각각 ABORTED, path 0 | 거부 확인 |

recorded map의 시작점은 deterministic known-free clearance cell이라는 **실험 입력**이다. 현재 로봇의 실측 pose가 아니다. edited historical map을 운영 지도 선택·초기 위치에 쓰지 않았다. occupancy/YAML hash, dimensions/resolution, 실제 시작/목표 좌표와 결과는 private `planner-recorded-execution.json`에 보존했다. 해당 결과는 운영 위치 정확도·주행 가능성의 증거가 아니다.

unknown 성공은 현재 plugin의 명시적 정책과 일치한다. 요구조건과의 차이를 기록하고 수치나 입력을 바꿔 통과시키지 않았다. 운영 wrapper의 unknown 목표 fence는 이번 격리 native-action 시험에 포함되지 않는다. KEEP_OUT filter가 tested config에 없고 실제 annotation→costmap 반영은 BLOCKED다. native ComputePathToPose는 map revision을 운반하지 않으므로 revision fence의 운영 경로 검증도 NOT_RUN이다. 격자 연결성만 검사한 WP04와 이 실제 action 실행은 구분한다.

## 회귀와 실행 한계

기존 가상환경에서 전체 Python 1675개(2 optional skip, failure/error 0), JavaScript 360개를 통과했다. 요구된 plain `python3` 전체 실행도 수행했으나 1633개 중 기존 FastAPI/Starlette/Pydantic 누락으로 import error 6개가 남았다. 환경 재설치는 하지 않았다. 최초 회귀 실패와 plain-Python 로그를 보존했다. 두 환경의 suite를 병행할 때 기존 테스트의 공용 임시 파일 충돌도 발생해 해당 검사를 확인하고 plain suite를 직렬 재실행했다. 최종 가상환경 회귀에는 실패가 없다. Bash syntax, JSON counts/null 계약, Markdown 링크와 diff whitespace도 확인했다.

## 상태와 종료

| 상태 | 소프트웨어·실행 구분 |
| --- | --- |
| `D2_ONBOARD_SUPPORTED` | 개발 source PASS; 장비 runtime BLOCKED(미배포/opt-in 0) |
| `D2_LIVE_CANDIDATE` | BLOCKED |
| `OPERATIONAL_LOCALIZATION_VERIFIED` | BLOCKED — 새 지도·실제 위치 대기 |
| `ACTUAL_NAV2_PLANNER_VERIFIED` | 실행 및 제한된 사례 PASS; 전체 요구조건 BLOCKED/unknown 거부 FAIL |
| `MOTION_AUTHORIZED` | false — 05단계 미승인 |

최종 읽기 전용 확인에서 이번 수집기·FAST-LIO·planner·카메라 capture 프로세스가 없고 기존 dashboard/bridge/relay service invocation이 유지됐다. viewer 0, lease 없음, deadman false, command zero, 운영 goal idle, 기존 preview running을 확인했다. 임시 도구 두 개만 정리하고 private bag·query·원본·기존 지도와 VSLAM 자산은 보존했다. 물리 종료의 독립 관측은 없으며 소프트웨어 상태로 대체하지 않는다.

사용자는 이 채팅 종료 확인 뒤 직접 대시보드에서 재매핑할 예정이다. 새 map/revision과 초기 위치가 알려지면 B 및 필요한 A의 후속 조건을 확인한다. 이번 결과로 05단계나 06단계를 자동 실행하지 않는다. 전체 구조화 판정과 측정/소프트웨어 source 구분은 [02_04_validation_matrix.json](02_04_validation_matrix.json)에 있다.

## 새 지도 후속 기록

운영자 재매핑·좌표 제공 이후의 실제 후속 실행은 [04_new_map_followup.md](04_new_map_followup.md)에 기록했다. 위의 최초 측정과 소프트웨어 회귀 기록은 그대로 유지한다.
