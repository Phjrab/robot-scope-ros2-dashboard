# 업데이트와 롤백

Robot Scope 업데이트는 소스만 바꾸는 작업이 아닙니다. Python 의존성, systemd unit,
외부 ROS workspace와 지도 runtime 상태가 함께 영향을 받을 수 있습니다. 실제 경기나
주행 직전에는 업데이트하지 말고 검증 시간을 확보하세요.

## 업데이트 전 조건

1. 로봇을 안전하게 정지하고 물리 리모컨을 확보합니다.
2. Controls를 DISARM하고 Navigation을 STOP합니다.
3. 매핑 start/stop/save/convert 작업이 모두 끝났는지 확인합니다.
4. Dataset Capture가 실행 중이면 `STOP & FINALIZE`를 누르고 `COMPLETED`와
   마지막 `manifest.json`을 확인합니다.
5. 현재 commit, 설치 mode와 외부 dependency revision을 기록합니다.
6. 환경 파일, 지도·상태 파일과 데이터셋을 checkout 밖의 접근 제한된 위치에
   백업합니다.

~~~bash
cd /path/to/robot-scope
git status --short --branch
git rev-parse HEAD
python3 scripts/robot_scope_doctor.py --mode observer
~~~

작업 트리가 깨끗하지 않으면 update를 중단합니다. 운영 호스트에서 임시 수정한 파일을
stash나 강제 checkout으로 숨기지 말고, 변경 내용을 호스트별 설정 또는 별도 patch로
정리합니다.

## 백업 대상

기본 경로는 설치에 따라 다를 수 있습니다.

- `<project>/runtime/config/robot-scope.env`
- `<project>/runtime/config/control.env`
- `<project>/runtime/state/`
- `ROBOT_SCOPE_DATASET_DIR` 전체; 빈 값이면 `<project>/runtime/datasets/`
- `ROBOT_SCOPE_MAPS_DIR`의 PCD/PGM/YAML
- 현장별 Hesai/FAST-LIO config와 SHA-256 기록
- 설치된 systemd unit과 sudoers 파일의 검증된 사본
- `/usr/local/libexec/robot-scope/realsense_mjpeg_relay.py`와
  `/etc/systemd/system/robot-scope-realsense-camera.service`의 검증된 사본 및 enable 상태

키와 토큰 백업은 암호 관리 도구나 접근 제한 저장소를 사용합니다. Git, issue, CI artifact에
올리지 않습니다. 지도와 데이터셋 백업은 원본을 덮어쓰지 않고 날짜가 있는 읽기 전용
snapshot으로 보관합니다. 데이터셋은 복사 전·후의 세션 수, `manifest.json`의
`sample_count`, 전체 byte 크기를 비교하고 최소 한 장의 JPEG를 열어 검증합니다.

## Fast-forward 업데이트

검증된 release tag 또는 승인된 commit만 사용합니다.

~~~bash
git fetch --tags origin
git pull --ff-only origin main
git rev-parse HEAD
./scripts/install_ubuntu.sh --mode observer
./scripts/install_ubuntu.sh --mode observer --apply
python3 scripts/robot_scope_doctor.py --mode observer
python3 -m unittest discover -s tests -v
~~~

실제 설치 mode로 installer와 doctor를 다시 실행합니다. 외부 workspace는 Robot Scope
업데이트와 동시에 움직이지 말고, 필요할 때 별도 변경 기록과 검증 절차로 업데이트합니다.
기존 배포에서 system package/service installer를 사용했다면 dry-run 검토 후 같은
`--install-system-packages`, `--install-service` opt-in을 명시합니다. Unit을 다시 설치하고
도 installer는 enable 상태를 바꾸거나 service를 자동 start/restart하지 않습니다.

서비스 재시작 전에 release note와 diff에서 다음 항목을 확인합니다.

- profile/topic 우선순위 또는 source persistence 변경
- control protocol, watchdog 또는 allowed action 변경
- mapping save/지도 형식 변경
- navigation parameter schema 변경
- systemd/sudoers 변경

로봇 탑재 RealSense relay를 수동 설치한 배포는 Git checkout만 업데이트해도 root-owned
실행 파일이 바뀌지 않습니다. `.18`에서 기존 자동 시작 정책과 실행 상태를 먼저 기록한 뒤,
검증한 checkout의 두 파일을 다시 설치합니다. 이미 active라면 enable 상태를 바꾸지 않고
restart해야 새 실행 파일이 적용됩니다. inactive였다면 업데이트만으로 임의 start하지
않습니다.

~~~bash
systemctl is-enabled robot-scope-realsense-camera.service
systemctl is-active robot-scope-realsense-camera.service
sudo install -o root -g root -m 0755 scripts/realsense_mjpeg_relay.py \
  /usr/local/libexec/robot-scope/realsense_mjpeg_relay.py
sudo install -o root -g root -m 0644 \
  deploy/robot-scope-realsense-camera.service.example \
  /etc/systemd/system/robot-scope-realsense-camera.service
sudo systemctl daemon-reload
# 업데이트 전 active였을 때만 실행
sudo systemctl restart robot-scope-realsense-camera.service
systemctl is-enabled robot-scope-realsense-camera.service
systemctl is-active robot-scope-realsense-camera.service
~~~

`enable --now`는 restart 대체 명령이 아니며, 실행과 함께 다음 부팅의 자동 시작까지
활성화합니다. 공용 개발 host의 manual-only 정책은 `disabled`를 유지하고 `systemctl start`로
현재 세션만 시작합니다. 전용 relay host로 합의한 경우에만 `enable --now`를 사용합니다.

## 재시작 후 스모크 테스트

~~~bash
robot-scope-dashboard restart
robot-scope-dashboard status
robot-scope-dashboard logs
curl -fsS http://127.0.0.1:8088/api/v1/health
~~~

SSH operator helper 또는 lifecycle sudoers를 설치하지 않은 배포에서는 기존 exact
`systemctl` 절차를 사용합니다.
Helper는 새 systemd 실행 ID까지 확인하므로 `--no-block restart` 직후의 이전 active 상태를
성공으로 오인하지 않습니다.

Control bridge가 설치된 호스트는 dashboard와 동일한 bridge key를 읽는지 확인합니다. 로봇에
명령을 보내기 전에 observer→sensor→mapping→control/navigation 순서로 readiness를
확인합니다.

RealSense는 `.99` dashboard host에서 실제 `/stream`을 열어 완전한 JPEG 프레임을 확인한
뒤 Sensors의 단일/2화면을 검증합니다. `/health`의 `idle`은 viewer가 없다는 뜻일 뿐,
카메라 프레임 정상의 증거가 아닙니다. 정확한 curl/JPEG 검사 명령은
[문제 해결의 카메라 절차](TROUBLESHOOTING.md#카메라-화면이-없음)를 사용합니다.

## 안전한 소스 롤백

업데이트 전에 기록한 이전 commit이 있고 작업 트리가 깨끗할 때만 롤백합니다. `reset
--hard`나 강제 pull은 사용하지 않습니다.

~~~bash
git switch --detach <PREVIOUS_VERIFIED_COMMIT>
./scripts/install_ubuntu.sh --mode observer
./scripts/install_ubuntu.sh --mode observer --apply
python3 scripts/robot_scope_doctor.py --mode observer
~~~

실제 mode로 installer/doctor를 다시 실행한 뒤 서비스를 재시작합니다. detached 상태는
운영 복구에는 적합하지만 다음 개발의 기준 브랜치는 아닙니다. 복구가 끝나면 담당자가
원인과 사용할 release를 결정합니다.

Python requirements는 현재 호환 범위로 관리되어 exact lock이 아닙니다. 완전히 동일한
롤백이 중요하면 release별 virtualenv 또는 검증된 package constraints/artifact를 함께
보관해야 합니다.

## 지도와 상태 롤백

소스 롤백과 지도 롤백은 별도 작업입니다.

- 업데이트가 실패했다는 이유로 최신 지도를 자동 삭제하지 않습니다.
- 원본 지도와 편집본의 revision을 확인한 뒤 필요한 파일 묶음만 복구합니다.
- YAML과 PGM은 항상 같은 snapshot의 쌍으로 복구합니다.
- source selection 상태를 복구하면 선택한 LiDAR가 현재 배선과 맞는지 확인합니다.
- Navigation runtime의 임시 job/snapshot을 운영 지도 원본으로 사용하지 않습니다.

## 데이터셋 복구

데이터셋 복구는 대시보드 서비스를 중지하고 Dataset Capture가 비활성인 상태에서만
수행합니다. 현재 `ROBOT_SCOPE_DATASET_DIR`을 덮어쓰지 말고 별도 임시 경로에 백업을
복사한 뒤 세션 디렉터리와 manifest를 검증합니다. 검증한 세션만 고정
`sessions/<session-id>/` 구조로 복사하고, 소유자와 권한을 서비스 사용자에 맞춥니다.
서비스를 시작한 뒤 웹 갤러리의 세션 수·샘플 수가 manifest와 같고 최신·이전
페이지의 JPEG가 열리는지 확인합니다. 손상된 manifest를 임의로 편집하거나 세션 ID를
바꾸지 않습니다.

## systemd와 sudoers 롤백

installer가 unit을 바꾼 경우 이전에 백업한 root-owned 사본과 diff를 먼저 확인합니다.
sudoers는 설치 전에 `visudo -cf`로 문법을 검사하고 wildcard를 추가하지 않습니다.

Dashboard lifecycle sudoers를 제거하면 웹의 restart/stop 기능만 비활성화되어야 합니다.
운영체제 reboot/poweroff 권한을 롤백 편의 목적으로 추가하지 마세요.

RealSense relay의 이전 버전으로 되돌릴 때는 백업한 script와 unit을 같은 root-owned 경로에
복원하고 `daemon-reload`한 뒤, 롤백 전에 active였던 경우에만 restart합니다. 기능을 완전히
제거하는 롤백은 `.18`에서 다음 exact 경로만 대상으로 수행합니다. 이 절차는 자동 시작
symlink와 현재 프로세스를 함께 제거하며 Dashboard, XT16 relay와 지도에는 손대지 않습니다.

~~~bash
sudo systemctl disable --now robot-scope-realsense-camera.service
sudo systemctl reset-failed robot-scope-realsense-camera.service
sudo rm -f /etc/systemd/system/robot-scope-realsense-camera.service
sudo rm -f /usr/local/libexec/robot-scope/realsense_mjpeg_relay.py
sudo systemctl daemon-reload
systemctl is-enabled robot-scope-realsense-camera.service
systemctl is-active robot-scope-realsense-camera.service
~~~

마지막 두 명령은 제거 후 각각 `not-found`, `inactive`를 보고 비정상 종료 코드를 반환하는
것이 예상됩니다. 다른 파일이 남아 있거나 다른 이름의 drop-in/unit이 서비스를 다시
활성화하지 않는지도 `systemctl status`로 확인합니다.

## 롤백 완료 기준

- doctor가 설치 mode의 필수 항목을 통과함
- health API와 브라우저가 정상 응답함
- 저장 지도 목록과 원본 파일 revision이 유지됨
- 데이터셋 세션·manifest·샘플 수가 유지되고 NEWER·OLDER 페이지의 JPEG가 열림
- Go2/XT16 source identity가 의도한 장치로 표시됨
- RealSense 사용 배포는 `.99`에서 실제 JPEG를 받고 기대한 enable/active 상태가 유지됨
- 로봇 없이 가능한 테스트가 모두 통과함
- 현장 승인 후 제한된 실기 스모크 테스트가 통과함
