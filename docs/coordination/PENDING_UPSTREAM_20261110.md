# 2026-11-10 작업의 원본 통합 기록

## 2026-11-11 원본 main 통합

사용자의 원본 저장소 push 요청에 따라 아래 네 커밋을 원본 `main`에 통합한다.
원본의 최신 `9b7dc8d272d5f142141613f96d6429b2211ae8d2`
(`fix(ui): preserve camera and map editor control spacing`)를 함께 병합해
카메라·지도 편집기 CSS 변경을 보존했다. 기존 커밋을 재작성하지 않는다.

| 커밋 | 내용 |
|---|---|
| `8eb2305` | 지도 확인·관측 소유권 수정 및 기존 브라우저 실패 세 건 수정 |
| `982b45a` | 원본 반영 대기 목록과 이관 절차 |
| `b1eaaeb` | 고정 비교 커밋을 원본 공개 저장소에서 읽는 CI 설정 |
| `e93d716` | 테스트 준비 보완 및 브라우저 검사의 두 shard 분할 |

`e93d716`의 최종 Linux 검증은 Python·JavaScript·정적/의존성 검사,
미션·수동 2D API 연동, 대회 오프라인 및 I0 제품 통합을 통과했다.
브라우저 첫 shard는 두 환경 모두 성공했고, 두 번째 shard는 환경별
168 passed / 1 failed였다. 아래 실패는 이번 게시 범위에서도 미해결이다.

- Ubuntu 22.04 / Python 3.10: `pre-draft rejects occupied map cells`.
- Ubuntu 24.04 / Python 3.12: `pre-draft rejects unknown map cells`.
- `tests/e2e/pre_nav_draft.spec.mjs:60`에서 UNKNOWN/OCCUPIED 대신
  `START NAV2가 위치추정 센서와 Nav2를 순서대로 준비합니다.`가 표시됐다.
- 전체 CI: https://github.com/deahfst/robot-scope-ros2-dashboard/actions/runs/42806081714
- I0 통합: https://github.com/deahfst/robot-scope-ros2-dashboard/actions/runs/42806081402

11월 11일 통합 사본에서 JavaScript 단위 테스트 765건, 문법 검사 135개 모듈,
추적 파일 자격증명 검사가 통과했다. 원본 CSS 두 파일도 `9b7dc8d`와 동일하다.
Python 전체 테스트는 Windows에서 import 오류가 발생해 중단했고,
집중 검사에서 Linux 전용 `resource` 모듈 부재를 확인했다.
이번 통합 사본의 Python 전체 검증을 통과로 집계하지 않는다.

GitHub 소스 게시와 장비 배포는 별개다. 이 통합 작업은 Jetson 서비스나
지도·주행 상태를 변경하지 않는다. 아래 대기·이관 절차는 11월 10일의 보관 이력이다.

## 최초 보관 목적 (2026-11-10)

사용자 요청에 따라 변경을 `deahfst/robot-scope-ros2-dashboard` 비공개
저장소에 보관하고, `Phjrab/robot-scope-ros2-dashboard` 반영은 나중에 진행한다.
원본을 가리키는 `origin`은 유지하고 개인 보관용 remote는 `backup`으로 구분한다.
이 문서는 보관 계획과 이관 내용을 기록하며, 업로드 성공 여부는 실제 remote
HEAD와 로컬 HEAD 대조로 확인한다.

## 반영할 변경

- 원본 기준: `24150c0e8c6bb5a98dc9f1326264e5a3733a2371`.
- 코드 커밋: `8eb2305e6efd5a12a4f9b04629e3c6876d3e155b`.
- 작업 내용: 같은 좌표계라는 사용자 확인에 따른 3D/2D 지도 연결,
  관측 소유권 조회의 이벤트 루프 처리, 지도 연결 변경 시 초안 무효화
  브라우저 테스트 세 건 수정.
- 어제 작업 원본: `d70e58c92e6039be13dea4d485920459ec8218e3`,
  `5bdd038e44455ec8b0bee40745481087a11130a3`.
- 위 두 커밋의 변경은 이미 코드 커밋에 통합했다. 이관할 때 중복 적용하지 않는다.
- 이 인계 문서를 추가한 후속 커밋도 함께 보관한다.
- 비공개 사본의 CI 실행 `42799555109`는 비교용 과거 커밋
  `380800ca9e211495769fe60ee8221e3f4fb40f16`이 사본에 없어 테스트 시작 전에
  실패했다. 후속 CI 설정은 C2/D0/I0의 고정된 비교 자료를 원본 공개 저장소에서
  읽는다. 고정 SHA와 테스트 조건은 유지하며, 사본 인증 헤더를 전달하지 않는다.
  이 설정 수정도 나중에 원본으로 옮길 커밋에 포함한다.
- 후속 Linux 실행 `42800265239`는 두 환경 모두 Python 3,740건
  (35건 skip), JavaScript 765건을 통과했으나 브라우저 단계에서 작업 제한
  25분에 도달했다. 대회 오프라인 및 별도 I0 통합 실행은 성공했다.
  이후 브라우저 테스트를 환경별 두 shard로 분리하고, 각 shard의 worker는
  1개로 유지한다. 준비 테스트는 지도 연결 응답 완료를 기다리도록 했고,
  cockpit 재진입 테스트는 합성 점군을 계속 공급해 정상 watchdog 재연결이
  소유권 검증에 섞이지 않게 했다. 기존 assertion과 제품 시간 제한은 유지한다.

## 최초 로컬 검증과 당시 남은 작업 (2026-11-10)

- JavaScript 단위 테스트 765건, 문법 검사 135개 모듈 통과.
- Ruff, 설정된 mypy 범위, 추적 파일 자격증명 검사 통과.
- 관련 브라우저 테스트 96건 통과. 기존 실패 세 건 모두 통과.
- 브라우저 테스트 6건은 Windows의 `python3` 명령 부재로 실패.
- Python 전체 테스트는 Windows의 Linux 전용 모듈 import 문제로 완료하지 못했다.
- Linux CI의 전체 Python/브라우저 결과를 확인해야 한다.
- 장비 배포와 실제 주행 검증은 수행하지 않았다.

자세한 범위와 실행 환경은 [통합 기록](C0_MAIN_INTEGRATION_20261110.md)을 참조한다.

## 최초 이관 절차 (이력)

1. 원본 쓰기 권한과 최신 `origin/main`을 확인한다. 작업 폴더의 미커밋 변경을 보존한다.
2. 개인 보관 저장소에서 `backup/main`을 fetch하고 아래 범위의 커밋을 검토한다.

   ```sh
   git log --reverse --oneline 24150c0e8c6bb5a98dc9f1326264e5a3733a2371..backup/main
   ```

3. 원본이 기준 커밋 그대로라면 검토한 커밋들을 fast-forward로 반영할 수 있다.
   원본에 새 작업이 있다면 최신 원본 `main` 위에 위 목록의 커밋을 순서대로
   cherry-pick하고 충돌 및 주행 보호 조건을 검토한다. force-push는 사용하지 않는다.
4. Linux 테스트와 관련 JavaScript/브라우저 검증을 통과한 뒤 `origin main`에 push한다.
5. GitHub 게시와 Jetson 배포는 별개다. 장비 배포는 별도 요청 이후 진행한다.

PC의 `handoff-20261110` 폴더에 추가 커밋만 담은 Git bundle과 patch를 보관한다.
bundle 사용 시 위 기준 커밋이 있는 저장소에서 `git bundle verify <파일>`을
실행하고, `git fetch <파일> main`으로 가져와 검토한 후 적용한다.
bundle과 patch는 같은 변경의 대체 전달 방식이므로 둘 다 적용하지 않는다.
