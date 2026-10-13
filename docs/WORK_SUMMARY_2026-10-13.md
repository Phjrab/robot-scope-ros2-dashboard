# Robot Scope 작업 정리 — 2026-10-13

Robot Scope는 ROS 2 로봇의 센서·지도·제어·경로 계획과 Jetson의 자원 사용량을
브라우저에서 확인하는 프로젝트입니다. 이 문서는 저장소의 기존 기능과 이번에
완료한 Jetson 자원 대시보드 작업을 정리합니다.

## 프로젝트 구성

| 영역 | 구현된 내용 | 상세 문서 |
|---|---|---|
| 로봇 관측 화면 | 카메라·3D LiDAR·Safety HUD·레이아웃 저장 | [Cockpit 운영](COCKPIT_OPERATOR_GUIDE.md) |
| 매핑·저장 지도 | Hesai/FAST-LIO 연결, 지도 저장·조회·편집 | [설치 가이드](INSTALL.md) |
| 제어·경로 계획 | Go2 수동 제어, ARM·deadman, Nav2 연결, Route Planner | [운영 안내](OPERATOR_GUIDE.md) |
| Jetson 내부 운영 | Go2 내부 Orin NX용 운영 프로필과 이전·인수 기록 | [온보드 이전](GO2_ONBOARD_MIGRATION.md) |
| 화면 구성 | Mission Control 화면, 밝은 테마·어두운 테마, 가독성 개선 | [UI 작업 기록](ui-redesign/FINAL_REPORT.md) |
| 자원 모니터 | 보드의 부하 관측과 설정 변경 전후 비교 | [자원 모니터 안내](JETSON_RESOURCE_MONITOR.md) |

기존 구현·검증의 범위는 [README](../README.md)와 [포트폴리오 근거](PORTFOLIO.md)에
기록돼 있습니다. 실장비 Nav2 목표 도달과 경기 완주는 확인되지 않았습니다.

## 이번에 완료한 Jetson 자원 모니터

CPU 전체·코어별 사용률, GPU 사용률·클럭, 공유 메모리·SWAP, 온도, 보드 입력 전력,
네트워크 처리량, 프로세스별 부하를 표시합니다. 측정은 웹 서버가 실행되는
호스트를 기준으로 하며, 화면의 호스트 이름으로 측정 대상을 확인할 수 있습니다.

- 약 1초 간격으로 값을 갱신하고 최근 15분의 추이를 표시합니다.
- 설정 변경 전 기준을 저장하고 변경 후의 별도 구간과 비교합니다.
- 해상도·FPS·LiDAR Hz 등 변경 내용을 메모하고 그래프에 시점을 표시합니다.
- 측정값과 변경 메모를 CSV로 내보낼 수 있습니다.
- 로봇·ROS 서비스 없이 보드 자원만 볼 수 있는 단독 실행 모드를 제공합니다.
- Robot Scope에 연결된 경우 기존 카메라·ROS 상태에서 센서 수신률을 함께 표시합니다.

센서 설정 변경은 해당 드라이버에서 수행합니다. 대시보드가 센서별 CPU·GPU
사용 비중을 추정하거나 로봇·클럭 설정을 변경하지는 않습니다.

## CPU·GPU 표시 개선

순간 사용률만 크게 표시하면 값이 자주 변해 전체 부하를 판단하기 어려웠습니다.
큰 숫자와 작은 숫자의 역할을 나누었습니다.

| 표시 위치 | 의미 |
|---|---|
| 큰 숫자·막대 | 최근 10초의 CPU·GPU 평균 사용률 |
| 바로 아래 작은 글씨 | 현재 사용률 |
| 클럭 표시 | 현재 GPU 클럭, 활성 CPU 코어의 클럭 범위 |
| 평균 수집 중 | 아직 10초가 모이지 않았을 때 수집한 값의 평균과 측정 개수 |

실제 0%는 평균에 포함하고 측정 불가능한 값은 `—`로 표시합니다. 연결 끊김,
일시정지, 창 비활성 또는 2.5초를 넘는 수신 공백 뒤에는 평균을 새로 모읍니다.
큰 숫자는 관측한 사용률의 시간 평균이며 최대 클럭 대비 연산 성능 비율은 아닙니다.

그래프·CSV·코어별 상세·부하 안내에는 현재 측정값을 사용합니다. 설정 전후 비교는
기존의 최근 30초 구간을 사용하며 최소 10초와 5개 이상의 연속 측정을 기다립니다.

## 실행 방법

현재 Jetson에 준비된 가상환경에서 실행합니다.

```bash
cd /home/unitree/robot-scope
.venv/bin/python -m robot_dashboard.resource_server --host 0.0.0.0 --port 8090
```

- Jetson 브라우저: `http://localhost:8090/`
- 같은 네트워크의 다른 PC: `http://<Jetson-IP>:8090/`
- 종료: 실행한 터미널에서 `Ctrl+C`
- 화면 수정 후 갱신: 브라우저에서 `Ctrl+Shift+R`

`address already in use`가 나오면 먼저 기존 주소에서 대시보드가 열리는지
확인합니다. 별도 포트가 필요하면 실행 명령의 `--port 8090`을 `--port 8091`로
바꾸고 접속 주소에도 `8091`을 사용합니다.

기존 Robot Scope에서 열 때는 **Jetson 자원** 메뉴 또는
`http://<Robot-Scope-주소>/static/resources.html`을 사용합니다.
새 PC나 새 Jetson에는 먼저 [설치 가이드](INSTALL.md)에 따라 환경을 준비합니다.

## 검증 결과

| 검사 | 이번 변경에서 확인한 결과 |
|---|---|
| JavaScript 모델·화면 테스트 | 10개 통과: 평균 구간, 실제 0%, 측정 누락, 실시간 값 분리, 일시정지·재연결, 비교·CSV |
| Python 자원 수집·API 테스트 | 8개 통과 |
| API 계약 테스트 | 6개 통과 |
| Runtime 구조 테스트 | 5개 통과 |
| HTTP 보안 테스트 | 7개 통과 |
| HTML 요소 연결·Git diff 형식 | 확인 완료 |

JavaScript 테스트는 이 환경에 Node.js가 없어 설치된 JavaScriptCore에서
Node 테스트 등록·assert 부분을 대체한 실행기로 같은 테스트 본문을 검증했습니다.
일반 개발 환경에서는 다음 명령으로 실행할 수 있습니다.

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_resource_monitor.py' -v
node --test tests/test_resource_monitor.mjs tests/test_resource_monitor_ui.mjs
```

전체 unittest는 시스템 Python의 FastAPI 누락, 기존 서비스 설정 소유권 검사 실패,
mapping coordinator 테스트의 시간 초과로 완료하지 못했습니다. 실제 브라우저의
수정 화면 렌더링과 LAN 접속도 이 실행 환경에서는 검증하지 못했습니다.

문서 정리 단계에서 가상환경으로 전체 검사를 다시 실행했으나, 서비스 설정 검사
4개와 installer 검사 1개의 실패·오류가 기록됐고 같은 mapping coordinator 구간에서
60초 제한에 도달했습니다. 전체 검사 통과로 보고하지 않습니다.

## 코드 위치와 작업 이력

| 경로 | 역할 |
|---|---|
| `robot_dashboard/resource_monitor.py` | Linux·Jetson 자원 측정 |
| `robot_dashboard/resource_server.py` | 단독 자원 모니터 서버 |
| `robot_dashboard/api/routers/resources.py` | 자원 조회 API |
| `robot_dashboard/static/resources.html` | 자원 대시보드 화면 |
| `robot_dashboard/static/features/resources/` | 평균·비교 계산, 화면 동작, 스타일 |
| `tests/test_resource_monitor*` | 측정·계산·화면 동작 테스트 |

- `a6d5f4a`: Jetson 자원 모니터·단독 서버·설정 전후 비교·CSV 추가.
- `dac467c`: CPU·GPU의 10초 평균과 현재 사용률·클럭을 구분해 표시.

측정 기록과 메모는 현재 브라우저 창에 보관되므로 필요한 기록은 새로고침 전에
CSV로 내보냅니다. 실제 주행·센서 설정·서비스 배포 검증은 해당 장비에서 별도로 진행합니다.
