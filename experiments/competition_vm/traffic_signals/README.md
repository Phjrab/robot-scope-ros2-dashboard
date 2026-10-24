# Traffic signals: VM-only prototype

이 디렉터리는 생산 제어 코드와 분리된 실험입니다. 로봇, 카메라, Jetson, Mac에 접속하지 않았으며 속도 명령을 발행하지 않습니다. 실제 YOLO 가중치와 RGB 자료가 없어 실물 인식 검증은 INPUT_REQUIRED입니다. 합성 결과는 실제 로봇 성능이 아닙니다.

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
