# C4 후속: 실제 RGB 탈락 경로와 시간 계약

기존 제출 `e2e9c5087767f3953d715c61e76388e4769d34b4`에서 이어 작업했다.
브랜치는 `review/20261024-c4-traffic-replay`, 공통 기반은 그대로 `7f2a707`이다.
시작 시 staged/unstaged 모두 깨끗했고 기존 제출 이후 C4 변경은 없었다.
원격 main은 `7ef47dc249e4dba83865e78dc283f40013ea92de`였다. main을 되돌리거나
병합하지 않았다. 기존 REVIEW와 실제 원본·모델·기존 실행 결과는 보존했다.
이번에는 로컬에 이미 받은 입력만 사용했으며 Jetson 조회/SSH/카메라 접근은 없었다.

## 1. 결론과 손실 경로

모델 실행 연결은 정상이다. 큰 손실은 **traffic 후보 부재 167장과 고정 expected ROI
불일치 74장**이다. ROI에 도달한 12장 중 RED 5, UNKNOWN 6, AMBIGUOUS 1이다.
색 UNKNOWN 6장은 적색 연결 성분이 12픽셀 기준에 못 미쳤다. 원본에 읽을 수 있는
녹색은 있다. 별도 작은 라벨 집합의 GREEN 3개 대상은 모두 검출 단계에서 놓쳤으며,
사람이 지정한 crop에서는 기존 color core가 GREEN을 반환했다. 이 oracle 결과를
생산 검출/association/stable GREEN으로 승격하지 않았다.

[255프레임 진단](../../../mission-competition/traffic-input/real-diagnosis-frames.jsonl),
[전후·시간 요약](../../../mission-competition/traffic-input/real-diagnosis-summary.json),
[라벨](../../../mission-competition/traffic-input/real-labels.json),
[라벨 평가](../../../mission-competition/traffic-input/real-label-evaluation.json).
원본 사진/가중치/전체 로컬 manifest/overlay는 Git에 없다.

| 단계 | 통과 프레임 | 단계 탈락/한계 |
|---|---:|---|
| 원본 해시·BGR decode·1280×720 | 255 | decode 오류 0 |
| YOLO post-NMS 객체 존재 | 248 | 객체 출력 자체가 없는 프레임 7 |
| class 9 allowlist traffic 후보 | 88 | 다른 클래스만 출력된 프레임 160; 합계 traffic 후보 부재 167 |
| C4 confidence ≥0.25 | 88 | 추가 confidence 탈락 0; 모델 floor 아래/NMS 소거 후보 수는 측정 불가 |
| expected ROI IoU ≥0.2 | 14 | bbox가 있으나 고정 ROI와 불일치 74 |
| 다중 신호 association 통과 | 12 | IoU 1·2위 차이 <0.15인 모호한 후보 2 |
| native crop 크기/경계 통과 | 12 | TOO_SMALL/ROI_TRUNCATED 0 |
| 원본 색 단일 RED/GREEN | 5 | 성분 부족 UNKNOWN 6, 두 색 AMBIGUOUS 1 |
| 검증된 mission association | 0 | 5장도 diagnostic binding 미검증 |
| stable 색/주행 권한 | 0 / 0 | 전체 255 stable UNKNOWN; 명령 생성 없음 |

객체 수와 프레임 수를 구분한다. post-NMS box 총 1,723개 중 비허용 클래스 1,618개,
traffic 105개가 88프레임에 분포한다. 모델 floor 0.25와 NMS 이전 logits는 관측하지
않았다. 따라서 167장을 '신호가 실제 존재하는데 YOLO가 놓친 장면'으로 단정할 수 없다.
이 255장의 전체 GT가 없으므로 전체 검출 recall도 계산하지 않는다.

단일 terminal reason의 합은 255다: DETECTION_REJECTED 167,
EXPECTED_ROI_MISMATCH 74, ASSOCIATION_UNCERTAIN 2, COLOR_REJECTED 7,
ASSOCIATION_UNVERIFIED 5. 독립 quality flag인 ASSOCIATION_UNVERIFIED는 모든 255장,
FRAME_RECEIPT_GAP은 2장에 붙는다. 이 flag 수를 terminal count에 더하지 않는다.
source/receiver stale, sequence/epoch 역전, 동일 콘텐츠 연속, crop clipping/size 실패는
이 기록에서는 각각 0이다. 별도 합성 회귀에서 실제 거부 동작을 검사했다.

### 전후 비교와 원인 구분

| 항목 | 기존 제출 | 후속 |
|---|---:|---:|
| DETECTOR_MISSING | 241 (ROI 불일치 포함) | 167 |
| 별도 EXPECTED_ROI_MISMATCH | 구분 없음 | 74 |
| 후보 프레임 / 선택 ROI | 88 / 12 | 88 / 12 |
| raw RED / AMBIGUOUS / UNKNOWN | 5 / 1 / 249 | 5 / 1 / 249 |
| stable UNKNOWN | 255 | 255 |

모든 프레임의 후보 bbox/confidence/class와 raw/stable 결과가 기존 결과와 동일하다.
코드 결함은 ROI mismatch 오분류, 같은 JPEG 무조건 차단, caller가 projection receipt를
새로 붙일 수 있던 경계, 완료 시각 차이를 temporal 지속 시간으로 사용하던 부분이다.
이들을 고쳤고 TTL 0.25초/stability 0.4초/색 임계값/association 임계값은 바꾸지 않았다.

고정 ROI `[540,45,640,155]`는 움직이는 카메라의 crossing/heading 교정값이 아니다.
74장 탈락은 현재 입력/설정의 한계다. detector bbox를 따라 expected ROI를 옮기거나
largest-box fallback을 넣어 결과를 좋게 만들지 않았다. 5개 RED도 sample117,123,128,
130,131로 끊겨 있고 최장 인접 RED는 약0.2초뿐이다. binding flag를 무시한 가정에서도
0.4초 RED 연속 증거가 없다. stable GREEN 입력은 이 255장에 없다.

## 2. 실제 모델·원본 좌표·색 확인

기존 사용자 제공 `yolov8n.pt`, SHA256
`f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`를 재사용했다.
Ultralytics 8.3.203/torch2.6.0+cpu에서 같은 VM loader로 로드했다. names80,
class9=`traffic light`; RED/GREEN 클래스가 아니다. checkpoint metadata의
8.0.0.dev0와 이 실행 loader 버전을 구분한다. 사용자 의도와 다른 학습 모델이라는
결론을 뒷받침하는 추가 학습 metadata는 없으므로 '잘못된 모델'이라고 단정하지 않는다.
새 YOLO 모델, 학습, confidence 튜닝, 패키지 재설치는 하지 않았다.

기존 VM loader가 가진 동일 CPU model.predict 경로에서 post-NMS 결과를 계수한 뒤
allowlist를 적용한다. 원본 BGR를 그대로 전달하며 실제 결과 orig_shape는 720×1280이다.
Ultralytics 결과는 native xyxy이므로 이 입력에는 letterbox 역변환을 다시 하지 않는다.
별도 letterbox 계약/padding 회귀도 유지했다. 원본3장(Pillow RGB를 역순으로 비교)의
BGR 채널 일치 PASS, 선택 ROI12개의 원본 BGR slicing과 저장된 crop PNG 픽셀 일치 PASS.

UNKNOWN6개의 red_component는 sample121=3,122=8,124=2,125=5,126=0,127=7이다.
sample129는 red25/green18로 AMBIGUOUS다. crop의 전체 blur variance는 약1800~2508,
white clip fraction은 0~0.000763으로 crop 전체가 완전 포화된 경우는 아니다.
그렇다고 발광부 색 정보가 충분하다는 뜻도 아니다. 수동 발광부 사각형에서
HSV saturation<55 픽셀은 34~72%, red channel≥250은 1.8~10.3%였다.
육안으로 붉은 테두리가 남지만 밝은 내부가 거의 무채색인 작은 신호다.
이 비율은 발광부 주변을 포함하는 수동 영역 통계이지 센서 노출 보정 성공 지표가 아니다.
CLAHE가 손실된 색을 복원했다고 주장하지 않는다.

D0/C1 최소 검토 제안: sample121/126/129의 공개 hash+native ROI+성분 수로 재현하고,
발광부와 검출 housing 배경을 분리하는 진단을 먼저 검토한다. 불필요한 배경의 녹색
성분과 거의 무채색 발광부를 whole-box chroma/blur 값만으로 평가하기 어렵다.
core 변경이나 min_pixels 완화는 이번 C4에 포함하지 않았다.

## 3. 작은 실제 라벨 평가

Codex가 원본과 nearest-neighbor crop 확대를 직접 검토한 초기 라벨이며 독립 검수는
아직 없다. 25개 서로 다른 원본, 27개 대상: RED15 / GREEN3 / UNREADABLE4 /
OTHER_LIGHT1 / NO_LIGHT4. NO_LIGHT는 신호등이 안 보이는 장면, OTHER_LIGHT는 전자
디스플레이 영역이다. 다른 crossing의 녹색은 별도 target으로 표시했다.
불분명한 흐림·부분 잘림·비스듬한 면은 UNREADABLE이며 정답률 분모에서 뺐다.

v3 전체 세션은 diagnostic으로 묶었다. 12장은 기존 선택 ROI에서 골랐으므로 선택
편향이 있으며 검출 recall test가 아니다. v3 RealSense1장까지 diagnostic13개다.
나머지 세션 전체는 session_holdout14개로 묶고 두 카메라/한 사진의 다중 target을
서로 다른 split으로 나누지 않았다. train/tune 과정은 없다. 이 holdout은 시간적·
통계적으로 독립된 대규모 시험이 아니며, 원본을 열어본 후의 탐색적 진단이다.

| frozen detector + GT target 매칭 후 raw color | 전체27 target | 세션 holdout14 target |
|---|---:|---:|
| RED / GREEN / UNKNOWN / AMBIGUOUS | 8 / 0 / 18 / 1 | 2 / 0 / 12 / 0 |
| 읽을 수 있는 RED/GREEN 중 UNKNOWN | 9/18 (50%) | 3/5 (60%) |
| false GREEN (RED/OTHER_LIGHT/NO_LIGHT 분모) | 0/20 | 0/7 |
| valid GREEN reject | 3/3 | 3/3 |

UNREADABLE4개에는 정답을 억지로 부여하지 않았다. NO_LIGHT는 후보 어디서든
GREEN이면 false GREEN으로 집계한다. 다중 target은 해당 ROI와 IoU≥0.2인 detector
후보만 매칭한다. 이는 GT가 위치를 제공하는 **localization-conditioned raw 진단**이며,
실제 mission association 정확도나 stable 성능이 아니다. 0/20은 false GREEN이 없다는
일반적 보장도 아니다. 안정 상태의 실제 성능은 binding 미검증으로 NOT_EVALUATED다.

GREEN은 v5 두 카메라의 같은 시점 2개와 v1 다른 crossing 1개다. v5는 후보 자체가
없고, v1은 foreground RED만 검출되어 녹색 target을 놓쳤다. 세 manual crop 모두
기존 color core GREEN이다. 이를 이용해 detector/association 결과를 대체하지 않았다.
**녹색 검증 입력은 있으나 연속 GREEN/전환/운영 binding 검증 입력은 없다.**

## 4. source timeline과 wall-clock 부하

`--clock-mode source-timeline`: 원래 captured_at의 상대 간격 51.8초를 fixture
시간으로 재현한다. 실제 sensor timestamp/epoch/sequence 검증은 아니다. CPU 실행은
14.181초, pipeline 평균27.84ms/p95 33.32ms/최대114.16ms였다.

`--clock-mode wall-clock`: 같은 source 간격에 맞춰 로컬 fixture receiver를 실제
시간으로 진행했다. scheduled arrival을 최초 receipt로 유지하며, 밀린 처리의 queue
지연과 완료 지연을 source age/receiver elapsed에 포함한다. 전체51.854초,
pipeline 평균34.21ms/p95 76.99ms/최대117.82ms였다. 양쪽 모두255장, 같은 후보/색/ROI,
source/receiver stale0이다. 원래 interval>0.25초인 sample21/23의 gap2는 그대로다.
총 wall duration에는 decode·저장·대기, pipeline latency에는 detector/ROI/color/temporal이
들어간다. CPU 계측 중 전체 suite를 함께 돌리지 않았다. 단일 로컬 PC 실행 수치이며
Jetson throughput, 통신 지연/경합/clock synchronization PASS가 아니다.

`clock_verified=True`인 fixture는 가상 시계 내부 관계만 뜻하며 historical_clock_verified는
항상 false다. fps5는 manifest 간격이 없는 경우의 보충값이다. 이 입력에는 sample
제거나 보간이 없으며 분석 sequence와 과거 실제 camera sequence를 혼동하지 않는다.

같은 bytes의 신뢰된 source epoch/seq/stamp 전진은 허용하고 hash는 진단만 남긴다.
source identity 검증은 기본 false이며 trusted CameraHub 경계가 설치해야 한다.
동일 source identity는 새 receipt/content nonce로 바꿔도 거부하고 원래 age/receipt를
유지한다. 새 sequence에 같은 source stamp를 넣어도 거부한다. epoch가 바뀌어도
receiver rollback은 거부한다. stale/invalid 이후 high-water와 retired epoch는 유지된다.
재시작 후 내구성 있는 재생 방지는 C1/C2 trusted ingress 책임이다.

## 5. D0/C2/C1 계약 확인과 연결 표

읽은 exact refs (합치거나 수정하지 않음):

- D0 `6403aab3afef96efa778b5265afd7ce5b351265c`의 core TemporalFilter, lifecycle.py,
  REVIEW. 새 highwater/receiver_highwater가 reset 이후 유지되는 변경 확인.
- C2 `efc2df6bfaad8f0032fee758b12e250435ffc71c`의 observations.py Normalizer와 HANDOFF.
- C1 원격 `2034cc72842ebda1e73f39d12021fb898e75e0b8` 확인. 공용 통합 변경은 C1 소유.

| C4 값 | C1/C2에서의 의미 |
|---|---|
| signal fields | C2 FIELDS['signal']의 signal_id/crossing_id/raw/stable/quality/confidence/ROI/native size/model hash에 대응. image/exposure/preprocess는 진단 sidecar로 보존 |
| source_id / producer_epoch / sequence / source_stamp_ns | trusted binding이 producer_id/epoch/ComponentStamp로 옮긴다. envelope sequence나 poll nonce로 대체하지 않음 |
| source_age_at_first_receipt_s / first_received_s | camera owner의 source age와 같은 호스트 최초 monotonic arrival. current age = age_at_first + now−first |
| processed_s / source_age_s | 처리 완료 시점과 그때의 누적 age. first receipt에 이 age를 다시 더하면 이중 계산이므로 구분 |
| binding_id / config_hash / signal_id / crossing_id | camera·heading·교정 revision을 mission scope에 trusted하게 연결. GT ROI나 detector track index는 운영 binding 증거가 아님 |
| identity_verified / clock_verified | 내부 trusted owner 계약. network payload의 자체 주장으로 true를 설정하면 안 됨 |
| signal_status | fragment 불가 사유, 마지막 유효 live 안정 색 관측의 최초 수신시각, 원래 identity/receipt. stale GREEN을 새 관측으로 만들지 않음 |

C2 Normalizer의 같은 component sequence 재사용은 최초 Received를 유지하고,
내용/ComponentStamp 변경은 DUPLICATE_COMPONENT_CHANGED로 거부한다. C1은 C2로
최초 넘기는 시각 R에 `age_at_first + (R−first_received)`를 component age로 한 번
전달하고, 이후 같은 component 재사용에서는 그 stamp/age/fingerprint를 그대로 둬야
한다. 다른 프로세스/호스트면 trusted clock-aware 전송 계약이 추가로 필요하다.
C4의 0.25초 만료를 C2의 더 느슨한 fixture 정책으로 연장하면 안 된다.

C2 scope/run/goal_generation/receiver_session은 C1이 검증하고 붙인다. 오래된 packet에
새 session nonce만 붙이는 재바인딩은 금지한다. 모든 component가 동일한 camera
clock을 갖는다고 가정하지 않는다. CameraHub가 기존 소유자로 bytes+metadata를
넘기며 C4는 카메라 polling/owner/FSM/command authority를 만들지 않는다.

D0 lifecycle은 접근 terminal/HOLD ACK/새 exit generation·ACK/그 이후 실제 departure를
분리한다. C4 raw/stable GREEN은 그 ACK, 물리 정지, 발 위치, path clearance 증거를
대체하지 않는다. D0 새 코드를 C4에 복사하지 않았고 두 역할의 동시 runtime 통합은
NOT_RUN이다. C1은 새 D0를 선택한 통합 revision에서 C4 회귀를 재실행해야 한다.

## 6. 검사·재현·최소 추가 입력

제출 후보에서 C4 69 PASS/0skip, 기존 VM traffic67 PASS/0skip,
전체 Python2760개(2758 PASS/2 SKIP), JavaScript70개 file-level PASS/0skip,
JS syntax104 modules PASS를 확인했다. Ruff 전체 대상 PASS, mypy 기존 대상4파일
PASS, staged-source secret scan 및 diff check PASS를 확인했다.
전체 suite의 SKIP2는 optional rosbags 미설치와 PCD_EDIT_NODE 미설정이다.
이전 제출 e2e9c50의 원격 CI run40094268039는 두 OS에서 browser E2E의
`GO2_JOINT_NAMES` named export/CommonJS 로딩 오류로 실패했음을 로그로 확인했다.
공용 observed_joints.js/E2E/package module 설정은 C1 통합 범위라 수정하지 않았다.
이번 push CI 결과는 최종 응답에서 exact HEAD에 연결해 별도 보고한다.
실제 모델/RGB는 두 모드 각255장 exit0, 라벨27 target private audit exit0다.
실제 ROS/Nav2/장비/브라우저 E2E와 역할 간 runtime 통합은 NOT_RUN이다.

전용 unit/contract 명령,
최소 dependency와 zero-skip gate, private replay 명령은
[README](../../../mission-competition/traffic-input/README.md#c1-dedicated-ci-jobs)에 있다.
기본 CI optional dependencies SKIP을 C4 PASS로 집계하지 않는다.

필요한 최소 다음 입력은 다음과 같다. 이번 작업은 촬영·장비 조작을 수행하지 않았다.

1. 현재 실제 거리/heading과 고정된 owner metadata에서 GREEN 유지≥1초 및 RED↔GREEN
   전환 연속 구간. 현재 GREEN3개는 두 세션의 개별 시점이며 latency/continuity GT가 없다.
2. 같은 장면의 신호 발광부가 무채색으로 뜨지 않는 노출과 거리별 작은 세트. 현재의
   밝은 RED 및 흔들린 장면과 비교할 실제 색 정보가 필요하다. 숫자 임계값을 추정해
   장비에 자동 적용하지 않는다.
3. 검증된 camera epoch/sequence/source timestamp와 clock 관계·오차 상한, 실제 최초
   receiver receipt, crossing/heading별 expected ROI 교정. 이는 저장 summary에 없다.
4. 다른 crossing GREEN과 현재 crossing RED가 동시에 보이는 연속 구간 및 전자 화면/
   반사광 negative. 현재 한 장의 opposite GREEN과 화면만으로 오연결률을 평가할 수 없다.

소스/검사/요약/해시/라벨만 기존 C4 브랜치에 focused commit/push한다. 원격 exact HEAD는
최종 응답에서 기록한다. 자기 SHA를 문서에 반복 커밋하지 않는다. main push, PR,
merge/rebase/force push, 로봇 명령·배포는 수행하지 않는다.
