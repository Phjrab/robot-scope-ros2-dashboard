# Traffic signal VM handoff

## 완료 범위와 근거

2026-10-24 UTC, x86_64 VM에서 구현 및 실행했습니다. 기본 commit은 BASE_COMMIT.txt에 기록합니다. 생산 코드 변경, 실제 ROS graph 연결, 카메라 변경, 주행/제어 명령, 가중치 다운로드는 하지 않았습니다.

- DETECTOR_READY: ADAPTER_IMPLEMENTED / INPUT_REQUIRED. 로컬 Ultralytics PT/ONNX 로더 경계만 구현했으며 실제 모델 추론 및 end-to-end 연결은 NOT_RUN.
- COLOR_READY: VM_SYNTHETIC_VERIFIED. OpenCV raw HSV, Lab L-only CLAHE, ExR/ExG 교차검증 경로 실행.
- STOP_ZONE_READY: CANDIDATE_GEOMETRY_ONLY. 사각형 후보 및 2점 포함 연산 검증. 실제 시각적 정지구역/발 추정과 좌표 보정은 INPUT_REQUIRED.
- FSM_READY: VM_SYNTHETIC_VERIFIED. 실제 안전성 인증 또는 deploy-ready를 의미하지 않음.
- REAL_RGB_VALIDATED: false / INPUT_REQUIRED.
- JETSON_NOT_RUN: true. TensorRT engine 생성/성능 미측정.
- NATIVE_ROS: NOT_RUN (rclpy 미설치). Python compile과 격리 환경변수 누락 시 거부 동작만 실행.

67개 unittest PASS. 별도 검토에서 발견된 identity 변경 시 dwell 지속, epoch sequence 초기화, 비정상 TTL, 짧은 replay, 중복 begin 재가동, 모순된 출발 관측을 수정하고 회귀 테스트를 추가했습니다. 검토는 유한한 테스트 범위이며 모든 오류 부재의 증명이 아닙니다.

## 합성 결과

results/metrics.json과 unit_tests.log가 원본입니다. 독립 정의한 합성 100프레임에서 raw/luminance/combined 각각 RED 30, UNKNOWN 10, GREEN 60이 해당 정답으로 분류되었습니다. 이 쉬운 fixture에서는 CLAHE 개선 효과를 주장할 수 없습니다. 잘못된 출발 의도 0건, GREEN 시작 4.0초, 안정 GREEN/출발 의도 4.4초입니다. 실제 움직임 확인은 4.8초, 완료는 7초입니다.

p95는 OpenCV/필터/FSM 부분의 VM wall-clock 측정이며 모델, 디스크 I/O, 렌더링, ROS, Jetson을 제외합니다. 실행마다 달라지므로 정확한 값은 metrics.json을 읽으십시오. YOLO recall, 모델 SHA, Jetson 지표는 null입니다. false_depart_intent_events도 이 시나리오 한정이며 현장 false-GO 확률이 아닙니다.

## 인식 경로

RGB/BGR encoding을 명시하고 native ROI를 사용합니다. Ultralytics Results.xyxy는 원본 좌표이므로 이중 letterbox 역변환하지 않습니다. 별도 letterbox helper는 반올림 및 비대칭 padding을 포함해 검증했습니다.

ROI가 없거나 미연관, 잘림, 작은 표본, settling, 흰색 포화, 저채도, 흐림이면 UNKNOWN입니다. 원본 색 증거가 없을 때 CLAHE만으로 GREEN을 만들지 않습니다. RED/GREEN 충돌은 AMBIGUOUS입니다. 배경의 가장 큰 신호등을 임의 선택하지 않습니다. Association은 사전 보정된 expected ROI가 없거나 후보가 동률이면 실패합니다. detection 인덱스는 영구 track ID가 아니며 실제 tracking/heading/map association을 통합해야 합니다.

모든 색/면적/blur/IoU/stability/TTL 숫자는 DESIGN_INITIAL입니다. 점수는 보정된 확률이 아닙니다. 0.4초 stability와 0.25초 TTL은 규정이 아닌 초기 설계값이며 실제 노출, 프레임율, 조명 데이터로 검증해야 합니다. 규정의 신호 5초 주기를 관측 대체 수단으로 쓰지 않습니다.

## FSM과 안전 통합 계약

시작은 begin(run_id, step_id, crossing_id, visit_id, signal_id, generation, zone_id) 명시 호출입니다. 같은 key의 중복 begin은 상태/dwell을 변경하지 않고 False를 반환합니다. CANCELLED/CLEAR 후 다시 방문하려면 새 visit 또는 generation이 필요합니다. 프로세스 재시작 후의 재전송 방지는 현재 메모리 외부의 mission owner가 책임져야 합니다.

규정 2초는 두 앞발 내부, 시각적 구역 증거, 몸체 정지, 유효한 관측이 연속되는 시간입니다. SIM_GT는 simulation=True에서만 허용하며 PROXY는 출발 증거가 아닙니다. KINEMATIC/VISUAL 입력은 실제로 검증된 adapter만 생성해야 합니다. 한 프레임의 boolean 입력만으로 실제 발 추정 완료를 주장하지 않습니다.

APPROACH 단계도 HOLD를 출력하는 보수적인 모듈입니다. 통합 시 approach action의 완료/취소 ACK 이후에 이 traffic constraint를 활성화해야 하며, approach 주행 중 활성화하면 자기 정지 deadlock이 생깁니다. 별도 mission owner가 action cancel/complete를 확인하고 새 주행 leg를 제출해야 합니다. 이 wrapper는 이를 수행하지 않습니다.

DEPART_PENDING은 유효 GREEN에서만 의도를 내며 RED/UNKNOWN/age/identity/epoch/gap/반복 자료로 취소됩니다. 실제 departure_observed=True와 body_stopped=False가 함께 확인되어야 COMMITTED입니다. 두 값이 모순되면 HOLD합니다. COMMITTED 이후 RED 자체는 현재 횡단을 중단하지 않지만 obstacle/localization/safety hold가 항상 우선합니다. full crossing 완료도 실제 adapter 증거가 필요합니다.

출력은 MotionConstraint 제안이며 actuator 명령이 아닙니다. HOLD는 vx/vy/wz=0, RELEASE의 null은 '이 소유자의 제한 해제'이지 장애물이나 다른 소유자의 HOLD 해제가 아닙니다. priority60은 임시값입니다. owner/run/step/request/generation/receipt TTL을 가진 실 arbiter에 연결할 때 상위 safety 우선순위와 합성을 검증하십시오. 해제 후 과거 velocity나 기존 action을 재생하지 말고 fresh leg를 생성해야 합니다.

receiver monotonic receipt, source age와 producer epoch를 분리합니다. sequence/시간 역전, old epoch replay는 거부하고 hold합니다. retired epoch와 begin key 이력은 메모리 보관하므로 장기 운용의 bounded retention 정책은 mission lifecycle과 함께 설계해야 합니다.

## Replay 입력

JSONL 각 행: image(동일 manifest 폴더 하위 파일), receipt_s, sequence, label(RED/GREEN/UNKNOWN), roi_xyxy_native, association_verified, source_age_s, producer_epoch, track_id, source_stamp_ns, detector_available. 선택적으로 feet_inside/body_stopped/departure_observed/fully_crossed.

실제 영상 replay는 기록된 metadata adapter이며 자동 YOLO 경로가 아닙니다. feet evidence는 기본 PROXY라 출발하지 않습니다. 실물 성공 판정은 별도 캘리브레이션/ground truth 평가 후 기록해야 합니다. label AMBIGUOUS 등 추가 클래스가 필요하면 confusion schema를 확장해야 합니다. 빈 manifest는 명확히 거부하며 짧은 manifest도 렌더링합니다.

## 필요한 입력 및 다음 작업

1. 사용자 소유 신호등 가중치와 SHA256, 획득 출처/라이선스, YOLO family/version, class mapping, 입력 크기/encoding, training metadata. PT는 pickle 실행 위험이 있어 출처 신뢰 확인 전 로딩 금지. trusted_pickle 플래그는 신뢰 증명이 아니라 명시적 경계입니다. ONNX도 승인된 로컬 모델만 사용.
2. RED/GREEN/OFF/포화/흐림/역광/정지구역 포함 RGB clips 및 타임스탬프와 camera readback. 기존 영상 수집 소유자를 유지하고 config/capture_proposal.json을 적용하기 전 검토.
3. 기대 신호등 heading/ROI, 두 정지구역 좌표, 실제 앞발/정지/이탈/완료 ground truth와 오차 한계.
4. pinned training-compatible Ultralytics 설치 후 detector→association→color→filter 통합 replay 및 raw/L-only/combined 평가. 검증된 모델 없이 임의 최신 모델로 대체하지 않음. YOLOv5 다른 loader는 현재 미지원.
5. 격리 ROS 환경에서 wrapper lifecycle/watchdog/실 contract 테스트. 실제 camera 입력/actuator 연결은 이 산출물에 없음.
6. Jetson target에서 별도 성능/메모리/열/TensorRT parity 검증. VM 값을 목표 장치 성능으로 전용하지 않음.

## 변경 및 롤백

이 디렉터리만 변경했습니다. 생산 파일과 service는 그대로입니다. 파일 목록은 CHANGED_FILES.txt, 해시는 SHA256SUMS에 있습니다. 통합 전 이 디렉터리를 제거하거나 채택하지 않는 것으로 rollback 가능합니다. 자동 launch, service 등록, dependency 전역 설치는 없습니다. 실제 ROS wrapper를 독립 실행했다면 해당 프로세스만 종료하십시오. git reset --hard 같은 광범위한 rollback을 사용하지 마십시오.

## 버전/라이선스/참고

Python3.12.14, OpenCV4.10.0, NumPy2.5.4, Pillow12.3.0, pytest8.3.5. 의존성 바이너리를 배포하지 않습니다. OpenCV Apache2, NumPy BSD, Pillow HPND, pytest MIT는 upstream 라이선스 확인 대상입니다. 선택적 Ultralytics는 AGPL3/Enterprise 조건 검토 필요, 사용자 가중치 라이선스는 미확인입니다. 생산 배포 전에 모델과 데이터의 사용/재배포 권한을 확인하십시오.

- 프로젝트 pack 01/02/03/30 및 제공 rulebook p8: 정지구역/2초/신호 변경 규칙.
- https://docs.opencv.org/4.x/da/d97/tutorial_threshold_inRange.html : HSV inRange. 웹 문서 최신 버전과 실행4.10 버전을 혼동하지 않음.
- https://docs.ultralytics.com/modes/predict/ : ndarray BGR 입력 및 원본 xyxy 출력. 문서의 최신 모델 예시는 사용자 모델 버전 선택 근거가 아님.

## 별도 통합 adapter 검증 추가

[../integration/HANDOFF.md](../integration/HANDOFF.md)에 실제 traffic FSM 출력과 avoidance CommandArbiter의 signal_hold 사이를 연결하는 VM in-process adapter를 기록했습니다. 16개 SYNTHETIC_IN_PROCESS 테스트와 합성 trace를 실행했습니다. owner/session/identity/TTL/mode 검증, 오래된 command 재사용 차단이 포함되며 원래 두 모듈 API는 변경하지 않았습니다. 이는 live ROS 연결이 아닙니다. traffic domain173과 avoidance domain183은 서로 분리되어 있으며 기존 standalone avoidance 실행에 자동 적용되지 않습니다. 네이티브 transport/epoch/수신자 인증과 실제 안전 통합은 여전히 NOT_RUN입니다.

## Git publication (2026-10-24)
This source snapshot is prepared for publication on main. Earlier no-publication statements describe the authoring stage. See experiments/competition_vm/PUBLICATION.md for included artifacts, exclusions and final test status. Module checksums describe the Git publication subset, not the separately delivered immutable ZIP. No real robot measurements are included.
