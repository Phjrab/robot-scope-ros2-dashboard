# I0 main 병합·보존 보고 — 2026-11-02

## 고정한 소스와 변경

- pre-main: `846121b4988ed2932d329020857925558f8f2c79`
- I0: `ae41a9b6cf5cf5c7c133e818e3fad4693eb2053e`, main 대비 ahead 14 / behind 0
- 초기 보존 C0: `06bd98ba279e149bfecfd91007d65002d83e30b0`; 병합 제외
- 게시 시점 새 C0 관측: `8d22fada23c60fa86e47d3fd24f0e9af57432b82`; 외부 6개 commit, 별도 archive 및 실패 기록 보존, main 미인수
- 독립 정상 clone의 로컬 main에서 I0를 `git merge --ff-only`로 인수했다. 기존 main checkout의 CSS dirty 2건은 그대로 두었다.
- I0 이후 변경은 `.github/workflows/i0-offline.yml` push branches의 `main` 추가와 이 release 문서뿐이다. production/test/dependency 파일은 I0와 동일하다. [CANDIDATE_SCOPE](CANDIDATE_SCOPE.json), [SOURCE_COVERAGE](SOURCE_COVERAGE.json) 참조.

검증된 최종 코드/workflow 후보는 `2c9bdd15bcfe49886716bd78975886a89bfd218a`이며 복구 tag는 `archive/20261102/i0-main-candidate-2c9bdd1`이다. main 변경 전 [표준 CI 41370956440](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41370956440) 3개 job과 [I0 41371021026](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41371021026) product-and-capacity가 **모두 success**로 종료됐다. Ubuntu 두 환경의 기존 browser 및 mission API와 I0 제품/콘/TTL/실제 core/capacity가 포함된다. [CI_BEFORE_MAIN](CI_BEFORE_MAIN.json)에 job/step receipt를 보존한다.

이후에는 검증·보존 결과 문서만 확정했다. 최종 main 게시본은 이 보고서와 `CI_BEFORE_MAIN.json`을 확정한 문서 commit이며, 코드/workflow는 위 후보와 동일하다. [VALIDATED_SOURCE_TREES](VALIDATED_SOURCE_TREES.json)에 비교할 Git object ID를 기록했다. 자기 commit SHA를 파일 안에 넣는 순환을 피하기 위해 최종 main SHA·tree·실제 main push CI·원격 보존 확인은 게시 후 별도 **FINAL_RECEIPT.json**과 최종 전달 메시지에 남긴다. main push 자체의 exact-head CI도 별도로 확인하며, tag 후보 CI를 main event CI라고 표시하지 않는다.

## 복구·정리 결정

main 원격 변경 전 최초 복구 50개와 코드/workflow 후보 1개, 총 51개 annotated archive tag를 push하고 tag object/peeled SHA를 원격 재조회했다. pre-main, I0, C0, 10개 역할 HEAD와 코드/재현 도구가 참조하는 repository historical commit 46개를 포함한다. 새 원격 clone에 tag를 fetch해 commit/tree, 전체 object 연결성, C0 역할별 이력을 확인했다. bundle 검증도 통과했다. [ARCHIVE_MANIFEST](ARCHIVE_MANIFEST.json), [RECOVERY_VERIFICATION](RECOVERY_VERIFICATION.json) 참조.

사용자 추가 답변은 “다른 기기 상태를 모름 — 불확실한 ref 유지”였다. 따라서 정리 후보 11개는 `ARCHIVE_ONLY`, C0와 main 및 범위 밖 과거 8개 ref는 `KEEP`다. 원격/로컬 branch·worktree·clone 삭제는 0건이다. 어떤 역할도 `MERGED_HISTORY`로 오기하지 않았으며 source 선별 인수와 원본 archive를 구분했다. [BRANCH_RETIREMENT](BRANCH_RETIREMENT.json)에 모든 ref, SHA, coverage, 제외 경로/이유, 삭제 미실행 receipt 및 복구법을 기록했다.

첫 main 게시 SHA는 `2526a683ca6abafcc2529b2f02feca4d7777a347`이다. 직전 main/I0는 lock과 같았고, C0만 외부에서 진행했다. 모든 ref를 비교한 추가 assertion은 이를 감지했지만 shell 후속 명령이 그 assertion에 연결되지 않아 정상 main push가 계속됐다. C0 ref나 코드는 변경하지 않았다. 이 관측과 새 C0 실패를 문서만으로 보완하고, 후속 게시에는 실패 시 중단하는 명시 guard를 사용한다. 추가 C0 역할/최신 checkpoint 6개를 원격 태그 및 새 clone에서 검증해 **총 57개 archive tag**를 보존한다. [C0_LATEST_OBSERVATION](C0_LATEST_OBSERVATION.json) 참조.

## 검증 범위와 미완료

이번 후보에서 전수 Python과 관련 JS·syntax·Ruff/mypy·secret scan, 기존 전체 browser, mission 실제 API fixture, I0 제품/콘·transport를 실행했다. Python 최종 3,397건 중 3,360 PASS/37 SKIP, JS 789건 중 787 PASS/2 기존 SKIP, syntax 131, Ruff, 설정 범위 mypy 4파일, secret scan이 통과했다. mission 10, 제품 9, 콘 browser 11, optional HTTP client 차단 4개와 C7 실제 HTTP, timer cleanup 3 round도 통과했다. 기존 전체 browser의 실패는 아래와 같이 별도 보존한다. 상세 실행 횟수·환경 차이·실패와 skip은 [LOCAL_VALIDATION](LOCAL_VALIDATION.json)에 보존한다. 최종 main hosted CI와 I0 제품 job은 [CI_COVERAGE](CI_COVERAGE.md) 및 최종 receipt로 확인한다.

macOS 전체 browser 첫 실행은 227건 중 226 PASS/1 FAIL이다. `tests/e2e/live_observation.spec.mjs:788`의 cancel 후 후보 중심 버튼 활성화 기대(`:809`)가 실패했다. 원본 I0와 같은 코드/테스트이며 원인을 확정하거나 flaky로 단정하지 않았다. timeout·assertion·skip을 바꾸지 않았다. 로컬 Python은 임시 경로의 symlink, 그룹 소유권, 비ASCII shell 출력 문제를 각각 보존했다. ASCII 정규 경로와 일치하는 소유권을 갖춘 최종 환경에서 3,397건(3,360 PASS/37 SKIP)이 통과했다. 37 SKIP은 기존 35건과 macOS에서의 Linux 전용 2건이며, 어떤 skip도 새로 추가하지 않았다. 최초 SLAM overlay 실패 1건의 원인은 확정하지 않았고 이후 같은 source의 전수 실행에서 통과했다. 원래 C0 실패와 C4 native 실패는 별도 [PRESERVED_FAILURES](PRESERVED_FAILURES.json)에 남긴다.

모든 확장은 기본 OFF, 운영 인증 `BLOCKED_AUTH`, C4 `BLOCKED_NATIVE_IDENTITY`, 보호 `ADVISORY_ONLY`다. 합성 콘 표시/과거 native 재생은 실측 검출·회피·새 native 통과가 아니다. 기존 Maps history poll/open 경합, opaque asset decoder, 실제 센서/clock/교정/부하, C0 최종 통합은 A0 backlog다.

**DEVICE_NOT_RUN**: Jetson/Go2 접속·배포·서비스/지도/설정 변경·ROS 제어·주행 0회. [A0_HANDOFF](A0_HANDOFF.md)에 코드·실패·검증 기록과 다음 작업을 남겼다.
