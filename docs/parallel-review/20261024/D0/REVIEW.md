# D0 오프라인 보완 검토 제출 — 2026-10-24 UTC

## A. 기준과 범위

- 역할: D0. 제출 브랜치: `review/20261024-d0-vm-offline`.
- 실제 작업 기준 SHA: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`. 시작 및 12:11 UTC 확인한 원격 main도 동일.
- 검증한 소스 커밋: `5983bdc86cddf77520ae5d4949d7361194e8e3af`. 최종 제출 HEAD는 별도 승인된 모델 revision과 이 문서를 추가한 후 마지막 응답에 별도 기록한다. 이 문서 안에 자기 자신을 포함하는 SHA를 반복 갱신하지 않는다.
- 이번 D0 변경은 main에 반영하지 않았다. 이전 VM 공개 커밋1cddada는 선행 산출물이며 이번 D0와 별개다.
- 기능 변경은 기존 competition_vm 4개 모듈 내부만. 추가 허용된 이 REVIEW.md 및 사용자가 후속 승인한 corridor-parallel-20261024 신규 asset revision만 예외다. 기존 공용 docs/API/UI/schema/CI/arena revision/production은 읽기 전용으로 유지했다. AGENTS.md 수정 없음. 다른 역할 브랜치 병합·복사 없음.
- 사용자의 후속 승인이 기존 LOCAL-ONLY/main-only 제출 지시를 대체했다. 기존 revision 문서의 no-commit 표기는 구현 당시 상태다. 이번 제출에서 main/PR/merge/device 권한은 없다.

## B. 실제 동작 변경 및 검토 지점

1. `traffic_signals/lifecycle.py::TrafficLifecycle`, `ActionEvent`: 접근 terminal SUCCEEDED 또는 CANCELED+ACK 뒤 HOLD 요청 → matching HOLD ACK → 실제 정지/두 앞발 관측 → 신선한 GREEN/pose/path → 새 exit generation/ACK → 해당 goal에 결합된 ACK 이후 취득 departure 관측을 분리했다. 기존 zone-only StopGoFSM을 접근 제어에 직접 연결하지 않는다.
2. `traffic_signals/core.py::TemporalFilter`: stale age 입력 이후 sequence high-water가 사라져 과거 GREEN이 다시 유효해지던 결함을 수정했다. `StopGoFSM`의 source TTL과 stop gap은 분리한다.
3. `integration/adapter.py::ConstraintAdapter`, `LifecycleConstraintAdapter`: source age+수신 후 경과, epoch/sequence, 잘못된 identity/goal, 이전 명령 재사용, cancel/restart 방어. 이벤트 직후 다음 센서 tick 전에도 기존 RELEASE를 차단한다. GREEN/pose가 명령 적용 전에 만료되면 중지한다. 기본 `integration/smoke.py`는 strict 경로다.
4. `arena_robot_sim/revisions/d0_20261024/regression.py`: 0/1/2/5/10콘, 고정 seed20261024, 동일 start/goal/body, 엄격한 주차 금지와 기존 허용 정책을 비교한다. 중심점이 아닌 body footprint와 제어 간 보간 충돌 검사, terrain first-hit 가림, 지연/dropout 및 중앙/경계/좁은/완전 차단 사례. 콘·벽·body를 성공용으로 조정하지 않았다.
5. `compact_fixtures.py`는 289개 delayed/dropout 프레임의 기존 검사 필드와 metrics를 손실 없이 투영한다. 원본과 동등성 검사 PASS. 전체 raw 없이도 13개 arena 검사가 PASS/0skip이며 raw 없이 dense audit를 실행하면 INPUT_REQUIRED로 실패한다.

### 시간·소유권 계약

- receiver TTL0.25초, source maximum age0.25초, 연속 stop observation gap0.5초를 독립 유지. remote monotonic 시각끼리 빼지 않는다. source age는 clock-aware trusted adapter 입력이라는 가정이다.
- 정지2초는 최초 stopped receipt부터 최신 source-supported observation end까지의 보수적인 하한. 통신 대기 시간을 실제 정지 증거로 더하지 않는다.
- HOLD ACK는 요청에 대한 완료 사건이며 지속적인 물리 정지 증명이 아니다. 물리 정지는 신선한 별도 관측이 필요하다. SDK 호출 성공이나 exit goal 전달만으로 출발 완료를 latch하지 않는다.
- departure는 명시적인 새 goal에 연결된 non-stopped 관측을 가정한다. 거리/속도 임계값, 실제 센서 인수·발 검출·신호 association이 구현됐다고 주장하지 않는다. committed 이후 RED만으로 통과를 중단하지 않지만 collision/estop/localization hold는 항상 우선한다.
- canonical competition.v0.1 / mission-action.v0.1 / competition-evidence.v0.1은 수정하지 않았다. local ActionEvent를 바로 네트워크 DTO로 사용하면 안 된다. 세부 차이는 integration/revisions/d0_20261024/CONTRACT_DIFF.md 참고.

## C. 검증

환경: Debian x86_64 VM, Python3.12.14, NumPy2.3.5, SciPy1.17.0, OpenCV4.10.0, Pillow12.3.0, pytest8.3.5. 프로젝트 전용 venv만 사용했고 호스트 패키지/OS/방화벽/서비스를 변경하지 않았다. 옛 traffic 기록의 NumPy2.5.4와 이번2.3.5를 구분한다.

소스 커밋 `5983bdc86cddf77520ae5d4949d7361194e8e3af`만 복제한 깨끗한 별도 clone에서 재실행:

```sh
python -m unittest discover -s experiments/competition_vm/avoidance/tests -v
python -m unittest discover -s experiments/competition_vm/traffic_signals/tests -v
python -m unittest discover -s experiments/competition_vm/integration/tests -v
(cd experiments/competition_vm/arena_robot_sim && python -m unittest -v)
python -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/d0_20261024 -p 'test_*.py' -v
python -m unittest discover -s experiments/competition_vm/integration/revisions/d0_20261024/independent_review -p 'test_*.py' -v
python experiments/competition_vm/integration/smoke.py
python -m unittest discover -s tests -v
node --test tests/*.mjs
python scripts/check_repository_secrets.py
git diff --check
```

- 관련 모듈: avoidance30 + traffic136 + integration44 + 기존 arena7 + 신규 arena13 =230 PASS, 0skip. 독립 블랙박스11 PASS.
- strict traffic→기존 arbiter 실제 연결38프레임 PASS. before/after 재현은 각 revision의 실행 가능한 reproducer/기준 소스 hash/결과 JSON 포함.
- 기존 avoidance48회:27GOAL_REACHED,6SAFE_WAIT,15SAFE_REJECT, 유한 fixture acceptance 전부 PASS.
- 신규 arena12배치×2정책×2회=48회, 24쌍 결정적 trace hash 동일. 총10도착/38대기. 엄격 정책에서 빈 경로만 성공, 모든11장애물 배치는 SAFE_WAIT. 다중 콘 우회 성공0. 이를 일반 자율주행 성공으로 표시하지 않는다.
-24개 distinct 저장 trace를10ms 단위로 보간한22,913pose 검사 PASS. 원본 repeat2는 deterministic projection이 동일하다. polygon sampled clearance와 grid circumscribed proxy는 다른 수치이며 연속 동역학 안전 인증이 아니다.
- 원래 single-cone 성공 기록의 주차구역 침범16프레임/최대0.077819m를 재현·보존했다.
- 전체 Python2691검사: **1failure,25errors,1skip**. 상세 차단은 아래. JavaScript660 PASS. credential scan/diff check PASS.
- 원격 CI는 이 문서 작성 시 아직 push 전이며 로컬 검사를 CI PASS로 표기하지 않는다. 최종 응답에서 실제 제출 HEAD에 연결된 상태/URL을 별도 보고한다.
- nativeROS/Nav2: NOT_RUN (rclpy/ROS/docker 없음). 실제 YOLO/RGB: INPUT_REQUIRED/NOT_RUN. Jetson/로봇/보행/주차 앉기/전 코스: NOT_RUN. 사용자 뒤이어 보낸 모델 링크는 무시 지시대로 열거나 사용하지 않았다.

### 신규 통합 실패: C1 revision evidence 선택 필요

```text
FAIL: test_vm_manifest_uses_published_hashes_without_registration_or_native_promotion
tests/test_competition_mission.py:97
AssertionError: 'UNAVAILABLE_OR_CHANGED' != 'SYNTHETIC_ONLY'
```

`robot_dashboard/mission_routes/competition_assets.py::vm_evidence`는 traffic core.py와 integration adapter.py를 옛 publication checksum과 비교한다. 새 소스와 옛 immutable checksum은 다르므로 두 모듈이 fail-closed로 UNAVAILABLE_OR_CHANGED가 되는 것이 현재 동작이다. 이는 이번 D0로 드러난 신규 연결 실패이며25socket errors와 별개다. 공용 코드를 D0에서 수정하지 않는다.

C1은 기존 manifest를 새 hash로 덮어써 과거 검증이 새 코드에도 적용되는 것처럼 승격하면 안 된다. 새 revision을 명시적으로 선택하고 **새 소스 hash + 새 validation/log hash**를 함께 검증하는 경계를 추가해야 한다. `integration/revisions/d0_20261024/D0_SOURCE_EVIDENCE.json`은 검토용 binding이며 적용된 production 설정이 아니다. native_connected=false, SYNTHETIC_ONLY를 유지하고 변경된 source/evidence는 거부해야 한다.

25errors는 이 VM 실행 traceback에서 socket.socket(AF_UNIX) 생성 PermissionError로 확인했다. 환경 제한을 완화하거나 테스트를 삭제하지 않았다. CI에 같은 오류가 난다고 예측하거나 과거CI와 동일 root cause라고 주장하지 않는다.

### 원격/로컬 자료 구분

- 원격: 소스·테스트·필수 compact fixtures·소형 결과 요약·raw 입력/trace hash·검토 문서.20.7초/1200×840/207프레임 comparison MP4(169876bytes)와 시작/종료 PNG는 실제 저장 trace 재생이다. SYNTHETIC/PLANAR/seed/실제 종료 사유를 표시한다.
- 로컬만: 신규 전체48raw traces 약36MB, avoidance full trajectory result, traffic replay GIF/전체 JSONL, 전체 실행 로그, venv/cache, 기존 ZIP/patch backup. 원격에서 접근 가능하다고 주장하지 않는다. RAW_TRACE_MANIFEST.json, summary paired hashes와 재생성 명령을 제공한다. GitHub Actions artifact는 별도 생성하지 않았다.
- 재생성: `python experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/regression.py` 뒤 같은 폴더 compact_fixtures.py/audit_trace.py/render_replay.py. 자세한 고정 입력·policy/seed는 INPUTS.json/README. 기존 결과를 보존하려면 새 출력 디렉터리/복사본에서 실행한다.
- 역사적 공개 결과/실패/영상/checksum은 보존. canonical/arena source는 미변경. full-course IN→전구간→P→OUT은 DRAFT 시퀀스 설명만이며 planar 렌더링을 실제 terrain 보행으로 집계하지 않는다.

## D. 의존성과 통합 순서

1. 이 D0 브랜치의 실제 diff와 source/evidence hashes를 별도 검토한다. 아직 사용자 통합 승인이나 외부 검토 완료를 받았다고 주장하지 않는다.
2. C1이 자기 브랜치에서 common revision evidence 선택/테스트 연결을 준비한다. 이 제출은 main 또는 다른 역할 결과를 자동 병합하지 않는다.
3. C2가 native terminal/cancelACK/HOLDACK/exitACK, 현재 세대/목표, trusted clock-aware 관측을 한 boundary에 결합한다. 출발/통과는 실제 관측 사건이어야 한다. C2 코드와의 실행 호환성은 NOT_RUN.
4. C3는 실제 Humble Nav2와 실제 형상에서 planner/controller 한계를 비교한다. D0의 보수적 A* SAFE_WAIT를 숨기기 위해 cone/body/parking허용을 바꾸지 않는다. C4는 승인된 실제 weights/classes/RGB 입력을 별도 검증한다. 다른 역할 브랜치를 참조하거나 결합하지 않았다.
5. 추후 별도 사용자 승인된 통합 브랜치에서 결합 회귀한다. main 반영 및 장비 검증 승인은 별도다. 이 브랜치 push workflow는 GitHub-hosted Ubuntu hardware-free CI이며 SSH/deploy/self-hosted 작업이 없다.

예상 충돌: traffic_signals/core.py, integration/adapter.py 및 향후 C1의 competition_assets.py revision 선택. rollback은 아래 목록의 D0 소스와 추가파일 범위만이다. 역사적 결과·실장비 서비스/설정은 영향이 없다.

## 변경 파일 목록 (소스 커밋)

M=수정,A=신규. 삭제/이동 없음. 이 문서 자체가 마지막 문서 전용 커밋으로 추가된다.

```text
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/.gitignore
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/BASE_COMMIT.txt
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/HANDOFF.md
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/INPUTS.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/PUBLICATION_FILES.txt
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/PUBLICATION_SHA256SUMS.txt
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/RAW_TRACE_MANIFEST.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/README.md
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/VALIDATION.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/audit_trace.py
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/compact_fixtures.py
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/fixtures/delayed_offset_1__legacy_parking_allowed.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/fixtures/dropout_offset_1__legacy_parking_allowed.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/regression.py
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/render_replay.py
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/rendering/d0_planar_policy_comparison.mp4
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/rendering/render_manifest.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/rendering/start.png
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/rendering/terminal.png
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/results/compact_projection_verification.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/results/compact_publication_validation.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/results/independent_trace_audit.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/results/summary.json
A	experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/test_regression.py
A	experiments/competition_vm/avoidance/revisions/d0_20261024/replay_baseline.py
A	experiments/competition_vm/avoidance/revisions/d0_20261024/results/legacy_scenario_summary.json
M	experiments/competition_vm/integration/adapter.py
A	experiments/competition_vm/integration/before_after.py
A	experiments/competition_vm/integration/d0_smoke.py
A	experiments/competition_vm/integration/revisions/d0_20261024/CONTRACT_DIFF.md
A	experiments/competition_vm/integration/revisions/d0_20261024/D0_SOURCE_EVIDENCE.json
A	experiments/competition_vm/integration/revisions/d0_20261024/HANDOFF.md
A	experiments/competition_vm/integration/revisions/d0_20261024/REPOSITORY_FAILURE_EXCERPT.txt
A	experiments/competition_vm/integration/revisions/d0_20261024/REPOSITORY_VALIDATION.json
A	experiments/competition_vm/integration/revisions/d0_20261024/VALIDATION.json
A	experiments/competition_vm/integration/revisions/d0_20261024/before_after.json
A	experiments/competition_vm/integration/revisions/d0_20261024/fixtures/baseline_adapter.py.txt
A	experiments/competition_vm/integration/revisions/d0_20261024/fixtures/baseline_smoke.py.txt
A	experiments/competition_vm/integration/revisions/d0_20261024/fixtures/baseline_traffic_core.py.txt
A	experiments/competition_vm/integration/revisions/d0_20261024/independent_review/FINAL_REVIEW.md
A	experiments/competition_vm/integration/revisions/d0_20261024/independent_review/manifest_integration_repro_targeted.txt
A	experiments/competition_vm/integration/revisions/d0_20261024/independent_review/review_tests.txt
A	experiments/competition_vm/integration/revisions/d0_20261024/independent_review/scope_check.json
A	experiments/competition_vm/integration/revisions/d0_20261024/independent_review/test_independent_review.py
A	experiments/competition_vm/integration/revisions/d0_20261024/tests.txt
A	experiments/competition_vm/integration/revisions/d0_20261024/trace.jsonl
M	experiments/competition_vm/integration/smoke.py
A	experiments/competition_vm/integration/tests/test_d0_lifecycle_integration.py
A	experiments/competition_vm/integration/tests/test_d0_transport.py
M	experiments/competition_vm/traffic_signals/README.md
M	experiments/competition_vm/traffic_signals/core.py
A	experiments/competition_vm/traffic_signals/lifecycle.py
A	experiments/competition_vm/traffic_signals/revisions/d0-20261024/HANDOFF.md
A	experiments/competition_vm/traffic_signals/revisions/d0-20261024/VALIDATION.json
A	experiments/competition_vm/traffic_signals/revisions/d0-20261024/fixtures/base_core_7f2a707.txt
A	experiments/competition_vm/traffic_signals/revisions/d0-20261024/reproduce_before_after.py
A	experiments/competition_vm/traffic_signals/revisions/d0-20261024/results/before_after.json
A	experiments/competition_vm/traffic_signals/revisions/d0-20261024/results/legacy_synthetic_replay/metrics.json
A	experiments/competition_vm/traffic_signals/revisions/d0-20261024/results/unit_tests.txt
A	experiments/competition_vm/traffic_signals/tests/test_lifecycle_d0.py
```


## E. 별도 후속 승인: 오른쪽 대각 통로 폭 모델 수정

사용자가 D0 검토 브랜치에 추가를 명시 승인하여, 원본을 덮어쓰지 않는 `assets/competition-arena/revisions/corridor-parallel-20261024/`를 별도 focused commit으로 포함한다. 모델 source commit: `5b3dd239003f828de76b12ee3c98ad436bd50d08`. 기존 `rulebook-20261015` revision 변경0이며 D0 source commit은 위5983bdc다.

- 주된 수정: 오른쪽 NE/SE 대각 통로를 기존1m/45도 설계 가정 아래 평행한 폭으로 만들고, floor/outerfence/terrain footprint 일관성을 맞춤. 공식 실측 치수가 확인됐다는 의미가 아니다. 왼쪽 슬라롬의 provisional narrowing은 이 revision 수정 범위가 아니다.
- 제작 작업의 검증: 자체402단면, 독립2002단면 폭 확인 PASS; 실제 GLB51objects/10floor triangle union과 semantic polygon 비교 최대면적차6.34e-7m², Blender 재개방 PASS. 각 validation JSON과 생성/검사 소스 포함.
- 제출 전 원본34checksum을 전부 확인했고, 복사한 원본파일 bytes도 동일함을 확인했다. 사용자 요청 모델 본체 .blend/.glb 및 소형 corridor-before-after PNG는 포함한다. 큰 중복 preview4개는 로컬만 보존한다. `PUBLICATION_SUBSET.json`과 `PUBLICATION_SHA256SUMS.txt`가 실제 원격 subset이며 원래 SHA256SUMS.txt는 제외된 preview를 포함한 원본 제작 결과 inventory다.
- **D0 장애물/신호 시뮬레이션은 새 모델에서 재실행되지 않았다.** 기존48회 arena 결과는 원본rulebook-20261015 기준이며 새 형상에 전용하면 안 된다. native Nav2/보행/주차/맵 정합도 NOT_RUN이다.
- `wall_id_changes.json` 필수 검토: 새 junction의 짧은 선분 때문에 wall_outer 숫자ID가 바뀐다. 새 GLB/semantic/fence를 함께 선택해야 하며 옛 opening ID를 무조건 재사용하면 안 된다. C1의 별도 revision 선택 및 새 형상에서의 회귀가 필요하다. 생산 선택기/checksum/default를 여기서 바꾸지 않았다.
- 새로운 관절 보행 애니메이션/왼쪽슬라롬 장애물 데모는 별도 진행이며 이 제출에 포함하지 않는다. 모델 비교 영상은 물리 보행 검증이 아니다.

## F. 제출 수단 및 검증된 commit 구분

일반 git push는 HTTPS 자격증명 부재로 실패했다. 새 인증정보를 만들지 않고 이미 연결된 GitHub API로 동일 blob/tree를 게시했다. 로컬 source commit dd0fed3의 tree `177cf20adc99e5fe9ea20a4edc8e3179dce2c611`과 API source commit5983bdc의 tree가 완전히 일치함을 확인했고, API source SHA 자체를 fetch한 독립 clone에서도230모듈 검사와 전체Python2691검사를 재실행했다. API source 재실행도1manifestfailure/25socketerrors/1skip이며 숨기지 않는다. 기존 로컬 commit/ZIP은 보존한다. API가 정한 author/time 때문에 commit SHA가 달라도 source bytes는 같으며 이를 혼동하지 않는다.

최종 원격 branch HEAD/검토 문서 URL/실제CI 결과는 제출 이후 응답에 기록한다. 이 문서를 고치기 위해 무한히 자기 SHA를 반복 커밋하지 않는다. 어떤 main ref도 변경하지 않으며 PR/merge/auto-merge/device action도 하지 않는다.
