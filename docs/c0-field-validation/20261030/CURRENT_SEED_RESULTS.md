# C0 새 현재 위치의 1회 정합 결과

로봇을 옮겼다는 사용자 확인 뒤, 사용자가 지도에서 새 위치·방향을 지정했다. 과거 seed를 재사용하지 않고 현재 FAST-LIO 입력으로 **한 번** 계산했다. 결과는 **FAIL / HIGH_RESIDUAL**, 후보 적용0건·실제 이동0건이다. [최초 실장비 1차 표](LIVE_ROUND1_RESULTS.md)와 그 stop FAIL 기록은 보존했다.

| 확인 | 실제 결과 |
|---|---|
| 새 입력·수치 작업 | job 71b49519f286e357642bb7bf succeeded는 계산 완료 의미. 품질 결과는 REJECTED |
| 실제 reference | 기존 검증된 편집 사본 13,546점, revision c7d7ce7e… / source SHA6ec38aa8… / EDITED_FULL_SOURCE. 전체 XYZ·순서 사용, sampling=false |
| scan·pose 연결 | 185점 현재 registered cloud를 exact-stamp FAST-LIO pose로 IMU 좌표에 역변환. 원시 센서 archive나 외부변환 검증으로 승격하지 않음 |
| 정합 품질 | RMSE0.2353827915m > 기존0.05m 한도, overlap75.135%; 수렴17회. 초기값 대비 XY0.2491m, yaw0.2537°, Z0.0962m |
| 정책 | 반경0.75m / yaw±25° / Z±0.3m / tilt±10°와 residual gate 유지. 범위·오차 한도·속도·yaw tolerance·progress·rear 가중치 변경0 |
| 적용·이동 | admissible=false, 적용 버튼 disabled. source/TF/Nav2 시작·goal·ARM·자세·버튼 출발 요청0 |
| 독립 다음 항목 | 관측 전용 FAST-LIO READY. 기존 리모컨을 통한 경사로 수동 입력 관측은 정밀 도착·저장 지도 정합과 독립적으로 준비, 새 현장 시험창 응답 대기 |

## 기능별 구현·배포·이번 결과

기존 구현과 software PASS는 인수한다. 공통 실제 코드 배포는15706c4이며 기능 존재와 이번 실기 완료를 구분한다.

| 요구 | 구현 / 배포 | 이번 상태와 증거 |
|---|---|---|
| E1/E2 | 기존 / 실제 배포 확인 | PASS: 영역·Z·undo/redo·전체 PCD1개 저장 및 속성/부모 hash 보존 |
| E3 | 기존 / 실제 배포 확인 | 수치 worker의 실제 편집본 hash·revision·전체13,546점 pin은 PASS. 지속 운영 worker는 정합 거절로 BLOCKED_DEPENDENCY |
| N1 | 기존 bundle/frame/origin / 배포 확인 | BLOCKED_DEPENDENCY: 새 후보 거절로 운영 bundle 미선택. 기존2D/3D 원본 보존 |
| N2/N3 | 기존 지속 matcher·TF/body/controller odom / 배포 확인 | BLOCKED_DEPENDENCY: fresh match FAIL. 브라우저 독립 correction와 Nav2 실제 소비는 미실행 |
| N4 | 기존 idle/재시작/rollback / 배포 확인 | idle·selected=null·LEGACY_2D 유지 확인. 활성 source 전환/rollback은 미실행 |
| N5 | 기존 Nav2 / 배포 확인 | BLOCKED_DEPENDENCY: 새3D source 불충족, 실제 goal0 |
| G1/G2/G3/G4 | 기존 모드·정지/dwell·단발 gate / 배포 확인, software PASS | BLOCKED_DEPENDENCY: actual success/정지/2초 dwell/source 미충족. 실제 버튼·next goal·출발0; 강제 통과0 |
| R1 | 독립 관측 경로 READY, 기록 준비 | BLOCKED_OPERATOR: 새 수동 시험창 대기. 300초/2GiB 한도, 특정 관측 session·bridge inactive·lease/command/goal guard. 아직 기록 실행 안 함 |
| R2/R3 | rear/side 운영 미구현·미채택 | INPUT_REQUIRED: 실제 ramp 자료 없음, 같은 입력 A/B 미실행 |
| R4 | 기존 관측 기능 / 배포 확인 | 저장 지도 경사로 정합은 BLOCKED_DEPENDENCY. 독립 raw·IMU·LIO baseline은 현장 준비 시 별도 진행 가능 |

최소 정지 보완 뒤 idle 프로세스 종료 비교는 PASS이나 물리 이동 중 정지·장비 ACK 증명은 아니다. 제어 bridge inactive, lease inactive, 명령0, Nav2/goal idle을 재조회했다. 관측은 기존30분 상한 내 세션만 사용한다. 자동 source 적용·STOP 해제·lease 우회는 없다.

실제 배포 **15706c48c5e6df28be105b6f5bde825dce7c4b1f**의 [CI41042751838](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41042751838)는 exact head에서 completed/success다. 이후 문서 commit은 배포하지 않는다. saved 설정71933bade…(.10m/.10rad, .25m/s,10Hz), overlay95c6ee9b…는 유지하며 현재 Nav2 idle이므로 generated/live controller 설정·라이브러리 로드는 측정되지 않았다.

[기계 판독 결과·증거 hash](CURRENT_SEED_RESULTS.json). 이 표를 먼저 마감한 후 원인은 별도 분석한다. raw 좌표·센서·원본 기록·endpoint·인증 정보는 공개 Git에 넣지 않는다.
