# Robot Scope 새 데스크탑 인계 — 2026-10-19

## 소스와 실행본

- 저장소: <https://github.com/Phjrab/robot-scope-ros2-dashboard>, branch `main`.
  새 데스크탑에서는 이 저장소를 작업 폴더에 clone한다. `AGENTS.md`의 단일
  branch 규칙을 따르고 기존 변경을 reset/clean으로 지우지 않는다.
- 최종 기능 소스는 **`1301e95453f0d45f0deade0ccc9ee6e3715fc6d8`**다.
  이후 이 공개 인계 문서를 추가했다. 정확한 게시 HEAD는 GitHub와 `git rev-parse HEAD`로 확인한다.
- 로봇에 실제 설치된 소스는 **`d7807de8f15fb457942039bb90ab41cf68d384c6`**다.
  checkout은 `/home/unitree/robot-scope`, 서비스는 `robot-scope.service`다.
  **GitHub 게시가 로봇 배포 완료를 뜻하지 않는다.**
- 인계 작성 전 작업 트리는 clean이었다. 미커밋 사용자 변경이나 진행 중인
  개발 작업은 없다. 맥북 담당의 종료를 확인한 뒤 새 데스크탑 하나만
  배포·제어 담당이 된다. 로봇 전원과 실행 서비스는 종료하지 않았다.
- 새 데스크탑이 같은 네트워크라는 것은 사용자 제공 정보다. 새 환경의
  인증·도구 설치·실제 로봇 접속 성공은 아직 확인하지 않았다.

## 완료한 작업과 미배포 기능

승인된 dashboard 배포 및 기존 소유 LiDAR 미리보기 재시작은 한 번 완료했다.
소스·설정·보존 데이터 검사를 통과했고, 60초 읽기 관측에서 LiDAR/pose 조회
62건이 모두 응답했다. 저장 3D 지도 표시도 확인했다. 당시 제어 브리지는
inactive/disabled, 자동 시작 OFF였으며 카메라·broker의 실행 주체는 유지됐다.
이는 당시의 관측 기록이다. 현재 상태는 새 담당이 읽기로 다시 확인한다.

새 기능 소스에는 기존 Maps 화면과 분리된 비동기 전역 관측 패널 및
start/get/cancel/export API가 있다. 요청 중복·취소·늦은 완료를 처리하고,
지도 revision·frame·observer epoch가 달라지면 결과를 무효화한다.
기존 subscription에서 명시적으로 요청한 한 장의 XYZ 전체를 display
throttle/cap/filter 전에 보존하고, 원본 binary PCD를 별도로 읽는다.
**새 기능은 로봇에 배포하지 않았고 실제 backend 정합도 실행하지 않았다.**

상세 계약과 환경변수는 [ASYNC_GLOBAL_OBSERVATION.md](ASYNC_GLOBAL_OBSERVATION.md)에 있다.
기본 provider는 `UNAVAILABLE`이다. 고정된 외부 Python·backend source·전체
source hash pin을 서버 설정에 준비해야 한다. 소스 해시 확인은 Open3D
의존성 실행 확인과 다르다. 현재 worker는 시작·import를 포함한 120초 deadline,
취소 시 process group 정리, 64KiB 출력 제한을 둔다. OS 메모리 hard cap은 없다.

## 결과 해석과 남은 검증

- 전체 입력의 범위는 **수신 PointCloud2의 XYZ 전체**다. 원래 센서 패킷이나
  비XYZ 필드 archive가 아니다. raw/converted 입력을 구분하며 upstream 처리와
  source clock은 미검증으로 기록한다. 0점·순서·정확한 ns 문자열을 보존한다.
  비유한 입력은 현재 backend가 명시 거부하며 조용히 제거하지 않는다.
- 결과는 항상 **HISTORICAL_ONLY / T_map_sensor**다. `current_result=null`,
  `body_pose=null`, `tracking_verified=false`다. 과거 캡처를 새 시각으로 바꾸거나
  현재 로봇 마커에 적용하지 않는다. 검증된 sensor-to-body 외부표정,
  동일 epoch odometry 전파 및 새 scan 검증은 별도 후속이다.
- **inlier RMSE ≤0.10m는 잠정 관측 기준이며 정밀 정확도가 아니다.**
  기존 5cm 결과와 수렴·inlier·overlap·geometry 등 다른 gate를 보존한다.
  기존 live 경로의 600ms, 1Hz, 1초 freshness, 150ms receipt pairing은 유지한다.
- 새 raw global backend는 원래 **5cm 선택·ambiguity·stationarity gate**를
  유지한다. 10cm는 저장 잔차 sidecar 비교이며 global 재선택이 아니다.
  `selected_candidate=null`을 잔차만으로 승격하지 않는다.
- 실제 비동기 정합, 현재 본체 pose, 실시간 추적, 독립 정답 기반 정확도와
  주행은 미검증이다. 명목 외부표정을 확정 calibration으로 자동 적용하지 않는다.

## 검증과 재현

기존 Mac 환경은 CPython3.13.2 가상환경이다. system Python이나 Mac 가상환경을
새 데스크탑에서 그대로 사용할 수 있다고 가정하지 않는다. 저장소 requirements와
CI에 지정된 환경을 참고한다. 테스트에는 로컬 Unix socket/localhost 허용이 필요하다.

| 검사 | 게시 전 결과 |
|---|---|
| Python 전체 | 2,410개 실행: 2,400 통과·3 skip·7 오류. 7개는 AST 격리 시험에 새 mixin 이름이 빠진 fixture 오류였다. fixture만 수정한 뒤 해당 모듈 19개 통과. 수정 후 단일 전체 재실행은 하지 않았다 |
| JavaScript | 전체 525개 통과 |
| 합성 브라우저 | 신규 global 3개 + 기존 live 6개, 총 9개 통과 |
| 정적 검사 | Ruff, 설정된 mypy 4모듈, frontend syntax 96모듈, secret/diff 검사 통과 |
| 실제 장비 | 앞서 설치한 d7807de의 입력·화면 확인만 수행. 새 비동기 기능은 미실행 |

브라우저와 새 worker 검사는 합성 fixture다. 실제 카메라·정합 검증으로
취급하지 않는다. 첫 전체 실행의 소켓 권한 제한과 API 목록/파일 길이 실패는
환경 재실행 및 최소 수정으로 해결했다. skip은 optional plotting, rosbags,
Mac에서 실행하지 않는 Linux `/proc` 시험이다. **GitHub CI는 게시된 정확한
HEAD의 Actions 결과를 확인하며 과거 CI 성공으로 대체하지 않는다.**

```sh
python -m unittest discover -s tests -v
npm run test:unit
npx playwright test tests/e2e/global_observation.spec.mjs tests/e2e/live_observation.spec.mjs --reporter=line
python -m ruff check robot_dashboard scripts
python -m mypy --config-file mypy.ini
node scripts/check_frontend_syntax.mjs
python scripts/check_repository_secrets.py
```

## 추가로 필요한 자료와 보존 범위

이 저장소에는 코드·프로젝트 문서·합성 회귀 자료만 게시한다. 원본 지도·센서
점군·bag·카메라 샘플, 비공개 수업 자료·링크, 인증자료는 이번 게시에 포함하지 않는다.

실지도·샘플·미션 이력은 로봇의 `/home/unitree/robot-scope-data/`에 보존되어 있다.
repo/config, `/home/unitree/.config/robot-scope`, systemd 설정, VSLAM 설치와
카메라/session lock을 보존한다. 배포 때 만든 source/config/data 백업은 로봇의
기존 deployment 디렉터리에 남아 있다. 자동 복구나 삭제를 수행하지 않는다.

실제 backend 연결에는 맥북에 별도로 보존한 **검토된 v0.3.1 backend source,
원본 해시 manifest 및 적합한 Python/Open3D 환경**이 필요하다. 그 자료와
과거 실험 재현용 private evidence는 Git에 없고 새 계정으로 전송하지 않았다.
공개 코드·합성 시험 검토에는 필요하지 않다. 필요할 때 사용자 승인 방식으로
별도 준비하며, 인증 개인키나 비공개 자료를 공개 저장소에 추가하지 않는다.

## 다음 첫 작업 / 복사용 시작 프롬프트

> 이 인계 문서를 읽고 Robot Scope를 이어받아줘. 맥북 작업 종료와 단일
> 담당을 확인한 뒤, 새 데스크탑의 인증·접속 및 로컬/로봇 HEAD, 미커밋 변경,
> 서비스 owner와 활성·미저장 세션을 읽기 확인해. 실제 설치 d7807de와
> 미배포 비동기 기능을 구분하고 지도·설정·이력을 보존해. 공개 코드와 해당
> HEAD CI부터 검토하고, private backend가 GitHub에 있다고 가정하지 마.
> 새 배포·재시작·센서·카메라·TF·initialpose·goal·이동은 정확한 변경·백업·복구와
> 현재 현장 조건을 포함한 별도 승인 전 수행하지 마. historical 센서 후보를
> 현재 본체 pose로 표시하거나 잠정 10cm 잔차를 정확도 검증으로 부르지 마.
