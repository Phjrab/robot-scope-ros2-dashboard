# I0 인계 — 오프라인 통합 후보

D1–D3/C1–C7의 258개 명시 경로를 고정 SHA에서 인수하고 실제 제품 `/extensions`와 독립 C7 CLI에 연결했다. 모든 확장 기능은 기본 OFF다. 운영 인증은 BLOCKED_AUTH, 새 충돌 보호는 ADVISORY_ONLY, C4 native는 BLOCKED_NATIVE_IDENTITY다. main/C0 병합·실장비 접속·배포·주행은 하지 않았다.

- [기능별 계층·원본SHA·커밋·미완료 표](INTEGRATION_MATRIX.md)
- [원본/수정 파일 hash와 최종 main/C0 ref](SOURCE_LOCK.json)
- [검증·실패 수정·재현 명령·기존 결함](VALIDATION.md), [machine-readable 결과](RESULTS.json)
- [flag별 조건과 복구](FEATURE_FLAGS_AND_ROLLBACK.md), [보안·안전](SECURITY_AND_SAFETY.md)
- [C0와 결합할 파일별 차이·후속 절차](C0_RECONCILIATION.md)
- [정확한 upstream CI](SOURCE_CI.json), [C7 집계](CAPACITY_RESULTS.json), [과거 native 기록 파서](NATIVE_REPLAY_RESULTS.json)

실제 지도 흐름은 2개/3개/AB+C의 전체 source 정합·immutable 저장·재조회와 ancestry/stale/인증 거부까지 검증했다. C4 최신 worker는 실제 D2/D3/C1/C3로 이어지며 초과 프레임은 전체 거부한다. C3는 기존 renderer를 재사용하고 PAUSED stale를 되살리지 않는다. C6는 실제 local picker·seek·비교·C3 표시·allowlisted Markdown CLI로 연결했다.

최종 로컬: Python3370(3335 PASS,35 명시 skip), JS776(774 PASS,2 historical fixture skip), syntax129, Ruff/mypy4, secret scan PASS. 설치 통합18, 기존 browser227, mission API10, 제품9, 과거 native browser1 PASS. 과거 D3 시나리오5개는 hash 검증 후 parser PASS이며 새로운 native 실행은0이다. C7 검사항목12개 PASS; sensor→render 지연과 Jetson 적합성은 미확인이다.

첫 원격 CI의 선택 httpx2 의존 실패를 C1의 기존 stdlib HTTP transport로 수정했다. optional clients를 강제 차단한 추가 검증도 통과했다. 기존 CI trigger는 그대로이며 I0 branch 전용 offline workflow를 추가했다. 문서 commit 이후의 정확한 최종 HEAD CI run/job 상태는 최종 채팅 보고와 VALIDATION의 조회 명령으로 확인한다.

남은 항목: 운영 auth/qualification owner, opaque asset codec, C4 native genuine identity 및 marking/clearing/planner/actuator, 기존 Maps history poll/open 경합, C0 수동 결합과 별도 실장비 검증이다. 기존 결함이 전체 브라우저 회귀에서 우연히 나타나지 않았더라도 해결됐다고 표시하지 않는다.

최종 C0는 `7321251f36ede748c73f8252f913b4cf2ac91fbd`로 문서2개 커밋만 진행됐다. main은 `846121b4988ed2932d329020857925558f8f2c79` 그대로다. C0 source·map pairing·height/tilt·lease/STOP 경계는 그대로 보존했다.
