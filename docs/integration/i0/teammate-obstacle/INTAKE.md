# 팀원 콘 표시 후속 인수

기존 완료는 `cdf9e04e3da6478409c19c2be3e1e35a58b229be`, 보존 커밋은 `595c32176143504b8c7ed472645e1e1a8cac1c2d`다. [CHECKPOINT.json](CHECKPOINT.json)은 기존 문서 해시와 정확한 최종 HEAD의 두 workflow/네 job 성공을 보존한다. 당시 Python 3370/35 skip, JS 776/2 skip, 기존 browser227·mission10·제품9 PASS다. 체크포인트 파일 생성 당시 진행 중이던 fresh Python tail은 최종 결과가 아니다. 이번 재실행 완료값은 [BASELINE.json](BASELINE.json)에 분리했다. 기존 HANDOFF/RESULTS는 덮어쓰지 않는다.

ZIP SHA256: `81661d5f3c64f30543b939949b0d5ffe1cf1777f65555dfd7c0206c34388fe2c`. CRC PASS, 합계 1.1MiB 미만, 절대경로/상위경로/symlink 없음. 임시 검토 영역에만 풀었고 패치 내 명령은 실행하지 않았다. `git am`, 전체 merge/cherry-pick, 원본 base에 적용됐다는 가정은 사용하지 않았다. 원본 author는 `hjj021717-netizen <256090870+hjj021717-netizen@users.noreply.github.com>`이다.

| 원본 commit | 역할 |
|---|---|
| 447d45e9451a6dcc0f718e8a78dc80041ce37998 | Python store/validator/scenario/GET |
| ff5d228fec28c811e393eb105973a70b504ed707 | cone silhouette/client/Live Mapping/E2E |
| 42da84fc26b450cd16e8a7258b39dedd5f25b465 | simulation 문서 |

원본 base는 `846121b4988ed2932d329020857925558f8f2c79`. 실제 diff는 17개 경로, app.py +4/-2, app.js +10, scene3d.js +90, 공용 backend +27이다. 신규 E2E는 단독 test 선언6개 + viewport 반복2개 = **8개**다. 원본 Python3188/JS725/E2E233 중1 실패라는 보고는 이번 실행 결과로 재사용하지 않았다. 원본8개를 완료된 I0에 직접 실행하지 않았으며 대응 시나리오를 실제 C1/C3 제품 테스트로 이식했다.

| 원본 경로 | 처리·사유 |
|---|---|
| robot_dashboard/obstacles.py | **변형 채택**: exact keys, bool/finite/range/duplicate ID/64개 검증을 cone_input.py의 순수 validator로 옮김. store/feed/환경변수 frame override는 미채택. scenario 변환은 cone_demo.py로 이식, 원 frame 유지·합성 공간 제한·파일 제한 강화 |
| robot_dashboard/api/routers/obstacles.py | **미채택**: 새 API 필요 없음. 기존 authenticated C1 snapshot/scene context 사용 |
| robot_dashboard/app.py | **미채택**: 기존 I0 bootstrap으로 충분. 현재1597줄, guard<1600 유지 |
| robot_dashboard/application/runtime.py | **미채택**: 두 번째 runtime owner/자동 source 설치 불필요 |
| tests/test_api_contract_phase8.py | **미채택**: route 증가 없음. 원래 API 계약 보존 |
| tests/test_obstacle_store.py | **변형 채택**: strict 거부14개 이식. 동등 stamp 수신 시 TTL 갱신 기대는 반대로 바꿈. C1 동시성/원래 receipt/명시 reset 검사 추가 |
| tests/test_obstacle_simulation.py | **변형 채택**: 실제 committed scenario·치수/frame·파일/JSON 검증 재사용. frame override·GET refresh 성공 기대 미채택 |
| tests/test_obstacle_api.py | **변형 채택**: 실제 C1 HTTP의 401/404/503/no-store/405·bounded response·GET 무갱신으로 대체. 별도 FastAPI TestClient 의존 추가 없음 |
| robot_dashboard/static/features/obstacles/cone_map.js | **미채택**: duplicate client/store/poller와 lifecycle 결함. 기존 C3 consumer/scene subscription 사용. 30초 상한 backoff·toggle/state 테스트 의도는 재사용 |
| robot_dashboard/static/scene3d.js | **변형 채택**: 16개 base point+silhouette 모양만 C3 draw.js에 이식. 기존 public projectWorld 사용; 공용 파일은 변경0 |
| robot_dashboard/static/app.js | **미채택**: 기존 /extensions hook 사용. 현재6873줄, guard<6900 유지 |
| robot_dashboard/static/index.html | **미채택**: C0 Live Mapping/Goal/Initial 보존; C3 scoped checkbox 기본 OFF |
| robot_dashboard/static/styles.css | **미채택**: 제품 scoped CSS에서 배지/라벨 대비와 줄바꿈만 보완 |
| tests/e2e/dashboard_backend.mjs | **미채택**: I0 cleanup을 과거 fixture로 덮지 않음. 새로운 tests/integration_i0/cone_fixture는 실제 C1을 사용 |
| tests/e2e/obstacle_map.spec.mjs | **변형 채택**: toggle·pixel·frame·stale·source unavailable·뷰포트 시나리오 재사용; 실제 C1 HTTP, 4폭×2테마, pending/pause/cleanup 등11개 |
| tests/test_obstacle_cone_map.mjs | **변형 채택**: dimensions/projection/expiry/off/backoff 의도 이식. 초과/잘못된 object를 잘라 정상으로 보이는 기대는 미채택; ingress 전체 거부 |
| docs/OBSTACLE_MAP_DISPLAY_SIM.md | **변형 채택**: provenance·문서상 치수와 실제 scenario 구분 보존. 잘못된 frame 선언 허용/미제공 real node 연결 전제는 제거하고 본 문서군으로 대체 |

C0 시작 관측 HEAD는 `2ff4f84a77d421b8bf3cd93b10e96bca16793cf0`. 이전 마감 뒤 navigation initialization proposal/preparation 코드와 공용 E2E fixture가 진행됐다. main 대비 C0 app.js +30/-8, shared backend +17, app.py/scene3d.js 차이0이었다. I0 후속은 위 네 공유 파일을 **기존 cdf9e04에서 한 줄도 변경하지 않았다**. C0의 proposal/명시 match/높이·자세/관측 provenance를 인수하거나 활성화하지 않았다.
