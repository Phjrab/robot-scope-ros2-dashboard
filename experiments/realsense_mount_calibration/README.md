# RealSense 장착 pitch 보정 — 오프라인 시제품

로봇을 **앉은 초기 자세에서 정지**시킨 뒤 카메라의 상하 각도만 바꾸어 같은 벽을 촬영하고, 사용자가 선택한 여러 깊이 점으로 **기준 샘플 대비 상대 pitch**를 계산하는 독립 실험입니다.

## 구현 범위와 한계

- 깊이 JSON 불러오기, 깊이 화면의 포인트 선택, 평면 적합, 상대각 비교, 결과 JSON 내보내기
- 합성 데모는 실제 카메라 측정이 아닙니다. 실데이터 결과도 실제 장착 정확도가 검증됐다는 뜻이 아닙니다.
- 로봇 제어·카메라 연결·ROS·VSLAM 실행·TF 반영·장치 flash 쓰기는 구현하지 않습니다.
- 카메라 내부/좌우 stereo 보정과 카메라→몸체 외부파라미터는 별개입니다.
- 이 시제품은 평면 법선의 회전 차이를 사용하며, 높이·translation·전체 6DoF 또는 절대 몸체 pitch를 추정하지 않습니다.
- 앉아 있는 몸통을 수평이라고 가정하지 않습니다. 기준 샘플은 단지 상대각 0입니다. 몸체 기준 절대각에는 실측 기준과 당시 몸체 자세가 필요합니다.
- pitch 외의 운동이 없다는 사용자 확인과 간단한 일관성 검사는 독립적인 운동 검증이 아닙니다. 단일 평면의 법선만으로 모든 운동을 관측할 수 없습니다.
- 브래킷 회전 중심과 광학 중심이 다르면 위치도 변할 수 있습니다. 법선 비교로 얻은 상대각이 translation까지 보정하지 않습니다.
- 실제 VSLAM 벽 중복/궤적 점프가 이 기능만으로 해결된다고 주장하지 않습니다.

## 실행

Python 3.10 이상 권장. 별도 가상환경을 사용합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

브라우저에서 `http://127.0.0.1:8765`를 엽니다. 외부에 공개하는 서버가 아니며 인증·TLS·다중 사용자 저장소는 포함하지 않습니다.

```sh
python -m unittest discover -s tests -v
```

## 사용 순서

1. 합성 데모로 UI를 확인하거나 별도 수집기가 만든 실제 깊이 샘플을 불러옵니다.
2. 로봇 정지, 동일한 벽, pitch만 변경한 조건을 확인합니다. 샘플 사이에 사람·로봇·벽이 움직이지 않아야 합니다.
3. 각 샘플에서 같은 평면 위의 여러 점을 넓게 선택합니다. 한 줄에 모인 점이나 물체 경계·구멍·반사 영역은 피합니다.
4. 기준 샘플을 지정하고 계산합니다. 선택점 수, 적합 잔차, inlier 비율과 경고를 확인합니다.
5. 결과를 JSON으로 내보냅니다. `RELATIVE_ONLY`를 유지하며 운영 TF/VSLAM에 자동 적용하지 않습니다.

## 캡처 데이터 계약

입력은 `samples` 배열을 갖는 JSON입니다. 각 샘플은 다음 필드를 가집니다.

```json
{
  "id": "sample-01",
  "width": 320,
  "height": 240,
  "intrinsics": {"fx": 280, "fy": 280, "cx": 160, "cy": 120},
  "depth_m": [null],
  "points": [],
  "metadata": {
    "serial": "REAL_DEVICE_SERIAL",
    "frame_id": "depth_optical_frame",
    "profile_id": "qualified-rectified-profile",
    "source_timestamp": 1.234,
    "clock_domain": "hardware_clock",
    "rectified": true,
    "synthetic": false,
    "depth_semantics": "optical_z"
  }
}
```

위의 depth_m은 **형식 설명용 축약**이며 실제 샘플은 2~12개, 해상도 최대 640×480, 선택점은 샘플당 6~100개를 지원합니다. 이는 오프라인 시제품의 자원 제한이며 센서 전체 해상도 지원 주장이 아닙니다. 실제 파일에는 width×height개의 행 우선 optical-Z 깊이(m)가 있어야 합니다. 누락값은 null입니다. JSON 배열에 NaN/Infinity를 사용하지 않습니다. API의 정확한 제한·검증은 calibration.py와 테스트를 기준으로 합니다.

- 픽셀·intrinsics·깊이는 같은 rectified pinhole 좌표계를 사용해야 합니다.
- RGB/IR/깊이의 같은 픽셀 번호가 같은 공간점이라고 가정하지 않습니다.
- rectification 여부를 이름만 바꾸지 않습니다. 왜곡된 raw 영상은 올바른 변환 없이 지원하지 않습니다.
- 실데이터에는 source_timestamp와 clock_domain이 필수입니다. frame_id는 모든 샘플에서 같은 광학 좌표계 이름이며 frame_number/sample_id와 다릅니다. frame 번호, 펌웨어, 원본 depth scale, 정렬 방법·원본 calibration 정보를 metadata에 함께 보존하는 것을 권장합니다.
- 좌표: 카메라 optical x=오른쪽, y=아래, z=앞. 정면 법선은 z>0으로 정렬합니다. 상대 pitch는 atan2(-normal_y,normal_z)의 기준 대비 차이이며 양수는 아래를 보는 기울기 증가입니다.
- 이 부호 정의는 로봇의 실제 TF pitch convention에 검증 없이 복사하면 안 됩니다.

## 수집 측 작업과 분리

기존 Isaac ROS stereo VSLAM은 좌우 IR 입력을 사용하며, 조회한 Robot Scope launch에서는 depth/color가 비활성화돼 있었습니다. 깊이 캡처는 기존 단일 카메라 소유권을 공유하는 **별도 보정 모드**로 통합해야 합니다. 이 폴더는 그 모드를 변경하지 않습니다.

## 근거

- [RealSense 픽셀/깊이 deprojection](https://dev.realsenseai.com/docs/projection-in-realsense-sdk-2-0/)
- [RealSense 내부 self calibration과 차이](https://dev.realsenseai.com/docs/intel-realsense-self-calibration-for-d400-series-depth-cameras/)
- [Isaac ROS 3.2 coordinate frames](https://nvidia-isaac-ros.github.io/v/release-3.2/repositories_and_packages/isaac_ros_visual_slam/isaac_ros_visual_slam/index.html#coordinate-frames)
- [Robot Scope 조회 시점 launch](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/e9aefd39f300cfc0778c9fa18bac078bf0d2546f/experiments/isaac_vslam/config/launch_contract.py)

## 선택적 DOM/API smoke 검사

이 검사는 실제 HTTP API와 UI 이벤트 논리를 검사하지만 canvas를 stub 처리하므로 브라우저 시각 검수는 아닙니다. 임시 경로에 jsdom을 설치하고 `NODE_PATH`를 지정해 `node tests/ui_dom_smoke.cjs`를 실행할 수 있습니다. Python 실행 파일은 `PYTHON` 환경 변수로 선택합니다. `VALIDATION.md`의 검증 범위와 한계를 확인하세요.
