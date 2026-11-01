# 관측 계약과 표시 경로

```text
committed scenario / bounded legacy display payload
 → cone_input.validate_legacy_cones (stateless, whole rejection)
 → cone_demo.adapt_cones (isolated SYNTHETIC only)
 → existing SceneSnapshotService 0.2 (one latest-state owner)
 → existing authorized /api/v1/extensions/scene/{context,snapshot}
 → existing scene subscription → adaptC1ScenePacket
 → C3 consumer (identity, age, TTL, queue/retirement)
 → C3 overlay painter → existing renderer.projectWorld
```

새 `/api/v1/obstacles`, detector, subscriber, ObstacleStore, renderer engine, costmap/TF/Nav2/속도 sink는 없다. 별도 데모 프로세스도 동일 C1/C3 제품을 조합한다. 원본 공용 E2E backend는 변경하지 않는다.

입구: legacy `robot-scope.obstacle-map/v1`은 공통 wire를 대체하지 않는다. payload64KiB, cone64개, exact key sets, finite non-bool 숫자, unique integer ID, 좌표±1000m, radius .01–2m, height .01–3m, count0–1e6를 검사한다. 잘못된 객체 하나라도 전체 거부한다. scenario 파일256KiB, 중복 JSON key/symlink/비합성 evidence를 거부한다. cone_ 명시 시나리오만 traffic_cone로 표시하고 LiDAR 미분류 객체는 변환하지 않는다.

원래 integer ID는 `cone-ID`로 유지되며 source epoch와 함께 해석한다. `n`은 observation_count, confidence는 null이다. 짧은 model digest는 `model_digest_hint`, 검증 상태 false이며 경로는 공개 snapshot에 없다. 지도 revision의64자리 hash는 **합성 display 내용의 hash**이며 모델 hash가 아니다. 문서상 실제 반경 .07m/높이 .23m를 모든 콘에 하드코딩하지 않았다. 예제의 .10m/.25m를 그대로 사용한다.

공간: synthetic-only context는 전용 map ID, full revision, generation, source epoch, stream epoch, frame, units, source identity, `ISOLATED_SIMULATION`을 갖는다. scenario의 `arena_design`을 map/odom으로 치환하는 옵션은 없다. input frame과 owner context가 다르면 UNALIGNED로 거부한다. C3는 같은 frame 이름이어도 map revision/generation/epoch/identity/space가 바뀌면 기존 geometry를 무효화한다. XY-only geometry는 SYNTHETIC + 전용 공간에서만 표시하며 LIVE로 승격하지 못한다.

높이: legacy x/y에는 실제 z·roll/pitch·지면 근거가 없다. 중심 z=h/2, 수직 cone은 **전용 flat demo 좌표에만 적용하는 표시 가정**이다. `FLAT_DEMO_ONLY / HEIGHT_UNVERIFIED / DISPLAY_ONLY`를 geometry provenance와 UI에 명시한다. 실제 경사로/계단에 이 가정을 적용하지 않는다. `flat-demo-assumption`은 교정 완료 ID가 아니다. 이 표시용 bounding box/glyph는 D3 충돌 계산이나 로봇 footprint로 전달하지 않는다.

시간: source stamp는 Decimal을 거쳐 ns 문자열로 변환하며 sub-ns 입력은 거부한다. 기존 canonical ns는 문자열/BigInt를 유지한다. legacy float가 제공한 것보다 더 높은 원본 정확도를 주장하지 않는다. host receipt는 신뢰된 owner가 제공한다. producer clock과 브라우저 clock을 직접 빼지 않는다.

C1의 기존 lock 안에서 순서 비교와 commit을 수행한다. obstacle stamp 동등/역행(새 sequence여도 포함), 이전 sequence, populated epoch의 producer/clock/host 변경은 거부한다. clock/source 재시작은 `reset_source`의 새 epoch, 지도 전환은 증가한 generation으로 명시한다. 기존 clock-unknown 회귀는 거부 후 새 epoch에서도 UNKNOWN을 유지하는지 검사한다. snapshot GET은 stamp/sequence/receipt를 바꾸지 않는다. demo timer만 새로운 합성 sample을 생성한다.

C1 snapshot은 server received_age_ms와 max_age_ms를 전달하며 no-store다. C3는 기존 정책 TTL과 server TTL 중 작은 값을 사용하고 `server age + transport elapsed + local holding elapsed`를 보존한다. 동일 stamp 재수신 시 기존 anchor보다 젊어지지 않는다. 예제 C1 TTL1초/C3 상한1.2초, 기존 다른 C1 owner의500ms도 유지한다. server의 expired/unavailable은 같은 sequence의 늦은 응답으로 되살아나지 않는다. 빈 정상 관측과 빈 stale 관측을 분리하며 expired geometry는 숨긴다(원본의 회색 잔류 대신 기존 C3 정책 유지).

Lifecycle: 기존 poll을 scene_poll.js로 분리했을 뿐 subscription은 하나다. context→snapshot 순차 single-flight, request/body 3초 timeout, AbortController, 실패 시1초부터30초까지 backoff, closed fence를 사용한다. C3 rAF/clock이 요청 완료와 독립적으로 만료를 판정한다. pause는 freshness를 멈추지 않는다. 탭/페이지 종료 시 pending request, timer, listener, subscription, overlay/renderer를 해제하고 늦은 응답을 무시한다.

UI: /extensions의 관측 진단에서 CONES는 기본 OFF다. existing scene poll은 일반 관측을 위해 그대로 존재하고 콘을 위한 추가 요청은0이다. 전체 확장 flag OFF면 화면/API/worker 추가가0이다. 출처(SIMULATED/REPLAY/LIVE), freshness(VALID/STALE/UNAVAILABLE), alignment(ISOLATED_DEMO_ONLY/UNALIGNED)를 구분한다. viewport에도 합성 평면 배지를 표시한다. 반경/높이는 캔버스·inspector에 제공하고 좁은 화면의 캔버스 라벨만 줄인다. 기존 Goal/Initial/current URDF 슬롯을 변경하지 않는다.

운영 인증은 여전히 BLOCKED_AUTH다. 독립 demo는 loopback 주소/Host/cross-site 검사와 HttpOnly SameSite=Strict 임시 session cookie로 생성된 공개 합성 데이터만 승인한다. production configure_expansion/owner에는 이 정책을 설치하지 않는다. 실제 source qualification은 미구현 상태로 남는다.

| 실제 node에서 주장된 필드 | 현재 처리 |
|---|---|
| stream_connected | 입력 미확보, UNKNOWN; READY 근거 아님 |
| frame_age_s | 원 clock mapping/receipt/TTL 없이는 변환하지 않음 |
| motion_gate | 관측·주행 승인을 부여하지 않음; UNKNOWN |
| last_error | 실제 schema 미확보; 가짜 정상 health로 대체하지 않음 |

실제 `/cones/state` 노드/메시지·모델 전체 hash·측정3D/pose·map/session pairing·교정이 제공되지 않았으므로 `PAIRED_REAL_PRODUCER_INPUT_REQUIRED`. detector/회피/실장비 연결 완료가 아니다.
