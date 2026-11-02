# C0 새 PC 재개 — 비이동 검증 결과

결과 ID `C0-ACCOUNT-RESUME-20261101-01`. 인계 팩의 과거 관측과 이번 실행을 구분한다. 사용자는 로봇 충전 중이며 전원을 켜기 전 가능한 작업을 진행하도록 요청했다. 장비 조회·변경·배포·관측·이동 창은 열지 않았다. 자동화·별도 채팅·확장 브랜치 통합도 없다.

## 최초 결과표 → 수리 → 최종 검증

| 항목 | 1차 결과 / 발견 | 수리 후 결과 |
|---|---|---|
| 인계 무결성 | MANIFEST의 44파일 크기·SHA-256 일치, 누락·추가 없음 | 원본 보존 |
| checkout 복원 | 기존 PC 경로 없음. 지정 C0 브랜치의 clean HEAD `49ed9e7c9d8ec5a616d4c6f8cd04789147159e88`에 patch check 후 1회 적용, 6파일 hash 일치 | 기존 C0 브랜치에서만 작업 |
| 게시된 HEAD CI | run `41280885114`: Ubuntu24/Python3.12 카메라 교정 1건 timeout, 전체 FAILURE, 해당 job의 mission API 생략 | 과거 run 재실행 없음. 새 commit CI는 별도 결과 |
| Python 전체 | 3,315건: 3,313 PASS / 2 SKIP, 134.826초 | 같은 3,315건: 3,313 PASS / 2 SKIP, 133.736초 |
| Node 전체 | 78개 파일 PASS | 720개 세부 test PASS (79파일), 1.478초 |
| JS 문법 | 113개 module PASS | 113개 module PASS |
| 브라우저 전체 | 260건: 256 PASS / 4 FAIL, 8.9분. 새 실제 ASGI 진단 계약 시험 4건에서 UI 필드 누락 재현 | 260 PASS, 8.3분 |
| mission localhost 실제 API fixture | 10 PASS, 41.8초 | 관련 소스 무변경으로 불필요한 재실행 없음 |
| 소켓 시험 fixture 수명 | page close 뒤 timer 1개 잔존, send 1→2 재현 | timer 0개, 추가 send 0회; 5개 수명 회귀 사례 PASS |
| 정적 검사 | ruff PASS, mypy 4파일 PASS | ruff PASS, mypy 4파일 PASS, diff whitespace PASS |
| 비밀정보 / 의존성 | tracked source scan PASS, npm 설치 audit 취약점 0건 | 게시 대상으로 stage한 뒤 source scan PASS. Python 온라인 취약점 audit은 로컬 NOT_RUN |
| 장비 SHA·지도·TF·Nav2·센서 | NOT_OBSERVED | NOT_OBSERVED |
| 배포·P1/P2·dwell·경사로 | NOT_RUN | NOT_RUN |

전체 1차 결과를 남긴 후 최소 수리와 2차 검증을 구분했다. 최초와 최종 PASS를 합산하지 않는다. 인계에 기록된 별도 127/19/4건이나 과거 전체 Python 결과도 위 수치에 합산하지 않는다. 최초와 최종 시험 각각 전후 소스 SHA-256을 비교했으며 시험 중 소스 변경은 없었다. 최종 소스 검증 뒤에는 이 결과 문서만 갱신했다. 정확 게시 SHA와 그 SHA의 CI 결과는 해당 GitHub commit에 연결해 기록한다.

## 구현 범위와 재현 근거

인계의 backend 수정은 느린 지도 검증·health·handoff 처리 후 새로운 동일 시각 cloud/pose pair를 취득하고 응답 직전 freshness를 다시 확인한다. source identity·stamp regression·교정·지도 세대·session fence를 유지한다. 최초 거절 단계, 당시 sample, 검사 조건, 구간 경과 시간을 bounded diagnostics로 제공한다. 복원한 backend 및 Python 회귀 시험 4파일은 인계 최종 hash와 동일하게 보존했다.

최종 backend가 반환하는 `failure_sample`, 구독 session/graph 식별자, 상태·단위·포인트 수·세션 시작 후 수신 여부, 추가 machine code를 UI가 일부 버리는 통합 차이가 있었다. UI가 이 항목을 형식·길이·enum 범위 안에서 보존하도록 수정했다. 실패 당시 sample을 나중 검사 값으로 대체하지 않으며, 미확인은 null로 남긴다. 기존 지도/세대 일치 및 10초 진단 표시 제한과 XSS 방어는 유지한다. 이 진단은 입장 gate나 실제 위치 정확도 판정에 사용하지 않는다.

새 브라우저 계약 시험 4건은 합성 manager/session/agent를 실제 FastAPI ASGI GET 경로와 실제 `asyncio.to_thread`로 실행해 응답을 얻는다. 성공·수신시각 누락·source 변경·구독 식별정보 누락 응답을 UI에 전달해 backend/UI 계약을 비교한다. 브라우저의 나머지 환경은 mock이며 실제 ROS·센서·장비 통합을 뜻하지 않는다. 기존 localhost mission API fixture 10건과도 구분한다.

과거 실패 trace SHA-256은 `12a0b8150eb8fc438150e2686e91a39bc2afbd4597cdd94fd54c7e027077dc6d`다. 해당 trace에서 이전 dashboard/live-observation 시험의 주기적 전송 호출 13,367개가 관측됐다. page close만으로 socket onClose가 불리지 않는 조건에서 timer가 남는 별도 결정적 재현을 확보했다. 시험 fixture가 socket close 또는 page close 중 먼저 오는 시점에 interval/reconnect timeout을 한 번 정리하도록 보완했다. **이 누수가 과거 카메라 timeout에 기여한 정도와 단독 원인 여부는 미확정**이다. 로컬 전체 1차에서 기존 카메라 사례가 통과했다는 사실만으로 과거 실패를 해소됐다고 처리하지 않는다.

## 실행 환경과 검증 한계

Ubuntu 24.04 / Python 3.12.3 / Node 20.20.2 / Playwright 1.62.1 / Chromium 151.0.7922.34(revision 1234). Node 배포본은 공식 SHA-256과 대조했고 JavaScript는 기존 lockfile의 `npm ci --ignore-scripts`를 사용했다. Python 패키지 온라인 설치가 연결 실패해 로컬 설치본을 별도 임시 venv로 복사했다. numpy 1.26.4, scipy 1.11.4, jsonschema 4.10.3, OpenCV 4.10.0.84다. OpenCV는 로컬 full distribution이며 CI의 headless distribution과 다르다. fresh PyPI resolution, Python 온라인 취약점 audit, 로컬 coverage 수치는 이번 결과에 포함하지 않는다. CI의 별도 OS/Python matrix·의존성 audit·coverage·기존 competition offline job 결과를 별도로 확인해야 한다.

Python 최초 sandbox 실행은 `asyncio.to_thread` executor 종료 hang으로 중단됐다. 단순 독립 probe에서도 같은 현상을 확인한 뒤 sandbox 밖에서 실제 thread를 사용해 전체 실행했다. thread를 inline fake로 바꾸지 않았다. ruff 실행 파일 누락은 검증 환경의 파일을 보완한 뒤 해결했다. Node sandbox reporter는 파일 단위로 출력하여 최종 세부 수치는 sandbox 밖의 Node test runner 결과로 기록했다. 이들은 제품 실패나 PASS로 합산하지 않는다.

Python SKIP 2건은 optional SVG plotting dependency와 optional rosbags backend 부재다. `C2_CROSS_REQUIRED=1`로 기존 비교 시험이 필요한 정확 과거 object를 fetch했으나 확장 브랜치를 merge하지 않았다. 센서 신선도·본체 축·정합 품질·정지 gate, 주행 설정, 속도·yaw tolerance·progress checker·후방 가중치는 변경하지 않았다.

## 과거 pin과 현재 미확인 항목

마지막 기록상 배포는 `c414a519bd18ece9ecf46469074046bb94dac33e`이며 현재 장비 실행 SHA로 확인하지 않았다. W05는 READY 후 `OBSERVATION_STALE_OR_SOURCE_INVALID`, proposal POST 0회로 종료·복구됐다. 느린 검증 중 구 pair 만료 및 늦은 handoff 이후 evidence 노후화는 합성 재현이다. **W05의 실제 원인은 미확정**이다.

| 항목 | 인계의 과거 값 — 현재 장비 확인 아님 |
|---|---|
| map1 ID | `49ea555eea2f4ca1adaea223` |
| map1 revision | `c9ad9bcc4c8b7c02a47a0db5822707853110b60cb4b9ef837e42b0c32e3c823e` |
| map1 content SHA | `930e7be693eac04fabeed0974031b0dccef4351c2365b6abd274fa4646be191c` |
| map1_2D ID | `2fc7070075fd522860e67480` |
| map1_2D revision | `f691b8e98e81de784c89f98127de9f4ccff4aa487c76747b860bdd70a523cc76` |
| calibration SHA | `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226` |
| navigation parameters revision | `9a47e9d4a6c0d2b5beb0664cc1370a7bf6b70d647418815c5381f196d335645a` |
| P1/P2 annotation revision | `c639ebe083cd57a0dd1dcbe61703cecc08eff51e4a6974fd10ef75a95d7a345a` |
| active policy | `ALL_DIRECTION_BASELINE`; rear policy 미채택/비활성이라는 과거 기록 |

우선순위는 다음과 같다.

1. 게시된 정확 SHA의 새 CI와 미검증 항목을 별도 기록한다. 이전 실패 run은 재실행하거나 성공으로 치환하지 않는다.
2. 전원 재개 후 현재 장비 변경 담당·현장 정지 조건을 확인하고 read-only 상태부터 실제 SHA·지도 ID/revision/계보·교정·현재 적용·P1/P2 결합을 확인한다. 지금 값은 모두 미확인이다.
3. 새 비이동 관측 범위에서 W05와 같은 센서 증거 실패의 최초 단계·당시 sample·신선도를 수집한다. 잔차·겹침·갱신 횟수와 단일 TF/Nav2 반영을 확인하되 이를 실제 위치 정확도라고 부르지 않는다.
4. 위 의존 조건을 충족한 뒤 현재 정지/회수 수단·새 목표/경로/횟수/시간을 한 번 확인한 시험창에서만 P1 → 실제 Nav2 성공·정지·dwell → 시험 녹색 버튼 → P2와 경사로 연속성·URDF 표시를 검증한다. 정밀 도착 오차와 stop-and-go 성공은 별도 결과다.

## 보존과 복구 경로

원본 인계 팩, 적용 전 base, 최초 실패 로그 및 각 snapshot hash를 로컬 evidence 폴더에 보존한다. 원시 센서·지도·개인 증거·인증정보는 신규 Git 기록에 포함하지 않는다. 이 변경은 미배포이므로 장비 원복을 수행하지 않는다. 소스 문제가 확인되면 게시 commit을 역으로 적용하는 새 revert commit을 검토하며 기존 이력을 reset/force-push하지 않는다.

오프라인 소스 archive/manifest를 만들더라도 배포·활성화 패키지나 현재 장비 base 확인을 뜻하지 않는다. 이후 실제 배포는 현재 base·보호파일을 확인하고 기존 검증된 backup/selector/restart 및 복구 절차를 확보한 뒤 별도 수행해야 한다. 과거 private deployer/백업은 새 PC에서 확보되지 않았고 `99d5681`용 도구를 실행하지 않았다. 배포·비이동 센서 관측·실제 이동은 각각 NOT_RUN이다.
