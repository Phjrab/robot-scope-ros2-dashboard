# Go2 내부 Jetson Isaac ROS VSLAM 검증 기록

현재 판정은 **독립 실험에서 Stereo VO 실행 가능·추가 센서 검증 필요**다. 운영 FAST-LIO/Nav2를 대체하거나 로봇 주행 안전성을 검증한 결과가 아니다. 검증일은2026-10-13~14(Asia/Seoul)이며 장비 측정 원본 시각은UTC로 기록했다.

| 항목 | 실제 확인 | 상태 |
|---|---|---|
| 공식 bag 설치/GPU 실행 | 실제 tracker 초기화와 odometry/status; 짧은 샘플 처리 제한 기록 | INSTALL_PASS |
| 실제 D435i stereo | IR640×480 mono8, 실제 CameraInfo/TF, USB2 | LIVE_INPUT_PASS(STEREO_ONLY) |
| 정지 Stereo VO | 600.026초,30.029Hz,18,018출력,LOST0,위치 변화 최대1.666cm | VO_PASS / CONTINUOUS_VO_PASS(정지 한정) |
| Stereo VIO | wrapper 및 SDK10초 직접 시험에서 gyro/accel0개 | BLOCKED |
| SLAM 지도 저장 | 45,056byte data.mdb 및 해시 확인 | SLAM_TESTED(SAVE) |
| 지도 재위치추정 | multi executor로 정체 해소; localize=false/code3 | FAILED |
| 물리 이동·복귀·루프 폐쇄 | 사용자 요청으로 제외 | MOTION_NOT_RUN |
| FAST-LIO 상대 성능·ATE/RPE | 정렬된 동시 데이터/기준 궤적 없음 | NOT_RUN / N/A |
| 운영 odometry·TF·Nav2·VSLAM UI | 독립 domain71만 사용 | OPERATIONAL_INTEGRATION_NOT_RUN |

- [통과 기준, 측정 구간, p50/p95, 실패 및 복원 결과](RESULTS.md)
- [고정 버전의 공식 근거와 실제 장비 차이](OFFICIAL_REFERENCE.md)
- [소스 SHA·게시·main 통합 범위](PUBLICATION.md)
- [전용 컨테이너/VO/VIO/SLAM/재생·녹화·통계·종료 도구](../../../experiments/isaac_vslam/README.md)
- [실제 패키지·이미지·소스 고정 manifest](../../../experiments/isaac_vslam/versions.runtime.json)
- [소규모 측정 증거](evidence/)

원시 bag·영상·지도·대형 로그는 `/home/unitree/experiments/isaac-vslam-lab/`에 보존했다. 실험 종료 후 운영 카메라 active/running, dashboard HTTP200, running Docker0, 운영 domain의 실험 노드0개를 확인했다. 새 실센서 시험은 매번 현재 장치 소유권·자원·정지/감독 조건을 다시 확인해야 한다. main 기록 통합은 운영 배포와 별개다.

새 Robot Scope 실장비 검증 채팅에는 [현재 자원 상태·설정 캡처 제한·복사 가능한 인계 요약](HANDOFF.md)을 전달한다. 이 기록은 새 설치나 운영 배포를 수행하지 않은 읽기 전용 감사다.
