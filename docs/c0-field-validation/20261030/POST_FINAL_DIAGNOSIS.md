# C0 1차 마감 뒤 원인·최소 후속 후보

이 문서는 [최종 1차 표](FINAL_ROUND1_RESULTS.md)와 closure receipt 뒤에 작성했다. 전항목을 성공시키기 위한 반복 주행·yaw/속도/progress/rear 설정 변경은 하지 않았다. 세 번째 지형 기록은 사용자가 따로 요청하고 새 시험창을 승인한 추가 데이터 수집이며 제어/품질 후보 비교가 아니다.

## 확인된 사실과 미측정 원인

| 사건 | 확인 수준 | 결론 |
|---|---|---|
| 기존 bridge stop | CONFIRMED·최소 수정 비교 완료 | SIGINT의 KeyboardInterrupt가 finalizer에서 무시되고 blocking spin이 계속돼2초 뒤 SIGKILL. flag+bounded spin_once와 failed-stop 보고를 보완한15706c4는 같은2초 설정에서 정상 inactive/exit0. 이동 중 장비 정지/ACK까지 입증한 것은 아님 |
| 저장 지도 초기 정합 | 거절 확인·물리 원인 미측정 | 새 사용자 seed의 단1회 작업은 계산 완료, 수치 결과HIGH_RESIDUAL. RMSE.23538m >.05m. 수렴·범위·overlap75.14%·형태 비율은 보고값 기준 통과. 잔차를 실제 위치오차23.5cm로 해석하지 않음 |
| 편집 reference | 실제 수치 worker 확인 |13546점 편집본의 전체 XYZ/revision/source SHA가 pin됐다. 원본/새12,619점 C0사본을 몰래 교체한 사건이 아님. 지속 운영 worker는 미실행 |
| 수동 지형 입력 | 수집 확인 |3개 bag 정상 종료, raw/LIO 약10Hz·IMU 약500Hz, 최대 API pose age .248s. 사례2/3 전수 header 역행0. 전구간 위치 정확도나 누락 없는 센서 원본 완전성을 입증한 것은 아님 |
| 지도/TF/Nav2/장애물 단계 | NOT_RUN / BLOCKED | 시작 전 flat initial match부터 거절됐다. 지형 이동 중 stored-map correction·운영 TF·Nav2·scan/costmap이 없었으므로 그 단계의 첫 악화나 바닥 투영 실패를 판정할 자료는 없음 |
| 첫 기록기 준비 | 인프라 원인 확인 | 실행 중 DB read 검증이 SQLite writer와 lock 충돌한 뒤 SIGABRT/metadata 없음. 실패 파일을 보존하고 이후 종료된 DB만 조회해 정상3개 bag 확보 |
| 관측 start409 | 거절 확인·원인 가설 | admission 때 raw_capture/navigation 이름으로 거절됐고 후속 readback은 clear. nonblocking ownership lock 경합 가능성은 코드상 가설이며 실제 task 점유/unknown의 정확한 순간은 미계측. gate·소유 작업을 강제로 해제하지 않음 |

초기 정합 scan은 현재 registered cache185점이며 exact-stamp FAST-LIO pose로 IMU 좌표에 역변환됐다. 여기서 sampling=false는 이 capture 층의 성질이다. 상류 처리·원시 센서 전체성·외부변환·PCD axes·메시지별 publisher identity가 검증됐다는 뜻이 아니다. 반대로 화면 샘플링이 원인이라고 단정할 근거도 없다.

가능한 원인은 현재 장면과 과거 edited reference의 관측 범위 차이, 높이/자세 근사 또는 장착·축·외부변환 관계, 상류 등록 점군의 분포·처리 차이다. 이번 한 번의 잔차만으로 어느 것도 확정되지 않았다. 탐색 범위/오차 한도를 넓히거나 후보를 강제로 적용하는 방법으로 해결하지 않는다.

## 분리한 다음 최소 작업

| 후보 | 먼저 할 일 | 조건·현장 필요 |
|---|---|---|
| 정지 정합 원인 | 보존한 첫 seed/캡처 계약·편집 reference와 지형 기록의 raw/registered/body cloud를 같은 stamp/frame으로 구분해 오프라인 재생. coverage·fields·수직 분포·외부변환 중 차이 위치 확인 | 품질 gate 유지. 서로 다른 LIO epoch를 같은 좌표로 붙이지 않음. 새 실기 초기화가 필요하면 사용자 현재 map seed와 새 정지 시험을 그때 확인 |
| 운영 source 연결 | 합격한 fresh match 뒤 기존 bundle/initial-pose로 correction sequence·TF/body/controller odom·실제 Nav2 소비와 브라우저 독립 갱신 확인 | 현재BLOCKED. 성공 없이 goal/stop/dwell/source를 강제하지 않음 |
| stop-and-go | 유효 source와 실제 Nav2 stop success·측정 정지·2초 dwell 뒤 기존 버튼으로 next goal1개→출발→종료 기록 | 옛 두 목표 승인은 소비됨. 이번 수동3회 승인도 자율 goal 승인이 아님 |
| progress/checker | [기존 synthetic 재현](POST_SWEEP_PROGRESS_REPRO.json)의 첫 작은 feedback 기준 고정 현상을 별도 수정 후보로 검토 | 공개 반올림 거리·합성 시간의 offline 재현이며 실기 raw feedback replay가 아님. 현장 checker·속도 미변경 |
| yaw/저속 접근 | 먼저 유효 source와 실제 잔차·진행 정체를 분리 | .05rad tolerance·최소속도·PoseProgressChecker를 차례로 적용하는 반복 주행은 하지 않음. 단일 변경마다 별도 근거 필요 |
| rear/side |3개 실제 raw/LIO 기록을 private 재생 입력으로 사용. baseline이 지도 정합까지 유효한지 먼저 확인 | alternate policy 미구현·미채택. 서로 다른3회 주행은 동일 입력 정책 A/B가 아님. baseline/실패 위치가 불명확한 상태에서 개선 효과나 BASELINE_RETAINED를 주장하지 않음 |
| admission 계측 | 필요 시 거절 순간 busy/unknown·lock 경합을 작은 구조화 영수증으로 보존하는 후보 검토 | unknown을 idle로 바꾸지 않음. 이번 runtime에는 추가 계측 후보 미배포 |

구간 표시는 사용자 채팅 수신 기준이며 정확한 물리 boundary timestamp/측량 정답은 아니다. 사례1은 경사로 상승·계단식 하강, 사례2는 계단 상승·경사로 하강, 사례3은 사용자 요청으로 사례1 방향을 반복했다. ground truth 없이 ATE/RPE·전역 drift·절대 경사각 정확도를 만들지 않는다.

## CI와 복구 상태

actual code15706c4 CI41042751838는 성공이다. 문서8d96840 CI41044928748 Ubuntu22/Python3.10은 global_observation_history.spec.mjs:90에서 오류 문자열 대신IDLE을 표시해226pass1fail이었다. 동일 mock UI 사례1개를 현재 로컬에서 올바르게 선택해 한 번 실행한 결과는PASS(2.6s)다. 앞선 anchored grep의No tests found는 테스트 결과가 아닌 선택 오류로 보존했다. 이 로컬1회 통과로 CI 실패를 flaky로 확정하지 않고, 주기 poll/history feedback 경합을 후속 가설로 둔다. 해당 UI 코드는 수정하지 않았다.

최종 dashboard PID43956/실제 robot-scope.service active, release15706c4다. bridge와 관측은 inactive/PID0/Result success, recorder 모두 종료, Nav2/goal idle, lease inactive·command0·STOP latch=false다. source는LEGACY_2D/selected=null이고 자동 재출발은 없다. 최초 백업과 동일한 git status 형식으로 직접 비교해 사용자 dirty 목록이 같고 selector 외5개 파일 hash가 일치한다. 기존 source-selection·calibration·profile·presets/control.env와 overlay95c6ee9b…를 보존했다.

기존 release와 백업 selector는 남아 있고 rollback하지 않았다. 구버전 복귀 시 관측한 bridge stop 결함도 돌아갈 수 있다. 원시 rosbag20,362,293,248B는 장비 private에, 각 file hash·metadata·telemetry·구간표시 사본은 PC private에 보존했다. 공개 문서에는 집계·상태·hash만 넣었다. 문서 commit을 실제 배포 SHA로 승격하지 않는다.
