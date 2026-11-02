# 경사로·계단을 포함한 새 3D 지도 비교 준비

사용자가2026-10-30에 **현재 최근 3D 지도는 경사로·계단을 포함하지 않는 평지 지도**라고 확인했다. 사용자가 지형을 포함한 새3D 매핑을 마친 뒤 알려주면 이번 기록으로 비교한다. 기존 [1차 결과](FINAL_ROUND1_RESULTS.md)와 [별도 진단](POST_FINAL_DIAGNOSIS.md)은 당시 사실로 보존하며 이 문서는 이후 확인한 지도 범위의 추가 조건이다.

기존 평지 지도로 미포함 지형의 저장 지도 위치추정 성능을 평가할 수 없다. 초기 정지 정합의HIGH_RESIDUAL(.23538m)은 그대로 남긴다. 그 정합은 지형 이동 전에 수행했으므로 경사로·계단 누락이 해당 초기 실패의 단일 원인이라고 확정하지 않는다. raw/IMU/FAST-LIO의 수집 결과도 저장 지도 정확도 판정과 구분한다.

## 이미 실행한 준비

장비에 새로 접속하거나 매핑/제어/관측 서비스를 변경하지 않고 PC에 회수한 private 자료만 처리했다. 원본 bag·기존 보고서·지도는 수정하지 않았다.

| 준비물 | 완료한 작업 |
|---|---|
| 사례1 | 경사로 상승→계단식 하강 기록의 식별자·원시 file hash·구간·입력 topic을 고정 |
| 사례2 | 계단 상승→경사로 하강을 별도 사례로 고정 |
| 사례3 | 사용자 추가 요청의 경사로 상승→계단식 하강 반복을 별도 사례로 고정 |
| 데이터 목록 | 원시78DB·20,362,293,248B의 기존 검증 hash와 metadata 연결; 이번 준비 중 장비 raw를 재스캔하지 않음 |
| telemetry 인덱스 |414개 표본의 source stamp·frame·epoch·pose age·자세를 private CSV로 구성 |
| 사용자 구간 인덱스 |16개 표시와 앞/뒤 telemetry 표본 연결,18개 구간 구성. 대표 source stamp를 지정하되 실제 bag에서 exact-stamp odom pair를 다시 확인해야 함 |
| 기존 평지 reference | 전체13,546점 edited PCD를 기존 다운로드에서 별도 보존하고 SHA6ec38aa8… 재검증. 전체 record count/layout도 확인 |
| 새 지도 인수 양식 | ID/revision/full PCD hash·frame/units·매핑 세션·경사로/계단 범위·epoch별 map 정렬 항목을 준비. 아직 값은 미지정 |
| 비교 계약 | 같은 기록 frame·처리 경로·품질 기준을 유지한 old/new reference 비교 조건 고정 |

진입/상승 표시가 같은 시각에 기록된 사례1·2에는 길이0의 구간이 각각1개 있다. 이를 정확한 물리 경계로 만들지 않았다. 사례1의 최종 정지 보고는 캡처 구간 밖이므로 바깥 표시로 남겼다. 사례1의 LIO epoch와 사례2·3의 epoch도 구분했다. 시작점 근처에 배치했다는 이유로 숫자 좌표를 같게 놓지 않는다.

실제 pose/점군·CSV·full PCD·bag 경로는 private에만 둔다. 공개 문서에는 집계와 준비물 hash를 남긴다. PC에 원시20GB 전체를 복사한 것은 아니며 원본은 이전에 검증한 장비 private 보관소에 있다.

## 새 지도 완료 통보 후의 비교 조건

1. 완료된 새 지도 목록에서 사용자가 지정한 지도의 ID/revision과 전체 PCD hash·fields·frame·units·경사로 및 계단 범위를 확인한다. 기존 지도를 덮어쓰거나 운영 source로 자동 선택하지 않는다.
2. 새 지도 좌표계와 두 LIO epoch의 관계를 각각 확인한다. 새 매핑 원점이 바뀌었다면 예전 seed 숫자를 재사용하지 않는다. 지도 수집과 이번 기록의 독립 lineage·장착 보정·시계 관계는 확인된 범위만 표시한다.
3. private 인덱스로 같은 기록의 진입/상승/정상/하강 source frame을 선택하고, 저장된 `/cloud_registered`와 exact-stamp `/Odometry`의 연결을 확인한다. 기존 입력 경로처럼 필요한 역변환은 한 번만 적용한다. raw `/lidar_points`와 `/cloud_registered_body`는 별도 진단 입력으로 유지한다.
4. 동일한 query/source stamp·전처리·solver·seed 근거를 고정해 기존 평지 reference와 새 지형 reference를 비교한다. 지도 원점이 다르면 같은 물리 prior를 각 지도 frame으로 표현하며 같은 숫자 transform을 강제하지 않는다.
5. 단계별 RMSE·overlap·형태/수렴·보정 변화·입력 gap·처리 시간/메모리를 비교한다. 기존 지도에서 미포함인 지형과 실제 중첩 평지 구간을 구분한다. 외부 정답 없이 ATE/RPE나 절대 위치 정확도를 만들지 않는다.

기본 비교는 기존 전체 방향 정책을 유지하고 reference 지형 포함 여부를 비교한다. RMSE.05m·overlap.60·correspondence.75m·geometry ratio.002 기준을 바꾸지 않는다. 후방/측면 가중치·Nav2 속도/yaw/progress 설정은 이 비교의 동시 변경 변수가 아니다.

기존 recorded-real evaluator는 calibration/clock/frame 연결/독립 수집 qualification을 요구한다. 이 플래그를 임의로true로 채우지 않는다. 미검증 항목이 남으면 수치 진단의 한계를 명시하거나 해당 평가 경로를BLOCKED로 둔다. bag→수치 배열 변환·새 지도 정합은 아직 실행하지 않았으며 현재 준비 완료 범위는 입력 인덱스·식별·기준 PCD·비교 계약이다.

상태: **준비물 검증 PASS / 새 지도 대기 / 실제 새 지도 수치 비교 NOT_RUN**. 이번 준비의 장비 호출·배포·주행 명령은0건이다. 사용자 매핑 완료 통보를 받은 뒤 후속 비교를 진행한다.

[기계 판독 준비 영수증](MAP_COMPARISON_PREP.json).
