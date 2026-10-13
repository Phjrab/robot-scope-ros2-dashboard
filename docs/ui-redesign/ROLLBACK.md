# UI rollback

적용 대상은 `codex/ui-robot-scope-mission-control`의 이 UI 리디자인 커밋 한 개다. 운영 배포는 이번 작업에 포함되지 않았다.

## 소스 복구

1. `git status --short`로 작업 트리를 확인하고 다른 미커밋 변경을 별도로 보존한다.
2. `git log --oneline --grep="Redesign dashboard as Robotics Mission Control"`로 UI 커밋을 확인한다.
3. 검토한 UI 커밋만 `git revert <UI_COMMIT_SHA>`로 되돌린다. 다른 기능 커밋·저장 데이터는 rollback 대상에 넣지 않는다.
4. 기존 정적 자산 실행 방식으로 이전 UI를 확인한다. 원격 push·서비스 재시작·배포는 별도 운영 절차다.

## 브라우저 preference

- layout schema v1, profile별 저장 key, import/export 형식은 유지했다. 기존 applied/default layout이 builtin보다 우선한다.
- v0 migration은 읽는 동안 메모리에서만 수행한다. 손상된 원문도 fallback을 띄우는 것만으로 덮어쓰지 않는다. 신규 E2E가 원문 byte 보존을 검증한다.
- 사용자가 Edit → Apply 또는 기존 layout 저장을 명시적으로 누르면 현재 UI preference를 저장한다. 이 명시적 저장은 이전 preference를 갱신할 수 있으므로 중요한 사용자 layout은 기존 Export 기능으로 사전에 보관한다.
- rollback 시 localStorage 전체 삭제가 필요하지 않다. export한 layout을 기존 preview/import/apply 경로로 복원할 수 있다. ARM·lease·deadman·mission 실행 상태는 layout에 저장하지 않는다.
- DB, 지도, dataset, 모델, ROS 설정은 변경하지 않았으며 데이터 삭제·복구 명령은 필요하지 않다.
