# A1 인계 · 비주행 리뷰

제품 SHA와 변경 경로는 SOURCE_LOCK.json의 product_commit, changed_paths에 고정한다. 기준 지도·장비 release 선택은 A1이 별도 시험창에서 결정한다. A2는 장비 조회, 배포, 생산자 시작, 활성 지도 선택, 운영 TF/ROS/제어 입력을 실행하지 않았다.

## 접근과 기본 상태

2026-11-05 사용자 요청으로 로그인과 코드 발급 단계를 제거했다. 활성화된 HTTPS 검토 주소의 방문자는 같은 사본 작업 공간을 조회·계산·수락·저장할 수 있다. 배포와 origin·입력 연결 절차는 [현재 사용 안내](DASHBOARD_ACCESS.md)를 따른다.

- `ROBOT_SCOPE_EXPANSION_MULTIMAP=1` 또는 `ROBOT_SCOPE_EXPANSION_SCENE=1`과 `ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN`을 설정한다. ORIGIN은 명시적 HTTPS origin이며 경로와 후행 slash를 붙이지 않는다.
- 서버는 HTTPS·Host·Origin과 요청 크기·schema·지도 revision·입력 계보를 검사한다. 사본과 asset 응답에는 no-store가 붙는다.
- `ROBOT_SCOPE_EXPANSION_REVIEW_DB`와 이전 세션 쿠키는 접근 판단에 사용하지 않는다. 기존 DB 파일은 롤백 자료로 보관할 수 있다.

## 공용 진입점에 필요한 단일 연결

A1이 준비한 읽기 전용 provider가 있을 때만 기존 호출에 keyword 하나를 전달한다. 제공 전에도 독립 REPLAY UI와 오류 상태를 쓸 수 있다. 아래는 공용 app.py에 대한 인계 예시다. 이름이 적힌 runtime 속성이 이미 존재한다고 가정하지 않는다.

```python
from robot_dashboard.expansion_integration.review_owner import ReviewInputs

review_inputs = ReviewInputs(
    maps_factory=make_private_review_maps,
    scene=existing_c1_read_service,
    scene_context=read_current_qualified_context,
)
expansion_index = configure_expansion(app, os.environ, review_inputs=review_inputs)
```

- `maps_factory`는 동기 무인자 callback이다. 기존 `compose_maps(saved_map_catalogue, qualified_metadata.get, private_bundle_root)`의 세 항목을 반환한다. 검토하도록 제공된 사본 디렉터리만 catalogue에 넣고 bundle 별도 root는 서비스 계정만 쓴다. 해당 검토 주소의 방문자는 이 고정 root를 공유한다. 요청자는 파일 경로나 source metadata를 지정할 수 없다. A1의 지도/계보 갱신 API를 연결하지 않는다.
- 지도 자격 메타데이터는 실제 map_id(24 hex), revision·원본 SHA-256(각 64 hex), frame_id, m 단위, evidence_kind(REPLAY/SYNTHETIC), source_epoch, 공개용 display_name을 제공한다. 있는 경우에만 원본 mapping_session_id(24 hex), 중력/평면, 편집 원본 DAG를 붙인다. 실제 기록 사본을 합성 세션에 결합하지 않는다. 현재 2차원 빈 칸 상태는 UNKNOWN이다.
- `scene_context`는 worker에서도 안전하게 호출할 수 있는 동기식 읽기 callback이다. 매번 하나의 일관된 snapshot 또는 None을 반환한다. `map_id/revision/generation`(비음수 safe integer), `frame_id/source_epoch/stream_epoch/clock_domain/source_identity/calibration_id`(유효하고 원본에서 확인한 토큰), `units="m"`가 필요하다. optional space_kind는 생산자 근거가 있을 때만 보낸다. 수집 세션·교정·원본 stamp와 수신 clock의 결속은 A1이 보장한다. A2는 누락을 503, map/stream 또는 읽기 전후 문맥 변경을 409로 거부한다. C3가 개별 slot의 epoch/clock/calibration/TTL도 검사한다.
- `scene`은 기존 C1 0.2 snapshot()/get_asset(id,revision) 읽기만 제공한다. 검토 화면에서 producer 시작 명령을 호출하지 않는다. asset의 등록된 ID·revision·MIME·byte length와 현재 snapshot의 ref를 유지한다. codec와 실제 바이트 표본이 없으므로 등록된 비공개 bytes까지 검증했고 표시 레이어는 UNAVAILABLE이다.
- A1이 실제 자료로 평가하려면 source map/revision/세대, 실제 측정 XY/XYZ와 프레임 변환·교정, stamp/clock/receipt/TTL, 모델 digest·track epoch·confidence의 유무, C6 원본 사건 시각/정지·ACK 증거, C7 입력 bytes와 동일 clock 단계 측정이 필요하다. 민감 원본은 비공개 사본으로만 전달한다.

## 인수 시 읽기 전용 확인과 복구

1. 로컬 사본으로 `python -m unittest tests.integration_i0.test_review_owner -v`를 실행한다. 임시 self-signed 테스트 인증서와 합성 지도를 만들고 종료 때 정리하는 검사다.
2. 별도 승인된 HTTPS 환경에서 쿠키 없이 `/api/v1/extensions/multimap/sources`와 `/scene/context`·`/scene/snapshot`의 identity·Cache-Control을 확인한다. 새 탭과 새로고침에서도 바로 조회되는지 확인한다. 잘못된 Origin과 HTTP API 요청은 403으로 거부한다.
3. A2의 리뷰 결과를 인수할 때는 GET /api/v1/extensions/multimap/exports/{id}의 manifest로 사본 ID·revision·output_hashes, sources/input_pins, anchor 및 T_fused_source, provenance_dag, 좌표·단위와 operational_installed=false를 대조한다. 원본 map 및 목표 선택은 A1의 별도 적용 절차를 따른다.
4. 기능 철회는 해당 opt-in/owner 설정을 해제한 후 A1이 승인한 시험창에서 이전 고정 release로 복구한다. 리뷰 사본은 독립 저장 위치에 보존한다. A2는 장비 서비스 조작과 rollback을 실행하지 않았다.

HTTPS·동일 출처 확인은 요청 시작 및 bounded JSON 본문 수신 후 서비스 dispatch 직전에 수행한다. 작업 취소는 기존 명시 취소 동작을 사용한다. C1 bundle v1 형식과 입력별 evidence_kind를 보존한다. 합성 원본이 하나라도 있는 검토 사본은 SYNTHETIC으로 재조회한다. 전체가 REPLAY일 때에만 결과를 REPLAY로 표시하며, 과거 클라이언트가 혼합 사본을 REPLAY로 요청하면 409/REVIEW_EVIDENCE_MISMATCH를 반환한다. UI/API는 같은 release를 사용하는 것이 필요하다.

## 다음 현장 시험의 최소 수집·판정

2026-11-05 후속 요청에 따른 A1 수집 계획이다. 11:15 정지 관측 사본은 local pose·점 개수 2건을 제공한다. 아래 세 평가는 지도 결속·XYZ·시계 대응을 추가로 확보할 때 진행한다. A1은 다음 승인된 현장 시험에서 수집하고, A2는 전달받은 사본으로 계산·재생한다. 시험 실행·배포·활성 지도·센서·이동 승인은 A1의 기존 현장 절차를 따른다.

### 공통 기록과 사전 기준

- 시험마다 현장 release 전체 SHA, 앱·생산자 설정 hash, 실제 세션/epoch, 지도 ID·revision·generation, frame과 m 단위, 시각의 단위·clock domain을 기록한다. 수집 파일에는 상대 이름·byte length·SHA-256을 붙이고 민감 원본은 비공개 사본으로 전달한다.
- 변환에는 방향(`T_target_source`), 좌표축, 단위, 측정 방법, 교정 hash, 유효 시간/세대와 오차 범위를 붙인다. dynamic transform은 해당 원본 표본 시각에 결속한다. clock mapping에는 대응 clock/epoch, offset·drift, 유효 구간, 측정 오차 상한을 붙인다. 확인되지 않은 값은 null로 남긴다.
- 시험 전에 목적별 한도를 A1과 운영자가 기록한다. 지도 `map_xy_limit_m / map_z_limit_m`, 콘 `cone_xy_limit_m / cone_z_limit_m`, 지연 `latency_p95_limit_ms / latency_max_limit_ms`, 허용 손실률 `missing_fraction_limit`을 별도로 정한다. 높이 평가를 생략하면 결과 범위를 XY로 표시한다. Nav2 설정과 독립적으로 표시·리뷰 목적의 한도를 정한다. 현재 인계 자료에서 이 평가의 승인 수치 한도는 미확정이다.
- 아래 3개 기준점·3개 콘 위치·30초/100표본은 이번 1차 현장 확인을 위한 A2 제안 최소치다. A1이 시험 전에 범위와 한도를 확정한다. 결과가 대표하는 범위에는 실제 지도 쌍·위치·거리·해상도·입력률·장비 설정을 함께 적는다.

### N03 · 지도 정합 정확도

**최소 사본**

1. 검토 대상 저장 지도 2개의 원본 파일과 metadata, 전체 해시, 지도별 원본 세션·frame·revision 및 기존 리뷰 manifest. 평가는 실제 두 원본의 전체 점과 기존 D1/C1 사본 저장 경로를 사용한다.
2. 고정한 정합 결과의 `T_fused_source`, anchor, 입력 pins, 출력 hash와 계산 설정. 변환을 고정한 뒤 독립 기준점으로 평가한다.
3. 겹치는 영역에 퍼진 비공선 물리 기준점 3개 이상. 각 점의 동일한 ID, 각 지도에서의 XYZ, 독립 실측 reference XYZ, reference→anchor 변환과 그 측량 근거, 측정 오차 상한을 기록한다. 기준점은 정합용 수동 anchor·튜닝에 사용한 점과 분리한다. 각 점을 식별한 기록도 첨부한다.

**계산과 판정**

- 각 지도 기준점에 고정한 변환을 적용해 `p_fused = T_fused_source · p_source`를 구한다. 같은 점의 두 지도 좌표 간 거리로 상대 정합 오차를, 독립 실측 reference를 fused 좌표로 옮긴 값과의 차이로 실측 기준 오차를 각각 산출한다.
- 기준점별 XY 오차·절대 Z 오차(m), RMS와 최대값, 기준점 수, 측량·좌표 추출·reference 변환 오차 상한을 보고한다. 높이 근거가 있으면 XYZ 거리도 보고한다.
- 합격은 평가 대상으로 정한 각 축의 최대 오차에 측정 오차 상한을 더한 값이 사전 한도 이내인 경우다. 오차 하한도 한도를 넘으면 FAIL, 오차 구간이 한도를 걸치면 INPUT_REQUIRED로 두고 재측정한다.
- 독립 reference와 anchor의 측량 연결이 없으면 상대 정합 값까지만 계산하고 절대 정확도는 INPUT_REQUIRED로 둔다. 기준점·원본·변환 중 필수 입력이 빠지거나 수치 한도가 미정이면 해당 판정도 INPUT_REQUIRED다.

### N04 · 콘 3D 좌표

**최소 사본**

1. 식별 가능한 콘 하나를 시험 구간의 근거리·중거리·원거리 3개 위치에서 정지 관측한다. 위치마다 최소 한 번의 실제 검출 원문과 그 검출에 결속된 점군 또는 영상·depth 원본, codec/schema·단위·hash를 제공한다. 위치·표본 ID로 일대일 대응시킨다.
2. 평가할 점을 콘 밑면 중심 또는 중심으로 시험 전에 고정하고, 해당 점의 독립 실측 map XYZ와 측정 오차 상한을 제공한다. 실제 치수·지면 높이/법선과 측정 근거를 포함한다. 경사면을 평가 범위에 포함하면 그 위치의 높이·자세를 실측한다.
3. 각 표본의 source stamp·수신 시각·clock/epoch·TTL, map ID/revision/generation, 검증된 생산자 신원, 원본 frame부터 map까지의 교정/자세·변환 체인을 제공한다. 모델을 사용하는 경로에는 모델 전체 digest·설정과 출력 confidence·track epoch의 제공 여부를 기록한다.

**계산과 판정**

- 기존 C1→C3 경로로 같은 표본을 로컬 재생하고, 표시 DTO의 동일 기준점 XYZ를 독립 실측값과 대조한다. 위치별 XY·절대 Z·XYZ 오차(m)와 측정/변환 오차 상한을 보고한다. 화면 픽셀 위치와 3D 수치 검사를 구분해 기록한다.
- 세 위치 각각의 XY·Z 오차 상한이 사전 한도 이내이고, 원문→변환→DTO→표시의 표본/지도/교정 결속과 유효 시간이 통과하면 해당 시험 위치의 3D 표시 PASS다. 오차 하한이 한도를 넘으면 FAIL, 한도를 걸치면 INPUT_REQUIRED다.
- 수집이 정상인데 예상 콘 검출이 없으면 그 위치는 FAIL로 기록하고 좌표 오차는 null로 둔다. 실제 검출 생산자·XYZ·교정·지면·clock 근거가 없으면 해당 위치의 3D 평가는 INPUT_REQUIRED다. 높이 근거가 부족한 경우 XY 결과와 높이 미검증을 함께 남긴다.

### N06 · Jetson 센서 취득→화면 표시 지연

**최소 사본**

1. 실제 Jetson 고정 release와 장비 유형, 전력 모드·클럭/열 제한 상태, 입력률·point/byte 수, 네트워크 조건, 브라우저 실행 장치·버전·해상도를 기록한다. 기존 C7 입력·설정 manifest 형식과 stage 측정 방식을 재사용한다.
2. 한 번의 연속 30초 이상 관측에서 같은 표본으로 연결되는 정상 구간 완료 표본 100개 이상을 확보한다. 기동/준비 구간은 표시해 별도로 집계한다. 마지막 입력의 처리·만료까지 추적하고, 생성한 전체 고유 표본 수와 drop·대기 교체·누락·거부·만료 사유를 함께 남긴다. 손실률은 완료하지 못한 고유 표본 수/전체 고유 표본 수로 계산하며 여러 사유가 붙은 표본은 한 번만 센다.
3. 각 표본에 원본 source epoch+sequence/stamp 또는 payload hash를 유지하고 다음 시각을 연결한다. 센서 취득 시각, Jetson 수신·처리 시작/끝·응답 송신, 브라우저 수신·해당 표본 draw 완료. 각 시각에 clock domain·단위·epoch를 붙인다. source stamp가 의미하는 센서 취득 구간과 timestamp 정확도도 기록한다.
4. sensor↔Jetson↔browser clock의 실측 대응과 오차 상한·유효 구간을 확보한다. 기존 float receipt는 원래 정밀도를 유지한다. 원본 정수 ns는 문자열로 전달한다. 화면 표시 종점을 주장할 때는 해당 표본 draw와 결속된 브라우저 presentation trace 또는 외부 표시 측정 근거까지 첨부한다.

**계산과 판정**

- 같은 Jetson clock의 대기·처리 시간과 같은 browser clock의 수신→draw 시간을 각각 계산한다. 실측 mapping으로 clock을 통일한 표본에 대해서만 센서→draw와 센서→표시 지연(ms)을 산출한다. draw 완료 시각만 있으면 센서→draw 결과까지 기록하고 화면 표시 지연은 INPUT_REQUIRED로 둔다.
- 기동/정상 구간별 표본 수·p50·p95·최대값을 기록한다. p95는 C7과 같은 nearest-rank 방식이다. 각 표본 지연에 clock mapping·센서 timestamp·표시 측정 오차 상한을 반영해 상한 집계도 함께 계산한다.
- 30초/100표본 요건, 표본 결속, 유효한 clock mapping이 성립하고, 정상 구간 p95·최대 지연 상한과 손실률이 사전 한도 이내면 측정 조건에서 PASS다. 유효한 측정의 하한이 지연 한도를 넘거나 손실률이 한도를 넘으면 FAIL이다. 경계가 불명확하거나 시계 대응·표시 종점·표본 수·한도가 부족하면 INPUT_REQUIRED로 둔다.
- 기존 stage만 측정 가능하면 그 stage 결과를 먼저 인수한다. 장비 처리 시간은 같은 표본의 Jetson 수신/처리 clock으로 별도 판정하고, 종단 지연에 필요한 나머지 근거를 결과 행에 남긴다.

### 반환할 결과 행

각 항목에 `release_sha, input_hashes, sample_count, measured_scope, metric/unit, uncertainty_bound, agreed_limit, PASS/FAIL/INPUT_REQUIRED, missing_evidence`를 남긴다. 기준 미확정이어도 계산 가능한 실측값과 원본은 전달한다. A2는 입력 해시와 기존 계약을 검증한 뒤 로컬 계산·재생 및 결과표 갱신을 수행한다.
