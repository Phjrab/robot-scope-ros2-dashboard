# C4 — 기존 모델·원본 RGB replay와 관측 입력 연결

작성: 2026-10-24 KST. 이 제출은 검토용이며 통합 승인 또는 실주행 검증이 아니다.

## A. 기준과 범위

- 역할/브랜치: C4 / `review/20261024-c4-traffic-replay`.
- 독립 일반 clone에서 작업했다. 다른 채팅 checkout을 수정하지 않았다.
- 실제 작업 기준: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- 시작 시 원격 main도 동일했다. 제출 직전 확인 main은 `5d78fcb7c7589134a533d6dc0ddd09995f9163f9`다.
- 그 사이 `ace55b0` 및 병합 커밋의 관측 세션 JS·E2E·문서 변경이 추가되었다. 읽기 전용 비교만 했으며 이 C4 브랜치로 병합하지 않았다.
- C4 변경을 main에 올린 적 없다. AGENTS 자체도 변경하지 않았다.
- 검증 대상 구현 커밋: `361186719456c4a61064bf68b56ec7b1409be019`.
- 본 REVIEW만 추가하는 최종 문서 커밋/제출 HEAD는 채팅 최종 응답에 기록한다. 구현 SHA와 구분한다.
- 새 파일만 추가한다. 삭제/이동/바이너리 변경은 없다.

변경 파일:

```text
robot_dashboard/competition_traffic/__init__.py
robot_dashboard/competition_traffic/artifacts.py
robot_dashboard/competition_traffic/config.py
robot_dashboard/competition_traffic/frames.py
robot_dashboard/competition_traffic/model.py
robot_dashboard/competition_traffic/pipeline.py
robot_dashboard/competition_traffic/projection.py
robot_dashboard/competition_traffic/replay.py
robot_dashboard/competition_traffic/replay_input.py
robot_dashboard/competition_traffic/requirements-replay.txt
tests/competition_traffic/__init__.py
tests/competition_traffic/helpers.py
tests/competition_traffic/optional_deps.py
tests/competition_traffic/test_pipeline.py
tests/competition_traffic/test_replay.py
docs/mission-competition/traffic-input/README.md
docs/mission-competition/traffic-input/owner-model-example.json
docs/mission-competition/traffic-input/real-replay-summary.json
docs/mission-competition/traffic-input/input-hashes.sha256
docs/parallel-review/20261024/C4/REVIEW.md
```

기존 VM replay는 기록된 ROI/metadata 입력 중심이고 실제 YOLO를 자동 연결하지 않았다.
새 CLI는 명시한 로컬 가중치와 원본 image/directory/video/JSONL을 연결하고,
기존 detector/color/filter를 재사용하여 원본 ROI·mask·색·품질·출처 로그를 남긴다.
공용 runtime/API/UI, camera owner, evidence schema, 기존 VM 소스는 그대로다.

## B. 구현 및 검토 지점

- `OwnerModel`: 체크섬·사용자 출처·명시적 pickle 신뢰 확인·loader pin·실제 model.names와 class-map 일치 검사. 외부 가중치를 내려받지 않는다. Ultralytics offline/autoinstall-off를 명시적 생성 시 설정한다.
- `Frame`/`from_owner_jpeg`: 기존 owner가 이미 취득한 bytes만 받는 경계. timestamp domain/age/epoch/sequence를 추측하지 않는다.
- `TrafficPipeline`: VM `LocalUltralytics`, `Association`, `classify_roi`, `TemporalFilter`를 사용한다. 이 기준에는 문서의 OptionalYoloAdapter라는 이름의 클래스가 없다.
- native xyxy 이중 역변환 방지, letterbox padding/잘린 ROI 차단, source age와 receiver latency·gap 구분, 모델 추론 시간 포함, duplicate/out-of-order/retired epoch 차단.
- `current_state`는 새로운 stamp/sequence를 만들지 않는 watchdog이다. stale GREEN을 새 관측으로 재발행하지 않는다.
- `signal_fragment`는 기존 canonical evidence의 신호 필드 부분집합이다. 완전한 Evidence를 합성하지 않으며 offline/미검증 binding/TTL 초과를 거부한다. 앞발·물리 정지·자세·경로 clear 등은 별도 C2 evidence가 필요하다.
- `save_images`: 원본 decoded PNG / native crop / 처리 color mask를 구분한다. 원본 JPEG SHA를 따로 보존한다. CLAHE 분기의 pixel 반환은 기존 core에 없어 enhanced_state/metrics만 저장하며 가짜 전처리 이미지를 만들지 않는다.
- 오프라인 출력에도 `departure_authorized=false`, `complete_mission_evidence=false`를 명시한다.

C1 연결 제안은 [traffic-input/README](../../../mission-competition/traffic-input/README.md)에 상세히 적었다.
기존 `robot_dashboard/ros/cameras.py::snapshots`와 `camera_snapshot_locked`,
`dataset_capture.py`의 소유권을 유지하고 검증된 source clock/epoch/sequence를 전달해야 한다.
frame 처리 work queue와 private image-handle registry는 C1 후속 작업이다.
C2는 source의 첫 receiver arrival을 유지해야 하며 polling 때 TTL을 갱신해서는 안 된다.
source signal/crossing, mission owner/run/step/goal generation을 검증한 뒤 독립 발·정지 evidence와 합쳐야 한다.
VM 0.25초 TTL과 fixture executor 0.5초 evidence gap은 통합 전에 별도로 검토해야 한다.

알려진 한계:

- binding은 실제 heading/신호/횡단구역과 보정되어야 한다. 예제의 고정 ROI는 검토용이며 `verified=false`다.
- detector 인덱스는 장기 track ID가 아니다. 다중 후보는 추정 선택하지 않는다.
- 동일 JPEG hash는 보수적으로 중복 처리한다. 완전히 같은 연속 프레임도 억제될 수 있다.
- replay 보호 상태는 pipeline 인스턴스의 메모리 범위다. 재시작 시 새로운 producer epoch 및 C2의 지속적 재전송 보호가 필요하다.
- 실제 raw source age/clock 검증, 장기 tracking, camera mount, native registration, Jetson 성능은 미검증이다.
- whole scene의 color/밝기를 바꿔 GREEN을 만들지 않았다. VM 품질/시간 임계값도 변경하지 않았다.

## C. 실제 입력 및 검증

### 실제 입력

사용자가 제공한 `/home/chosun/Desktop/yolov8n.pt`:

- 6,549,796 bytes.
- SHA256 `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`.
- pickletools로 내부 선언을 실행 없이 조사한 뒤 사용자가 직접 제공한 파일을 명시적으로 로드했다.
- 실제 로드한 names는 80개, allowlist는 `{9: "traffic light"}`다. RED/GREEN 클래스로 추측하지 않았다.
- checkpoint version은 `8.0.0.dev0`, 성공적으로 시험한 pinned loader는 `8.3.203`이다. 정확한 학습 환경을 복원했다는 주장이 아니다.

첨부 cross_1은 원본 249장 및 횡단보도 라벨이다. 전부 해시·decode 검사했고 신호등 정답으로 사용하지 않았다.
사용자의 추가 승인으로 Jetson 대시보드 **기존 저장 자료 GET만** 조회했다.
SSH, 카메라 취득, capture/export POST, 서비스 재시작, 배포, 제어 명령은 수행하지 않았다.
처음 일반 SSH 금지 문구와 충돌했으므로 사용자에게 확인했고, 저장 사진 읽기 전용 예외를 명시적으로 받았다.

- 신호등 저장 세션 7개(v1 이름 2개 및 v2~v6) 확인.
- 세션별 대표 두 카메라 사진 총 14장: 4장에서 신호 후보 발견. 이는 recall/정확도가 아니다.
- `20260911T061550Z_f1becd2e93b4420ca4e97af7dee09403`, go2_front v3: 255장, 원본 27,004,919 bytes, 캡처 구간 51.8초.
- HTTP sample summary의 captured_at 간격을 상대적 offline timeline으로 보존했다. 원래 source clock이 검증됐다고 주장하지 않았다.
- 프레임 SHA256은 [input-hashes.sha256](../../../mission-competition/traffic-input/input-hashes.sha256), 비민감 수치는 [real-replay-summary.json](../../../mission-competition/traffic-input/real-replay-summary.json)에 있다.
- 255장 decode 오류 0, 모델 후보가 있는 프레임 88, 고정 diagnostic ROI 선택 12.
- raw color: RED 5, AMBIGUOUS 1, UNKNOWN 249. 모두 stable UNKNOWN(association 미검증).
- `DETECTOR_MISSING=241`은 VM의 expected-ROI 불일치도 포함한다. 241장을 모두 모델의 미탐으로 해석하지 않는다.
- 정답 라벨이 없으므로 false GREEN/혼동행렬/recall/정확도는 null. 노출 문제 해결, 실제 정지·출발 허용은 주장하지 않는다.
- 실제 영상과 가중치, 전체 로컬 manifest/ROI/mask/log는 Git에 올리지 않았다. 원격 검토자는 포함된 요약/해시/코드만 확인할 수 있다.

### 실행 환경과 검사

Linux x86_64, Python 3.12.3. 작업 전용 venv의 CPU torch 2.6.0+cpu,
torchvision 0.21.0+cpu, Ultralytics 8.3.203, OpenCV 4.10.0, NumPy 1.26.4.
호스트 전역/온보드 패키지는 변경하지 않았다. PyPI 접속 실패 후 같은 버전 패키지를
미러에서 설치했다. 초기 sandbox 전체 suite는 기존 비동기 HTTP fixture에서 정체되어
중단했고, 동일 코드의 sandbox 밖 하드웨어 없는 suite는 완료됐다.
이는 C4 테스트를 제거하거나 timeout을 늘려 PASS를 만든 결과가 아니다.

구현 `361186719456c4a61064bf68b56ec7b1409be019`와 동일한 소스 트리에서:

| 검사 | 명령/결과 |
|---|---|
| 전체 Python | `python -m unittest discover -s tests -v`: 2744개, 2742 PASS / 2 SKIP, 89.416초 |
| C4 전용 | `python -m unittest discover -s tests/competition_traffic -t tests -v`: 53 PASS, 커밋 후에도 재확인 |
| 기존 VM 신호 | `python -m unittest discover -s experiments/competition_vm/traffic_signals/tests -v`: 67 PASS |
| JS | bundled Node로 `node --test tests/*.mjs`: 70개 file-level PASS, FAIL 0 |
| JS syntax | `node scripts/check_frontend_syntax.mjs`: 104 modules PASS |
| Ruff | `python -m ruff check robot_dashboard scripts tests/competition_traffic`: PASS |
| mypy | `python -m mypy --config-file mypy.ini`: 기존 대상 4파일 PASS |
| secret scan | `python scripts/check_repository_secrets.py`: staged 포함 tracked-source PASS |
| diff check | `git diff --cached --check`: PASS |
| 실제 모델/RGB | replay CLI, 255장 RUN/PASS(exit 0); 주행·정확도 판정 아님 |
| 원본 횡단보도 입력 검사 | 249장 decode/hash PASS; 별도 config 없이 dry-run exit 2(INPUT_REQUIRED) 정상 확인 |
| native ROS/Nav2 / 실장비 관측·주행 | NOT_RUN, C4 범위 아님 |
| Browser E2E | NOT_RUN, C4 UI 변경 없음; C1 별도 담당 |

전체 suite의 2 SKIP은 선택적 rosbags 미설치 및 `PCD_EDIT_NODE` 미설정 geometry parity다.
C4 optional deps는 공용 requirements에 추가하지 않았다. 기본 CI에 cv2/jsonschema가 없으면
C4 모듈은 명시적으로 SKIP된다. C1은 별도 replay dependency job을 추가해야 한다.
로컬의 53 PASS를 그러한 원격 skip의 PASS로 표현하지 않는다.

실제 replay 재현 명령(로컬 원본은 Git에 포함되지 않음):

```sh
YOLO_OFFLINE=true YOLO_AUTOINSTALL=false \
YOLO_CONFIG_DIR=/absolute/private/work/yolo-config \
MPLCONFIGDIR=/absolute/private/work/mpl-config \
python -m robot_dashboard.competition_traffic.replay \
  --model /absolute/yolov8n.pt --config /absolute/owner-v3-config.json \
  --input /absolute/jetson-v3/frames.jsonl --fps 5 \
  --output /absolute/new-private-replay-output --acknowledge-trusted-pickle
```

원본별 SHA, 캡처 간격, sidecar 보존 규칙과 config 구조는 README와 예제 파일을 참조한다.
문서 예제는 pickle trust=false이므로 출처를 확인한 로컬 구성에서만 명시적으로 바꿔 사용한다.

## D. 의존성과 통합 참고

- 다른 역할의 브랜치/미완료 코드를 가져오지 않았다. 공통 기준 VM 계약만 읽었다.
- C1 runtime/camera-owner/handle 전달, C2 evidence 결합, D0 반환값 보완과의 브랜치 간 호환성은 NOT_RUN이다.
- 예상 충돌은 새 C4 경로에 한정된다. 공용 schema/API/wiring/CI는 수정하지 않았다.
- 권장 순서: 이 브랜치 검토 → D0 공개 함수/clock contract 확인 → C1에서 owner·image handle 연결 → C2 소유권/세대 및 독립 evidence 결합 → 별도 통합 브랜치 회귀 → 사용자 승인 범위의 반영.
- 새 패키지/전용 tests/docs를 제외하면 rollback되며 로봇 상태나 저장된 원본은 변경되지 않는다.
- `.github/workflows/ci.yml`은 GitHub-hosted test jobs만 포함한다. branch push로 장비 자동 배포하는 workflow는 발견되지 않았다.
- 제출은 이 C4 브랜치만 explicit push한다. PR 생성/병합/자동병합/main push는 없다. 원격 CI의 최종 제출 SHA 기준 실제 상태는 최종 응답에서 따로 보고한다.
