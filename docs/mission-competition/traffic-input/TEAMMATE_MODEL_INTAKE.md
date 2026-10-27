# C4 팀원 YOLO 모델 인수·관측 통합 후보

2026-10-27 KST. 검사한 구현 SHA는 `3f9f2ba33021f18418bb9bf2ab379f972d16f029`다.
제출 브랜치는 `review/20261024-c4-traffic-replay`이며, 이 보고서와 결과 JSON은 후속 문서 커밋이다.
main 병합·PR·장비 접속·배포·카메라 취득·이동은 수행하지 않았다.

**실제 best.pt 로드와 C4→현재 main의 C1 worker/ingress 연결을 완료했다.**
원래 25원본/27대상 및 255프레임은 이 Mac 작업 환경에 없어, 해당 RGB의 정확도·지연 비교는
NOT_RUN이다. 학습 시각화로 실행한 실제 추론은 입출력 smoke로만 별도 기록한다.
과노출/반사의 현장 성능이 개선됐다고 주장하지 않는다.

## 확인한 기준과 보존한 기존 작업

| 대상 | 확인한 SHA / 결과 |
|---|---|
| 최신 origin/main | `d6e3fe9675f31e436f5236b390e36e188934f473` |
| 기존 C4 HEAD | `bf0436687a0a9dbab1ff7ac370f1bc0de42d07ad` |
| 팀원 저장소 HEAD / 다운로드 고정 commit | `fe523233aeca933942b81df5d305777db2bb6c5d` |
| 이번 코드·검사 source | `3f9f2ba33021f18418bb9bf2ab379f972d16f029` |

원격 fetch와 Git 변경사항, ROUND3/ROUND4 및 main의 C1 ROUND3/4/5를 확인했다.
로컬 main 및 I1 디렉터리의 미커밋 변경은 보존하고 기존 C4 원격 브랜치에서 별도 worktree를 열었다.
이번 diff는 C4 모델/config/pipeline, C4 전용 비교·검사·문서에 한정된다.

- ROUND3 일반 YOLO/상단 타일은 GREEN 3대상 중 검출·raw GREEN 1개를 회복했지만,
  전체 raw GREEN 34개에는 비신호 표지판 3개와 후면/잘린 housing 28개가 포함됐다.
- ROUND4 `enclosed-chroma-v1`은 153 box 전부 UNKNOWN으로 만들고 실제 GREEN/RED도 잃었다.
  **기본 OFF / NOT_ADOPTED를 유지**했다. 이번 후보는 그 필터의 재조정이 아니다.
- main에는 최초 receipt/설정 binding, `TrafficWorker`의 단일 실행+최신 pending,
  `ReplayReview`의 exhaustive/latest-wall-clock 분리가 병합돼 있다.
  worker/replay/ingress/C2/FSM/D0 core/UI는 수정하지 않았다. main export 위에 이번 C4 package만
  읽기 경로로 얹어 실제 worker와 C1/C2 회귀를 검사했다.

## 실제 모델 인수

출처: [팀원 best.pt](https://github.com/hjj021717-netizen/traffic-light-detector/blob/fe523233aeca933942b81df5d305777db2bb6c5d/best.pt).
사적 로컬 경로:
`/Users/hajoonpark/자율설계/c4-private-20261027/upstream/best.pt`.

| 항목 | 실측 |
|---|---|
| bytes | 5,460,506 |
| SHA-256 | `3bae0ae05522fe92cbda850b4d604e9babaa34ebbd130fd69cd9c7e61a9e44ec` |
| Git blob | `3aece35e93131e0214680614480c3d8e8a0982d7` (`git hash-object`로도 대조) |
| root / training_results/weights/best.pt | 고정 commit tree에서 같은 blob·같은 크기 |
| 실제 names | `0: traffic_light_green`, `1: traffic_light_red`, `2: crosswalk` |
| task / architecture | detect / `yolo11n.yaml`, scale n, nc 3, parameters 2,590,425 |
| checkpoint metadata | version `8.4.148`, date `2026-09-12T04:09:55.855555+00:00`, epoch -1 |
| checkpoint train_args | yolo11n.pt, epochs 50, imgsz 640, batch 16, `traffic_light_final_v3`, cls_remap false |
| 실제 성공 loader | Python 3.13.2, torch 2.10.0, torchvision 0.25.0, Ultralytics 8.4.15 |
| 이미지 환경 / 장치 | NumPy 2.4.2, OpenCV 4.13.0.92 / macOS arm64 CPU |

`data.yaml`, `train.py`, `training_results/args.yaml`과 실제 metadata가 일치한다.
checkpoint epoch -1은 inference용 저장 상태이므로 best epoch 번호로 해석하지 않는다.
8.4.148은 checkpoint 기록이고 8.4.15는 이번에 성공한 로더다. 학습 환경 전체 재현이나
Jetson 호환성을 입증한 것이 아니다. 기존 ROUND3/4의 8.3.203 환경은 변경하지 않았다.
전용 venv는 로컬 시스템의 이미 설치된 torch를 재사용하고 검사 의존성만 별도로 설치했다.

사용자가 지정한 저장소의 파일을 명시적으로 `OwnerModel`→`LocalUltralytics`로 로드했다.
hash 검증과 trusted-pickle acknowledgement를 유지했고, 최초 로드는 제한된 로컬 실행에서 했다.
해시가 pickle 안전성을 증명한다는 주장은 없다. 앱 import 시 모델을 열지 않는다.
`train.py`, `robot_node.py`, `behavior.py`는 읽기만 했다. `/cmd_vel` publisher와 카메라 구독은 사용하지 않았다.

트리는 44개 entry이며 독립 원본 `images/train`, `images/val`은 없고 학습 그림만 있다.
nested gitlink는 실행하지 않았다. 원본 color source는 공개 repo에 복사하지 않고, 명시적으로 승인한
고정 SHA-256 파일만 비교 CLI에서 로드한다. 저장소 license 파일은 확인되지 않았고 checkpoint에는
AGPL-3.0 metadata가 있다. 가중치/외부 코드의 재배포 권한은 별도 확인 대상으로 남긴다.

## 적용한 최소 관측 규칙

[설정 예제](teammate-model-example.json)의 `color_policy: teammate-color-consensus-v1`은 명시적 opt-in이다.
기존 일반 모델 config와 hash는 그대로 유효하다. 새 policy는 allowlist `{0,1}` 및 전체 names
`{0:green,1:red,2:crosswalk}`를 검사한다. ID/name 순서가 다르면 거부하며 class2는 색 루트에서 제외한다.

최종 색은 **모델 색과 유효한 C4 색이 일치할 때만 RED/GREEN**이다. 둘이 충돌하면
AMBIGUOUS + MODEL_COLOR_CONFLICT, 색 품질 불량·근거 부족이면 UNKNOWN이다.
모델 GREEN 단독 또는 `not red`를 GREEN으로 승격하지 않는다. 기존 C4의 chroma/component/clip/blur
검사를 유지하므로 흰색의 손실된 색을 복원했다고 주장하지 않는다.

각 `free_observations`에 class ID/name, detector confidence, native bbox, `model_state`,
`c4_raw_state`, `color_consensus` 및 최종 `raw_state`가 함께 남는다. 선택된 관측에도
`context.selected_model_color`로 원래 클래스와 충돌 사유를 보존한다. RGB/HSV 품질 metrics,
기존 association snapshot, epoch/seq/source stamp/최초 receipt/처리시간은 기존 경로를 유지한다.
Ultralytics native xyxy를 한 번 floor/ceil하고 이중 inverse-letterbox하지 않는다.

모델·정책·C4 color profile은 기존 `inference_settings_sha256`로 식별한다.
예제 config hash는 `1266442c96c6678229bd66888b2e610d7e0b75b26ec7c3464131ea92018236ba`,
inference hash는 `4b40b9c7e5d3df9074e2cae9bd6a5b57a0d974e268cec58d718fd42acb8616ea`다.
conf .25, full640, CPU, rect=True, NMS IoU .7, max_det300, emitter OFF를 사용했다.
provenance/geometry/버전 등 config를 바꾸면 config hash도 다시 고정해야 한다.
C2 기대값을 관측에서 자동 갱신하는 코드는 없다.

## A/B/C 실제 실행 범위

같은 모델의 같은 bbox에서 A는 원래 클래스, B는 기존 C4, C는 팀원 원본 color 함수,
후보는 A+B 합의 규칙이다. 팀원 함수의 RGB/HSV 분기와 보정되지 않은 점수도 별도 저장한다.
crop은 원본 범위·유한값·양의 면적을 확인한 뒤 전달하고, 예외는 UNKNOWN 사유로 기록한다.

### 기존 원본 RGB

| 비교 항목 | A 모델 | B C4 | C 팀원 | 후보 |
|---|---|---|---|---|
| 기존 25원본/27대상 정확도·유지율·UNKNOWN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| 255프레임 실제 저장 replay·지연·drop | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| 기존 표지판/후면 false GREEN 재평가 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

문서에 있는 이전 `/home/chosun/Desktop/yolov8n.pt`, `../jetson-v3/frames.jsonl`,
`../jetson-originals`는 이 Mac의 경로가 아니다. 작업 workspace와 Downloads의 해당 파일명·manifest를
확인했지만 원본이 없었다. 비교 CLI는 27 label 행의 파일 부재/25 unique images를 기록했다.
모델 없는 옛 차단과는 다른 **RGB 원본 위치의 누락**이다. 사용자에게 현재 경로를 문의했고
답변을 받기 전에도 나머지 구현·실제 모델·회귀를 진행했다. 타 계정/로봇 저장소 탐색은 하지 않았다.

### 학습 시각화 입출력 smoke — 정확도 자료 아님

고정 source의 `training_results/train_batch0.jpg` (1920×1920, SHA-256
`c82c468d89ebd932172299fdd269be68c6c344a28d7b31a49790d408d81e4df3`)를 사용했다.
전체 그림 full640은 신호 후보 0개다. 그림의 4×4 layout을 480×480 패널 16개로 나눠
각 패널에 같은 full640을 한 번 적용했다. 모델 bbox나 정답으로 crop을 만들지 않았다.
원본 이미지·독립 평가·카메라 시간으로 취급하지 않았다. 라벨/텍스트 오버레이가 포함돼 있다.

| 같은 신호 bbox 5개 | RED | GREEN | UNKNOWN | AMBIGUOUS |
|---|---:|---:|---:|---:|
| A 모델 원래 클래스 | 3 | 2 | 0 | 0 |
| B 기존 C4 | 3 | 1 | 1 | 0 |
| C 팀원 원본 색 | 3 | 2 | 0 | 0 |
| 후보 A+B | 3 | 1 | 1 | 0 |

59개 non-allowlist(crosswalk) box는 색 분석에서 제외됐다. UNKNOWN 1개도 원래 모델 GREEN과
bbox를 보존한다. 이 5개에 GT 정확도/오검출/유지율을 부여하지 않는다.
검출이 있는 panel13을 C1 worker에 다시 넣어 실제 RED 1/GREEN 1의 class·bbox·최종색 전달과
미검증 입력의 live projection 거부를 확인했다. grid 선택은 smoke이며 새 inference tile profile이 아니다.

### 합성 색 재현 — 실제 모델 예측 아님

[재현 recipe와 결과](teammate-synthetic-comparison.json). 64×64 수동 ROI에서 비교했다.

| 합성 입력 | B 기존 C4 | C 팀원 combined | 후보의 처리 |
|---|---|---|---|
| 검정/흰색/회색 | UNKNOWN | RED | 모델 색과 무관하게 UNKNOWN |
| 낮은 채도 초록/파랑/노랑 | UNKNOWN | GREEN | 모델 색과 무관하게 UNKNOWN |
| 빨강 원 r12 | RED | RED | 모델 RED면 RED, GREEN이면 AMBIGUOUS |
| 초록 원 r12 | GREEN | RED | 모델 GREEN이면 GREEN, RED이면 AMBIGUOUS |
| 초록 원 r24 | GREEN | GREEN | 모델 GREEN이면 GREEN, RED이면 AMBIGUOUS |
| 빨강 원 r1 | UNKNOWN | RED | 모델 색과 무관하게 UNKNOWN |

팀원 HSV가 saturation을 쓰지 않아 무채색의 hue0을 RED로 읽고, 작은 발광부에서는
percentile 동률인 배경까지 밝은 픽셀로 포함하는 현상을 재현했다. RGB 점수는 1을 초과할 수 있다.
초록 대형 원/작은 원을 모두 검사했으며 모든 관측을 UNKNOWN으로 만드는 방식은 채택하지 않았다.
모델과 C4가 함께 잘못 GREEN인 후면·배경은 이 합의 규칙만으로 배제할 수 없다.

## 지연과 검증

초기 blank 1280×720 실제 모델 첫 호출은 77.53ms, setup은 5.645s였다. 최초 호출 한 번의
CPU smoke이며 정확도·실영상 p95·Jetson 지연이 아니다. 모델 보고 stage/실제 wall time은
[결과 JSON](teammate-model-results.json)에 분리했다. static 원본 coverage는 0/25,
replay coverage는 0/255이며 drop/실시간 유지율은 미측정이다.

| 검사 | 결과 |
|---|---|
| C4 전용 최종 회귀 | 105개 PASS, skip0 |
| 현재 main + 이번 C4, 실제 모델 worker/ingress | PASS; 추론 worker thread, 최초 receipt/seq/stamp 보존, live 권한 없음 |
| 같은 main export C1/C2 회귀 | 173개 PASS, skip0; 기존 historical cross checks 포함 |
| 전체 Python 최종 실행 | 2,796개, 실패0, error1, skip3 |
| 전체에서 error인 native registration 검사 단독 재실행 | 1개 PASS (15.759s) |
| JavaScript | 660 PASS, skip0 |
| frontend syntax | 104 modules PASS |
| Ruff / 지정 mypy 4파일 / secrets / diff | PASS |

전체 error1은 변경하지 않은 `test_offline_registration`의 extended native benchmark subprocess
exit1이다. 앞선 전체 실행에서는 같은 검사가 통과했고 마지막 단독 재실행도 통과했다.
실패 실행의 subprocess 상세 metrics는 unittest가 출력하지 않아 원인을 확정하지 않는다.
**전체 suite 단일 실행 PASS라고 보고하지 않는다.** C4 관련 실패는 없다.
skip3은 optional rosbags 미설치와 Linux /proc/fd 전용 2개다.

첫 전체 실행은 macOS `/var` symlink와 sandbox socket 제한으로 실패했다. 실제 경로의
전용 TMPDIR에서 소켓 fixture를 허용하고, `/private/tmp`의 wheel 그룹 상속을 현재 사용자 그룹으로
맞춘 뒤 나머지 환경 실패가 사라졌다. 이 조치는 사적 테스트 임시 폴더에만 적용했다.
소스의 장비/파일 보안 규칙이나 다른 역할의 테스트를 수정하지 않았다.

## 재현 명령과 통합 인계

```sh
C4_PRIVATE=/Users/hajoonpark/자율설계/c4-private-20261027
C4_PY="$C4_PRIVATE/venv/bin/python"
export YOLO_CONFIG_DIR="$C4_PRIVATE/yolo" MPLCONFIGDIR="$C4_PRIVATE/mpl"
export TMPDIR=/private/tmp/c4-tests-20261027
# 저장소 root에서 실행. 아래 input-root에는 실제 기존 원본이 있을 때 그 경로를 지정한다.
"$C4_PY" -m robot_dashboard.competition_traffic.teammate_compare \
  --input-root "$C4_PRIVATE" \
  --labels docs/mission-competition/traffic-input/real-labels.json \
  --config "$C4_PRIVATE/teammate-config.json" --model "$C4_PRIVATE/upstream/best.pt" \
  --upstream-color "$C4_PRIVATE/upstream/color_detector.py" \
  --output "$C4_PRIVATE/label-comparison-new" \
  --acknowledge-trusted-pickle --acknowledge-upstream-source

# source main은 git archive d6e3fe9로 만든 사적 export. worker/ingress는 복사·수정하지 않는다.
C2_CROSS_REQUIRED=1 "$C4_PY" tests/competition_traffic/check_teammate_c1.py \
  --main-source "$C4_PRIVATE/main-source" --model "$C4_PRIVATE/upstream/best.pt" \
  --config "$C4_PRIVATE/teammate-config.json" \
  --image "$C4_PRIVATE/upstream/train_batch0-panel13.png" \
  --image-kind training-visualization --require-signal-detection \
  --output "$C4_PRIVATE/c1-adapter-new.json" --acknowledge-trusted-pickle
# panel13 = train_batch0.jpg[1440:1920,480:960], PNG 무손실 저장. 원본 평가자료가 아니다.

"$C4_PY" -m unittest discover -s tests/competition_traffic -t tests -v
"$C4_PY" -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
"$C4_PY" -m ruff check robot_dashboard scripts tests/competition_traffic
"$C4_PY" -m mypy --config-file mypy.ini
"$C4_PY" scripts/check_repository_secrets.py
git diff --cached --check
```

비교 CLI exit0은 실행 완료를 뜻한다. `STATIC_RGB_NOT_RUN_INPUT_MISSING` 또는
`STATIC_RGB_PARTIAL`은 결과 JSON에서 반드시 별도로 읽어야 한다. 누락을 accuracy PASS로 세지 않는다.
기존 replay CLI도 새 config로 `--observation-mode detection-only`를 사용하면 같은 모델/정책을 적용한다.
원본 확보 후 255장 비교는 기존 C1의 exhaustive/latest 분리와 원래 manifest 시간을 유지한다.

| 인계 수준 | 상태 |
|---|---|
| MODEL_ACQUIRED / MODEL_LOADED / CLASS_MAPPING_VERIFIED | 완료 |
| C1_ADAPTER_TESTED | 실제 모델 호출 및 173 회귀 완료 |
| STATIC_RGB_TESTED | NOT_RUN_INPUT_MISSING; 기존 원본의 현재 경로 필요 |
| TEMPORAL_REAL_NOT_RUN | 실제 동일 신호 RED→GREEN→RED 자료 없음 |
| JETSON_NOT_RUN | CPU 검증만 수행 |
| MOTION_NOT_AUTHORIZED | 관측 후보만 제출 |

**배포 담당이 이어받을 한 가지:** 기존 저장 원본의 위치를 연결해 이 고정 모델/config로
A/B/C를 실행한 뒤, 검토된 source/model/config/inference hash를 owner/binding에 명시적으로
고정하여 관측 모드 후보를 평가한다. 예제 `association.verified=false`를 운영 검증 없이 올리지 않는다.
Jetson 로더/속도, 실제 연속 신호, 발/정지·주행 자격은 그 이후 별도 검증이다.
기존 main에 이번 구현 커밋의 C4 diff만 적용하고 ROUND4 OFF 후보/공통 코드를 통째로 덮어쓰지 않는다.
