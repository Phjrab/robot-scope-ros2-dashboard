# 운영 배포 · 2026-10-07

사용자가 기존 로컬 구현 완료 후 Git push와 운영 배포를 명시적으로 승인했다.

- GitHub `codex/ui-robot-scope-mission-control`에 UI 커밋 `544e108d00538af184f1cb15e8bbe565171962d5`를 push했다.
- 원격 main의 별도 하드웨어 변경은 그대로 보존했다. force push/main 교체 없음.
- 운영 URL: http://192.168.50.10:8088/
- 외부 dashboard Orin의 release symlink를 새 full-commit 디렉터리로 원자 전환했다.
- 이전 release `0e3532ad5641ade44550f00a654741d0645135fb`를 rollback용으로 보존했다.
- archive SHA256: `5a09d7a13e20c9e233e901a326cbe39aaab9da8ee6cb38702b9c2eb9a859e4ac`.

## 준비와 보존

기존 실행 release의 운영 소스 206개가 검증 commit과 동일했다. control/API/ROS/native
소스·의존성·runner 변경 없음. 기존 native build는 검증 후 이전 release 경로를 재사용하며,
이전 release를 삭제하면 안 된다. 비공개 schematic 자산과 기존 static map 파일을 보존했다.
기존 환경 파일과 persistent state는 접근 제한된 Jetson backup 디렉터리에 백업했다.
환경 파일의 배포 전후 SHA256이 동일하고 map/dataset/state 경로는 기존 설정을 유지한다.
개인키·토큰·환경 파일·지도 원본·데이터셋은 Git에 추가하지 않았다.
운영 Git 개발 checkout의 사용자 변경은 건드리지 않았다.

새 release에서 Jetson의 `test_final_architecture.py` 5개가 통과했다.
배포 기록 커밋 전 로컬 Python 전체 1,483개 중 1,482 통과·1 skip,
JavaScript unit 340개가 다시 통과했다. [Python](deployment/python.txt) · [unit](deployment/unit.txt).
service preflight는 blocker 없음, lease 없음, deadman 해제, zero-command,
Navigation/goal/mapping 작업/dataset idle, Mission ownership 없음, Competition unlocked였다.

## 시작 오류와 복구

최초 배포에서 operator-event 데이터를 보존하려고 만든 runtime symlink가 기존
`operator event root cannot contain symlinks` 보안 검사에 거부돼 대시보드 시작이 실패했다.
고정 helper는 HTTP 준비 대기 60초를 초과했다. systemd 자동 재시작은 18회 발생했다.

이번 배포가 만든 runtime symlink만 제거하고 이전 operator-event 디렉터리를 실제
디렉터리로 검증 복사했다. 기존 보안 검사·코드·원본 데이터는 변경하지 않았다.
이후 자동 복구돼 active/running·HTTP 200이 됐다. PID `3499596`과 NRestarts `18`이
복구 초기부터 uptime 147.9초의 최종 검사까지 유지됐다. 실패 이력을 0으로 지우지 않았다.

## 운영 검증

[전 상태](deployment/preflight.json) · [최종 상태·HTTP 해시](deployment/postflight.json).

- 실제 process cwd가 `544e108d00538af184f1cb15e8bbe565171962d5` release이다.
- HTML/CSS/JS 8개와 폰트 8개, 총 16개 HTTP 200 및 제공 bytes의 SHA256이 release 파일과 일치했다.
- 실제 브라우저에서 font request 8개 성공, page error 0, 쓰기 요청 0.
- CDP: 영문 제목 `IBMPlexSans-SmBld`, 한글 설명 `IBMPlexSansKR` + Sans,
  숫자/FPS `IBMPlexMono-Medm`의 custom glyph를 확인했다.
- 배포 후 lease 없음, deadman 해제, zero-command, Navigation/goal/mapping 작업/dataset idle,
  Mission ownership 없음, service blockers 없음.
- Go2는 offline/Bridge waiting이다. 새로운 Bridge release·move/action counter는 확인 불가다.
  배포 전 cached counter의 0을 실제 장비 검증이라고 주장하지 않는다.

외부 `robot-scope.service`만 재시작했다. robot-side Bridge·센서 unit·네트워크·enable 정책을
변경하지 않았으며 ARM·이동·Nav2 goal·Mission start·매핑 시작을 실행하지 않았다.
기존 appliance의 sensor preview auto recovery는 원래 startup 설정을 유지한다.

## 실제 운영 캡처

두 화면은 같은 1440×900 viewport의 실제 운영 앱이며 fixture가 아니다.
센서 표시값은 화면에 나타난 당시 상태로, 실센서 성능·안전 acceptance 증거가 아니다.

[Before](deployment/before-cockpit-1440x900.png) → [After](deployment/after-cockpit-1440x900.png).
[브라우저/CDP 결과](deployment/after-browser.json) · [SHA256 manifest](deployment/MANIFEST.json).

기존 열어둔 화면은 새로고침하면 새 UI·테마·폰트가 적용된다.
실제 Go2 동작/카메라 프레임/센서 성능·Nav2·정지 성능은 여전히 미검증이다.

## 운영 rollback

현재 상태와 source를 기록하고 기존 고정 helper로 idle preflight를 통과한 뒤,
`/home/jetson_orin_nano/robot-scope` symlink를 이전 full-commit release로 원자 전환한다.
그 다음 `robot-scope-dashboard restart`로 외부 대시보드만 재시작하고
process cwd·HTTP 자산·제어 zero/idle 상태를 확인한다.

현재/이전 release와 각각의 operator-event 기록, persistent map/dataset/state, backup은
삭제하지 않는다. Git reset/checkout/stash, 환경 덮어쓰기, robot-side 서비스 재시작은 필요 없다.
