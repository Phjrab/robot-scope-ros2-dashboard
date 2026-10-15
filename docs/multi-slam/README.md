# 선택형 SLAM 사용

기존 Live Mapping에서 LiDAR · FAST-LIO 또는 Stereo VSLAM을 선택한다.
선택만으로 engine/카메라/운영 pose가 바뀌지 않는다. 시작은 명시적 사용자
동작이며, 서버가 반환한 실제 상태와 effective mode를 표시한다. Stereo는
위치 관측(vo)과 지도 작성(slam_vo)을 지원한다. IMU 미검증 VIO는 비활성이다.

1. 장비 담당자가 DEPLOYMENT의 stage16 조건과 camera handoff를 완료한다.
2. Live Mapping에서 엔진/작업을 선택하고 요약 확인 후 시작한다.
3. 왼쪽은 실제 입력 IR 영상 위 현재 관측점 재투영이다. 정합/추적이 유효하지
   않으면 영상은 보여도 점은 숨긴다. 오른쪽은 전역 map-frame 지도·궤적이다.
4. 저장은 공식 native save job 완료까지 기다린다. 저장 후에도 mapping은
   계속되므로 저장 후 중지는 마지막 저장 이후 관측 폐기를 명시적으로 확인한다.
5. Saved Maps에서 native 지도와 기존 LiDAR 지도를 필터·미리보기·관리한다.
   native preview는 엔진/카메라 없이 볼 수 있다. metadata revision으로 변경을
   검증하며 사용 중인 지도는 변경/삭제할 수 없다.
6. 재위치추정은 호환 native 지도, 새 SLAM 세션, 실제 검증된 pose hint를
   요구한다. 기본 원점/방향을 만들지 않는다. native load와 localize 성공은
   별개이며 결과는 관측 세션에만 적용된다.

전역 지도는 현재 시야 밖도 탐색할 수 있다. LL_MAP 출력 상한32768 때문에
현재 유지 지도 전체 특징점 제공은 아직 BLOCKED다. 표시/출력/엔진 총수를
구분하고, 미확인 총수는 null로 둔다. 궤적은 입력의 bounded snapshot이며
무한 과거 기록이 아니다. 카메라 시야는 실제 optical pose와 보정으로 계산한
1m 표시 광선이며 가시거리/장애물/로봇 본체 pose가 아니다.

SW 테스트는 synthetic fixture 기반이며 live mapping·성능·지도 재사용 성공을
증명하지 않는다. 실제 상태는 ACCEPTANCE_MATRIX와 FINAL_REPORT를 따른다.
초기 상태에서는 관리자가 제공한 runtime/broker/handoff가 없어 VSLAM 시작이
차단될 수 있다. 기존 실험을 재설치/초기화하지 않는다.

주행 입력은 기존 navigation authority다. VSLAM 선택은 ARM/initial pose/goal을
발행하지 않는다. 관측 세션 중 새 수동 ARM/미션/서비스 변경은 서버에서
충돌을 차단한다. 실제 수동 매핑 이동은 stage16 별도 운영자 창을 요구한다.
