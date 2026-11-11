# 진행률 후속 조사 — 2026-11-11, 2회차

기준 소스: `488d279b3a97300db80fd32843008b3e83344c5a`.
운영 코드 변경 없음. `scripts/reproduce_navigation_progress.py`와 그 진단 회귀만 변경했다.

## 실행으로 추가 확인한 것

- production send_goal 및 goal response callback으로 새 goal을 수락하고, 신선한
  map frame의 목표점과 일치하는 endpoint를 `/plan` metrology callback에 전달한 뒤
  같은 거리열을 넣었다. 여전히 initial=.042m, 마지막=.490m, 표시 공식 0%,
  progress rate=0, DEGRADED/GOAL_PROGRESS_TOO_LOW다.
- metrology는 endpoint error=0이면서도 association을
  `OBSERVED_DURING_GOAL_NO_ACTION_UUID`로 유지한다. plan은 합성 endpoint 관측이며
  planner 실행·path 추종·feedback의 해당 path 소비 증거가 아니다.
- 정상 작은 목표 `.0416856 → .030 → .015 → .008`은 initial=.042m,
  표시 공식 약 80.95%, READY다. 작은 양수 모두를 무시하는 임계값은 채택하지 않는다.
- `.838 ↔ .898` 왕복은 진행으로 인정되지 않고 기존 stall deadline을 유지한다.
  거리 증가 때마다 baseline을 reset하는 함수를 메모리에서만 임시 주입하자 새 회귀가
  `last_progress_at: 103.1 != 100`으로 실패했다. 이는 **위험 후보 거절 증거**이며
  제품 시험 통과나 실제 이동 증거가 아니다. 이 함수를 저장하거나 배포하지 않았다.
- goal generation만 다르거나 goal ID만 다른 두 callback도 각각 상태 변경 없이 거절된다.
- 진단의 기존 all(...) 집계는 일부 재현만 남으면 exit 0을 반환할 수 있었다.
  이제 전부 재현=REPRODUCED/1, 일부 재현=PARTIALLY_REPRODUCED/1,
  대조 실패=INCONCLUSIVE/2, 모든 지정 조건 미재현=NOT_REPRODUCED/0이다.
  NOT_REPRODUCED도 장비 통과나 포괄적 수정 완료 판정이 아니다.

## upstream source 확인과 아직 없는 근거

Nav2 tag 1.1.20은 조회 당시 `a097086719c88f781aa59788eca29ac6ca5e56db`였다.
[고정 소스 navigate_to_pose.cpp](https://github.com/ros-navigation/navigation2/blob/a097086719c88f781aa59788eca29ac6ca5e56db/nav2_bt_navigator/src/navigators/navigate_to_pose.cpp)를 읽었다.
initializeGoalPose는 start time/recovery/goal을 갱신하지만 path를 비우지 않는다.
onLoop는 blackboard path에서 거리를 계산하고 현재 pose 및 navigation time과 함께
feedback을 발행한다. 따라서 새 goal UUID·새 pose stamp·작은 navigation time만으로
이전 path 사용 가능성을 배제할 수 없다. 이는 소스 구조에 따른 추론이며 이번 장비의
실행 버전이나 당시 blackboard 전환을 계측한 증거가 아니다.

대시보드의 선택적 `/plan`은 UUID 없는 독립 관측이다. endpoint 일치와 수신 순서만으로
feedback과 결합하지 않는다. 실제 baseline 수정에는 feedback 생산 지점에서 현재
runtime/goal 세대와 소비 path 세대를 결속한 증거, 또는 이전 path 재사용을 불가능하게
하는 검증된 native 불변조건이 필요하다. 새 goal, 동일 endpoint 재목표, replan,
늦은 planner 완료, cancel, 재시작 및 위 정체/왕복 대조를 함께 검증해야 한다.
현재 producer 계약을 바꾸는 패치나 native overlay 후보는 만들지 않았다.

원시 ROS bag replay, 브라우저 거리 실측, 물리 정지/이동 검증은 모두 NOT_RUN이다.
저속 접근 정체와 정지 yaw 잔차는 이 진단의 해결 범위가 아니다.
