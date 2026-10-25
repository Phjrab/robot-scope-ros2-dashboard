# C4 ROUND4 — 발광부 후보 검증, 미채택·동결

2026-10-25 KST. 기존 브랜치 `review/20261024-c4-traffic-replay`에서 이어서 진행했다.
실제 시작 SHA는 `9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd`, 기능·검사 대상 SHA는
`119c8690f9e2e46180c8a2c429da446b496a62d8`다. 시작 작업 트리는 깨끗했고 기존 원본과
ROUND3 실행 기록을 보존했다. 이 문서만 후속 커밋이며 최종 제출 SHA/원격 CI는 최종
응답과 로컬 제출 기록에 보고한다. 문서 자신의 SHA를 넣기 위한 반복 커밋은 하지 않는다.

**선택적 `enclosed-chroma-v1` 후보는 실패했다. 기본값 off, 미채택 상태로 동결한다.**
255원본의 검출 bbox 153개가 모두 UNKNOWN이 됐다. 표지판 3개와 근거 부족 housing
28개의 GREEN을 억제했지만, 실제 다른 crossing GREEN 3개도 전부 잃었다.
별도 25원본/27대상에서는 기존에 맞힌 GREEN 1개와 RED 8개를 모두 잃었다.
이를 false GREEN 0이라는 성공으로 세지 않는다. 추가 threshold/타일 탐색은 중단했다.

- [수치·동결 설정·실행 한계](../../../mission-competition/traffic-input/round4-results.json)
- [알려진 GREEN 반환 34개 before/after](../../../mission-competition/traffic-input/round4-green-audit.json)
- [한 장짜리 데이터 요청](../../../mission-competition/traffic-input/EMITTER_DATA_REQUEST.md)
- [옵션과 재현 방법](../../../mission-competition/traffic-input/README.md)

## 후보 한 개와 변경 범위

기존 가중치 `yolov8n.pt` SHA256
`f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`를 사용했다.
names80/class9 traffic light라는 기존 확인을 유지한다. 대체 모델 다운로드·학습·교체는 없다.
기존 `upper-overlap640`, confidence .25, full640+상단 3개 tile을 그대로 사용했다.
모델/타일/좌표 결합/원래 color core/association 기준/TTL은 변경하지 않았다.

`emitter.py`는 원본 bbox에서 기존 color core의 **원본 chromatic mask**와 원본 HSV V를
본다. V는 보정된 물리 휘도가 아니다. 최소 crop 12px, 프레임 가장자리 여백 1px,
성분 12px 이상, crop 경계 여백 2px, 면적≤25%·너비≤65%·높이≤55%, 중앙 x 20~80%,
성분 median V≥160, 주변 ring 대비≥60, V가 40 이상 낮은 ring 비율≥65%를 요구한다.
ring 반경은 성분 최대 변의 15%(최소 2px)다. 전체 설정은 JSON에 고정했다.

색·채널·크기·잘림·성분 증거가 부족하면 UNKNOWN이다. 원래 raw diagnostic은 보존한다.
native 좌표의 성분 bbox/측정값/거부 이유를 함께 남긴다. CLAHE 색 복원, 고정 정답 bbox,
sample 번호, known-negative 좌표 blacklist는 사용하지 않는다. 밝은 인쇄물·반사는 이
형태 조건을 통과할 수도 있어 `supported`도 발광/전면/운영 crossing의 증명이 아니다.

소스 7개 SHA와 설정을 `2026-10-25T06:02:58.979968Z`에 먼저 동결했고, 최종 분석 때
소스 hash가 같음을 확인했다. 실제 결과를 본 뒤 기준을 변경하지 않았다.

| 소유 파일 | 변경 |
|---|---|
| `robot_dashboard/competition_traffic/emitter.py` | 후보 하나, raw 보존·native 성분 진단 |
| 같은 디렉터리 `inference.py`, `model.py` | 기존 설정 hash에 옵션 포함, 모델 단계별 시간 진단 |
| 같은 디렉터리 `pipeline.py`, `replay.py` | 명시적 opt-in, unsupported 선택색 UNKNOWN, 완료 시각에 비용 포함 |
| 같은 디렉터리 `experiments.py`, `artifacts.py` | 동일 bbox before/after, raw/emit와 mission stage 분리 표시 |
| `tests/competition_traffic/test_emitter.py` | 9개 후보/기본값/시간·설정 경계 회귀 |
| `docs/mission-competition/traffic-input/` 및 이 문서 | 작은 수치·해시·실패 분석·데이터 요청 |

D0 core, C1/C2 공용 코드, camera owner, production defaults, CI는 수정하지 않았다.

## 실제 원본 손익

25원본/27대상에는 동일 고정 프로필로 모델을 새로 실행했다. native bbox/confidence가
ROUND3와 모두 같았다. 전체 255장에서는 이번 완료된 baseline 검출 153개도 ROUND3와
동일함을 확인하고, **255 JPEG를 다시 읽고 해시 검증한 뒤 color core/emit만 적용**했다.
모든 raw 색 153개가 재현됐다. 이 전체 audit를 emitter-on 모델 추론 255회 완료라고
부르지 않는다. 아래 모두 이미 본 탐색 자료이며 독립 test/일반 정확도가 아니다.

| 알려진 raw GREEN 34개 모집단 | before | emit 후 | 해석 |
|---|---:|---:|---|
| 비신호 버스정류장 표지판 3 | GREEN 3 | UNKNOWN 3 | 억제됨 |
| 뒤쪽/잘린 housing 28 | GREEN 28 | UNKNOWN 28 | 근거 부족 억제; 정답은 여전히 UNREADABLE |
| 다른 crossing 실제 GREEN 3 | GREEN 3 | UNKNOWN 3 | 실제 positive 3개 전부 손실 |

| 기존 라벨 27대상(25원본) | before | emit 후 |
|---|---|---|
| GREEN 3 | GREEN 1, UNKNOWN 2 | UNKNOWN 3 |
| RED 15 | RED 8, UNKNOWN 6, AMBIGUOUS 1 | UNKNOWN 15 |
| UNREADABLE 4 | UNKNOWN 4 | UNKNOWN 4 |
| OTHER_LIGHT 1 | UNKNOWN 1 | UNKNOWN 1 |
| NO_LIGHT 4 | UNKNOWN 4 | UNKNOWN 4 |

GREEN 3대상의 검출은 여전히 1개, RED 15대상의 검출은 여전히 15개다. 새 손실은
검출 변화가 아니라 emit 거부다. 두 표의 GREEN 모집단을 합치지 않는다.
전체 bbox 153개는 raw RED84/GREEN34/AMBIGUOUS6/UNKNOWN29 → UNKNOWN153이다.
전체 GT가 없으므로 RED84가 모두 실제 RED라는 주장도 하지 않는다.

실패는 작은 chromatic 부분의 밝기/주변 대비가 발광부 전체를 대표한다는 가정에 있다.
예를 들어 기존에 회복한 `preview-2` GREEN은 성분 V112.5, ring61, 대비51.5로
160/60 기준을 못 넘는다. 실제 다른 crossing GREEN(sample51/68/222)의 성분 V는
64~89, 대비6~38이고 표지판(sample223/224/226)의 성분 V69.5~90과 겹친다.
RED `preview-11`은 대비92와 dark ring .910인데 V138 때문에 거부된다.
`v3-117`의 빨간 성분은 V132지만 ring164(대비 -32)다. 밝은 중심의 chroma가 빠지고
상대적으로 어두운 색 테두리가 mask에 남는 경우를 이 후보가 처리하지 못한다.
housing 28개 중 13개는 프레임 잘림으로, 나머지는 성분 경계/형태/밝기 등으로 거부됐다.

따라서 현재 자료에 맞춰 밝기 기준만 낮추지 않는다. 다음 단계는 전면/후면/표지판 라벨과
노출 metadata를 갖춘 독립 recording에서 구분 가능성을 확인하는 것이다. 그 증거로
전면/발광부를 구분하는 학습 모델이 필요한지, 노출 영향이 큰지 결정한다. 기존 모델이
잘못됐거나 노출 조정만으로 해결된다고 단정하지 않는다. 실제 노출 설정은 변경하지 않았다.

## 측정한 시간과 제외한 비교

아래는 로컬 CPU 측정이며 Jetson 수치가 아니다. 각 분위수는 nearest rank다.
모델 단계는 Ultralytics가 보고한 4개 view의 합이다. cold 첫 추론도 포함했다.

| 원본 처리 단계 | n | p50 / p95 / max (ms) |
|---|---:|---:|
| 25원본 모델 전처리 | 25 | 3.220 / 5.882 / 11.194 |
| 25원본 모델 추론 | 25 | 112.180 / 157.711 / 282.817 |
| 25원본 모델 후처리 | 25 | 2.639 / 3.240 / 3.529 |
| 25원본 emit 검사(후보 없는 이미지 포함) | 25 | 0.013 / 0.393 / 0.733 |
| 전체 audit JPEG decode | 255 | 2.378 / 2.933 / 4.134 |
| 전체 audit 기존 color core/bbox | 153 | 0.694 / 1.524 / 70.839 |
| 전체 audit emit/bbox | 153 | 0.174 / 0.355 / 0.985 |
| 전체 audit emit/frame(141장 후보 없음 포함) | 255 | 0 / 0.374 / 1.135 |

25원본 모델 호출 전체 mean/p95/max는 133.503/184.793/298.902ms, setup은827.292ms다.
서로 다른 단계 분위수를 더해 전체 latency라고 하지 않는다. cached-bbox audit에
queue/source age를 새로 만들어 붙이지 않았다.

wall-clock workload는 baseline이 끝나기 전에 제가 후보 실행을 시작해 일부가 겹쳤다.
baseline은 255장 완료(exit0), 겹친 후보는 기록된 8장 뒤 **자기 프로세스만 중단**했다
(exit143). partial 로그도 보존했다. 아래는 실제 관측값이지만 격리된 A/B 성능 비교나
emit-on 전체 throughput 근거로 사용하지 않는다. baseline도 겹치기 전부터 느렸다.

| wall-clock 단계 | baseline 255장 p50 / p95 / max (s) | 중단한 후보 8장 p50 / p95 / max (s) |
|---|---:|---:|
| 모델 전처리 | .00759 / .03243 / .07494 | .05702 / .06501 / .06501 |
| 모델 추론 | .47852 / 3.18056 / 12.50204 | 10.20563 / 11.25521 / 11.25521 |
| 모델 후처리 | .00355 / .04281 / .11281 | .08932 / .11776 / .11776 |
| emit/frame | 0 / 0 / 0 | .000242 / .001263 / .001263 |
| pipeline | .49894 / 3.27129 / 12.64483 | 10.36283 / 12.78059 / 12.78059 |
| queue residence | 203.65075 / 217.01421 / 217.93981 | 29.63375 / 70.73565 / 70.73565 |
| source/receipt age | 204.25398 / 217.20965 / 218.13528 | 39.99653 / 81.16539 / 81.16539 |

baseline 실행 총260.455초, 후보 프레임114/box153, SOURCE_STALE와 RECEIPT_EXPIRED 각255,
stable UNKNOWN255다. freshness가 association을 끊어 선택 ROI는0이다. 이는 raw 검출
실패율이 아니다. replay summary의 PASS는 실행 완료이며 정확도/실시간 PASS가 아니다.
기존 ROUND3의 p95약235ms/max492ms/stale26장 기록도 JSON에 그대로 별도 보존했다.
이번 emit 결과가 실패하여 전체 workload를 다시 반복하지 않았다. TTL 완화는 없다.

## 표시·시간·C1/C2 인계

`detection-only → associated → stable` 경계는 유지한다. raw와 emit 결과를 별도로
표시하고 transient detector index를 실제 signal identity로 쓰지 않는다. 합성 밝은
원형 성분이 통과해도 crossing/전면 검증 flag를 올리지 않는다. 실제 stable GREEN은
미검증이며 이번 검사는 실장비 관측·실이동의 증거가 아니다.

옵션 전체 descriptor를 기존 `inference_settings_sha256`에 포함했다. 별도 emit hash는
추가하지 않는다. 옵션 off의 기존 tile hash는
`233c4de80d698728e98e5f015ade05b01528a4ba45ce7c6fd7b9e74b352008b7`, 옵션 on은
`9e5f1496f6fcd4772c88d8b4c3ac64ddb2efb60ebd4ca8fca0f965bd31b05b9c`다.
프로필이 바뀌면 기존 GREEN/association evidence를 재사용하지 않는 회귀를 통과했다.
`context.emitter_profile`, `selected_emitter_validation`, `raw_state_before_emitter`,
`emitter_validation_wall_s`와 각 free box의 결과/소요 시간을 추가했다.

**최신 소스에서 이미 해결된 receipt 계약을 다시 요청하지 않는다.** 확인한 C1
`85c5b6b85ca85e74503876b075e5ceba92dd4565`의 `CompetitionIngress.join`은
frame/context identity를 검증하고 `signal_fragment(...received_s=frame.received_s)`를
호출한다. C2 `8a58370be8562a8f40377ab659ee3f7776fe5200`의 `join_signal`은 최초 수신·
최초 source age·완료 시각 일관성과 identity를 검사한다. 이 의미는 변경하지 않았다.
C1의 1,200 tick/중복 관측 endurance 코드와
[해당 SHA CI 성공 run 40164585569](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164585569)을
읽어 확인했다. C4에서 설치·공통 fixture·Nav2·1차 통합을 재실행하지 않았다.

C1은 아직 이전 C4 `380800c` 계열을 통합한 상태다. 향후 새 search/emit 설정을 검토해
채택할 경우 C1 owner/binding과 C2 `SignalBinding`에 **동일 combined settings hash**를
pin하고 observation과 대조해야 한다. 현재 C4 내부 hash reset과 외부 trusted binding
검사는 서로 다른 경계다. 이 미채택 후보의 production 활성화 요청이 아니다.
증분 통합은 C1 소유이고 C4가 다른 역할 파일/브랜치를 수정하거나 병합하지 않았다.

## 연속 원본과 남은 한 가지 작업

기존 v3 원래 timestamp는 `2026-09-11T06:15:51.219Z`~`06:16:43.019Z`, 255장/51.8초다.
간격 min194ms/max801ms, 250ms 초과 gap2개다. 확인한 실제 GREEN sample51/68/222는
시작 후11.0/14.4/45.2초다. 움직이는 카메라와 다른 crossing이 섞여 동일 대상의
RED→GREEN→RED 연속 전환이 검증되지 않았다. preview14장은 7개 세션의 paired-camera
중간 사진으로 연속 입력이 아니다. crosswalk249장은 49.6초의 crosswalk 라벨 입력이며
검증된 신호 target 전환 라벨이 없다. 미검토 구간 어디에도 전환이 없다는 주장은 아니다.

**INPUT_REQUIRED:** 기존 owner가 제공하는 한 관측 창의 동일 대상 RED→GREEN→RED 원본과
전면/후면/옆 crossing/표지판/가림/반사 라벨, 원래 source 시간·sequence·해상도·가능한
exposure/gain/WB/settling 값을 확보해 recording 단위로 독립 검토한다. 미제공 값은 null.
이것이 남은 한 가지 작업이다. [데이터 요청](../../../mission-competition/traffic-input/EMITTER_DATA_REQUEST.md)에
사람이 검토할 프레임·라벨 행·split 기준을 명시했다. 기존 C1 owner→Frame/TrafficWorker
경계에 맞춰 인계하며 별도 camera open이나 capture script를 만들지 않았다.

## 실제 검사와 재현

기존 Python3.12.3/CPU torch2.6.0/Ultralytics8.3.203 환경을 재사용했다. 소스 동결 후
전체 Python **2,781개, 실패0, skip2**(90.159초). skip은 optional rosbags 미설치와
PCD_EDIT_NODE 미지정이다. C4 전용90개 skip0, 새 emitter 회귀9개 포함이다.
JS **660개 pass**, frontend syntax104모듈, Ruff pass, 설정된 mypy4파일 pass,
tracked-source secrets scan 및 git diff check pass. 전체 suite에는 최종 코드가 포함된다.

```sh
PY=../c4-venv/bin/python
export YOLO_CONFIG_DIR=../ultralytics-settings MPLCONFIGDIR=../mpl
$PY -m robot_dashboard.competition_traffic.experiments \
  --input-root .. --labels docs/mission-competition/traffic-input/real-labels.json \
  --config ../owner-v3-config.json --model /home/chosun/Desktop/yolov8n.pt \
  --output ../round4/labels --emitter-profile enclosed-chroma-v1 --acknowledge-trusted-pickle
$PY -m robot_dashboard.competition_traffic.replay \
  --input ../jetson-v3/frames.jsonl --output ../round4/v3-before-wall \
  --config ../owner-v3-config.json --model /home/chosun/Desktop/yolov8n.pt \
  --fps 5 --clock-mode wall-clock --inference-profile upper-overlap640 \
  --no-image-artifacts --acknowledge-trusted-pickle
# Candidate attempt used another output and --emitter-profile enclosed-chroma-v1;
# it was stopped after 8 records, not a completed whole-session replay.
$PY -m unittest discover -s tests/competition_traffic -t tests -v
$PY -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
$PY -m ruff check robot_dashboard scripts tests/competition_traffic
$PY -m mypy --config-file mypy.ini
$PY scripts/check_repository_secrets.py
```

원본·가중치·full private outputs는 로컬에 보존하고 Git에는 코드·작은 수치·해시만 남겼다.
위 출력 디렉터리는 보존 대상이며 재실행 시 새 경로를 사용한다.
실제 저장 RGB 검사와 합성 계약 회귀를 구분한다. 실제 Nav2+가상 센서 재실행, 실장비 관측,
실이동, 완전한 emit-on 255-frame workload, 독립 holdout 정확도 시험은 이번에 미실시했다.
main 변경·PR·로봇 접속·서비스 변경·배포는 없다.
