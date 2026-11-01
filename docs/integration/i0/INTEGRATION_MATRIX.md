# I0 기능 인수 결과

기준 main `846121b4988ed2932d329020857925558f8f2c79`. 10개 역할의 **258개 명시 경로**만 인수했다. 원본 40자리 SHA, Git blob, 원본/통합 SHA256, I0 수정 경로는 [SOURCE_LOCK.json](SOURCE_LOCK.json)에 있다. 전체 브랜치 merge/cherry-pick은 0회다. PASS는 합성 입력 또는 과거 기록으로 검증한 계층만 뜻한다.

| 역할 | 원본 SHA 앞 12자리 | 제품 연결 / 인수 commit | core / HTTP / browser | native 및 실장비 |
|---|---|---|---|---|
| D1 | 203c144f6b4a | multimap_core → catalogue.py; b267f1f | 실제 solver / C1 / C2 DOM PASS | DEVICE_NOT_RUN |
| C1 | 8fd42bdd5a1c | 계약0.2, job/store/scene router; b267f1f | 실제 서비스·401/403/409 PASS; 운영 BLOCKED_AUTH | DEVICE_NOT_RUN |
| C2 | 7625c87ede24 | /extensions Multimap Fusion; b267f1f | 2개·3개·누적 정합, 저장·재목록·계보 거부 PASS | 리뷰 전용 사본 |
| C3 | e394b090221c | /extensions 관측/REPLAY, 기존 renderer; 83859c6 | 실제 C1 HTTP·PAUSED stale·map/clock fence PASS | diagnostic only; opaque asset decoder 미연결 |
| D2 | 7313f0a31c00 | CanonicalCorePorts.from_installed; f110bed | 실제 perception → C1 → UI PASS | RGB-D 실측 교정·YOLO 성능 미검증 |
| D3 | 0bb91b70b4ff | 공식 URDF·라이선스·advisory collision; f110bed | 실제 충돌 계산 → C1 → UI PASS | 과거 native 기록 재생 PASS; ADVISORY_ONLY |
| C4 | b7242fca7c1b | create_review_runtime; f110bed | bounded async → D2/D3 → TCP HTTP → C3 PASS | BLOCKED_NATIVE_IDENTITY; planner/actuator 미확인 |
| C5 | 2a51d9906c39 | scoped multimap/obstacle helper; 83859c6 | 390/768/1440, dark/light, 키보드·44px PASS | 조작 gate 변경 없음 |
| C6 | 23da4f7360db | 로컬 파일 REPLAY; 99dd359 | 실제 parser→picker/seek/비교/C3, CLI Markdown PASS | 목표 재전송 없음 |
| C7 | ec724dafd33d | 독립 expansion_diagnostics CLI; 8e22f6f | 실제 코어·한도/TTL/큐 진단 PASS | 센서→화면 지연 UNKNOWN; Jetson NOT_RUN |

모든 역할은 SOURCE_IMPORTED/UNIT_PASS다. C7은 독립 CLI로 인수했고 나머지 제품 host는 b899f74에 연결했다. 최종 commit별 변경과 검증은 VALIDATION/RESULTS 및 Git 이력을 확인한다.

## 실제 연결

- 지도: 기존 SavedMapCatalog full-source resolver → 서버 metadata qualification → D1 solver → C1 FusionJobManager/BundleStore → C2 실제 HTTP/DOM. 400점×2=800, ×3=1200, AB+C=1200 전체 PCD를 저장했다. preview160점은 저장 입력으로 쓰지 않는다. 원본 hash 보존, mapping_session_id=null, legacy family DEFERRED, operational_installed=false다.
- 관측: 명시 synthetic/replay factory → C4 최신 worker → D2/D3 → C1 0.2 → 별도 생산자 context와 HTTP snapshot → C3 → 기존 RobotScene3D. 미제공 pose/joints/coverage/asset은 UNKNOWN/UNAVAILABLE다. 실제 Goal/Initial 슬롯은 건드리지 않는다.
- 재생: 사용자 로컬 JSON만 읽는다. 기존 GoalPrecision/sink 및 C1 producer를 실제 parser에 넣고 ns 문자열을 보존했다. 동일 renderer에서 seek, map/epoch 변경, 비교, 잘못된 JSON/HTML, 재열기를 검증했다. 공개 Markdown/JSON 요약은 CLI allowlist만 사용한다.

## 남은 제한

1. 운영 인증·mutation 정책과 source qualification owner가 미확정이다. 기본 OFF, opt-in 후에도 private API는 BLOCKED_AUTH다. 합성 fixture header를 운영 인증으로 쓰지 않는다.
2. C4 genuine source/owner identity가 해결되지 않았고 로컬 ROS가 없다. QoS UNKNOWN/history=0를 허용하거나 GID/epoch를 위조하지 않았다. C4 native marking/clearing/planner/actuator PASS가 아니다.
3. C1 opaque asset의 제품 decoder/등록 정책은 미확정이다. 캐시·hash·byte 경계 테스트는 인수했지만 화면에서 임의 디코딩하지 않는다.
4. 기존 Maps historical open/poll 경합은 결정적으로 재현되며 남아 있다. 해당 생산 파일은 I0에서 수정하지 않았다.
5. 실장비 배포·주행, 능동 충돌 보호, C0 결합, 운영 지도 설치는 모두 수행하지 않았다.
