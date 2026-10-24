# C3 검토 제출 — Humble Nav2 격리 비교 환경

## A. 기준과 범위

- 역할: C3, 브랜치: `review/20261024-c3-nav2-benchmark`.
- 실제 작업 기준 SHA: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- 작업 시작/브랜치 전환 시 확인한 원격 main: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- 테스트 대상 코드 커밋: `dfeabb36e16a80f14c65f23361fd29d36504ac6b`. 테스트한 작업 트리 내용을 변경 없이 이 커밋으로 기록했다. 이 REVIEW와 검증 요약은 뒤의 문서 전용 커밋에 포함되므로 최종 제출 HEAD와 구분한다. 최종 HEAD는 제출 응답에서 확인한다.
- 독립 일반 clone에서 작업했다. 이전 C2 clone의 Git 기준 객체만 복제했으며, 다른 작업자의 미커밋 소스나 결과는 복사하지 않았다. 사용자 변경 요청에 따라 기존 수정 내용을 유지한 채 지정 브랜치를 만들었다.
- C3 변경을 main에 반영한 적 없음. PR/merge/cherry-pick/force-push 없음. AGENTS.md 변경 없음.
- 아래 파일은 전부 **추가**이며 기존 파일 수정·삭제·이동·바이너리 추가는 없다.

- `docs/parallel-review/20261024/C3/REVIEW.md`
- `experiments/competition_nav2/.gitignore`
- `experiments/competition_nav2/README.md`
- `experiments/competition_nav2/compare.py`
- `experiments/competition_nav2/config/manifest.json`
- `experiments/competition_nav2/config/mppi_baseline.yaml`
- `experiments/competition_nav2/config/mppi_tuned.yaml`
- `experiments/competition_nav2/config/replan.xml`
- `experiments/competition_nav2/config/rpp_baseline.yaml`
- `experiments/competition_nav2/config/rpp_tuned.yaml`
- `experiments/competition_nav2/configure.py`
- `experiments/competition_nav2/container/Dockerfile`
- `experiments/competition_nav2/container/manage.py`
- `experiments/competition_nav2/core.py`
- `experiments/competition_nav2/docs/HANDOFF.md`
- `experiments/competition_nav2/docs/REFERENCES.md`
- `experiments/competition_nav2/docs/input_manifest.json`
- `experiments/competition_nav2/execute.py`
- `experiments/competition_nav2/fixtures.py`
- `experiments/competition_nav2/launch/native.launch.py`
- `experiments/competition_nav2/matrix.py`
- `experiments/competition_nav2/native_runner.py`
- `experiments/competition_nav2/preflight.py`
- `experiments/competition_nav2/requirements-offline.txt`
- `experiments/competition_nav2/results/check-summary.txt`
- `experiments/competition_nav2/results/fixture_manifest.json`
- `experiments/competition_nav2/results/focused-tests.txt`
- `experiments/competition_nav2/results/host_preflight.json`
- `experiments/competition_nav2/results/image_lock_status.json`
- `experiments/competition_nav2/results/native_comparison.json`
- `experiments/competition_nav2/results/native_plan.json`
- `experiments/competition_nav2/results/offline_validation.json`
- `experiments/competition_nav2/tests/test_offline.py`
- `experiments/competition_nav2/validate.py`

기존 VM의 Python A* 성공을 native 결과로 사용하는 대신 실제 Humble Nav2 서버를 실행하도록 구성한 독립 하네스를 추가했다. 다만 이 호스트에서는 native 실행이 없으므로 **실행 환경과 하네스 준비 완료, native 비교 미완료** 상태다.

## B. 구현과 주요 검토 지점

- `configure.py:candidate/validate_config`: 동일 footprint·map·속도·가속도·센서 조건, RPP/MPPI baseline/tuned 후보 4개, tuning delta와 hash. 기존 후보의 10 Hz/.05 s MPPI 불일치를 20 Hz/.05 s로 수정했다. Humble 미지원 newer acceleration 키는 넣지 않았다. 기본 후보는 upstream 무수정 기본값이라는 뜻이 아니다.
- `launch/native.launch.py:generate_launch_description`: 환경 차단 검사 후 실제 map/planner/controller/behavior/BT/lifecycle 서버를 로드한다. 자동 lifecycle activation은 끈다. 같은 이름의 대체 planner/controller 노드는 없다.
- `native_runner.py:Plant/main/plugin_library_names`: SIM_GT TF/clock/odom/virtual scan, native action, lifecycle/전체 명시 controller parameter readback, 실제 프로세스 maps의 플러그인 라이브러리와 해시. MPPI package 이름과 `libmppi_controller.so` 이름이 다르므로 설치된 plugin XML을 읽어 검사한다.
- `core.py:Boundary`: HOLD→캐시 제거·세대 변경, RELEASE 이후 새 명령 필요, .25 s 명령 TTL, DDS 동일 호스트 source age와 receiver monotonic TTL 분리, .3 s sensor source+receipt freshness, latched fault. 원시 controller/behavior 입력은 action owner와 graph publisher 소유권으로 제한한다. production의 최종 arbiter를 변경하지 않는다.
- `fixtures.py:World/cases`: rulebook revision을 읽기만 한다. 12개 고정 시나리오, 원래 중앙 콘/5.75 m 실패/5.70 m 비교 조건, 주차 허용/금지 분리. 시작·목표·footprint를 성공시키기 위해 이동하지 않았다. 경사로·계단·플랫폼은 occupied. RGB bbox를 미터 좌표로 변환하지 않는다.
- `validate.py`: backend 구분, 실제 로그·플러그인·action·명령·해시 없으면 native PASS 거부. 명령으로 pose를 독립 재계산하고 5 mm/.01 rad 이하 보간 충돌 검사를 수행한다. ZERO를 UI 상태만으로 판단하지 않는다.
- `execute.py`, `container/manage.py`: build 다운로드와 network-none 실행 분리, digest/패키지 lock, readonly/cap-drop/전용 namespace, graph audit, 자식 및 container 종료 증거. 미검증 이미지 digest를 임의로 기입하지 않았다.
- `matrix.py`, `compare.py`: 12×2×2×3 = 144회 계획, 반복/실패/미완료 pair 보존. native source 증거 없이 순위·컨트롤러 추천을 생성하지 않는다.

### 계약/통합 제안

공용 `competition.v0.1`, `mission-action.v0.1`, `competition-evidence.v0.1` schema/API를 변경하지 않았다. 실험 결과 enum은 runtime enum이 아니다. C2에 실제 연결할 때 명령 소유권·session/generation·freshness를 기존 단일 arbiter 계약에 매핑해야 하며, 이 plant/gate를 production 입력으로 import하지 않는다. 관측 gap과 명령 TTL은 별개다.

C1에 제안: `.github/workflows/ci.yml`에 별도 hardware-free C3 테스트 명령을 추가하고, 승인 이후 기존 container runner에서 실제 native matrix를 실행한다. 기존 `tests/` discover는 이 새 subtree를 실행하지 않는다. production `config/nav2_params_go2_humble.yaml`/profile/wiring 교체 제안은 실제 비교 뒤 별도 검토 사항이다. 이 제출에서 공용 파일을 수정하지 않았다.

### 한계와 회귀 위험

**native 실행 경로 전체는 아직 설치본으로 검증되지 않았다.** launch·BT·QoS·plugin parameter 소비 여부·프로세스 확인·Docker/Podman 호환성은 실제 Humble 환경에서 확인해야 한다. readback에 값이 있다는 것만으로 파라미터 소비를 증명하지 않는다. 이미지/설치 패키지 버전은 build 전이라 미확정이며 reference source commit과 구분한다.

평면 차동 plant, 이상적인 scan, 0.716×0.324 m mesh envelope, 즉시 ZERO는 물리 로봇의 보행·제동 모델이 아니다. 센서는 기존 multi-height renderer와 다른 2D base projection이다. `map_transform=null`, route DRAFT, 경기장 치수 불확실성 유지. 주차 허용은 잠정 비교 조건이며 경기 경로 허가가 아니다. MPPI seed 파라미터가 확인되지 않아 fixture seed만 고정되고 optimizer bitwise 재현은 주장하지 않는다. CPU/RSS와 시간은 호스트 지표이며 Jetson 성능으로 환산하지 않는다.

## C. 실제 검증

실행 환경: Ubuntu 24.04 x86_64, Python 3.12.3. C3 전용 venv와 기존 설치 패키지를 읽기 전용으로 재사용했다. NumPy 1.26.4/SciPy 1.11.4/PyYAML 6.0.1, Ruff 0.6.9. 전역 패키지/OS/daemon 변경 없음.

| 검사 | 결과 | 실제 명령/범위 |
|---|---|---|
| C3 순수/합성 테스트 | PASS: 38/38 | `python -m unittest discover -s experiments/competition_nav2/tests -v` |
| 기존 Python 전체 | PASS: 2689, SKIP: 2 (2691 실행) | `python -m unittest discover -s tests -v`, 84.805초 |
| JavaScript | PASS: Node runner 70개 | `node --test tests/*.mjs` |
| JS 문법 | PASS: 104 modules | `node scripts/check_frontend_syntax.mjs` |
| 정적 검사 | PASS | `ruff check experiments/competition_nav2 robot_dashboard scripts` |
| Python 문법/fixture/config | PASS | compileall, fixtures.py(12), configure.py(4) |
| staged/tracked 비밀 검사 | PASS | `python scripts/check_repository_secrets.py`, `git diff --cached --check` |
| 로컬 browser E2E | NOT_RUN | C3 UI 변경 없음. 원격 CI는 baseline의 browser suite를 실행할 수 있음 |
| Humble image build/native Nav2 | NOT_RUN | 144 계획/0 실행; container CLI와 Humble 부재 |
| 실제 모델·영상 replay | NOT_RUN | C4 범위; 첨부 RGB 데이터는 C3에서 사용하지 않음 |
| 로봇/전체 코스 | NOT_RUN | 승인 범위 밖; 접속/배포/주행 없음 |

2개 skip은 optional rosbags backend 미설치, PCD_EDIT_NODE 미지정이다. 초기 sandbox 실행은 asyncio executor 종료에서 정지했고, 같은 mapping 13개를 sandbox 밖에서 재현하여 통과했다. 이어 전용 환경의 FastAPI/Pydantic 누락과 NumPy/SciPy ABI 불일치를 해결한 후 전체 검사를 통과했다. 초기 실패를 삭제하거나 테스트 기준을 변경하지 않았다. 핵심 오류: `ModuleNotFoundError: No module named pydantic`, `numpy.dtype size changed`, sandbox `asyncio.runners.close` 대기. 정확한 요약/로그 해시는 `results/offline_validation.json`에 있다.

작은 C3 원문 테스트 로그와 전체 검사 terminal 요약은 Git에 포함했다. 전체 로컬 테스트 로그, 생성 map 파일은 원격 업로드하지 않았다. 네이티브 실행 로그/플러그인 runtime receipt/action 결과는 아직 존재하지 않는다. 순수 테스트 통과는 native 운용·실물 안전·실제 정지/자세/인지·전체 코스 통과를 증명하지 않는다.

재현 명령은 `experiments/competition_nav2/README.md`의 Local checks / Build once 항목을 따른다. 실제 이미지를 build하여 lock 생성 후 `matrix.py --run`을 실행하고 `validate.py`/`compare.py`로 원본 증거를 검증한다. 환경이 없으면 `preflight.py`가 code 2/NOT_RUN으로 끝나며 host Jazzy를 대신 실행하지 않는다.

## D. 의존성과 통합 참고

- 순수 테스트/격리 하네스는 다른 역할의 변경 없이 고정 기준에서 독립 실행하도록 작성했다.
- 다른 작업 브랜치의 commit을 참고/merge/cherry-pick하지 않았다. C2 작업의 대화는 C3 역할 확인에만 사용했다.
- C1/C2/D0/C4와 브랜치 간 호환성은 NOT_RUN. 다른 역할 완료를 주장하지 않는다.
- 예상 충돌: 현재는 신규 실험 subtree와 C3 REVIEW뿐이다. 이후 공용 CI/profile/arbiter 연결 시 C1·C2의 명시적 계약 검토가 필요하다.
- 권장 순서: 별도 검토 → 사용자 통합 승인 → 별도 통합 브랜치에서 pure 회귀 → 격리 Humble image/native 반복 → 근거를 보고 production 후보를 별도 검토한다. 이번 제출은 통합 승인이 아니다.
- 롤백: `experiments/competition_nav2/**`와 이 C3 REVIEW를 제외하면 된다. production 파일/서비스/지도에 rollback할 변경 없음.
- push-trigger workflow는 `.github/workflows/ci.yml`의 hosted Ubuntu hardware-free CI뿐이며 로봇 배포/서비스 재시작 작업은 없다. 브랜치만 push하며 원격 main에는 쓰지 않는다.
