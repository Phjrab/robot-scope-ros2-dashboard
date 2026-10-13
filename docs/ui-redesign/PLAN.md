# 순차 구현

1. inventory와 baseline을 확보한다.
2. Mission Control shell/token을 기존 HTML에 적용하고 기본 진입을 Cockpit으로 바꾼다. 기존 hash route는 유지한다.
3. 기존 registry/schema/lifecycle로 Observation / Mapping / Navigation / Dataset Capture preset을 제공한다. Edit/Apply interlock을 유지하고 saved layout을 먼저 복원한다. inspector는 기존 snapshot을 읽고 별도 network owner를 만들지 않는다.
4. Mapping/Saved Maps/Capture/Navigation의 viewport + inspector 구성을 정리한다. Advanced에서 모든 기존 기능에 접근한다. 좁은 화면에서 안전 영역을 유지한다.
5. 기존 suite, 새 fixture 회귀, actual browser captures·geometry·keyboard·contrast·network/mutation evidence를 기록한다.
6. preservation/validation/final/rollback/handoff를 작성하고 자신의 변경만 로컬 커밋한다.
