# 카메라 데이터셋 수집과 AI 모델 배포

Robot Scope의 데이터셋 캡처는 브라우저 화면 캡처와 별개입니다. 대시보드 서버가
Go2 전면 카메라, RealSense 컬러 카메라 또는 두 카메라를 직접 구독하고 대시보드가
실행되는 호스트의 고정 디렉터리에 JPEG와 메타데이터를 저장합니다. Sensors 화면을
벗어나 Controls에서 주행하거나 브라우저 탭이 백그라운드로 이동해도 수집은 계속됩니다.

## 수집 순서

1. **Sensors → Dataset Capture**에서 `GO2`, `REALSENSE`, `BOTH` 중 하나를 고릅니다.
2. 기본 1 Hz 또는 0.2–5 Hz 범위의 저장률과 선택적 세션 표시 이름을 정합니다.
3. `START SERVER CAPTURE`를 누르고 상태가 `CAPTURING`인지 확인합니다.
4. Controls 또는 Navigation으로 이동해 로봇을 주행합니다. 상단의 빨간
   `SERVER CAPTURE` 표시가 유지되는지 확인합니다.
5. 수집이 끝나면 `STOP & FINALIZE`를 눌러 manifest와 마지막 샘플을 마무리합니다.
6. `웹에서 폴더 열기`에서 세션을 고르고, 페이지당 최대 24개 샘플을
   `NEWEST`·`NEWER`·`OLDER`로 이동하며 JPEG 전체를 확인합니다.

Safari나 다른 원격 브라우저는 Jetson의 Nautilus/Finder 폴더를 `file://`로 직접 열 수
없습니다. 이 버튼은 같은 대시보드 안의 안전한 웹 갤러리를 엽니다. 갤러리는
페이지당 24개 샘플로 제한하여 원격 Safari의 메모리와 Wi-Fi 대역폭을 보호하며,
변경 없는 페이지는 목록 polling 때 다시 렌더링하거나 JPEG를 다시 요청하지 않습니다.
화면에는 실제 서버 경로도 읽기 전용으로 표시되므로 SSH나 로컬 터미널에서는 그
경로를 그대로 사용할 수 있습니다.

## 저장 계약

기본 저장 루트는 프로젝트의 `runtime/datasets`이고 Git에서 제외됩니다. 다른 절대
경로를 쓸 때만 populated `robot-scope.env`에 다음을 설정합니다.

~~~text
ROBOT_SCOPE_DATASET_DIR=/absolute/path/to/robot-scope-datasets
~~~

Custom 경로를 Robot Scope checkout 안에 지정하면 기본 `/runtime/` Git ignore에
포함되지 않을 수 있습니다. 가능하면 checkout 밖의 접근 제한 경로를 사용하고,
checkout 안에 두어야 한다면 해당 경로를 `.gitignore`에 명시적으로 추가합니다.

HTTP 요청은 경로나 파일명을 받지 않습니다. 서버가 세션 ID와 샘플 번호를 만들며,
각 샘플은 같은 파일시스템의 임시 디렉터리에 완성한 뒤 원자적으로 게시합니다. 대략적인
구조는 다음과 같습니다.

~~~text
runtime/datasets/
└── sessions/<session-id>/
    ├── manifest.json
    └── samples/00000001/
        ├── go2_front.jpg          # 선택한 경우
        ├── realsense_color.jpg    # 선택한 경우
        └── metadata.json
~~~

두 카메라를 선택하면 대시보드 호스트에서 관측한 시각이 가까운 두 프레임만 한 샘플로
묶습니다. 이는 하드웨어 트리거 동기화가 아니며 manifest에도 해당 사실을 기록합니다.
디스크가 느리거나 프레임이 오래됐거나 중복이면 샘플을 무한히 쌓지 않고 drop counter를
올립니다. 수집 중에는 대시보드 서비스 재시작/종료가 차단되므로 먼저 정상적으로 수집을
중지해야 합니다.

## 저장 한도와 fail-closed 조건

기본 운영 한도는 다음과 같으며 Dataset Capture 상태 화면에서 세션 한도와
파일시스템 여유 공간 기준을 확인할 수 있습니다.

- 세션당 저장 한도: 20 GiB
- 파일시스템 최소 여유 공간: 5 GiB
- JPEG 하나의 최대 크기: 4 MiB
- 시작 후 fresh frame 대기: 10초
- stale frame 기준: 2초, 두 카메라 host timestamp 최대 차이: 250 ms

세션 한도를 넘거나 5 GiB 여유 공간을 보장할 수 없고, JPEG·freshness·pairing
검사를 통과하지 못하면 수집은 불완전한 샘플을 게시하지 않고 fail-closed로
중지합니다. 화면의 오류와 drop counter를 확인한 뒤 저장 공간과 카메라 신호를
해결하고 새 세션을 시작합니다.

## 라벨링과 학습

저장 직후의 JPEG는 **원본 수집 데이터**이며 지도학습 라벨은 아직 없습니다.

- YOLO detection 학습 전에는 각 이미지에 class와 bounding box를 작성해 YOLO 또는
  COCO 형식으로 내보내야 합니다.
- UFLD 학습 전에는 lane point/curve annotation과 train/validation split을 해당
  구현이 기대하는 형식으로 만들어야 합니다.
- 세션 표시 이름은 이미지 라벨이 아니며 학습 정답으로 사용되지 않습니다.

따라서 “바로 학습에 활용”은 원본 JPEG와 재현 가능한 manifest를 즉시 라벨링 파이프라인에
투입할 수 있다는 뜻입니다. 라벨 없이 supervised YOLO/UFLD 학습을 시작해서는 안 됩니다.

## 로봇 탑재 Jetson의 AI 적합성

2026-08-12 읽기 전용 실측 환경은 다음과 같습니다.

| 항목 | 실측 |
|---|---|
| 모듈 | Jetson Orin NX 16GB, P3767-0000 / P3768-0000 |
| OS | Ubuntu 20.04.5 aarch64, kernel 5.10.104-tegra |
| JetPack | 5.1.1 / L4T R35.3.1 |
| 가속 스택 | CUDA 11.4.315, cuDNN 8.6.0, TensorRT 8.5.2.2 |
| 전력/CPU | 15W mode ID 2, CPU 4/8 online |
| 메모리 | 16GB급 통합 메모리, 약 12GB 가용 |
| 저장공간 | NVMe, 약 386GB 여유 |
| 현재 AI Python | Python 3.8.10, PyTorch/torchvision/Ultralytics 미설치 |

판정은 다음과 같습니다.

- **YOLO 추론:** 조건부 적합. JetPack 5.1.1용 NVIDIA aarch64 PyTorch wheel을 별도
  가상환경에 설치하거나, 대상 Jetson에서 FP16 TensorRT engine을 생성해 nano 모델부터
  검증합니다.
- **UFLD 추론:** ONNX를 외부 학습 장비에서 만든 뒤 이 Jetson의 TensorRT 8.5에서
  engine을 다시 생성·검증하는 방식이 현실적입니다. 원본 UFLD 저장소의 오래된 Python/
  CUDA 설치 절차를 시스템 Python에 그대로 적용하지 않습니다.
- **학습:** 소형 YOLO fine-tune은 기술적으로 가능하지만 RealSense/XT16 relay와 자원을
  공유하는 15W 운영 장비에서는 권장하지 않습니다. UFLD/UFLDv2 학습도 외부 x86 GPU
  워크스테이션에서 수행하고 Jetson은 추론만 담당하는 구성을 권장합니다.
- 공개 벤치마크를 맞추기 위해 `nvpmodel`이나 `jetson_clocks`를 자동 변경하지 않습니다.
  전원·발열·냉각을 확인하고 별도 승인한 경우에만 검토합니다.

최종 배포 전에는 YOLO와 UFLD를 각각 단독으로 검증한 뒤 동시 실행하며 카메라 15fps,
end-to-end 지연, RAM/swap, 온도/throttling, XT16 drop counter를 함께 측정합니다.

공식 근거:

- [NVIDIA JetPack 5.1.1](https://developer.nvidia.com/embedded/jetpack-sdk-511)
- [NVIDIA PyTorch for Jetson 설치](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/index.html)
- [Ultralytics NVIDIA Jetson 가이드](https://docs.ultralytics.com/guides/nvidia-jetson/)
- [Ultralytics 현재 Python 의존성](https://github.com/ultralytics/ultralytics/blob/main/pyproject.toml)
- [UFLD 공식 설치 문서](https://github.com/cfzd/Ultra-Fast-Lane-Detection/blob/master/INSTALL.md)
- [UFLDv2 공식 설치 문서](https://github.com/cfzd/Ultra-Fast-Lane-Detection-v2/blob/master/INSTALL.md)
- [UFLDv2 TensorRT 배포 예제](https://github.com/cfzd/Ultra-Fast-Lane-Detection-v2/blob/master/deploy/trt_infer.py)
