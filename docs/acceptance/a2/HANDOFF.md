# A2 비주행 제품 인수

2026-11-05 후속 변경으로 확장 로그인·세션 단계를 제거했다. 아래 표는 최초 인수 결과이며 현재 접근 방법은 [DASHBOARD_ACCESS](DASHBOARD_ACCESS.md)를 따른다.

현재 결과는 OWNER_IMPLEMENTED_OFFLINE이다. 통합 main에서 기존 C1/C2/C3, D1, SavedMapCatalog, C6 및 C7 경로를 사용했다. A1의 공유 진입점/배포 파일은 편집하지 않았다. 제품 소스는 SOURCE_LOCK.json의 product_commit, 출발점과 최초 실패는 ROUND1_RESULTS.md/json에 고정했다.

| 흐름 | 확인한 결과 |
|---|---|
| 권한 | HTTPS에서 서버 발급 일회용 코드 교환, 읽기/저장 역할 분리, 세션 만료·logout·관리자 폐기 및 느린 POST 거부. 무권한 401, 권한/Origin 403, 오래된 revision·문맥 409, 입력/권한 저장소 미가용 503. Host·HTTPS 검증, private asset·경로 탈출·no-store 검사 |
| 실제 브라우저+HTTPS | Chromium에서 테스트 헤더/라우트 대체 없이 로그인→두 원본 선택→D1 후보 수락→800점 사본 저장·재조회→로그아웃·재열기. 전체 요청 관찰에서 확장 API 이외 쓰기 0, 외부 요청 0 |
| 다중 지도 | 별도 제품 E2E에서 2/3개·AB+C의 800/1200/1200점, 원본 해시·필드·DAG·중복 ancestry 거부. 포인트 미리보기와 nullable session은 원본으로 승격하지 않는다. 등록 사본에는 operational_installed=false와 파일별 hash가 있다 |
| 지도 경합 | 지연 poll 중 첫 상세 GET이 발생하며 늦은 poll/상세/오류가 다음 선택을 덮지 않는다. map·화면 수명, 성공·404·네트워크 오류를 검사했다. 과거 history_poll_probe는 기준 SHA의 실패 재현 전용이다. 융합 입력 review와 별도 export가 동시에 완료되며 취소·중복 저장·stale revision fence가 작동한다 |
| 관측·콘·asset | 검토용 scene/context와 private asset에 권한/세대 검사를 연결했다. C1→C3→Canvas 합성 콘 5개, 같은 stamp TTL 불연장, 잘못된 frame/세대·권한/탭 해제 검사. 유효한 빈 입력은 0개, 만료된 개수는 —개로 표시한다. opaque bytes를 임의로 decode하지 않는다 |
| 기록 | C6 파서와 로컬 파일 선택, 원본 ns·playhead 구분, 양방향 seek, 다른 조건 경고, ACK/정지 증거 누락, allowlist 요약. 재생 중 업로드·제어 쓰기 0 |
| 용량·시간 | C7 baseline 합성 cone 1개, 1,176점, raw 14,112 B, snapshot 4,342 B. 고정 byte 한도·두 입력군/메타데이터별 26조합 중 전달 18, 예산 초과 미전달 8. 큐 입력 60, 처리 2, 대기 교체 58, pending 최대 1. exact input SHA·stage 시간·현지 CPU/RSS는 ROUND1_RESULTS.json. end-to-end는 UNKNOWN |
| 화면 수명 | 390/768/1440px dark/light의 한글 폰트·긴 오류 줄바꿈·키보드·대비, 작은 화면 터치 로그인/REPLAY, 로그아웃·세션 만료·401 정리. socket fixture 3회 모두 남은 interval 및 종료 후 callback 0 |

## 검증 집계

제품 커밋은 `3bcb1d58116cc8411f78be1d4fc148c6c5da78d5`이다. 인계 문서만 더한 게시 HEAD의 Linux CI는 GitHub Actions에서 그 HEAD의 표준 CI와 I0 두 workflow로 확인한다.

- I0 Python 52개, 전체·확장 JavaScript 845개(선택 fixture 포함, skip 0), syntax 133개 모듈, Ruff 및 기존 mypy 대상 4개, 추적 파일 비밀정보 검사 통과.
- 제품 브라우저 10개, 콘 브라우저 11개, Maps history 브라우저 5개 통과. 이와 별도로 실제 TLS/Chromium 사본 저장과 세션 UI는 고정 제품 SHA에서 확인했다. DOM의 원인별 오류·만료는 라우팅한 응답, 실제 권한/저장은 TLS 서버로 구분한다.
- 최종 macOS 전체 Python 3,695개 실행, 실패 항목 5, 오류 59, skip 37. 오류 59개의 traceback에 모두 Linux `/proc` 부재가 나온다. 실패 5개는 해당 navigation handoff의 409/200 및 후속 대기 assertion이다. 기존 플랫폼 안전 검사는 유지했다. 최초 전체 실행에는 임시 파일 소유 그룹과 공백 포함 interpreter의 Hesai fixture 오류도 있었고, 실제 사용자 그룹의 임시 디렉터리와 공백 없는 실행 경로에서 해소됐다. 첫 실패 로그와 최종 로그 해시는 SOURCE_LOCK.json에 별도 기록했다.
- 기준 SHA의 GitHub 성공, A2 코드의 로컬 검사, 최종 게시 SHA의 지원 Linux 결과는 각각 별도 증거다. 장비 실행 횟수는 0이다.

## 재현

테스트는 독립 clone, 일반 사용자 임시 디렉터리, 로컬 Chromium 및 저장소의 offline/quality 의존성을 사용한다. Python 3.10/3.12 지원 Linux가 전체 CI 기준이다. 실제 ROS나 운영 서비스를 시작할 필요가 없다.

```sh
python3 -m unittest discover -s tests -v
python -m unittest discover -s tests/integration_i0 -t . -v
python -m tests.integration_i0.verify_declared_dependencies
node --test tests/*.mjs tests/expansion_c2/*.test.mjs tests/expansion_c3/test_*.mjs tests/expansion_c6/test_replay.mjs
node scripts/check_frontend_syntax.mjs
npx playwright test tests/e2e/global_observation_history.spec.mjs
npx playwright test --config playwright.i0.config.mjs
npx playwright test --config playwright.i0-cones.config.mjs
node experiments/expansion_20261030/c7_capacity/ci/socket_cleanup_probe.mjs .
```

C2의 선택적 비교 두 개는 experiments/expansion_20261029/c2_map_ui/README.md의 54629c7 고정 export와 fixture 환경변수를 사용했다. C7 baseline/bounded는 I0 workflow의 정확한 PINS Git export와 첫 설정 snapshot을 사용한다. 원본 지도·영상·실행 로그·자격 자료는 공개 Git에 포함하지 않는다.

## 현장 인수

A1_FIELD_HANDOFF.md에 권한 프로비저닝, 지도/생산자 port 계약과 읽기 전용 인수 절차, rollout/rollback 경계를 기재했다. 실제 지도 정확도, 콘 모델/실측 좌표·교정/codec, 현장 기록 비교 및 Jetson 성능은 INPUT_REQUIRED다. 장비 권한 설정, 실제 입력 연결, 운영 지도 전환, 위치추정·제어·이동은 이번 검증에 포함하지 않았다.
