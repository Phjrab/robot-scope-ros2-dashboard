# C0 독립검토 후속 — 실패 당시 진단값 보존

결과 ID `C0-ACCOUNT-RESUME-20261101-02`. 검토 base는 `a8b501470b4041e1cf49a02b2c3af7a0787a9be3`다. 이 base의 [CI 41284662629](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41284662629)는 세 job 모두 SUCCESS다. 두 OS 각각 Python 3,315건 중 3,313 PASS/2 SKIP, coverage 79%, Node 720 PASS, browser 260 PASS, mission 실제 API fixture 10 PASS다. 이것은 아래 후속 수정 전 snapshot의 결과다. 과거 `49ed9e7` CI의 FAILURE도 별도로 보존하며 재실행하지 않았다.

사용자 요청으로 새 C1.1~C1.4 채팅을 `gpt-6.1-terra / xhigh`로 생성한 후 같은 base를 독립 검토했다. 모두 공유 소스와 장비를 변경하지 않고 각자 결과를 기록했다. C0가 발견 사항을 수리·통합한다. [최초 복원·통합 결과](ACCOUNT_RESUME_RESULTS.md)는 당시 상태를 나타내며 이 후속 결과와 합산하지 않는다.

## 독립 결과와 최소 수리

| 역할 | 독립 결과 | 후속 조치 |
|---|---|---|
| C1.1 backend | FAIL: health 뒤 중간 source 검사에서 표본이 만료되면 이미 취득한 sample이 `failure_sample`에 남지 않음. 합성 당시 age 1.12초, evidence 거절/reference null은 유지 | 두 snapshot을 순서대로 보존하고 검사 시각을 source 판정과 진단에 공유. 예외에서도 취득한 쪽만 보존하고 미취득 값은 null로 유지 |
| C1.2 UI | FAIL: server가 `CLOUD_UNITS`로 거절한 실제 단위 `mm`를 UI가 null로 바꿈. bounded 상태 문자열에도 같은 불일치 가능 | 진단용 units/state/graph_state를 길이·통제문자 제한 내 문자열로 보존. 실제 ASGI의 잘못된 단위·알 수 없는 상태 2사례 추가 |
| C1.3 검증/배포 자료 | PASS: 2,281개 Git/manifest/archive 파일 집합·내용·실행 비트 및 로그 수치 일치 | tar mode는 0664/0775이고 Git은 100644/100755. 실제 배포 전체 mode/소유권·runtime links·현재 base·보호자료·HTTP는 미확인으로 유지 |
| C1.4 W05/경계 | PASS: 보존 보고와 capture-order 19건 대상 4파일 hash 일치; 다음 정지 관측의 증거표 작성 | private W05 원본 JSON은 이 PC에 없어 직접 재검증 BLOCKED. W05 실제 원인은 미확정 |

새 반례는 수정 전에 Python 2 FAIL 및 실제 ASGI→브라우저 2 FAIL로 별도 보존했다. 두 Python 사례는 health 지연 후 당시 receipt age/stamp 보존, pose 조회 실패 때 이미 취득한 cloud 보존을 확인한다. 브라우저 사례는 거절된 단위 `mm`, pose state `initializing`, graph state `unresolved`를 검사 당시 값으로 유지하는지 확인한다. 변경된 metadata는 진단에만 사용하며 입장/정합/주행 허용조건을 변경하지 않는다. 문자열은 계속 `textContent`로 표시하고 미지 schema·stage/code 제한, 길이·통제문자·시간·세대 검증을 유지한다.

## 후속 snapshot 검증

| 항목 | 이번 결과 |
|---|---|
| capture-order 표적 | 21 PASS, 0.036초 (기존 19 + 신규 2) |
| preparation browser 전체 | 35 PASS, 41.1초; 실제 ASGI 계약 6사례 포함 |
| Python 전체 | 3,317 실행: 3,314 PASS / 3 SKIP, 125.429초 |
| 추가 skip 보완 | 전체 실행에서 Node 경로 설정이 빠져 생긴 geometry parity 1 SKIP은 정확 Node20 경로 지정 후 해당 1건만 PASS. optional SVG plotting·rosbags 2건은 여전히 SKIP |
| Node / 문법 | 720 PASS / 113 modules PASS |
| 정적 / 비밀정보 | ruff PASS, mypy 4파일 PASS, staged tracked-source scan PASS, diff whitespace PASS |
| snapshot | 전체 2,281파일의 검사 전후 hash 동일; 이후 이 결과 문서만 추가 |
| 후속 exact SHA CI | 게시 후 실행되는 별도 run을 해당 commit 기록에 연결. 이전 a8 CI 성공으로 대체하지 않음 |

전체 Python의 3 SKIP 결과를 임의로 2 SKIP 로그로 고치지 않는다. 별도 parity 보완은 기존 PASS의 반복이 아닌 미실행 항목의 환경 보완이다. 새 수정 후 로컬 browser 260/262건 전체를 실행했다고 주장하지 않으며 관련 35건만 실행했다. 새 exact-SHA CI가 전체 matrix를 검증한다. 로컬 환경과 optional dependency 한계는 최초 결과 문서와 같다.

## 승인·현장·복구 경계

사용자는 이후 필요한 작업과 자동화 재개를 승인했다. 새 계정에는 기존 자동화 설정이 없어 C0에 시간당 후속 확인을 생성했다. 변화 없는 상태 보고와 이미 통과한 검사는 반복하지 않는다. 일반 승인을 현재 전원·물리 정지·회수 수단·구체 시험창의 실측 증거로 사용하지 않는다.

이번 변경은 로컬 구현·검증·Git 게시다. 장비 접근·배포·새 센서 관측·실제 이동은 모두 NOT_RUN이다. 현재 장비 SHA/base·지도·교정·활성 정책은 미확인이다. map1/map1_2D와 P1/P2·주행 설정·ALL_DIRECTION_BASELINE의 과거 pin은 최초 보고를 따른다. 후보 정책 활성화나 확장 브랜치 통합은 수행하지 않았다.

미배포이므로 장비 원복 동작은 없다. 과거 배포 도구를 실행하지 않았으며 source archive는 배포·활성화 패키지가 아니다. 실제 전원 재개 후 승인된 읽기 전용 조회로 현재 base/소유권/보호물부터 확인하고, 장비 변경 전 기존 backup/selector/restart·실패 시 복구 경로를 확보해야 한다. 보존한 최초 실패/독립 probe/검증 로그 및 각 snapshot hash로 소스 변경을 추적한다.
