# 02 — 정지 센서·TF 기록

2026-10-14. Run ID: `run-20261014T041650Z`. 사용자에게서 04단계까지의 실행 조건 확인과 승인을 받았다. 05단계는 미승인이다. 첨부 문서의 예시를 현장 확인으로 대신하지 않았다.

**180초 정지 관측과 제한된 기록을 완료했다. 절대 위치 정확도, 센서 원시 시계 동기화, 완전한 운영 TF는 아직 검증되지 않았다.** 원래 01단계의 SSH BLOCKED 기록은 보존하고 이번에 해결된 접근과 측정을 후속 증거로 분리한다.

## 실행본과 범위

- 실제 장비 checkout: clean `416d25c6e1c98b0c51097c9d6576b6ae34a690e9`. 서비스 cwd/interpreter, 허용 목록 ROS 환경, 실행 파일·설정 hash를 직접 조회해 private inventory에 보존했다.
- 개발·원격 main 확인: `48d33df8101b2c704db830a8ff7e3241355b48d4`. 이번 03/04 도구·수정의 테스트는 이 base에 변경을 추가한 dirty 개발 트리에서 수행했다. 장비의 측정 SHA와 문서를 게시하는 커밋을 구분한다.
- 기존 SSH 키는 보존하고 사용자가 요청한 별도 키를 추가 등록해 인증했다. 인증정보·키는 보고서·Git에 포함하지 않는다.
- 기존 XT16 preview를 유지하고 dashboard의 기존 mapping start/stop 경로로 관측 FAST-LIO job 하나를 시작·종료했다. 지도 save, initialpose, ARM, lease, 운영 goal, 이동 명령은 실행하지 않았다.
- VSLAM build/run/playback/record와 새 모니터를 기동하지 않았다. 기존 서비스와 기존 리소스 API를 사용했다.

## 측정

| 구간 | UTC / KST | 결과 |
| --- | --- | --- |
| 짧은 구독 시험 | 04:22:14–04:22:24 / 13:22:14–13:22:24 | 10.001초, odometry 100개, 시작점 대비 최대 2.85 mm |
| 본 기록 | 04:23:26–04:26:26 / 13:23:26–13:26:26 | 180.001초, odometry 1800개, 시작점 대비 최대 8.02 mm |
| FAST-LIO 종료 | 04:27:18 / 13:27:18 | 이 검증의 job만 종료, exit 0, 기존 preview 유지 |

정지 확인의 출처는 사용자의 명시적 확인과 연속 소프트웨어 관측이다. 별도의 물리 정답 센서는 없다. 180초 동안 x/y/z 범위는 각각 8.94/10.22/3.91 mm, roll/pitch/yaw 범위는 0.000944/0.000514/0.002197 rad였다. quaternion 최대 norm 오차는 `8.1e-13`, pose finite 실패는 0이다. 이 변동량은 정지 안정성 지표이며 절대 정확도·ATE/RPE는 `null`이다.

| 토픽 | 직접 구독 수 / Hz | 최대 callback gap | frame / 의미 |
| --- | --- | --- | --- |
| `/lowstate` | 87805 / 487.81 | 0.1383 s | vendor headerless; 원시 시간 계약 미측정 |
| `/imu/body` | 83431 / 463.51 | 0.1620 s | `body_imu`, bridge 변환 |
| `/lidar_points` | 1800 / 10.0003 | 0.1148 s | `hesai_lidar`, 원시 장치 시간 |
| `/velodyne_points` | 1800 / 10.0003 | 0.1140 s | `hesai_lidar`, bridge 시간 변환 |
| `/Odometry` | 1800 / 10.0004 | 0.2387 s | `camera_init → body` |
| `/cloud_registered` | 1800 / 10.0004 | 0.2414 s | `camera_init`, 통상 약 400점의 sparse 출력 |
| `/tf` | 1800 / 10.0008 | 0.2415 s | 관측 edge `camera_init → body` |
| `/tf_static` | 0 | `null` | 시작·종료 graph에서 publisher 없음 |

시작·종료 endpoint GID/type/QoS/cardinality가 동일했다. `/tf_static`은 reliable/transient-local로 구독했으나 publisher와 메시지가 없었다. 이 결과를 정적 센서 외부 파라미터 검증 PASS로 처리하지 않는다. 운영 `map→odom→base_link`도 이 FAST-LIO 기록으로 입증되지 않는다. endpoint 종류와 payload 점검 범위는 private summary에 있다. cloud finite 검사는 제한된 6개 샘플이며 전체 1800 payload의 정밀 검사가 아니다.

## 시간·parameter 계약

source stamp, 같은 장비의 wall-clock callback 시각, monotonic callback 시각, bag 저장 시각을 각각 보존했다. raw device stamp는 호스트와 약 `202015823.6 s` 차이가 났다. 이를 센서 전달 지연으로 해석하지 않는다. 기존 C++ bridge의 offset 변환은 scan 시간 진행성을 보존하며 이 도구는 timestamp를 덮어쓰거나 음수 age를 잘라내지 않았다. 원시 clock의 호스트 동기화·물리 end-to-end latency는 BLOCKED다.

변환된 odometry stamp는 단조 증가했고 source 최대 gap 0.10013 s, callback에서 계산한 host-wall age 0.0269–0.1749 s였다. IMU source 최대 gap은 0.1684 s였다. callback gap은 수집 도구의 executor/serialization 지연도 포함하므로 센서·RMW 도착 gap이나 네트워크 지연과 동일하지 않다. 서로 다른 호스트의 monotonic 값을 빼지 않았다.

`/clock` publisher 0, 수집 node의 `use_sim_time=false`를 확인했다. 실행 중인 `/laser_mapping` 전체 parameter readback은 exit 0: `use_sim_time=false`, `dense_publish_en=false`, `extrinsic_est_en=true`, `time_sync_en=false`, `pcd_save_en=false`. 저장 config만으로 effective parameter를 대신하지 않았다. 해당 readback은 [VSLAM 인계](../experiments/isaac-vslam/HANDOFF.md)의 별도 실패한 parameter capture와 다른 시험이다.

| 기준 | 값 | 실제 적용 범위 |
| --- | --- | --- |
| D2 source age / future / gap | 0.50 / 0.10 / 0.50 s | opt-in D2 observer; 이번 운영 서비스는 opt-in 0 |
| C4 callback gap | 0.25 s | competition profile; onboard에 적용됐다고 보고하지 않음 |
| Nav2 command timeout | 0.30 s | 기존 Nav2 제어 입력 계약; 이번에는 입력 없음 |
| manual / bridge watchdog | 0.20 s | 기존 제어 입력 계약; 변경 없음 |

## 기록·자원

고정한 8개 센서/TF 토픽만 구독했다. `record -a`나 제어 토픽 기록은 사용하지 않았다. cloud는 번호 1/30/100/600/1200/1750만 저장해 대용량 기록을 제한했고, odometry/IMU/lowstate/dynamic TF는 수신분을 기록했다. cloud의 의도적 sampling은 drop이나 연속 bag으로 보고하지 않는다. 모든 source progression 분석에는 관측 metadata를 사용했다.

180초 bag은 191537152 bytes, SQLite integrity `ok`. 주요 메시지 수는 위 표와 일치하고 cloud 세 토픽은 각각 6개, `/tf_static` 0개다. 짧은 bag도 별도로 보존했다. 두 bag의 원격/로컬 SHA-256이 일치했다. 도구의 serialized evidence 상한은 512 MiB, 시간 상한 180초였고 기존 reserve를 침범하지 않았다. 운영 domain에서 replay하지 않았다.

창 내 기존 resource API 표본 30개를 분석했다. 첫 CPU 계산 구간은 98.3초로 측정 창 이전을 포함해 CPU 요약에서 제외했다. 나머지 29표본의 CPU 51.16–57.84%, sampled GPU 0%, 최대 RAM 사용 1491304448 bytes, swap 사용 0, 최고 thermal 67.062°C였다. throttling·절대 처리 여유는 미측정이다. workload에는 수집기와 5초 sleep을 둔 순차 GET 관측이 포함된다. VSLAM·카메라·planner·파일 전송은 180초 창 밖에서 수행했다.

## RealSense 별도 사용 창과 종료

사용자 승인 후 privileged device owner와 dashboard viewer 0을 확인했다. 독점 SDK 인수 대신 기존 운영 on-demand relay의 단일 dashboard viewer로 04:29:16–04:29:36 UTC / 13:29:16–13:29:36 KST에 사용했다. 20.043초 동안 JPEG 282개, envelope 오류 0; 중간 API는 640×480, 약 14.97 FPS, decode failure 0이었다. 픽셀·영상은 공유 파일에 저장하지 않았다. 실제 센서→브라우저 지연과 stereo/VIO는 이 시험의 범위가 아니다.

연결 해제 후 viewer 0과 active source 0을 확인했다. 서비스는 원래대로 active 상태를 유지했다. 최종 privileged device 조회에서 열린 owner가 없었다. 카메라는 계속 운영 relay 예약 상태이며 VSLAM에 반환됐다고 간주하지 않는다.

원본은 private evidence root의 `device-capture/`, `stationary-analysis.json`, `resource-window-summary.json`, `bag-and-map-audit.json`, `realsense-window.json`, `direct-inventory.json`, `final-device-state.json`에 있다. 최초 수집기는 프로세스 시작 후 LD_LIBRARY_PATH를 설정해 import에 실패했다. 최초 실패를 보존하고 시작 전 ROS 환경 적용으로 수정해 짧은 시험부터 다시 통과했다. 서비스·센서 환경은 변경하지 않았다.

운영자가 수행하는 이동 구간·out-of-plane 실기 데이터는 NOT_RUN. 03단계 독립 query/정답 qualification과 04단계 새 지도·실제 초기 위치 확인이 남았다. 구조화 판정은 [02_04_validation_matrix.json](02_04_validation_matrix.json)을 참조한다.
