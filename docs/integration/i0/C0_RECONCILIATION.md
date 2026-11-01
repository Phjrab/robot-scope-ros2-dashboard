# C0와 추후 결합

시작 C0 HEAD는 4f90612379705b7b7c8c86cca99941266e3ae611이다. 요청 문서의 과거90b8d5c보다 진행됐음을 확인하고 최신 HANDOFF/NAVIGATION_PAIR_RESULTS/RESUME_AFTER_CHARGE를 읽었다. 이는 근거 자료이며 C0에 지시를 전송하지 않았다. 최종 ref 관측은 RESULTS.json에 별도 기록한다.

C0의 map1/map1_2D pairing, INITIAL_HEIGHT_TILT_REQUIRED, 명시 map match, 관측 준비 입력과 실제 seed/goal 구분을 유지한다. 문서의 과거 배포·속도·tolerance는 I0가 현재 장비에서 재검증한 값이 아니다. I0는 이를 하드코딩하거나 준비 상태를 승인하지 않았다.

| 파일 | I0와 main 차이 | 시작 C0와 main 차이 / 추후 적용 |
|---|---|---|
| app.py | configure_expansion, OFF index 동일, ON 링크 | 시작 C0에서는 동일. 최신 C0 app에 이 얇은 hook만 수동 적용, lifespan/auth 확인 |
| static/scene3d.js | finite XYZ를 기존 _project에 위임하는 projectWorld | 시작 C0에서는 동일. 공개 메서드만 추가, renderer 덮어쓰기 금지 |
| static/features/maps/saved_scene.js | 빈 기본값 displayOptions 인자 | 시작 C0에서는 동일. 기존 호출/Goal/Initial 동작 유지 |
| static/app.js, index.html, navigation.js | 수정 없음 | C0 준비 패널·seed/측정/stale 구분 보존. I0는 기존 index에 링크만 동적으로 추가 |
| navigation_runtime.py, preparation UI/inputs | 수정·인수 없음 | C0 pairing/height/tilt/명시 match/관측 ownership 보존 |
| saved_maps.py, map_editor.js, calibration/presets | 수정 없음 | C0 변환·계보 보존. I0 resolver adapter와 최신 메타데이터 재검증 |
| static/go2_official_model.js | 수정 없음 | C0 pose-origin·INITIAL/GOAL/현재 측정 구분 보존. I0 슬롯은 별도 renderer |
| E2E fixture2개 | page/context에서도 interval/timeout 정리 | C0 fixture의 추가 변경을 보존하며 idempotent cleanup만 이식 |

양방향 비교: `git diff <main-pin> <C0-pin> -- <file>` 및 `git diff <main-pin> integration/20261101-expansion -- <file>`. 결합은 지금 수행하지 않았다.

1. 합의한 시점의 최신 C0 HEAD/배포 상태는 C0 소유자가 고정한다. I0는 시작/최종 두 번의 Git ref 관측만 한다.
2. 운영 인증·Origin·mutation gate와 metadata qualification owner를 정한다. 없으면 BLOCKED_AUTH다. runtime/ROS source ownership은 별도 검토한다.
3. 전용 모듈은 명시 경로로 인수하고 세 생산 공유 파일의 작은 hook만 최신 C0 위에 적용한다. 과거 app/navigation/지도 파일로 덮어쓰지 않는다.
4. 전부 OFF에서 C0 pairing/preparation, 높이·roll/pitch 부족, INITIAL/GOAL URDF, 현재 pose stale, STOP/Cancel·lease·watchdog를 회귀한다. 없는 값을0으로 채우지 않는다.
5. flag별 합성/기록 검토를 수행한다. 리뷰 지도는 별도 승인·다중 원본 family 설계 없이는 운영 설치하지 않는다.
6. C4 genuine per-message identity 또는 검토된 graph evidence와 격리 환경을 먼저 확보한다. 이후 marking→clearing근거→plan변경→simulated actuator를 별도 검증한다. 실제 배포·주행은 별도 승인/C0 운영 절차를 따른다.

최종 관측: main은 기준 SHA 그대로이며 C0는 `7321251f36ede748c73f8252f913b4cf2ac91fbd`다. 시작 이후 `0a9fdd0`/`7321251` 두 문서 커밋이 추가됐다. `git diff <start-C0> <final-C0> -- robot_dashboard`는 비어 있어 위 생산 파일 비교는 여전히 유효하다. C0 checkout/실행환경은 변경하지 않았다.
