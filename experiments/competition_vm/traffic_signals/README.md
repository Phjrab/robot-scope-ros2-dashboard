# Traffic signals: VM-only prototype

이 디렉터리는 생산 제어 코드와 분리된 실험입니다. 로봇, 카메라, Jetson, Mac에 접속하지 않았으며 속도 명령을 발행하지 않습니다. 실제 YOLO 가중치와 RGB 자료가 없어 실물 인식 검증은 INPUT_REQUIRED입니다. 합성 결과는 실제 로봇 성능이 아닙니다.

## D0 현재 미션 연결 진입점 (2026-10-24)

새 오프라인 미션 연결은 `lifecycle.py`의 `TrafficLifecycle`과 수정된 `../integration/adapter.py` / strict smoke를 함께 사용합니다. 접근 terminal/cancel ACK, HOLD 요청/ACK, 관측 기반 2초 정지, 새 exit goal/ACK, 실제 출발 관측을 분리합니다. `StopGoFSM`은 과거 replay용 zone/dwell core이며 APPROACH에 직접 연결하면 자기 HOLD가 생기므로 단독 미션 연결에 사용하지 마십시오.

새 결과와 계약 차이는 [revisions/d0-20261024/HANDOFF.md](revisions/d0-20261024/HANDOFF.md)에 있습니다. 기존 `results/`와 `VM_TO_CODEX_HANDOFF.md`는 원래 공개 시점의 이력으로 보존합니다. 수정된 경로도 SYNTHETIC_IN_PROCESS 검증일 뿐 native ROS/실장비 연결이 아닙니다.

## 재현

Python 3.12 환경에서 requirements.txt를 별도 가상환경에 설치한 뒤 이 디렉터리에서 실행합니다.

```sh
python -m unittest discover -s tests -v
python replay.py --synthetic --output results
python replay.py --manifest /path/to/local/manifest.jsonl --output recorded_results
```

검증 당시 임시 의존성 경로는 /tmp/traffic-deps였으며 PYTHONPATH로 적용했습니다. requirements.txt는 이 실행의 버전을 기록합니다. 새 환경의 wheel 지원은 별도로 확인하십시오.

- core.py: OpenCV 품질 판정, 색 분류, 시간 필터, 정지/출발 의도 FSM
- detector.py: 명시적 로컬 모델 로더, checksum 및 출처 검사, 기대 ROI 기반 연관
- stop_zone.py: 사각형 후보와 두 발의 다각형 포함 판정. 실제 발 검출기는 아닙니다.
- replay.py: 합성 또는 기록된 ROI/관측 metadata replay. YOLO 추론을 자동 연결하지 않습니다.
- ros_wrapper.py: 선택적 localhost/domain 173 VM wrapper. native ROS 미실행. Twist publisher 없음.
- config/: 임시 설계 설정과 arena 연결. 실제 보정값 아님.
- results/: 실행 로그, 판정 JSONL, GIF, 비교 이미지, 지표.

통합 주의사항과 미검증 영역은 VM_TO_CODEX_HANDOFF.md를 먼저 읽으십시오. 생산 시스템에 자동 적용하지 마십시오.
