# A3 검증 기록

합성 경계는 실제 FastAPI, 지도 카탈로그, Navigation coordinator와 화면을 사용한다. ROS 메시지, Nav2 액션 서버, 제어권과 프로세스는 테스트 입력으로 바꾼다. 별도 ROS 테스트는 실제 runtime/gateway 콜백을 테스트 메시지와 그래프 fixture로 호출한다.

| ID | 오프라인 판정 | 근거 |
| --- | --- | --- |
| E00 | PASS · SYNTHETIC | 실험의 GET과 화면 진입에서 쓰기 0건. 기본 API는 3D 사전 검사 유지. 운영 모드의 bundle 누락을 거부. |
| E01 | PASS · SYNTHETIC | nonzero odometry 원점과 회전에서 기존 SE(2) 수동 정렬, seed 이후 상대 이동, 새 스탬프의 TF echo를 검사. 기존 변환 회귀 포함. |
| E02 | PASS · SYNTHETIC | 실험 job manifest/인자 및 3D bundle 미생성 확인. 입력 불충분에서는 활성화 0건, 소유 작업 정리 확인. |
| E03 | PASS · SYNTHETIC | job/map/revision, seed generation과 odom epoch, 2초 정지 관측, 지연·중복 및 TF 없는 수락을 거부. runtime receipt와 TF echo 확인. |
| E04 | PASS · SYNTHETIC | 회전된 저장 지도에서 드래그로 한 목표를 보냄. FastAPI fixture에서 저장 주석 revision과 목표당 액션 1건 확인. 공유 좌표 변환과 URDF 표시 회귀. |
| E05 | PASS · SYNTHETIC | source epoch 변경, 제어 heartbeat 중단, 활성 목표에서 재초기화 거부, 관리 지도 변경 감지 뒤 종료. 새 요청 없이 이전 seed와 목표를 복원하지 않음. |
| E06 | PASS · SYNTHETIC | 일반/실험/위치추정 전용 작업 경합, 외부 TF·cold odom 소유자 거부 및 정확한 job만 정리. |
| E07 | PASS · SYNTHETIC | signed STOP/lease·목표 취소·stale gate와 실제 callback의 fail-closed 분기를 확인. 실제 Nav2 장애물 반영과 물리 정지는 E10 및 A1 범위. |
| E08 | PASS · SYNTHETIC | 전체 대시보드에서 실제 로컬 FastAPI로 준비 → 드래그 seed → 목표 → 취소 → STOP 검증. 센서·Nav2·제어는 합성 경계. |
| E09 | 로컬/CI 결과 아래 참조 | C0 기본 준비, A0 지도·프리셋, A2 확장, REPLAY 및 기존 Navigation 회귀. |
| E10 | PASS · NATIVE, Nav2 ACTIVE 확인 후 | 후속으로 `4cebeed`를 네트워크 없는 Humble 컨테이너에서 실행했다. 7개 케이스 통과. 시드 수락 직후 목표 거부 사례도 보존했다. [측정값과 A1 확인 사항](HANDOFF.md) · [실행 결과](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41983696807) |
| E11 | DEVICE_NOT_RUN | A1용 코드·사용법·readback·복귀 순서를 인계 문서에 기록. |

## 첫 실패와 조치

- JavaScript 전체 검사에서 기존 3D 편집 테스트가 파일 끝의 초기화 구간을 함께 읽었고 실험 초기화가 그 안에 포함되었다. 실험 연결을 해당 구간 밖으로 옮겼다. 이전에 폐기 상태였던 `#experiments`를 새 메뉴로 열도록 기존 라우트 기대값을 갱신했다.
- 브라우저 첫 실행은 루프백 권한이 없어 서버가 뜨지 않았다. 이후 합성 실험에서 목표 도구로 전환할 때 이미 스크롤된 캔버스 좌표를 사용하던 시험을 수정했다. 제품 흐름에서 도구마다 실제 화면 위치를 읽고 조작한다.
- Python 첫 전체 검사에서 `app.py` 크기 기준을 초과해, 실험의 소유자 검사를 ApplicationRuntime으로 이동하고 기존 API 모델 전달을 재사용했다. 최초 환경의 임시 경로 및 루프백 제한은 같은 시작 SHA에서도 실패를 재현했다.
- 실험에 job 및 map revision 외에 seed 세대와 source epoch를 결속했다. 기존 seed와 다른 발행자나 작업에서 온 초기값, 수락 직후 재전송된 동일 요청은 거부한다.

- 게시 후 실행기 점검에서 실험의 상대 odometry 전용 FAST-LIO가 비활성화한 `/Laser_map`을 기존 매핑 준비 단계가 기다리는 결함을 찾았다. 유선과 무선 실행기에서 실험만 기존 `/Odometry` 준비 검사를 쓰는 단계를 선택한다. 일반 매핑은 기존 `/Laser_map` 조건을 함께 유지한다.

## 로컬 재검증

- Navigation, API, ROS 콜백, 공용 인터페이스와 아키텍처 관련 Python 115개 통과. 일반 `RosAgent`의 메서드 시그니처는 보존했고 수동 작업은 동일 gateway의 별도 포트를 사용한다.
- 전체 JavaScript 765개와 문법 검사 통과. 실제 대시보드 + FastAPI 합성 Playwright 1개 통과.
- 전체 로컬 브라우저 337개 중 첫 실행 328개가 통과했다. Python 환경을 지정한 재검사에서 A0 프리셋, C0 준비 API 및 모바일 미션 화면이 통과했다. 간헐적인 준비 화면 시험은 단독 반복 4회에서 모두 통과했다.
- 상대 odometry 전용 준비 단계 수정 후 XT16, 작업 관리, 무선 profile 회귀 65개 통과.
- 전체 Python은 로컬 macOS에서 실행했다. 기존 Linux `/proc`와 파일 소유권에 의존하는 검사에 로컬 제약이 남는다. 지원 Linux의 전체 시험은 게시된 SHA의 CI에서 확인한다.
- Ruff, mypy, 변경 shell 구문, Git 변경 검사 통과.

## 재현 명령

```sh
python3 -m unittest discover -s tests -v
PYTHONPATH=tests python3 -m unittest test_manual_navigation_api test_manual_navigation_ros test_navigation_jobs -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
npx playwright test --config playwright.manual-navigation.config.mjs --reporter=line
```

실제 대시보드 시험의 Python 경로는 `MANUAL_NAVIGATION_TEST_PYTHON`으로 지정할 수 있다. CI는 저장소 고정 Playwright와 ROS 없는 Linux 환경을 사용한다.
