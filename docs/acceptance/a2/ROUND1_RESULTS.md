# 1차 결과 · 변경 전

dce1e88995e5989d63fab257ea55b8d7d2ab8e24 · 2026-11-05T01:55:41.773970+00:00 · macOS arm64, Python 3.12, Chromium, 로컬 합성 데이터.

|항목|범위|판정|대표 근거|
|---|---|---|---|
|N00|HTTP|PASS|기본 OFF 라우트·worker·원본 index 검사, 미설정 flag 차단.|
|N01|HTTP|BLOCKED_DEPENDENCY|제품 bootstrap에는 인증 주입이 없다. 기본 C1은 401, 인위적으로 읽기만 허용하면 입력 503·변경 403. 독립 테스트 인증만으로 제품 인증이 성립하지 않는다.|
|N02|UNIT|FAIL|poll 대기 중 reading=true, changed=0. 첫 클릭의 상세 GET 0회, 재시도 후에만 404가 표시됐다.|
|N03|REAL_CORE / HTTP / BROWSER|PASS|합성 원본 400점씩. AB 800, ABC와 AB+C 각 1200. 원본 해시·DAG·중복 ancestry 409, PCD 편집/2D 변환 33건.|
|N03.session|HTTP / SOURCE|FAIL|C1 descriptor의 mapping_session_id=null인데 미리보기 input_pin과 C2 화면에는 unverified:<map_id>가 세션값으로 들어간다.|
|N04|HTTP / BROWSER|PASS|C1 단일 구독, 콘 Canvas·TTL·지연·탭 종료·권한 11건. 실제 모델·XYZ·교정과 opaque codec은 INPUT_REQUIRED.|
|N05|REAL_CORE / BROWSER|PASS|C6 합성 parser→picker→seek/비교/요약. 업로드·제어 쓰기 0, 실제 현장 기록은 INPUT_REQUIRED.|
|N06|REAL_CORE|PASS|고정 C7 기준 및 bounded 26개 조합. byte 한도 초과 거부, 큐·캐시·geometry 검증. Jetson·capture-to-render는 미측정.|
|N07|BROWSER|PASS|제품 host 9건에 390/768/1440 dark/light 6조합 포함. DOM, contrast, 탭 종료, 재열기 및 합성 오류 검사.|

첫 실행의 환경 실패도 보존했다. Node 하위 프로세스의 python 경로 누락, loopback bind 제한, 임시 디렉터리 symlink 거부를 확인했다. 준비된 Python, 실제 임시 디렉터리, loopback 허용 후 같은 소스로 I0 Python 45개, 확장 JS 87개(별도 skip 2), 제품 브라우저 9개, 콘 브라우저 11개가 통과했다. C7의 별도 browser-load trace는 NOT_RUN이다.

재현은 저장소 루트에서 node experiments/expansion_20261030/c7_capacity/ci/history_poll_probe.mjs . 를 위 기준 SHA에 실행한다. 이 역사적 probe의 종료 0은 결함 재현을 의미한다. 각 단계 로그 해시, 입력/설정 해시와 시간 측정은 ROUND1_RESULTS.json에 있다.
