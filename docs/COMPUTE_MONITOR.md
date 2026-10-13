# Robot Scope 호스트 자원 모니터

기존 설정 화면(`#settings`)에 CPU/GPU/RAM/swap/disk/thermal 카드와 CPU/GPU/RAM 최근 추이를 추가했다. endpoint는 읽기 전용 `GET /api/v1/system/resources`이며 별도의 서비스 설치·SSH·제어 명령·ROS publisher를 사용하지 않는다. 기존 UI와 마이그레이션 checkout은 수정하지 않았고 실험 전용 clone/branch에서 구현했다. 운영 배포는 NOT_RUN이다.

사용자가 지목한 Codex CLI 결과물은 `/Users/hajoonpark/Documents/Codex/2026-08-07/new-chat/outputs/robot-scope` 및 sibling zip에서 발견됐다. 확인한 소스는 예전 ROS 대시보드이며 별도의 Jetson 자원 수집 구현을 찾지 못했다. 이를 찾은 monitor라고 주장하거나 원본을 수정하지 않고 요청한 기능을 현재 GitHub 프로젝트에 구현했다.

수집 대상은 **대시보드를 실행하는 호스트**다. Jetson에서 실행하면 그 Jetson을, Mac에서 실행하면 Mac을 표시한다. Mac 화면에서 원격 Jetson을 자동 SSH 수집하지 않는다. `/proc/stat` 두 표본의 delta, MemAvailable 기준 RAM, swap 사용량, dashboard filesystem 용량, Jetson GPU sysfs load(0..1000 → percent), thermal zone 최고 온도를 사용한다. 없음/첫 CPU 표본은 N/A다. 온도만으로 throttling을 판정하지 않으며 NOT_OBSERVED로 둔다. 프로세스별 VSLAM 자원량은 아니다.

모든 클라이언트가 2초 캐시를 공유하고 history는 60개로 제한한다. UI polling은 설정 화면이 보일 때만 수행한다. 요청 timeout은 4.5초이고 연결 실패 시 이전 값임을 표시한다. 서로 다른 RAM 수집기의 정의나 GPU 1초 표본/순간 sysfs load 차이를 동일하게 해석하지 않는다.

실제 Jetson에서 collector만 읽기 전용으로 검증했다: CPU 41.22%, GPU 0%, RAM 약 1.77GiB(10.77%), max thermal 65.156°C. [실제 snapshot](experiments/isaac-vslam/evidence/dashboard-resources-live.json)을 보존했다. 기존 운영 dashboard service에 코드를 배포하거나 재시작하지 않았다.

검증: Python collector/API tests, JavaScript formatting tests, Playwright 1440px/390px 화면·오류 표시·탭 이탈 polling 중단. 브라우저 검증은 fixture를 사용했고 실제 운영 Jetson UI 검증으로 확대하지 않는다. `.mjs`의 MIME과 no-store 캐시도 반영했다.

```sh
npm run test:unit
npx playwright test -c playwright.resources.config.mjs --reporter=line
python3 -m unittest discover -s tests -v
```

핵심 파일은 `robot_dashboard/host_resources.py`, `robot_dashboard/api/routers/system.py`, `robot_dashboard/static/host_resources.{mjs,css}`, `robot_dashboard/static/index.html`이다. 향후 UI branch/main 반영과 Jetson 운영 배포는 담당자의 별도 검토 범위이며 자동 merge/cherry-pick/서비스 등록을 하지 않았다.
