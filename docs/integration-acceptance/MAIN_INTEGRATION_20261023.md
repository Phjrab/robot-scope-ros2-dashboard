# main 브랜치 통합 — 2026-10-23

사용자 요청: 열린 브랜치와 최근 UI 수정을 확인해 main에 안전하게 병합하고,
병합이 완료된 브랜치를 삭제한다. 장비 배포·서비스 재시작·로봇 제어는 이 작업의 범위가 아니다.

## 보존과 통합

시작 시 main은 `680d625f200eb161c91e75dee658e53cdbe278d5`였다.
미커밋 UI·검사·인계 자료 9파일은 저장소 밖에 patch, tar, SHA-256 manifest로
백업한 후 `6f673dd`에 기록했다. 백업은 로컬 private validation 폴더의
`main-integration-20261023-180325`에 보존한다.

| 브랜치 | 확인한 tip | 처리 |
| --- | --- | --- |
| `codex/maps-localization-integration` | `95571110e06fc476c91704e702918c4b0711f33c` | 센서 관측·전체 원본 PCD 편집·소유권 조회를 통합 |
| `codex/ui-dashboard-consistency` | `db83e62710aba2b0f3637d73822c658e5b33fd22` | 최신 관측/보정/수집 도움말 접기와 화면 배치를 통합 |
| `codex/ui-readability-refinement` | `badd801288d66b24033a3642db983ab9e4bd3a5d` | 기존 main에 적용된 UI와 이후 수정 보존, 인계 문서·이력 연결 |
| `codex/ui-robot-scope-mission-control` | `42c6cce986029548e5cc7e0f6f9bd830144cabe3` | 시작 시 이미 main의 조상 |
| `experiment/isaac-vslam-onboard` | `d54625481f84ef9c6054bd9ebd10fb08d0ab8a64` | 10월 14일 선별 통합과 이후 실험 보완 보존, 이력 연결 |
| `feature/competition-route-planner` | `ab1010be1ec11e343e04b38fed7e3b11cd3f7a48` | 시작 시 이미 main의 조상 |
| `hardware/go2-cargo-plate-v1-20261003` | `7364268a8333886c6fab894ea83a18d2d4712b73` | 기존 main의 CAD 자료와 동일함을 확인, 이력 연결 |

위치 관측 충돌에서는 최신 FAST-LIO IMU 표시, 독립 수신 pose,
정합 실패 시 현재 pose 유지, worker 종료 처리, 명시적 과거 결과 선택을 보존했다.
새 센서 관측이 화면을 점유하면 기존 수동 기준점 관측을 일시 중지한다.
같은 지도 revision을 다시 읽을 때 연결을 유지하는 판정은 `saved_scene.js`로
옮겨 앱 크기 제한을 지켰다. 지도 revision이 바뀌면 기존 연결은 해제된다.

UI 충돌에서는 접기 UI와 기존 기록 선택을 결합했다. 상태·실패 사유·관측 한계를
계속 표시하고, 기준점·고급 옵션·수신 메타데이터를 펼쳐 볼 수 있다.
과거 결과 select/input은 작은 화면 너비 안에 머무른다. 기존 메뉴 위치,
Inspector 재배치, 레이아웃 조작, Settings의 소프트웨어 STOP 위치를 보존했다.

실험 브랜치의 구형 설정 화면 모니터는 현재 전용 자원 페이지/API와 응답 계약이
다르다. 현재 `resource_monitor.py`, `api/routers/resources.py`와 전용 자원 페이지를
보존하고, 구형 `host_resources.*` 및 해당 전용 검사 7파일은 최종 트리에서 제외했다.
이 제외는 실험 병합 직후 후속 커밋에 기록되며 이력을 재작성하지 않는다.
[과거 모니터 문서](../COMPUTE_MONITOR.md)에 현재 구현 안내를 추가했다.
실험의 카메라 profile 검증 분리와 CameraInfo ROI 보존도 유지했다.

## 검증

- Python unittest: 2,628개 실행, 성공, 선택 의존성 등 4개 건너뜀.
- JavaScript: 개별 검사 640개 성공.
- 전체 Playwright: 182개 성공. 작은 화면, 다크/라이트, 메뉴/Inspector,
  과거 결과 조회, 동일 시작점 추적, 동일/변경 revision 재조회, 3D 편집,
  미션, SLAM/Depth, 자원 페이지와 페이지 전환을 포함한다.
- 하드웨어 manifest 22개 항목의 바이트 수, SHA-256, Git blob SHA-1 일치.
- 충돌 표식 및 `git diff --check` 확인.
- CI 정적 검사: Ruff, 지정 모듈의 strict mypy, 대시보드 JavaScript 100개
  모듈 구문 검사 성공. 병합된 관측 모듈의 미사용 `tempfile` import를 제거했다.

macOS 검사는 `.venv/bin/python3`와 심볼릭 링크를 해소한 사용자 소유 임시
디렉터리에서 실행했다. `/var` 링크, `/private/tmp`의 상속 그룹, sandbox의
Unix socket bind 제한으로 발생한 환경 오류는 실행 환경을 맞춰 해소했다.
제품의 경로·소유권 보호 조건은 완화하지 않았다. 브라우저 검사는 로컬 합성
backend를 사용했으며 실장비 성능 검증이 아니다.

로컬 로그: `/private/tmp/scope-merge-ui-python.log`,
`/private/tmp/scope-merge-ui-js.log`, `/private/tmp/scope-merge-ui-browser.log`.
최종 통합 재확인 로그는 `/private/tmp/scope-main-final-python.log`와
`/private/tmp/scope-main-final-js.log`에 저장한다.

## 게시와 정리 조건

main을 일반 fast-forward push로 게시한다. 원격 main과 로컬 HEAD 일치 및
각 tip이 main의 조상임을 확인한 뒤 위 7개 원격 브랜치와 같은 이름의 로컬
브랜치 2개를 삭제한다. 삭제 직전에 원격 tip을 다시 확인하며 새 커밋이 있으면
삭제하지 않는다. main, 작업 파일, 검증 자료와 원본 장비 데이터는 보존한다.

이 기록은 소프트웨어 통합 상태다. 이전 날짜의 인계 문서와 실험 기록은
해당 시점의 증거로 보존하며, 이번 작업으로 장비 설치 상태가 바뀌지는 않는다.
