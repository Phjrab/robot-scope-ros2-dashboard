# C4 ROUND3 — 실제 GREEN 검출 회복과 연결 경계

2026-10-25 KST. 브랜치 `review/20261024-c4-traffic-replay`.
작업 기준은 `380800ca9e211495769fe60ee8221e3f4fb40f16`, 기능/검증 대상 커밋은
`9f5d81433675752f8522d5478e184192e2e2dc57`다. 검출/association 구현은
`80399344738d4a1374c488b37928ba77e256401b`이며 후속 변경은 stale 뒤 stage 표시 정정이다.
실제 replay의 추론/좌표/색/수치는 동일하고, 최종 전체 회귀는 stage 정정까지 포함한다. 시작 시 C4 작업 트리는 깨끗했으며
앞선 설치·하네스·제출·사적 원본을 보존했다. 검토 문서만 후속 커밋으로 분리한다.
이 문서 자신의 최종 SHA는 최종 응답에 보고한다.

**실제 GREEN 3대상 중 원본 좌표 검출+raw GREEN이 0→1개로 개선됐다.**
일반 상단 타일은 RED 15대상 검출을 유지했지만, 255장 전체의 raw GREEN 34개 중
확인 가능한 다른 crossing 녹색은 3개뿐이다. 비신호 표지판 false GREEN 3개와
뒷면/잘린 housing의 근거 부족 GREEN 28개도 확인했다. 따라서 탐색 옵션은 제공하되
생산 기본값·색 threshold·TTL을 바꾸지 않는다. 실제 stable GREEN은 입증하지 못했다.

- [기계 판독 결과](../../../mission-competition/traffic-input/round3-results.json)
- [34개 GREEN 반환 crop 사후 검토](../../../mission-competition/traffic-input/round3-green-audit.json)
- [최초 receipt 입출력 예제](../../../mission-competition/traffic-input/round3-timing-example.json)
- [재현 방법/패키지 README](../../../mission-competition/traffic-input/README.md)

## 1. 동일 원본 검출 실험

동일 사용자 제공 `yolov8n.pt`, SHA256
`f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`를 유지했다.
names 80개/class9 traffic light, checkpoint metadata 8.0.0.dev0다. 기존 제공 영역에서
추가 .pt/.onnx 및 관련 학습 metadata를 찾았으나 대체 학습 모델을 확인하지 못했다.
이 사실만으로 사용자 모델이 잘못됐다고 판단하지 않는다. 다운로드/학습/재설치 없음.

입력은 이전에 열어본 25원본/27대상(RED15/GREEN3/UNREADABLE4/OTHER_LIGHT1/NO_LIGHT4)이다.
기존 diagnostic/session_holdout 이름을 유지하되 **이번 결과는 독립 test가 아니다**.
라벨은 추론 뒤 IoU≥0.2 매칭/평가에만 사용했다. GT bbox로 추론 crop을 만들지 않았다.
사람 crop oracle와 실제 검출 bbox 결과를 분리했다.

모든 후보는 CPU, rect=True, predictor NMS IoU .7, max_det300을 명시한다.
`upper-overlap640`은 full640 + 사전 고정된 3개 상단 tile이다. 1280×720 기준
`[0,0,640,432]`, `[320,0,960,432]`, `[640,0,1280,432]`; 다른 해상도에는 정규화 비율을
적용한다. 내부 tile 경계에 닿은 bbox를 제외하고 원본 offset을 한 번만 더한 뒤
same-class IoU .5 NMS를 적용한다. 색/GT/최근 GREEN/가장 큰 box로 선택하지 않는다.

| 추론 후보 | GREEN 검출 / raw GREEN (3) | RED 검출 / raw RED (15) | RED UNKNOWN / AMBIGUOUS | 평균 / p95 / 최대 추론 ms |
|---|---:|---:|---:|---:|
| full640, conf .25 baseline | 0 / 0 | 15 / 8 | 6 / 1 | 28.73 / 35.09 / 101.18 |
| full960, conf .25 | 1 / 1 | 12 / 7 | 7 / 1 | 53.78 / 68.52 / 72.19 |
| full1280, conf .25 | 1 / 1 | 11 / 5 | 10 / 0 | 93.43 / 113.94 / 121.82 |
| full+upper tiles640, conf .25 | 1 / 1 | 15 / 8 | 6 / 1 | 112.95 / 132.49 / 134.40 |
| full640, conf .10 별도 ablation | 0 / 0 | 15 / 8 | 6 / 1 | 25.88 / 29.97 / 38.09 |
| full+upper tiles640, conf .10 별도 ablation | 1 / 1 | 15 / 8 | 6 / 1 | 106.96 / 123.29 / 125.76 |

각 후보 25회, 최초 cold inference 포함, 모델 setup은 별도 기록했다. 위 latency는
모델 호출/좌표 결합이며 아래 전체 pipeline latency와 구분한다. 실행 순서/CPU 부하에
따른 차이가 있으므로 .10 실행이 더 빠른 것을 일반적인 성능 향상으로 해석하지 않는다.

회복된 것은 `preview-2`(v5 Go2)다. 타일 후보 bbox `[694,31,751,114]`, confidence
0.289119, target IoU .902741, raw GREEN이다. v5 RealSense와 v1 반대 crossing의 GREEN은
여전히 놓쳤다. 해상도만 올리면 RED 검출 손실이 있어 기본 채택하지 않았다.
confidence .10도 추가 GREEN을 찾지 못해 채택하지 않았다.

여섯 후보 모두 원래 라벨의 UNREADABLE4/OTHER_LIGHT1/NO_LIGHT4는 localized UNKNOWN이다.
원래 RED/OTHER_LIGHT/NO_LIGHT 20대상 false GREEN은 0/20이지만 아래 사후 검토에서
오검출이 확인됐으므로 일반적 무오검출이나 전체 세션 정확도라고 보고하지 않는다.
OTHER_LIGHT 사진에 실제 다른 신호등 후보가 있는 것과 전자화면 target 오검출도 구분했다.

설정 SHA 전체는 JSON에 있다. baseline `.25`:
`f237ce7aea41a89a6dfaf228b206631a15c465857868c2830bd1bc4f470f56ec`.
탐색 tile `.25`:
`233c4de80d698728e98e5f015ade05b01528a4ba45ce7c6fd7b9e74b352008b7`.
모델/해상도/타일/threshold/NMS를 canonical hash에 포함한다. 모델만 같아도 설정 hash가
바뀌면 pipeline은 기존 association/temporal evidence를 재사용하지 않는다.

## 2. 255원본 전체 및 false GREEN 검토

| 원래 source 간격을 보존한 replay | 이전 380800c | ROUND3 full640 | ROUND3 tile640 |
|---|---:|---:|---:|
| traffic 후보 프레임 | 88 | 88 | 114 |
| traffic 후보 없음 | 167 | 167 | 141 |
| expected ROI mismatch | 74 | 74 | 97 |
| 선택 ROI | 12 | 10 | 12 |
| 선택 raw RED / GREEN | 5 / 0 | 4 / 0 | 4 / 0 |
| stable UNKNOWN | 255 | 255 | 255 |

새 baseline의 ROI 10/RED4는 가림 뒤 2회 재확인 때문에 이전의 첫 프레임을 바로
승격하지 않는 차이다. 검출 bbox 자체를 나쁘게 만든 결과가 아니다. 타일의 추가 ROI2는
sample58/59 UNKNOWN이며, 나머지 선택은 sample122~131이다. 읽을 수 있는 선택 RED는
123/128/130/131이다. 바뀐 association의 재획득/ambiguity/track reset은 JSON에 각각 남는다.
어떤 고정 ROI도 움직이는 카메라의 운영 crossing 교정값으로 바꾸지 않았다.

자유 검출 bbox 색은 full640 총105개(RED65/GREEN15/UNKNOWN20/AMBIGUOUS5), tile 총153개
(RED84/GREEN34/UNKNOWN29/AMBIGUOUS6)다. **box 수, 후보 프레임 수, mission 선택 수는 다르다.**
전체 세션 GT가 없으므로 88→114를 recall이라고 하지 않는다.

타일의 GREEN 반환 34개 모두 원본 전체와 nearest-neighbor 확대 crop을 직접 확인했다.
후보 결과로 선택된 사후 audit이며 독립 검수/독립 precision 시험이 아니다.

| crop 시각 검토 | full640 GREEN15 | tile GREEN34 | 해석 |
|---|---:|---:|---|
| 보이는 다른 crossing 녹색 발광부 | 0 | 3 | sample51/68/222; 서로 떨어진 프레임 |
| 뒤쪽/잘린 housing + 녹색 배경 | 12 | 28 | 발광부 상태를 읽을 수 없음; GREEN의 근거 부족 |
| 비신호 버스정류장 표지판 | 3 | 3 | sample223/224/226; 명확한 traffic false GREEN |

뒤쪽 housing을 RED 정답으로 추측하지 않았다. 반대 면의 진짜 상태는 UNREADABLE이며,
따라서 28개를 확정 RED→GREEN 오분류율 분모에 넣지 않는다. 그래도 이 반환을 올바른
GREEN으로 셀 수 없다. 초반에는 창/수목 배경, 후반에는 민트색 포스터가 bbox에 섞인다.
표지판은 이미지 전체 NO_LIGHT라고 라벨링하지 않았다. 같은 전체 영상에 다른 실제 신호가
있으므로 **검출 bbox 대상이 비신호**라는 negative다.

34개 중 이전보다 추가된 19개는 실제 다른 crossing GREEN3 + 근거 부족 housing16이다.
실제 GREEN3을 diagnostic expected ROI의 목표 신호로 선택하거나 연속 GREEN으로 만들지
않았다. 반대 crossing 선택 정확도는 geometry 미검증으로 NOT_EVALUATED, 이번 replay의
잘못된 GREEN 출발 권한 생성은 0이다. 권한 0을 인지 성능 PASS로 대신하지 않는다.

## 3. association/표시 및 발광부 실험

`association.py::BoundedAssociation`은 expected IoU .2, 1·2위 margin .15, 이전 bbox
continuity IoU .25를 사용한다. 여러 plausible 후보, 가림, geometry jump, source gap,
손상 이미지/모델 실패/stale 처리는 연결을 끊는다. 재획득에는 새 geometry-consistent
검출 2개가 필요하며 그 뒤 temporal .4초를 다시 쌓는다. 외부 detection index 교환은
identity로 쓰지 않는다. 회귀에는 두 신호, 순서/ID 교환, merge ambiguity, occlusion,
새 generation, model/decode 실패, 설정 hash 교체가 포함된다.

이것은 이미지 좌표 안에서의 제한된 연속성이다. 이동 camera pose/heading/crossing을
추정하거나 보증하지 않는다. 빠른 움직임이나 서로 겹쳐 indistinguishable한 신호는
잘못된 운영 identity를 배제할 수 없으므로 trusted geometry binding은 별도 필요하다.

`--observation-mode detection-only`는 bbox/raw 색만 `free_observations`에 남기며
mission identity/stable은 null이다. canonical raw/stable은 UNKNOWN, ROI는 null이다.
별도 PNG `detection_only_overlay`는 raw box와 signal stage를 표시한다. context는
`detection-only / associated / stable`을 구분하고 tracker의 image-space association
snapshot은 crossing 검증을 주장하지 않는다. 설정의 verified flag를 올리지 않았다.

검출 비교 뒤 남는 UNKNOWN/AMBIGUOUS에만 `--lamp-experiment`를 적용했다. 미리 정한
housing 상단55%에 combined core와 원본 HSV를 비교했다. GT 수동 crop과 detector crop은
분리했고 실제 signal에는 항상 기존 core의 전체 detector crop 결과를 쓴다.

| detector crop | 전체 housing state / red,green component | 상단55% combined | 상단55% HSV |
|---|---|---|---|
| sample121 | UNKNOWN / 3,0 | UNKNOWN / 3,0 | UNKNOWN / 3,2 |
| sample126 | UNKNOWN / 0,0 | UNKNOWN / 0,0 | UNKNOWN / 0,11 |
| sample129 | AMBIGUOUS / 25,18 | AMBIGUOUS / 25,18 | AMBIGUOUS / 25,31 |

기존 sample121 chroma1629→1227,126 469→304,129 549→359처럼 배경 픽셀 수는 줄었지만
상태는 개선되지 않았다. 따라서 발광부 실험은 **미채택**이다. 원본 HSV에서도 충분한
단일 색 성분을 확보하지 못했고 min_pixels12 완화/포화색 복원 주장도 없다.
`experiments/competition_vm/traffic_signals/core.py`는 수정하지 않았다. C1/D0에 제안할
인터페이스는 optional diagnostic return뿐이며 이 실험을 production classifier로 넘기지 않는다.

## 4. 실제 시간 계측과 C1/C2 연결 요청

source-timeline 모드는 원래 기록의 약51.8초 간격을 유지하고 CPU duration은 별도다.
입력은 historical clock 미검증 fixture이며 실시간 freshness 성공으로 취급하지 않는다.
source-timeline pipeline 평균/p95/최대는 baseline 27.27/31.31/211.27ms,
tile 133.31/220.62/285.53ms다. 두 실행 모두255장, decode/model 오류0이다.

wall-clock 모드는 동일한 scheduled first receipt에 실제 처리/queue 지연을 누적했다.
최종 코드 replay255장: 총51.964초, pipeline 평균174.98/p95 235.42/최대492.21ms,
queue 최대296.77ms, receipt age 최대493.35ms, SOURCE_STALE/RECEIPT_EXPIRED 각26장.
후보114는 같지만 freshness 이후 연결 재확인 때문에 선택ROI10이다. stable UNKNOWN255.

최종 freshness 후 tracker reset 보강 전의 첫 workload 실행도 숨기지 않고 JSON에 보존했다:
평균146.07/p95 218.03/최대1552.41ms, queue최대1777.60ms, stale49장이다. 호스트 부하
변동이 크며 유리한 실행만으로 online 가능이라고 보고하지 않는다. 모델 실험 중 전체
suite를 병행하지 않았다. 최신 프레임 worker를 쓰더라도 개별 추론이 TTL을 넘을 수 있다.
이 수치는 로컬 CPU fixture workload이며 Jetson/전송 지연/센서 clock PASS가 아니다.

새 context에는 `processing_started_s`, `queue_residence_s`, `pipeline_wall_s`,
`inference_settings_sha256`, detector `inference_wall_s`가 있다. 다음 기존 값은 유지한다:
`first_received_s`, `source_age_at_first_receipt_s`, `processed_s`, `source_clock`,
`clock_verified`, `identity_verified`, `producer_epoch/sequence/source_stamp_ns`.

실제로 실행한 합성 계약 예제(실영상 GREEN 근거 아님):

- 최초수신10.00, 최초 source age.02, 처리시작10.01, 완료10.08.
- queue.01, receiver age.08, 완료 source age.10. now10.15에서는 age.17.
- `signal_fragment(obs, now_s=10.15)` 또는 `received_s=10.00`: 통과. 최초 프레임이므로
  raw GREEN / stable UNKNOWN이고, mission 전체 Evidence/권한이 아니다.
- `received_s=10.08`: `FIRST_RECEIPT_MISMATCH`로 거부.
- now10.240001에서는 source age>.25이므로 status.fragment=null,
  `SIGNAL_EVIDENCE_EXPIRED`. receipt/epoch/sequence는 갱신되지 않는다.
- 느린 처리 합성 회귀에서는 raw diagnostic GREEN을 유지하되 stale fragment가 없다.

**다른 역할 소유 파일은 수정하지 않았다. C1 증분 통합 때 필요한 정확한 변경:**

| 소유 위치/함수 | 확인한 문제 | 요청하는 입출력/동작 |
|---|---|---|
| C2 `robot_dashboard/mission_routes/competition_native/fragments.py::join_signal` | docstring이 `signal_fragment(... received_s=processed_s)`를 지시; e2e9c50 계약을 전제 | `signal_fragment(obs, now_s=now)` 사용. explicit first/processed args가 context의 first/processed와 일치하는지 검사. initial age는 명시적인 `source_age_at_first_receipt_s`와 `source_age_s-receiver_age_s`의 일관성을 검증해 한 번만 계산. `identity_verified is True` 필수 |
| C1 `robot_dashboard/mission_routes/competition_native/ingress.py::CompetitionIngress.join` | live branch가 실제로 `received_s=sample.processed_s`를 전달 | 최초 context receipt로 projection. worker sample/frame과 context의 epoch/seq/stamp/receipt 일치 검사. ComponentStamp는 원래 receipt와 최초 age를 사용. fixture는 synthetic 허용 경계에서만 처리 |
| C1/C2 binding 구성 | config/model만 pin하면 새 resolution/tile을 구분 못함 | trusted binding에 `inference_settings_sha256`를 추가하고 observation과 대조. 다르면 새 generation/검토 없이는 GREEN 재사용 금지 |
| C1 기존 camera owner→TrafficWorker | 원래 source identity 검증은 trusted owner 책임 | epoch/sequence/stamp, clock, identity를 실제로 검증. 테스트 fixture에만 명시적 identity_verified=True; payload 자기신고로 올리지 않음. 단일 실행+최신 pending 정책과 queue/source age 유지 |

C1의 이미 통과한 초기 full-path를 새로 구현하거나 다른 역할을 병합하지 않았다.
C1은 기존 통합 브랜치에서 이전 C4 이후 변경만 채택하고 위 경계를 실제 joined regression으로
확인해야 한다. **C4 standalone 계약 PASS와 C1/C2 최신 통합 PASS는 다르며 후자는 NOT_RUN**이다.

## 5. 검증과 재현

환경: Python3.12.3, torch2.6.0+cpu, torchvision0.21.0+cpu, ultralytics8.3.203,
numpy1.26.4, OpenCV4.10.0.84, jsonschema4.10.3. 기존 전용 venv를 재사용했다.
저장소 root에서 실행한 주요 명령(사적 입력은 로컬 work에만 있음):

```sh
PY=../c4-venv/bin/python
MODEL=/home/chosun/Desktop/yolov8n.pt
export YOLO_CONFIG_DIR=../ultralytics-settings MPLCONFIGDIR=../mpl
$PY -m robot_dashboard.competition_traffic.experiments \
  --input-root .. --labels docs/mission-competition/traffic-input/real-labels.json \
  --config ../owner-v3-config.json --model "$MODEL" \
  --output ../round3/comparison --include-confidence-ablation --acknowledge-trusted-pickle
$PY -m robot_dashboard.competition_traffic.replay \
  --input ../jetson-v3/frames.jsonl --output ../round3/v3-upper-wall-final \
  --config ../owner-v3-config.json --model "$MODEL" --fps 5 \
  --clock-mode wall-clock --inference-profile upper-overlap640 \
  --lamp-experiment --no-image-artifacts --acknowledge-trusted-pickle
# Separate source-timeline runs used --inference-profile full640 and upper-overlap640,
# --clock-mode source-timeline, and distinct new output directories.
$PY -m unittest discover -s tests/competition_traffic -t tests -v
$PY -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
$PY -m ruff check robot_dashboard scripts tests/competition_traffic
$PY -m mypy --config-file mypy.ini
$PY scripts/check_repository_secrets.py
git diff --cached --check
```

| 검사 | 실제 결과 |
|---|---|
| 6후보×25원본 탐색 비교 | 실행 완료, exit0; 독립 accuracy 시험 아님 |
| 255장 source-timeline baseline/tile + wall-clock tile | 실행 완료, exit0; 성능/오검출/TTL 한계는 위 표 |
| C4 weight-free 단위/계약 | **81 PASS, 0 SKIP** |
| 전체 Python | **2,772 실행, 0 실패, 2 SKIP**, 86.405초 (최종 stage 정정 포함) |
| JS unit/file-level | **70 PASS, 0 SKIP** |
| frontend syntax | **104 modules PASS** |
| Ruff | PASS |
| mypy 저장소 지정 4 source files | PASS; C4 전체 타입 증명으로 표기하지 않음 |
| staged source secret scan / diff check | PASS |
| native Nav2 실행 / 물리 로봇 검증 | NOT_RUN, 이번 C4 범위 아님 |

전체 Python의 SKIP2는 optional rosbags 미설치와 PCD_EDIT_NODE 미설정의 기존 선택 검사다.
C4는 모델 없이 회귀하며 실제 가중치 replay는 별도 사적 입력 실행이다. 최소 CI job은
cv2/jsonschema를 명시 설치하고 C4 81개 이상, skip0을 요구해야 한다. 공용 CI의 optional
module skip을 실제 인지 검사 PASS로 계산하지 않는다.

공용 CI YAML은 GitHub-hosted hardware-free push workflow 하나이며 배포/장비 연결이 없다.
main/PR/공용 workflow를 바꾸지 않는다. 직전 C4 `380800c` CI는
[run40098198981](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40098198981)
completed/failure로 확인했다. 양쪽 Python matrix의 static/Python/JS 단계는 통과했고
browser E2E에서 `observed_joints.js`의 CommonJS named export `GO2_JOINT_NAMES` 오류로
종료됐다(실제 job 로그 확인). C1이 담당하는 공용 수정은 중복 적용하지 않았다.
최종 제출 exact SHA의 원격 상태와 실제 run 링크는 push 후
조회하여 최종 응답에 기록한다. 로컬 PASS를 원격 PASS로 대체하지 않는다.

## 6. 변경 파일·다른 역할·제출 경계

기능 변경: `competition_traffic/{model,inference,pipeline,association,lamp,artifacts,replay,experiments}.py`.
회귀: `tests/competition_traffic/{test_recovery,test_diagnosis,test_pipeline,test_replay}.py`.
문서/작은 JSON: traffic-input README + round3-results/green-audit/timing-example, 이 ROUND3.
삭제/이동 없음. C4 소유 경로 외 변경 없음. VM core, C1 wiring, C2 adapter, UI, 공용 CI,
main 위치추정/자동 초기값, L1 파일을 수정하지 않았다. rollback은 이번 C4 기능 2개와 문서 커밋을 되돌리는
검토로 제한하며 사적 입력과 기존 제출은 유지한다.

읽기 전용 참고/원격 확인:

- main `104692fa0070ef085eee918913ea05fdb2d88c05`; 자동 초기 pose 관련 기존 작업 보존.
- C1 `review/20261024-c1-integration-r2` / `765622ecbe20dd29b40296dd2ad24fa508ac9443`.
  INTEGRATION_REVIEW의 기존 C4 기준은 e2e9c50이므로 380800c 이후 변경만으로는 충분하지
  않다. 기존 통합본에서 빠진 최초 receipt/identity 변경까지 증분 범위를 확인한다.
- C2 `review/20261024-c2-mission-adapter` / `ae52d9899c743221c88c9e0e1bab2a4a543103eb`.
- D0 core/계약 참고 시 `69789d3cadded006dfc303e65e57f61941753214`, 제출 직전
  `924345a0f4b46f1d2f3f467142cad069124a17ad`로 진전. 이후 diff는 collision 연구 범위이며
  C4에 가져오지 않았다.
- C3 참고16c63e0 이후 원격 `7a220d458fe8bce8cdd366caa4e9a546bddebd60`; 읽기 전용 유지.
- **L1 브랜치는 제출 직전 실제 존재**:
  `review/20261024-l1-lidar-stale` / `5339e3b5c9906991e08766b61bd27d92e725aa6f`.
  `docs/lidar-stale/DIAGNOSIS.md`와 변경 경로를 읽었다. main/C1-r2의 ancestor 검사 둘 다
  exit1이고 git cherry도 해당 L1 patch를 `+`로 반환하여 현 시점 두 브랜치에 미통합이다.
  L1의 장비 작업 승인/주장을 C4의 승인이나 검증으로 전용하지 않았다.

원본 JPEG/모델/전체 관측 JSONL/overlays/가상환경은 Git에 없다. 공개 JSON은 해시·bbox·
수치·라벨·합성 계약만 담는다. 실제 이미지와 전체 로그는 로컬 사적 결과이며 GitHub
artifact로 올렸다고 주장하지 않는다. branch push는 이 C4 브랜치만 대상으로 한다.

**남은 한 가지 작업:** 검증된 source clock/epoch/sequence와 camera→crossing/접근 방향
교정이 함께 있는 원본 연속 RED→GREEN→RED 입력으로, C1의 증분 연결 후 emitting-region
identity와 stable 실영상 동작을 검증한다. 최소 묶음은 원래 해상도/카메라 source,
노출·gain·화이트밸런스/settling metadata(없으면 null), .25초 이하 실제 frame 간격,
같은 crossing의 전환 전후 지속 구간, 옆 crossing/뒷면/잘림/표지판/UNKNOWN 장면이다.
정지 GREEN 3장의 복제나 timestamp 압축으로 대체하지 않는다. 새 자료 획득을 위해
장비에 접속하거나 카메라를 열지 않았으며, main 병합·PR·서비스 변경·배포·실이동 없음.
