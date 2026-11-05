# A1 인계 · 비주행 리뷰

제품 SHA와 변경 경로는 SOURCE_LOCK.json의 product_commit, changed_paths에 고정한다. 기준 지도·장비 release 선택은 A1이 별도 시험창에서 결정한다. A2는 장비 조회, 배포, 생산자 시작, 활성 지도 선택, 운영 TF/ROS/제어 입력을 실행하지 않았다.

## 권한과 기본 상태

`OWNER_IMPLEMENTED_OFFLINE`은 실제 로컬 TLS/ASGI 및 브라우저에서 검증했다. `OWNER_CONFIGURED_DEVICE`와 `LIVE_SOURCE_CONNECTED`는 NOT_RUN이다. 플래그 기본값은 모두 OFF다. 별도의 권한 설정이 없으면 기존 C1 차단 경로를 유지한다. 아래 예시는 A1이 선택할 수 있는 구성 계약이다.

- `ROBOT_SCOPE_EXPANSION_MULTIMAP=1` 또는 `ROBOT_SCOPE_EXPANSION_SCENE=1`과 함께 `ROBOT_SCOPE_EXPANSION_REVIEW_DB`, `ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN`을 설정한다. ORIGIN은 브라우저가 사용한 명시적 HTTPS origin 전체이며 path와 후행 slash 없이 소문자 host 및 필요시 port를 쓴다. TLS를 직접 종료하거나 신뢰하는 프록시에서만 ASGI scheme을 설정한다.
- 작업 공간 하나를 공유하도록 설계했다. read는 이 공간의 비공개 지도·작업·asset을 조회한다. review는 같은 읽기 권한에 job 생성/취소, 후보 수락과 사본 저장을 더한다. 별개 사용자 자료는 별도의 공간·DB·저장소로 분리한다.
- DB는 서비스 계정 소유의 0700 디렉터리 안에 둔다. canonical absolute path와 owner-only 0600 regular file이 필요하다. 상위 경로도 타 계정이 교체할 수 없는 위치를 선택한다. 공개 static, 지도 catalogue, review bundle 디렉터리와 분리한다. 관리자는 아래 명령을 해당 계정의 사설 터미널에서 실행한다. issue가 출력하는 코드만 의도한 검토자에게 비공개로 전달한다. 로그와 셸 인자에 코드를 넣지 않는다.

```sh
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" init
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" issue read --ttl 900
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" issue review --ttl 900
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" revoke "$GRANT_ID"
```

`$REVIEW_DB`는 미리 마련한 사설 디렉터리 안의 DB 파일 경로다. init은 새 파일만 만든다. 하나의 코드는 한 번만 redeem된다. 발급 시점부터 최대 3600초, 활성 grant 최대 256개다. DB는 SHA-256 digest만 저장한다. 브라우저는 `/extensions`에서 코드를 입력한다. 로그인/로그아웃은 정확한 HTTPS origin에서 POST하며, 세션 쿠키는 Secure·HttpOnly·SameSite=Strict, Path=/api/v1/extensions다. 서버는 매 요청에서 만료와 폐기를 확인한다. 인증 오류와 비공개 응답에는 no-store가 붙는다. DB 접근 실패는 503으로 차단한다.

## 공용 진입점에 필요한 단일 연결

A1이 준비한 읽기 전용 provider가 있을 때만 기존 호출에 keyword 하나를 전달한다. 제공 전에도 A2의 권한·독립 REPLAY UI와 오류 상태를 쓸 수 있다. 아래는 공용 app.py에 대한 인계 예시다. 이름이 적힌 runtime 속성이 이미 존재한다고 가정하지 않는다.

```python
from robot_dashboard.expansion_integration.review_owner import ReviewInputs

review_inputs = ReviewInputs(
    maps_factory=make_private_review_maps,
    scene=existing_c1_read_service,
    scene_context=read_current_qualified_context,
)
expansion_index = configure_expansion(app, os.environ, review_inputs=review_inputs)
```

- `maps_factory`는 동기 무인자 callback이다. 기존 `compose_maps(saved_map_catalogue, qualified_metadata.get, private_bundle_root)`의 세 항목을 반환한다. 검토하도록 제공된 사본 디렉터리만 catalogue에 넣고 bundle 별도 root는 서비스 계정만 쓴다. signed-in 사용자와 공간은 이 고정 root를 공유한다. 요청자는 파일 경로나 source metadata를 지정할 수 없다. A1의 지도/계보 갱신 API를 연결하지 않는다.
- 지도 자격 메타데이터는 실제 map_id(24 hex), revision·원본 SHA-256(각 64 hex), frame_id, m 단위, evidence_kind(REPLAY/SYNTHETIC), source_epoch, 공개용 display_name을 제공한다. 있는 경우에만 원본 mapping_session_id(24 hex), 중력/평면, 편집 원본 DAG를 붙인다. 실제 기록 사본을 합성 세션에 결합하지 않는다. 현재 2차원 빈 칸 상태는 UNKNOWN이다.
- `scene_context`는 worker에서도 안전하게 호출할 수 있는 동기식 읽기 callback이다. 매번 하나의 일관된 snapshot 또는 None을 반환한다. `map_id/revision/generation`(비음수 safe integer), `frame_id/source_epoch/stream_epoch/clock_domain/source_identity/calibration_id`(유효하고 원본에서 확인한 토큰), `units="m"`가 필요하다. optional space_kind는 생산자 근거가 있을 때만 보낸다. 수집 세션·교정·원본 stamp와 수신 clock의 결속은 A1이 보장한다. A2는 누락을 503, map/stream 또는 읽기 전후 문맥 변경을 409로 거부한다. C3가 개별 slot의 epoch/clock/calibration/TTL도 검사한다.
- `scene`은 기존 C1 0.2 snapshot()/get_asset(id,revision) 읽기만 제공한다. 검토 화면에서 producer 시작 명령을 호출하지 않는다. asset의 등록된 ID·revision·MIME·byte length와 현재 snapshot의 ref를 유지한다. codec와 실제 바이트 표본이 없으므로 등록된 비공개 bytes까지 검증했고 표시 레이어는 UNAVAILABLE이다.
- A1이 실제 자료로 평가하려면 source map/revision/세대, 실제 측정 XY/XYZ와 프레임 변환·교정, stamp/clock/receipt/TTL, 모델 digest·track epoch·confidence의 유무, C6 원본 사건 시각/정지·ACK 증거, C7 입력 bytes와 동일 clock 단계 측정이 필요하다. 민감 원본은 비공개 사본으로만 전달한다.

## 인수 시 읽기 전용 확인과 복구

1. 로컬 사본으로 `python -m unittest tests.integration_i0.test_review_owner -v`를 실행한다. 새 임시 계정 DB, self-signed 테스트 인증서와 합성 지도를 만들고 종료 때 정리하는 검사다.
2. 별도 승인된 환경에서 read grant로 로그인해 GET /api/v1/extensions/session, /multimap/sources 및 /scene/context·/scene/snapshot(모두 같은 API prefix)의 권한·identity·Cache-Control을 확인한다. 로그아웃 후 같은 cookie의 private GET은 401이다. read grant는 지도 사본도 저장할 수 없다.
3. A2의 리뷰 결과를 인수할 때는 GET /api/v1/extensions/multimap/exports/{id}의 manifest로 사본 ID·revision·output_hashes, sources/input_pins, anchor 및 T_fused_source, provenance_dag, 좌표·단위와 operational_installed=false를 대조한다. 원본 map 및 목표 선택은 A1의 별도 적용 절차를 따른다.
4. 회수는 revoke 또는 logout, 기능 철회는 해당 opt-in/owner 설정을 해제한 후 A1이 승인한 시험창에서 이전 고정 release로 복구한다. 리뷰 사본은 독립 저장 위치에 보존한다. A2는 장비 서비스 조작과 rollback을 실행하지 않았다.

쓰기 권한 확인은 요청 시작 및 bounded JSON 본문 수신 후 서비스 dispatch 직전에 수행한다. 이미 접수된 job을 로그아웃으로 자동 취소하지 않는다. C1 bundle v1 형식과 입력별 evidence_kind를 보존한다. 합성 원본이 하나라도 있는 검토 사본은 SYNTHETIC으로 재조회한다. 전체가 REPLAY일 때에만 결과를 REPLAY로 표시하며, 과거 클라이언트가 혼합 사본을 REPLAY로 요청하면 409/REVIEW_EVIDENCE_MISMATCH를 반환한다. UI/API는 같은 release를 사용하는 것이 필요하다.
