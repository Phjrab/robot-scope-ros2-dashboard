# Go2 내부 Jetson Isaac ROS VSLAM 실험 — 2026-10-13

실제 D435i의 정지 Stereo VO는 5분간 연속 추적했다. 공식 bag GPU 실행과 실제 stereo 입력도 확인했다. IMU 입력은 얻지 못했고, SLAM 지도 저장은 성공했지만 새 추정기의 재위치추정은 제한 시간 내 완료되지 않았다. 현재 권고는 **독립 실험 유지·추가 센서 검증 필요**다. 운영 자율주행 적용이나 FAST-LIO 대체 근거로 사용할 수 없다.

## 환경과 버전

Ubuntu 22.04.5/aarch64, kernel 5.15.199-tegra, L4T 36.5.2, Orin NX 16GB, Docker 29.1.3/NVIDIA runtime에서 실행했다. JetPack archive에서 L4T 36.5.2는 6.2.3에 대응하지만 호스트에는 CUDA 12.4/12.6/12.9 패키지가 섞여 있다. `/usr/local/cuda`는 12.6을 가리킨다. 이 전체 조합의 공식 인증을 주장하지 않는다. 컨테이너의 실제 CUDA/cuVSLAM 초기화와 출력으로 실행 가능성을 확인했다.

ROS Humble, VSLAM apt 3.2.6, common/interfaces/NITROS/GXF 3.2.5를 사용했다. image-proc는 3.2.10이다. 실제 이미지 ID, 저장소 SHA, 설치 패키지는 [runtime manifest](../../../experiments/isaac_vslam/versions.runtime.json), [package lock](packages-observed.tsv)에 기록했다. NVIDIA 소스는 별도 runtime workspace에 있고 Git에는 포함하지 않았다. Isaac apt 바이너리의 내부 build SHA가 참고 소스 SHA와 같다는 보장은 하지 않는다.

D435i serial 242322077753, firmware 5.17.3.10, USB 2.1/480Mbps, librealsense 2.55.1, NVIDIA wrapper 4.51.1-isaac이다. [공식 3.2 근거](OFFICIAL_REFERENCE.md)의 firmware 5.13.0.50과 다르며 펌웨어를 변경하지 않았다. 원래 전력 모드 MAXN, fan/clock 정책, OS/BSP/CUDA/호스트 ROS는 변경하지 않았다.

## 통과 기준과 실제 결과

| 항목 | 기준 | 판정과 관측 |
|---|---|---|
| T0 설치 | 실제 GPU tracker 초기화, bag 입력, 연속 odometry/status, 정리 | INSTALL_PASS, 성능 제한 있음. 60 stereo pairs 중 출력 26개, 모두 TRACKING; 출력 header span 13.64Hz, 최대 간격 200ms |
| 실제 stereo 입력 | 서로 다른 IR 영상, 실제 CameraInfo/TF/baseline, timestamp 및 profile 관측 | LIVE_INPUT_PASS(STEREO_ONLY). 640×480 mono8 30Hz. 전체 입력 trial 1166 pairs, 안정화 후 900 pairs/30.014초, 29.995Hz, stereo offset p50/p95/max 0ms |
| T1 정지 VO | 10초 안정화 후 약 300초 관측, 연속 출력·명시적 LOST 없음, 정상 정리 | VO_PASS(정지 시험 한정). 300.000초, odom/status 9016개, header span 30.026Hz, LOST 0 |
| VIO | stereo 통과 후 실제 카메라 IMU rate/축/단위/시간/TF 검증 및 융합 | BLOCKED. gyro/accel 지원 profile은 있으나 실제 IMU 메시지 0. 융합 실행·VIO_PASS 없음 |
| SLAM 저장 | 실제 mapping 활성화와 SLAM path, save 서비스 성공, 비어 있지 않은 지도 파일 | SLAM_TESTED: 정지 mapper/지도 저장. data.mdb 45,056 bytes, SHA256 c8426f33dfa789c0a13eef9bcf101a6cbb8bcee3f8c60eecd2e0263982d933ce |
| 지도 재사용 | 새 추정기, 검증된 저장 파일, 명시적 hint, 실제 localize 결과와 pose 검토 | FAILED: load_map 경로 수락 true, localize_in_map 20초 timeout. 재사용 성공 아님 |
| 물리 이동·루프 폐쇄 | 감독하 측정된 이동/복귀·폐경로와 기준량 | MOTION_NOT_RUN. 직선 1m/방향 전환/복귀/루프 폐쇄 모두 NOT_RUN |
| T3 연속 10분 | 별도 10분 관측, memory trend/손실/중단 복구 검증 | NOT_RUN. 5분 VO 결과를 10분 시험으로 확대하지 않음 |
| 운영 통합 | 운영 odometry/TF/Nav2/UI 연결 및 인수검증 | OPERATIONAL_INTEGRATION_NOT_RUN |

T0의 원본 시퀀스는 약 1.997초다. collector 관측 시간과 bag 내용 길이는 다르다. 이 짧은 샘플에서 입력 전부 처리 또는 장시간 안정성 통과를 주장하지 않는다. 원본은 NGC assets 3.1.0이며 공식 release-3.2 quickstart의 버전 선택 규칙으로 골랐다. archive와 db3를 모두 해시 검증했다.

정지 VO의 위치·각도 변화 p50/p95/max는 출력상 모두 0m/0°였다. 정지 중 일정 pose 출력이 이동 정확도나 미세 흔들림 검출을 증명하지는 않는다. 좌우 영상 9008 pairs가 관측됐고 header 간격 p50 33.298ms, p95 33.329ms, 최대 66.689ms였다. 단발 66ms 간격은 공식 센서 요구사항의 ±2ms 범위를 벗어난다. jitter 경고 임계값을 늘리지 않았다. 입력 FPS·tracking 통과와 엄격한 센서 timing 적합성은 구분한다.

| 측정 | 표본 수 | p50 | p95 | 최대 |
|---|---:|---:|---:|---:|
| VO cuVSLAM track 시간 | 9016 | 2.572ms | 2.836ms | 14.971ms |
| VO node callback 시간 | 9016 | 2.810ms | 3.170ms | 15.234ms |
| T0 track 시간 | 26 | 14.863ms | 40.382ms | 91.554ms |
| SLAM save trial track 시간 | 1318 | 2.725ms | 2.995ms | 5.120ms |
| 호스트 CPU(VO 주변 350초) | 347 | 44.5% | 48.84% | 65.63% |
| 호스트 GR3D(같은 구간) | 347 | 0% | 18% | 40% |
| tegrastats RAM(같은 구간) | 347 | 1745MB | 1760MB | 1764MB |

CPU 평균 44.76%, GR3D 평균 8.00%, swap 0이었다. GPU thermal 최대 60.062°C, CPU thermal 최대 63.781°C였다. 1초 sampling 및 시작/종료 idle 구간이 포함되므로 GPU p50=0을 GPU 미사용으로 해석하면 안 된다. 호스트 전체 수치에는 다른 작업이 포함된다. `/proc/meminfo`의 available 기준 RAM과 tegrastats RAM은 정의가 달라 숫자가 다르다. 클럭 저하 원인 판정은 NOT_OBSERVED다.

최종 SLAM save trial은 안정화 후 65.006초에 odometry/path 1320개, status 1318개 모두 TRACKING이었다. 출력 header span은 약 20.84Hz로 VO보다 낮았고 최대 output 간격은 199.774ms였다. 원인을 mapping 자체로 단정하지 않는다. 영상도 약 20.84Hz로 관측됐다.

새 추정기의 reuse trial은 안정화 후 50.008초 관측했다. 마지막 status 수신 후 종료까지 15.148초 공백이 생겼다. 수신된 779 status는 TRACKING이지만 이 상태만으로 해당 공백을 정상 또는 tracking lost라고 단정할 수 없다. localize 요청 timeout과 종료 시 추정기 component의 SIGINT/SIGTERM 응답 실패가 함께 기록됐다. launch가 자신의 component에 SIGKILL을 적용했고 이후 소유 컨테이너를 종료했다. VSLAM 지도 재사용을 운영에 연결하기 전 해결해야 하는 제한이다.

지연은 NVIDIA status의 알고리즘 track 시간 및 callback 시간만 보고한다. 센서 timestamp와 수신 ROS clock의 직접 관계를 충분히 검증하지 못해 end-to-end data age는 N/A다. 서로 다른 clock을 빼서 지연으로 계산하지 않았다. ATE/RPE, 측정 이동량 오차, 시작점 복귀 오차는 기준 궤적과 물리 이동이 없어 N/A다.

## 입력과 보정의 범위

IR1/IR2의 실제 intrinsic과 right P baseline은 0.04991525784134865m이며 관측 static TF와 일치했다. camera base는 `vslam_lab_camera_link`이다. 오른쪽 Image의 frame은 infra2_optical이지만 pinned wrapper의 오른쪽 CameraInfo header는 infra1_optical로 발행된다. 소스의 `updateExtrinsicsCalibData` 동작과 실제 metadata를 확인하고 명시적 RealSense 예외로 보존했다. VSLAM에는 두 Image의 distinct optical frame을 지정했다. header나 보정값을 꾸미지 않았다.

IMU profile은 gyro 200/400Hz, accel 100/200Hz가 노출됐다. 입력 시험에서는 200/100Hz 후보를 열었으나 IMU 메시지는 없었고 `IMU Calibration is not available, default intrinsic and extrinsic will be used` 및 USB control_transfer 경고가 있었다. USB 2 연결, firmware 차이, IMU calibration 부재는 조사 항목이며 어느 하나가 원인이라고 확정하지 않는다. RSUSB backend의 실제 USB 접근을 사용했으므로 hidraw 누락만을 원인으로 단정하지 않는다. Go2 body IMU는 연결하지 않았다.

emitter는 모든 trial에서 `preserve`로 지정했고 설정 변경을 요청하지 않았다. 사전 읽기값은 1이었다. 종료 후 직접 option 읽기는 Python binding namespace 오류로 실패해 **emitter_after NOT_OBSERVED**다. 이를 최종 값 복원 검증 성공이라고 기록하지 않는다. 운영 카메라 서비스 복원은 아래 별도 증거로 확인했다.

## 실패 보존과 시스템 영향

초기 bag 시도들의 TF/clock/discovery/transport 실패는 `runs/t0-20261013-0430/vo*`에 남겼다. 최종 T0는 component 전체 TF remap, 선택한 원본 static TF 재발행, FastDDS local SHM profile을 사용했다. SHM은 64MiB transport, container `/dev/shm`은 512MiB다.

초기 실센서 시험은 다른 작업의 카메라 점유로 BUSY였다. 그 작업을 종료하지 않았다. 사용자 조정 후 재시험했고 첫 retry는 호스트 CPU >90%가 연속 5회 관측돼 owned watchdog이 이 실험 컨테이너만 중지했다(exit137, OOM false). collector INCOMPLETE로 보존했다. 이후 사용자 요청 재부팅과 추가 사용자 수행 재부팅을 거쳐 정지 VO를 완료했다. 재부팅 전후의 모든 결과를 하나의 연속 trial로 합치지 않았다.

첫 지도 저장 helper는 custom rclpy Context의 `AttributeError: __enter__`로 실패했다. 기본 Context로 수정 후 새 run에서 저장을 통과했다. 최초 실패 기록과 최종 성공 기록을 모두 보존했다. 지도 재위치추정 실패는 위에 별도로 기록했다.

운영 카메라 relay는 사용자의 명시적 허용으로 실험 시간에만 일시 중지했다. 마지막 복원 확인(12:20:45 UTC)에서 camera service active/running, MainPID 17095, Robot Scope active였다. 모든 running Docker container 목록은 비어 있었다. 동일 operational domain 0/CycloneDDS 환경으로 읽은 node 목록은 hesai driver, robot_scope_agent, Go2 control bridge, xt16_fastlio_bridge이며 `vslam_lab` 노드는 없었다. TF output 두 개는 실험 내에서도 비활성화했다. 운영 map/odom/base_link TF를 발행하지 않았으며 로봇 ARM/이동/자세/Nav2 goal/cmd_vel 명령은 전송하지 않았다. FAST-LIO bridge 존재가 FAST-LIO estimator 실행 또는 Nav2 정상 운용을 증명하지 않으므로 해당 전체 상태는 NOT_OBSERVED다.

호스트 의존성 변경, 운영 서비스 등록, 전력·팬·네트워크·시각 변경은 없었다. 승인된 재부팅 및 카메라 서비스 stop/start 외 운영 변경을 하지 않았다. 카메라 스트림을 복원 후 직접 소비하는 검증은 수행하지 않았다.

## 재현·보관·인계

[실행 README](../../../experiments/isaac_vslam/README.md)에 정확한 시작/재생/정지 명령을 제공했다. runtime은 `/home/unitree/experiments/isaac-vslam-lab/`이며 sources/data/runs/evidence/recordings를 분리했다. 원본 bag·map·대형 로그·build/install은 Git에 없다. closed recorder 전체 861,400,067 bytes를 shared `recordings/`로 이동했고 원본과 실패 데이터를 삭제하지 않았다. 이동 전후 경로는 runtime `evidence/recording-consolidation-20261013T122507Z.json`에 남겼다. 2GiB/run, 8GiB 누적, max(10GiB, filesystem 10%) 여유 공간, 60초 초기 recording 제한을 적용한다. 재사용 도구는 새 컨테이너에도 같은 shared archive를 mount해 누적량을 센다. Polling 제한은 filesystem hard quota가 아니며 bounded write rate 위반은 실패로 기록한다.

마이그레이션 담당: base SHA 093600fc002006fba3ba520c7c58f2f202c85111, 결과는 `experiment/isaac-vslam-onboard`의 실험 commit에만 있다. 최종 commit ID는 [PUBLICATION.md](PUBLICATION.md)에 기록한다. 호스트 dependency 변경 없음, 위 service 복원 증거, 자원 표본 및 domain71/frame/topic 설정을 참조한다. 운영 통합에는 USB3 연결/IMU 입력·보정 확인, camera-body extrinsic/clock 검증, 감독 이동·루프 시험, map reuse timeout 해결, 운영 자원 예산 및 카메라 시간 조정이 선행돼야 한다.

UI 담당: VSLAM status는 명시적 cuVSLAM tracking 상태, trajectory는 camera 기준, track/callback time은 end-to-end 지연과 다르다. 이번에는 VSLAM 화면을 추가하지 않았다. 사용자의 추가 요청으로 CPU/GPU/RAM/swap/disk/thermal host resource panel을 기존 설정 화면에 추가했으며 [COMPUTE_MONITOR.md](../../COMPUTE_MONITOR.md)에 별도 인계를 제공한다. 운영 배포는 하지 않았다.

FAST-LIO 대비 확인된 장점은 실제 stereo로 카메라 기준 VO 출력이 독립 GPU 환경에서 생성됐다는 점이다. LiDAR 없이 시각 추정 보조 후보가 될 수 있다. 실제 상대 정확도·열세/우세·암부/반복무늬/진동 내성은 미확인이다. 동시 정렬된 FAST-LIO bag이나 ground truth가 없으므로 비교 수치와 ATE/RPE를 만들지 않았다. FAST-LIO는 ground truth로 취급하지 않는다.

검증 기록: 전체 Python unittest 1663개 실행, 2개 optional skip, 실패 없음. JavaScript 342/342 통과. 자원 UI Playwright 2/2 통과. 실험 전용 offline guard/분석 테스트 107개 실행(1개 optional skip). 원본 실센서 bag 분할 파일과 실패 bag의 해시는 [bag inventory](evidence/bag-inventory.json)에 기록했다.
