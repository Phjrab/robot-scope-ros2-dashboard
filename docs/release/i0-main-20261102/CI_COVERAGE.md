# main CI와 historical dependency

이번 실행은 소스 병합/오프라인 회귀다. 로봇·ROS graph·native Nav2를 실행하지 않았다. 이 문서는 실제 수행 범위와 과거 근거를 구분하며, 최종 문서 commit 자체의 CI는 push 이후 별도 확인한다.

## 이관 변경

`.github/workflows/i0-offline.yml`의 push branches에 `main` 한 항목을 추가했다. 기존 integration trigger와 `workflow_dispatch`, `contents: read`, Ubuntu hosted runner, timeout, 테스트/assertion, 합성 screenshot/trace artifact 정책은 유지한다. 배포 trigger와 self-hosted runner는 추가하지 않았다.

| main 자동 실행 | 담당 범위 |
|---|---|
| CI: competition-offline-integration | C2 historical comparative, C4 traffic, 실제 package integration, D0 별도 interpreter, C3 offline |
| CI: hardware-free-tests (Ubuntu 22.04/Python 3.10) | 전수 Python/coverage, root JS, syntax, Ruff/mypy, secret/dependency audit, 기존 browser 및 mission 실제 API fixture |
| CI: hardware-free-tests (Ubuntu 24.04/Python 3.12) | 위와 같은 두 번째 지원 환경 |
| I0: product-and-capacity | 설치된 core/API·권한·default OFF, optional HTTP clients 차단, 확장 JS, 제품 지도/관측/replay, 콘/TTL/transport/lifecycle, timer cleanup, 정확한 과거 core 용량 진단 |

표준 Python과 I0 core 검사에는 일부 중복이 있다. 표준 CI는 지원 환경 전체 회귀를 맡고 I0 job은 전용 제품 browser·콘·capacity를 맡으므로 기존 job을 제거하거나 확장 검사를 표준 성공으로 대체하지 않았다. 기존 root observation browser도 표준 CI에서 계속 실행한다.

## 고정 객체 복구

[ARCHIVE_MANIFEST](ARCHIVE_MANIFEST.json)의 50개 annotated tag를 main 원격 변경 **전에** push했다. tag object와 peeled commit을 원격 재조회했다. main만 clone한 새 원격 clone에 archive tag를 추가 fetch해 최초 50개 HEAD/tree와 historical repository commit 46개를 확인했다. `git fsck --full` 통과, 모든 tagged tree에서 .gitattributes/.gitmodules 및 gitlink 없음(선언된 LFS/submodule 의존성 없음)이다. 전체 로컬 Git bundle도 `git bundle verify`를 통과했다. 추가 코드/workflow 후보 태그 `archive/20261102/i0-main-candidate-2c9bdd1`도 원격 push/peeled SHA와 새 clone fetch를 확인했다(총 51개). 결과·bundle SHA256는 [RECOVERY_VERIFICATION](RECOVERY_VERIFICATION.json)에 있다.

| 소비자 | exact historical SHA |
|---|---|
| 표준 C2 comparative | `765622ecbe20dd29b40296dd2ad24fa508ac9443`, `380800ca9e211495769fe60ee8221e3f4fb40f16`, `9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd` |
| C3 D0 prepare | `83f4ee8d6971d00ab31b2de0eeebf329542dd5d6` |
| C7 baseline/current cores | `robot_dashboard/expansion_diagnostics/dependencies.py::PINS`의 main·C1–C4·D1–D3 8개 SHA; 전부 개별 archive tag로 보존 |
| C6 historical parser export | `tests/expansion_c6/pins.json`의 main `5154761…`, C1 `50600c7…`, C3 `5bf5809…`, C4 `7ac0d55…`, D3 `356d0a0…`; 전체 SHA는 manifest에 보존 |
| 과거 D3 native 기록 provenance | `fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`; recorded ZIP의 SHA256 `0f09cf101555dbef3368fc6913acd9cdd61e380ad45c51472ea5e6b1b3cdc6aa` |

workflow의 fetch는 branch 이름이 아닌 exact SHA를 사용한다. read-only exporter는 `git show/archive <sha>`를 사용한다. C7 과거 재현 README에는 역할 branch clone 예제가 남아 있지만 이번에는 ref를 삭제하지 않으며, 장기 복구에는 `archive/20261102/x-c7-ec724dafd33d`를 사용하면 된다. 외부 Isaac/ROS/URDF upstream SHA는 이 저장소의 branch 정리로 삭제되는 object가 아니며 이번에 그 외부 저장소 검증을 수행했다고 주장하지 않는다. ZIP·GitHub artifact·기존 사적 증거는 Git object bundle과 별개이며 raw 데이터를 새 Git에 넣지 않았다.

## 검증 대상과 결과 기록

인수 전 I0 exact head `ae41a9b6cf5cf5c7c133e818e3fad4693eb2053e`에서 [CI 41276984997](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41276984997)의 3개 job, [I0 41276984979](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41276984979)의 product-and-capacity가 성공했다. 이는 과거 기준이며 최종 main 성공을 대신하지 않는다.

이번 후보는 해당 I0와 production/test/dependency tree가 같다. 변경은 workflow branch 목록과 release 문서뿐이다. `app.py` 1,597줄/상한 1,600, `app.js` 6,873줄/상한 6,900이며 guard는 변경하지 않았다. 새 환경 설치의 PyPI 연결 실패로 기존 C7 Python 환경을 전용 디렉터리에 복사했다. 로컬은 Python 3.13.2/Node 26.13.0/Playwright 1.62.1이며 CI의 Python 3.10/3.12·Node 20과 구분한다. 실제 로컬 검사 수·실패·skip 및 최종 main run/job은 [MERGE_REPORT](MERGE_REPORT.md), [LOCAL_VALIDATION](LOCAL_VALIDATION.json), 후속 CI receipt에 기록한다.

게시 전 후보 `2c9bdd15bcfe49886716bd78975886a89bfd218a`의 실제 hosted 결과: [표준 CI 41370956440](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41370956440) job `125041125639`(competition), `125041125979`(Ubuntu 22.04/Python 3.10), `125041125898`(Ubuntu 24.04/Python 3.12) 모두 success; [I0 41371021026](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41371021026) job `125041319999` success. 이 I0 run은 candidate tag 대상 workflow_dispatch이며 main push run과 구분한다. main 게시 commit의 변경은 release 문서뿐이고, 동일 코드/workflow tree 검사 결과를 재사용한다. 최종 main event의 SHA·job 결과는 게시 후 FINAL_RECEIPT에 별도 보존한다.

새 native 실행은 0이다. 원래 C4 identity 실패, native marking/clearing/planner/actuator 미실행, C0 실패는 [PRESERVED_FAILURES](PRESERVED_FAILURES.json)와 [A0_HANDOFF](A0_HANDOFF.md)에 남긴다. optional ROS/plotting/rosbags 및 historical export skip을 native 통과로 합산하지 않는다.

최종 문서 commit의 SHA/CI는 자기 자신을 파일 내용에 넣을 수 없으므로, 문서 전달 commit을 `git rev-parse HEAD`로 확인하고 아래 exact-head 조회를 사용한다. 최종 전달 시 별도의 `FINAL_RECEIPT.json`에 그 SHA·tree·run/job terminal 상태를 저장한다.

```sh
gh api 'repos/Phjrab/robot-scope-ros2-dashboard/actions/runs?head_sha=<full-final-main-SHA>&per_page=20'
gh api repos/Phjrab/robot-scope-ros2-dashboard/actions/runs/<run-id>/jobs
```
