# C0 후속 결과 이후 진단

[1차 시점 결과표](CONTINUATION_RESULTS.md)를 먼저 동결했다. 현재 실제 이동 sweep은 OPEN이며 다음 분석을 실기 성공으로 계산하지 않는다.

| 확인한 사실 | 해석과 최소 후속 |
|---|---|
| 사용자 준비 뒤 2D Nav2는 READY였으나 selected=null/LEGACY_2D | 기존2D 성공 인수와 현재3D 이동 증거를 구분. 준비한 source를 정상 절차로 연결해야 함 |
| source 연결 요청 20초 timeout, 원래 교정 hash로 복구 | 원인 미확정. 현재 map1/map1_2d로 작업 대상이 바뀌었으므로 이전 binding을 자동 재시도하지 않음 |
| map1은 실제 크롭 PCD인데 manageable=false로 변환 목록과 서버에서 제외 | 읽기 변환 권한과 원본 변경 권한을 분리하는 최소 보완 완료. 불변 manifest·SHA·revision 확인과 재확인 유지 |
| 실제 사용자 변환은 성공, UI만 TRACKING LOST | cached topic render가 이전 idle을 재사용하는 경로 재현. 새 mapping 응답에서만 추적 판정하도록 수정 |
| 후방·측면 후보는 일부 A 개선과 B/C 회귀·처리시간 증가 혼재 | 기본 운영 정책 NOT_ADOPTED. weighted 목적함수 감소를 위치 정확도 개선으로 보고하지 않음 |
| 기존 bags에 현재 운영 matcher/scan/costmap 관측 없음 | F03 실기 때 부족한 운영 증거만 추가. 기존 보행·수동 지형 주행 반복을 완료 조건으로 두지 않음 |

후보는 최종 저장 지도 ICP 단계만 수정했다. FAST-LIO/IMU core, 장애물 scan, 브라우저 렌더러 자체 개선으로 보고하지 않는다. 방향별 현재 관측점·품질·구조·중복 질량을 반영했고 단일 평면 신뢰 제한, 전환 상한, baseline 복구 회귀를 검증했다. 수치 비교의 부분 품질 통과 수와 실제 stop/dwell/source 통과는 별개다. [후보 결과](REAR_SIDE_COMPARISON.md).

정밀 도착 오차는 실제 action success·정지·대기 및 버튼→다음 goal 성공 여부와 별도 기록한다. 실제 gate가 막히면 원인을 남기고 독립 항목으로 진행한다. yaw tolerance·속도·progress checker·후방 가중치를 1차 도중 연속 변경하지 않았다. 과거 HIGH_RESIDUAL·지도 원점·구/신 지도 비교는 다시 조사하지 않았다.
