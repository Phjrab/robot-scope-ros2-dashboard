# 통합 오프라인 지도 작업

확장 기능의 두 탭은 입력과 보정 단위가 다릅니다.

| 탭 | 입력 | 계산과 저장 |
|---|---|---|
| 주행 기록 보정 | 키프레임 자세·오도메트리·로컬 스캔을 담은 offline-keyframes JSON | 앵커를 고정한 3D 포즈 그래프 최적화, 스캔 재투영, 전후 비교, 새 PCD·점유 지도·ZIP 저장 |
| 여러 지도 병합 | 완성된 원본 binary PCD 2개 이상과 고정된 출처 정보 | 기존 다중 지도 정합·그래프 계산, 후보 검토·수락, 원본 필드를 보존한 새 병합 지도 저장 |

완성된 PCD만으로 내부 주행 드리프트를 복구하지 않습니다. 이 경우 여러 지도 병합을 사용하며, 주행 기록 보정에는 키프레임별 원본 스캔과 상대 이동 측정이 필요합니다.

## 로컬 실행

저장소의 Python 의존성이 설치된 환경에서 실행합니다. Windows에서는 `python` 대신 `.venv/Scripts/python.exe`를 사용할 수 있습니다.

```sh
python -m robot_dashboard.offline_slam.workbench --root runtime/workbench --port 8092 --synthetic-demo
python -m robot_dashboard.offline_slam.demo --output runtime/synthetic-drive.json
```

브라우저에서 `http://127.0.0.1:8092/`의 메인 대시보드를 열고, 왼쪽 **확장 기능** 메뉴에서 **주행 기록 보정** 또는 **여러 지도 병합**을 선택합니다. 확장 화면 상단의 **메인 대시보드로 돌아가기**로 복귀할 수 있습니다. 로컬 메인 화면에는 로봇 운영 API가 없으므로 연결·센서 상태는 미연결로 표시됩니다.

주행 기록 보정에서 `synthetic-drive.json`을 불러오고 검색 반경 1.2 m, 최소 키프레임 간격 10으로 보정합니다. 저장 후 ZIP을 내려받을 수 있습니다. 여러 지도 병합 탭에서는 생성된 합성 지도 두 개를 선택해 정합·후보 수락·새 PCD 저장을 진행합니다. 저장된 병합 지도는 같은 로컬 목록에 다시 나타나며 출처 계보 중복 검사는 그대로 적용됩니다. 기존 `/extensions#trajectory`, `/extensions#multimap` 직접 링크도 지원합니다.

`--synthetic-demo`를 생략하면 합성 지도는 생성되지 않습니다. 기존 단독 실행기 `python -m robot_dashboard.offline_slam.server`도 계속 지원합니다.

## 다른 PC에서 접속

분석 서버 PC에서 네트워크 모드를 명시적으로 실행합니다. 다른 PC는 각자 서버를 설치하지 않고 분석 PC의 주소를 브라우저로 엽니다. 계산과 지도 저장은 분석 서버의 동일한 작업 저장소에서 수행됩니다. 기본 실행은 계속 로컬 전용입니다.

아래 주소는 예시이며 분석 PC의 실제 LAN IP와 서브넷으로 바꿉니다. 비밀번호 파일은 Git에 추가하지 않습니다.

```sh
python -c "from pathlib import Path; import secrets; p=Path('runtime/network-access'); p.mkdir(parents=True,exist_ok=True); (p/'password.txt').open('x').write(secrets.token_urlsafe(32))"
python -m robot_dashboard.offline_slam.workbench --root runtime/workbench --port 8092 --host 0.0.0.0 --allow-host 192.168.50.10:8092 --allow-host 127.0.0.1:8092 --allow-host localhost:8092 --allow-network 192.168.50.0/24 --password-file runtime/network-access/password.txt
```

다른 PC에서 `http://192.168.50.10:8092/`를 열고 브라우저 인증창에 사용자 이름 `review`와 파일의 비밀번호를 입력합니다. 메인 → 확장 기능 → 작업 선택 흐름은 동일합니다. 로컬의 `127.0.0.1` 주소도 네트워크 모드에서는 인증이 필요합니다. 비밀번호 변경 후 서버를 재시작하면 이전 비밀번호는 더 이상 사용할 수 없습니다.

이 모드의 HTTP Basic 인증은 HTTP 자체를 암호화하지 않습니다. HTTP 실행은 신뢰하는 사설 LAN용입니다. 공유·비신뢰 네트워크에서는 브라우저가 신뢰하는 인증서와 `--ssl-certfile server.pem --ssl-keyfile server.key`를 함께 지정하여 HTTPS로 접속합니다. 프록시 전달 헤더는 신뢰하지 않습니다. 포트 포워딩으로 인터넷에 공개하지 않습니다.

방화벽에는 해당 Python 실행 파일의 TCP 8092 인바운드만 허용하고, 원격 주소를 같은 LAN 서브넷으로 제한합니다. Windows에서는 이 규칙 추가에 관리자 권한이 필요합니다. 방화벽 전체를 끄거나 네트워크 프로필 전체를 변경할 필요는 없습니다. 공유기의 게스트 Wi-Fi/AP 격리가 켜진 경우 PC 사이 접속이 차단될 수 있습니다.

허용 Host, 클라이언트 네트워크, 비밀번호는 메인·정적 파일·두 API·다운로드에 동일하게 적용됩니다. 변경 요청은 같은 출처와 프로토콜이어야 합니다. 인증된 사용자들은 같은 분석 작업 공간을 공유하므로 개인별 자료 격리 서비스는 아닙니다. 기존 로봇 대시보드 서버의 연결 주소나 배포 설정은 이 실행으로 변경되지 않습니다.

## 실제 로컬 지도 사본 등록

워크벤치 루트 아래에 원본의 **사본**을 두고 `sources.json`에 다음 구조의 배열을 작성합니다. `descriptor`는 기존 `MapSourceDescriptor` 계약 전체입니다. 데이터 파일은 Git에 추가하지 않습니다.

```json
[
  {
    "file": "inputs/source-a.pcd",
    "descriptor": {"...": "MapSourceDescriptor의 전체 필드"},
    "lineage": {}
  }
]
```

실측 사본의 `evidence_kind`는 `REPLAY`이고, `sha256`, 포인트 수, 스키마, 좌표계는 실제 파일과 일치해야 합니다. 경로는 워크벤치 루트 내부만 허용하며, 요청에서 임의 파일 경로나 원격 주소를 받지 않습니다. 키프레임 JSON은 주행 기록 보정 탭에서 직접 불러옵니다.

## 공통 구현과 운영 경계

- 기존 확장 페이지와 다중 지도 UI·API 계약·작업 관리자·BundleStore를 재사용합니다. 주행 기록 UI는 같은 페이지의 `/analysis/`에 마운트하며 단독/통합 모드가 동일한 코드와 상대 API 경로를 사용합니다.
- 강체 적합과 SE(3) 역변환은 기존 `relocalization.experimental_se3` 구현을 공유합니다. 키프레임 그래프와 지도별 그래프는 의미와 품질 판정이 달라 각각 유지합니다.
- 파일 잠금은 공통 `file_lock`을 사용합니다. POSIX에서는 기존 flock, Windows에서는 실제 바이트 잠금을 사용합니다. Windows 저장은 파일 flush 후 rename하며 디렉터리 fsync는 지원하지 않습니다.
- 워크벤치는 기본적으로 127.0.0.1에만 바인딩합니다. 네트워크 모드에는 명시적 허용 주소·사설 네트워크·비밀번호가 필요하며 원본 변경 검사와 동일 출처 검사를 유지합니다. ROS, 로봇 애플리케이션, 센서 연결, 지도 선택·배포 경로를 시작하지 않습니다. 계산량은 분석 PC에서 사용합니다.
- 기존 운영 대시보드의 확장 메뉴에는 같은 두 탭이 표시됩니다. 운영 서버의 주행 기록 탭은 분석 PC의 통합 워크벤치 실행 안내를 제공합니다. 로봇 서버에 계산기를 자동 탑재하지 않습니다.
- 저장 위치는 `--root` 아래의 `trajectory/`, `merged/`입니다. 결과는 새 리뷰용 사본이며 운영 지도에 자동 적용되지 않습니다.

## 검증 명령

```sh
python -m unittest tests.test_offline_slam tests.test_offline_workbench -v
python -m unittest discover -s tests/expansion_d1 -v
node --test tests/*.mjs
node scripts/smoke_offline_slam.mjs --workbench
python -m unittest tests.test_offline_network -v
node scripts/smoke_offline_slam.mjs --workbench --network
```

브라우저 검사는 `OFFLINE_SLAM_PYTHON`에 Python 경로를 지정할 수 있습니다. 합성 데이터로 두 모드의 실제 계산, 검토·저장·재조회, 화면 전환, 모바일 주행 비교 화면을 검사합니다. 실장비 검증은 별도입니다.

### 2026-11-16 로컬 검증 결과

- 통합 API·오프라인 보정·등록 진단·기존 병합 솔버·동시 저장/롤백 집중 검사: 45건 통과.
- 기존 대시보드 JavaScript 단위 검사: 781건 통과.
- Playwright 통합 화면 및 기존 단독 화면: 실제 합성 보정, 저장, ZIP 다운로드, 재조회, 모바일 비교 통과. 통합 화면의 병합 후보 수락·저장·목록 재조회·탭 복귀 통과.
- 전체 Python `unittest discover -s tests -v`도 실행했으나 Windows의 Linux 전용 의존성·프로세스 API 제약으로 통과하지 못했고 프로세스 관리 테스트에서 중단됐습니다. 추가 범위에는 `fcntl`·`fork`·심볼릭 링크 권한, 디렉터리 fsync 가정, C++ 시험 컴파일 환경에 의한 실패가 있습니다. 전체 회귀 통과 또는 실장비 검증으로 해석하지 않습니다.
- 실장비 접속, ROS 실행, 배포, 운영 지도 채택 없음. 검증 입력과 생성 지도는 Git에서 제외된 `runtime/` 또는 임시 디렉터리에만 저장했습니다.
