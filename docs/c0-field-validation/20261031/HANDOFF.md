# C0 후속 인계

이 채팅과 `review/20261030-c0-3d-field-sweep` 브랜치를 계속 사용한다. [전체 현재 표](CONTINUATION_RESULTS.md), [최종 실제 배포와 복구](EDITED_PCD_CONVERSION.md), [2차 후보 비교](REAR_SIDE_COMPARISON.md)를 함께 읽는다. 과거 결과표는 별도 인수 증거다.

다음 순서:

1. 사용자 변환으로 이미 생성된 `map1_2d`를 사용한다. 같은 이름의 변환을 중복 실행하지 않는다. 원본 map1/PCD와 교정은 보존한다.
2. 현재 source·TF·Nav2를 짧게 읽고 map1/새 2D revision의 정상 source 연결을 완료한다. 이전 map binding 준비 스크립트를 재실행하지 않는다. 사용자가 저장한 P1/P2는 이전 2D revision 소속이므로 현재 지도에 적용 가능한지 확인한 뒤 사용한다.
3. 이동 직전 현재 현장 준비·정지/회수 수단·새 P1→정지/dwell→녹색→P2의 유효 범위를 한 번 확인한다. 이전 두 목표/5분 수동 관측 승인을 재사용하지 않는다. 같은 창의 하위 단계에서 승인을 반복하지 않는다.
4. F01/F02를 한 번 검증해 실패 증거를 남기고 다음 독립 항목으로 진행한다. F03은 현재 운영 위치추정의 부족한 관측만 수집한다. 목표 URDF·현재 상태와 실제 종료를 확인한다. quality/stop/dwell/source gate 강제 통과 금지.
5. 전체 결과표를 갱신한 뒤 실패 진단·최소 수정·2차 후보를 분리한다. 후보 가중치는 구현·동일 입력 비교 완료지만 혼합 회귀로 NOT_ADOPTED, 기본 비활성이다.

실제 release 전환은 지도 변환 보고서의 검증된 장비 경로와 정상 idle lifecycle API를 사용한다. 새 release는 추적 코드 hash뿐 아니라 기존 `.venv`·`workspaces` symlink와 의존 import를 **활성화 전에** 검증한다. PID/cwd만으로 성공을 선언하지 말고 HTTP·실제 asset hash·source·lease/명령·보호 지도/설정 hash를 읽는다. 이전 시작 실패는 이 링크 누락을 복구해 해결했다. 새 패키지 설치나 센서/교정 변경은 없었다.

현재 source가 idle인 상태를 물리 정지 측정 PASS로 바꾸지 않는다. 자동 목표·자세·가짜 gate 발행은 이번0건이다. raw map/bag/좌표/교정 전체/화면은 private 보관하고 공개 Git에는 집계·입력 hash·검증 및 복구 설명만 남긴다. C1~C7/D1~D3 통합은 범위 밖이다.
