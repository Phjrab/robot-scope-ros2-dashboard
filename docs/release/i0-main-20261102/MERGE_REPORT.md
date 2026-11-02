# I0 main 병합·보존 보고 — 2026-11-02

## 고정한 소스와 변경

- pre-main: `846121b4988ed2932d329020857925558f8f2c79`
- I0: `ae41a9b6cf5cf5c7c133e818e3fad4693eb2053e`, main 대비 ahead 14 / behind 0
- 보존 C0: `06bd98ba279e149bfecfd91007d65002d83e30b0`; 병합 제외
- 독립 정상 clone의 로컬 main에서 I0를 `git merge --ff-only`로 인수했다. 기존 main checkout의 CSS dirty 2건은 그대로 두었다.
- I0 이후 변경은 `.github/workflows/i0-offline.yml` push branches의 `main` 추가와 이 release 문서뿐이다. production/test/dependency 파일은 I0와 동일하다. [CANDIDATE_SCOPE](CANDIDATE_SCOPE.json), [SOURCE_COVERAGE](SOURCE_COVERAGE.json) 참조.

이 첫 기록은 main 원격 갱신 전 후보의 기록이다. 후보 commit은 이 파일을 처음 도입한 commit으로 결정한다. 로컬 macOS browser 실패를 숨기지 않기 위해 후보를 별도 annotated archive tag로 보존하고, 정확한 후보 SHA의 hosted 표준 CI를 확인한 뒤 main을 정상 push한다. 최종 병합 SHA·run/job은 다음 기록과 최종 전달 receipt에 추가한다. 기존 성공 CI를 현재 후보 통과로 대신하지 않는다.

## 복구·정리 결정

main 원격 변경 전 50개 annotated archive tag를 push하고 tag object/peeled SHA를 원격 재조회했다. pre-main, I0, C0, 10개 역할 HEAD와 코드/재현 도구가 참조하는 repository historical commit 46개를 포함한다. 새 원격 clone에 tag를 fetch해 commit/tree, 전체 object 연결성, C0 역할별 이력을 확인했다. bundle 검증도 통과했다. [ARCHIVE_MANIFEST](ARCHIVE_MANIFEST.json), [RECOVERY_VERIFICATION](RECOVERY_VERIFICATION.json) 참조.

사용자 추가 답변은 “다른 기기 상태를 모름 — 불확실한 ref 유지”였다. 따라서 정리 후보 11개는 `ARCHIVE_ONLY`, C0와 main 및 범위 밖 과거 8개 ref는 `KEEP`다. 원격/로컬 branch·worktree·clone 삭제는 0건이다. 어떤 역할도 `MERGED_HISTORY`로 오기하지 않았으며 source 선별 인수와 원본 archive를 구분했다. [BRANCH_RETIREMENT](BRANCH_RETIREMENT.json)에 모든 ref, SHA, coverage, 제외 경로/이유, 삭제 미실행 receipt 및 복구법을 기록했다.

## 검증 범위와 미완료

이번 후보에서 전수 Python과 관련 JS·syntax·Ruff/mypy·secret scan, 기존 전체 browser, mission 실제 API fixture, I0 제품/콘·transport를 실행한다. 상세 실행 횟수·환경 차이·실패와 skip은 [LOCAL_VALIDATION](LOCAL_VALIDATION.json)에 보존한다. 최종 main hosted CI와 I0 제품 job은 [CI_COVERAGE](CI_COVERAGE.md) 및 최종 receipt로 확인한다.

macOS 전체 browser 첫 실행은 227건 중 226 PASS/1 FAIL이다. `tests/e2e/live_observation.spec.mjs:788`의 cancel 후 후보 중심 버튼 활성화 기대(`:809`)가 실패했다. 원본 I0와 같은 코드/테스트이며 원인을 확정하거나 flaky로 단정하지 않았다. timeout·assertion·skip을 바꾸지 않았다. 로컬 Python 첫 두 실행은 macOS 임시 경로의 symlink/그룹 소유권 거부를 각각 기록했고, 올바른 임시 폴더에서 후속 검사한다. 원래 C0 실패와 C4 native 실패는 별도 [PRESERVED_FAILURES](PRESERVED_FAILURES.json)에 남긴다.

모든 확장은 기본 OFF, 운영 인증 `BLOCKED_AUTH`, C4 `BLOCKED_NATIVE_IDENTITY`, 보호 `ADVISORY_ONLY`다. 합성 콘 표시/과거 native 재생은 실측 검출·회피·새 native 통과가 아니다. 기존 Maps history poll/open 경합, opaque asset decoder, 실제 센서/clock/교정/부하, C0 최종 통합은 A0 backlog다.

**DEVICE_NOT_RUN**: Jetson/Go2 접속·배포·서비스/지도/설정 변경·ROS 제어·주행 0회. [A0_HANDOFF](A0_HANDOFF.md)에 코드·실패·검증 기록과 다음 작업을 남겼다.
