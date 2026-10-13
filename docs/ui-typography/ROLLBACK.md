# Typography rollback

기존 리디자인·테마·저장 레이아웃을 유지하며 타이포그래피 전용 커밋만 되돌린다.
현재 브랜치의 로컬 변경을 먼저 확인하고, 사용자 작업과 충돌하면 충돌 부분을 보존하며 해결한다.

```sh
git status --short --branch
git log -1 --format='%H %s' --grep='Apply self-hosted IBM Plex typography'
git revert <위에서 확인한 타이포그래피 커밋 SHA>
```

커밋 SHA는 최종 답변 또는 위 명령으로 확인한다. `reset`, 전체 checkout, stash가 필요하지 않다.
layout/theme localStorage와 backend·map·dataset 데이터는 변경하지 않았으므로 지울 필요가 없다.
최초 구현 단계는 로컬 커밋까지 진행했다. 후속 승인으로 수행한 push·외부 대시보드 배포와 운영 rollback은 [DEPLOYMENT](DEPLOYMENT.md)에 기록했다.

before 자산 기준은 `b0a2f69`이다. 비교 재현 시 `git archive`로 이 commit의
`robot_dashboard/static`만 별도 임시 디렉터리에 추출해 fixture server에 전달한다.
현재 작업트리를 before로 전환하지 않는다.
