# C0 전체 1차 결과 및 추가 수동 기록

실제 배포는 **15706c48c5e6df28be105b6f5bde825dce7c4b1f**, C0 브랜치는 `review/20261030-c0-3d-field-sweep`다. 기존 편집·저장과 최소 정지 보완은 확인했으나 **저장 지도 초기 정합은 FAIL**, 실제 Nav2/버튼 재출발은 의존 BLOCKED다. 사용자가 따로 승인한 수동 지형 기록3건은 정상 저장했다. 최초 [offline 표](ROUND1_RESULTS.md), [실장비 표](LIVE_ROUND1_RESULTS.md)의 stop FAIL, [새 seed 표](CURRENT_SEED_RESULTS.md)를 보존한다.

## V00~V09

| 검사 | 이번 결과 | 실제 증거·범위 |
|---|---|---|
| V00 배포·설정 인수 | PASS | main846121b와 actual15706c4 구분, source2216/2216, PID43956/cwd·실제 robot-scope.service active 확인 |
| V01 software/UI | PASS 범위 명시 | Python3137·JS700·대표 browser18, actual code CI 성공. 후속 문서8d CI의 별도 browser FAIL은 아래 기록 |
| V02 편집·전체 저장 | PASS | 실제 영역/Z·undo/redo, 사본1개13,546→12,619점. XYZ/intensity 및 retained record bytes/order·부모 hash 보존 |
| V03 저장 지도→운영 TF/Nav2 | FAIL / 이후 BLOCKED | 옮긴 현재 위치를 사용자가 지정. 단1회 정합 HIGH_RESIDUAL, RMSE.23538m > 기존.05m, overlap75.14%. 적용0 |
| V04 실제 정지점 도착 | BLOCKED_DEPENDENCY | 운영 source 미충족. 실제 자율 goal0, 도착/정밀 오차 미측정 |
| V05 버튼→next goal→출발 | BLOCKED_DEPENDENCY | actual success/정지/2초 dwell/source gate 부재, 강제 통과0·GREEN 조작0 |
| V06 독립 수동 지형 입력 | PASS 범위 명시 | 아래3개 mixed 경사로/계단 사례의 raw·IMU·FAST-LIO 기록. stored-map 경사로 정확도 PASS는 아님 |
| V07 첫 악화 경계·후방 정책 | BLOCKED_DEPENDENCY | raw/LIO 연속 입력 확보. 정합·운영 TF·scan/costmap 비활성이어서 해당 단계의 지형 성능 미측정; 정책 A/B 미실행 |
| V08 종료·복구 | PASS 범위 명시 | idle bridge stop 보완 비교 PASS, 수동 안전 정지는 사용자 보고. bridge/관측/기록기 종료·lease/명령0. 이동 중 자율 정지/ACK 미측정 |
| V09 표→별도 분석 | PASS | 모든 행 판정 후 이 표를 먼저 마감. 실패 원인·수정 후보는 별도 문서 |

## 요구사항별 구현·배포·이번 실기

공통 runtime은15706c4로 실제 source manifest를 확인했다. mock/기존 실기/이번 실기를 구분한다.

| 요구 | 구현 / 배포 | 이번 결과 |
|---|---|---|
| E1/E2 | 기존 구현 / 배포 확인 | PASS: 실제 편집·전체 PCD 새 사본·재조회·속성 보존 |
| E3 | 기존 구현 / 배포 확인 | 수치 worker는 검증된 편집본13,546점의 revision/hash/full XYZ pin PASS. 지속 운영 worker와 새 C0사본은 미실행 → 전체 요구 BLOCKED_DEPENDENCY |
| N1 | bundle/frame/origin 기존 / 배포 확인 | 새 초기 정합 FAIL로 운영 bundle 미선택, 기존 지도 보존 |
| N2/N3 | 지속 matcher·운영 TF/body/controller odom 기존 / 배포 확인 | BLOCKED_DEPENDENCY: 실제 지속 보정·브라우저 독립 소비·Nav2 연결 미실행 |
| N4 | idle/재시작 비복원/rollback 기존 / 배포 확인 | idle·LEGACY_2D/selected=null 유지 확인. 활성 source 전환/rollback 실기는 미실행 |
| N5 | 기존 Nav2 / 배포 확인 | BLOCKED_DEPENDENCY: 새3D source의 실제 goal0 |
| G1/G2/G3/G4 | 기존 시험 gate / 배포 확인, software PASS | 실제 stop/dwell/current source와 next goal/출발 BLOCKED_DEPENDENCY. 수동 종료를 Nav2 arrival로 사용하지 않음 |
| R1 | 기존 독립 관측 + private 기록 준비 / 실장비 실행 | PASS:3개 승인 수동 기록. 한 경로에서 경사로 왕복을 했다고 주장하지 않음 |
| R2/R3 | rear/side 미구현·미채택 | NOT_RUN: 실제 replay 자료는 확보. 운영 정합 baseline 미활성이라 정책 변경/동일입력 성능 비교·채택 미실행 |
| R4 | 기존 관측 기능 / 배포 확인 | stored-map 지형 위치추정은 BLOCKED_HIGH_RESIDUAL. 독립 raw/LIO 관측 완료와 분리 |

## 상승부터 하강까지 분리한 수동 기록

각 사례는 새 현장 창을 확인했고 조종자는 기존 리모컨을 사용했다. 별도 rosbag·telemetry·구간표시·종료 영수증·각 DB SHA를 보존했다. C0의 비영점 이동/자세/자율 goal 명령은0건이다. 시간은 실제 메시지 기록 구간이며 초기화/종료 시간이 포함된 recorder elapsed와 다를 수 있다.

| 사례 | 실제 경로 | raw cloud | FAST-LIO cloud/odom | IMU | 기록 약초 | 파일/용량 |
|---|---|---:|---:|---:|---:|---|
| 1 | 경사로 진입·상승→정상→계단식 하강 | 3,006 | 각3,006 | 150,288 | 300.5 | 27DB /7,081,345,024B |
| 2 | 계단 진입·상승→정상→경사로 하강 | 2,942 | 각2,941 | 147,042 | 294.1 | 27DB /7,081,013,248B |
| 3 | 사용자 추가 요청: 경사로 상승→계단식 하강 반복 | 2,608 | 각2,607 | 130,354 | 260.7 | 24DB /6,199,934,976B |

총78DB,20,362,293,248bytes다. raw/LIO 약10Hz, IMU 약500Hz다. 모든 bag 정상 exit0·metadata 존재·강제 kill0. API pose 최대 age는 사례1 .165s /2 .248s /3 .135s이며 각 case의 pose/cloud source stamp는 표본에서 증가했다. 전체 header stamp를 추가 검사한 사례2/3은 역행0, raw/LIO 최대 양의 간격 약.1014s 이하, IMU 약.0134s 이하다. 사례1은 이 전수 header 검사 미실행이며 같은 수준으로 승격하지 않는다. cross-sensor 절대 clock 관계와 ATE/RPE는 미검증이다.

구간은 사용자 채팅의 수신 시각 기준이다. 첫 두 사례의 진입/상승은 순서 있는 같은 batch로 기록돼 정확한 물리 경계 시각을 제공하지 않는다. 지형은 사용자 보고이며 영상/측량 ground truth가 아니다. 사례1과 사례2/3은 관측 epoch가 다르므로 단순히 시작 좌표를 같게 맞춰 정확도를 비교하면 안 된다. 원시 bag는 장비 private 경로에, hash·metadata·telemetry 사본은 이 PC private 증거 경로에 보존했다. 공개 Git에 raw cloud/rosbag/좌표·사용자 화면을 넣지 않는다.

## 남겨진 배포·설정·복구 상태

실제 robot-scope.service는 active/PID43956, release15706c4다. bridge와 observation은 inactive/PID0/Result success, 소유한4개 recorder PID는 모두 없다. Nav2/goal idle, lease inactive, 명령 전축0, SOFTWARE STOP latch=false, LEGACY_2D/selected=null, busy/unknown component 모두[]다. 마지막 물리 정지는 사용자가 안전한 위치에서 완료했다고 보고했으며 장비 ACK는 미측정이다. 자동 재출발0이다.

saved revision71933badef736b1361f1162355527488a9350b86a8b4b8865b81c38031100387, XY/yaw .10m/.10rad, 속도.25m/s,10Hz·progress 기준은 유지했다. 현재 Nav2 idle이므로 generated YAML/live controller params/실제 plugin load는 없다. overlay의 실제 install/lib/libnav2_rotation_shim_controller.so SHA는95c6ee9b0294651c182092031eb4926291946eb8e72be5cf1bfb976219f1754d로 보존됐다. 원본 /opt/ros·사용자 dirty checkout·기존 지도·새 C0 PCD·프리셋·백업 release를 보존했다. rollback은 하지 않았고 기존5154761 및 백업 selector가 복구 지점이다.

정지 준비 recorder는 동시 read가 SQLite writer와 충돌해 SIGABRT/metadata 없음으로 실패했다. 파일을 보존하고 실행 중 DB 조회를 없앤 뒤 한 번 대체했다. 준비 용량은 실제 입력량에 맞춰2GiB에서12GiB로 늘렸고300초 상한은 유지했다. 이 준비 실패는 실제 이동 기록 성공과 구분한다. 관측 재시작409(raw_capture/navigation)는 gate를 유지하며 기록했고 다른 소유 작업을 취소하지 않았다. 실제 UI를 통해 준비가 성공한 원인을 lock 경합으로 확정하지 않는다.

실제 code15706c4의 [CI41042751838](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41042751838)는 success다. 후속 문서8d96840의 [CI41044928748](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41044928748)는 Ubuntu22/Python3.10 browser에서 global_observation_history.spec.mjs:90 실패(기대 synthetic job not found / 실제 IDLE · HISTORICAL_ONLY,226pass1fail)다. Ubuntu24/competition은 성공했다. flaky로 단정하거나 배포 code 통과로 덮지 않는다.

[전체 JSON 및 증거 hash](FINAL_ROUND1_RESULTS.json), [앞선 정지 보완 상세](LIVE_FOLLOWUP_AND_HANDOFF.md). 이 문서의 commit/push와 실제 배포 SHA는 별개다.
