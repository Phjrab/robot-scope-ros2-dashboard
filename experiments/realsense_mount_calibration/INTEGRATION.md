# 운영 대시보드 연결 전 인계

이 폴더는 다른 VSLAM 작업과 충돌하지 않는 독립 실험이다. 기존 robot_dashboard 파일·카메라 설정·운영 TF를 변경하지 않는다.

## 다른 Codex 채팅의 역할
- 현재 카메라/ROS 상태를 확인하고, 기존 owner/broker/session lock을 재사용하는 depth 수집 모드 구현
- 영상/depth/CameraInfo 정합과 프로필·타임스탬프·깊이 단위 기록
- 실제 캡처 데이터로 이 시제품의 입력·잔차·부호·반복성을 검증
- 배포·카메라 재시작·서비스 전환은 현재 사용자 허용 범위에서만 수행
- Isaac ROS 업그레이드/RGB-D 전환은 이 기능의 선행조건이 아니며 범위 밖

## 통합 후보 파일 (현재 checkout에서 재확인)
- robot_dashboard/static/features/slam/dashboard.js: 보정 패널
- robot_dashboard/api/routers/slam.py / slam_wiring.py: API와 의존성 조립
- slam_sessions.py: calibration/VSLAM 간 세션 전환과 잠금
- slam_camera.py / slam_managed_scope.py: 기존 카메라 소유권
- slam_ros_runtime.py: source-stamped 캡처

기존 pose_precision.py는 독립 외부파라미터 증거를 요구한다. 본 실험의 사용자 확인이나 평면 적합만으로 그 검증을 통과시키지 않는다.

## 운영 적용 조건
1. 실제 데이터 포맷과 광학 좌표계 검증
2. 실제 동일 벽의 여러 각도 샘플 및 반복성 확인
3. 필요하면 몸체 기준의 절대각/고정 yaw·roll/translation/브래킷 기준 증거 확보
4. 앉은 자세의 몸통 기울기와 장착각 구분
5. 불변 profile ID·카메라 serial·mount revision을 저장하고 사용자가 검토
6. 카메라를 고정한 후 새 VSLAM 세션에만 검증된 설정 연결

순수 camera-frame VSLAM의 시작과 '검증된 body-frame pose'를 구분한다. 상대각만 계산한 상태를 full body calibration이라고 표시하거나 실행 중 TF를 바꾸지 않는다.
