# A1 1차 마감 후 진단과 2차 확인

1차 JSON SHA256 `d9c035bddd6a2bee87ab2a55dd8b7439e4f22b538a925c3776de83533caeebb9`을 유지했다. 이후의 장소 확인, 배포, 정지 시험은 [현장 기록](FIELD_SESSION.md)에 구분했다.

| 사건 | 관측·원인 | 적용 및 2차 결과 |
|---|---|---|
| 입력/초기화 | 1차는 선택 쌍·정지 관측이 없었다. 이후 운영자가 지도와 다른 장소라고 확인했다. 지도 목록에는 이름이 비슷한 2D revision 2개가 있었다. | 실제 3D 계보와 P1/P2 주석이 결속된 revision을 읽었다. 장소에 맞지 않는 선택·초안·proposal·INITIAL POSE를 만들지 않았다. 관측 중 MAP_PAIR_REQUIRED 확인. |
| 실행본/인계 | 기존 `4ff0e474`와 후보의 준비 API/코디네이터 소스가 달랐다. 기존 장비는 유효한 python -m 실행이었다. | 고정판 사전 import 및 양 실행본 전환. 과거 PROCESS_MODULE_ARGUMENT 원인은 미확정으로 유지. 정지 세션 stop 수락·실제 비활성 및 signed hold 해제 확인. geometry 기반 journal과 Nav2 인계는 현장 의존. |
| 배포 경합 | 구판 브리지 PID 0 직후에는 해당 제품 종료 operation이 진행 중이었다. 안전한 lifecycle이 dashboard stop을 거부했다. | 기존판 복구 후 절차에서 해당 operation ID/succeeded와 유휴 재검사를 기다렸다. 같은 후보와 안전 조건으로 두 서비스 전환 성공. 제품 코드는 변경하지 않았다. |
| 지도 목록 조회 계측 | 최초 GET은 HTTP 200/51개였고 재연결 후 별도 수집기의 6초 예산 안에 목록 응답이 오지 않았다. 첫 수집기는 누락된 maps 키에서 중단됐다. 서버 지연 원인은 미확정이다. | 수집기에서 timeout을 보존하고 파일·계보·주석과 다른 GET들을 독립 검증했다. 제품 timeout·지도 내용은 수정하지 않았다. |
| OS·테스트 환경 | 첫 macOS 전체 3,652건, 실패 7·오류 192·skip 40. Linux /proc 미제공 및 임시 경로의 심볼릭 링크 금지 등이 원본 로그에 있다. 초기 unittest discovery/선택 runner 오류도 보존했다. | 실제 임시 경로로 동일 suite 재실행 3,652건, 실패 12·오류 61·skip 40. Linux /proc 및 임시 계층의 교정 소유권 가정 등은 남았다. Linux exact-SHA CI와 별도 판정. 소유권·경로·신선도 검사를 완화하지 않았다. |
| 센서/C4/측정 | 과거 격리 C4 run은 QoS UNKNOWN/depth 0으로 ingress/publish 0. 이번 실제 장비의 graph는 cloud·pose 모두 단일 endpoint와 관측된 QoS를 제공했다. | 실제 metadata 4건을 현재 subscription_evidence_key로 재생. 각 receipt 시점 4/4 허용, graph 관측 후 3.001초에는 4/4 만료. 원본 integer receipt ns, mapping·TF·선택 세대 없는 새 adapter의 field ingress 및 costmap marking/clearing·planner·actuator 미실행. |
| 접근/회전/정지/화면 | 지도 공간이 달라 목표를 보내지 않았다. 동작 결과·정지 오차·경사로 보정·렌더 연속성 측정값이 없다. | yaw·속도·progress·가중치·맵·교정 튜닝 없음. 다음 지도 현장에서 승인된 1회 시험으로 평가. |

Humble rclpy 3.3.22의 take_message는 두 타임스탬프만 노출하고 일반 executor는 메시지만 콜백에 준다. 그래프의 GID를 메시지별 신원으로 승격하지 않았다. 새 경로는 비활성, URDF는 ADVISORY_ONLY다. [Humble native binding](https://github.com/ros2/rclpy/blob/3.3.22/rclpy/src/rclpy/subscription.cpp) · [executor](https://github.com/ros2/rclpy/blob/3.3.22/rclpy/rclpy/executors.py)

후속 REPLAY 배포의 첫 OWNERSHIP 거절은 원문 누락으로 원인 미확정이다. 두 번째 전환과 원복 직후의 거절은 `system/ownership-readback`이 잠금/대기자 존재 시 `pipeline_coordination / owners_not_sampled`를 반환한 것이며 제품의 정상 보수적 동작이다. 배포 도구가 이 응답을 즉시 최종 실패로 판정한 문제가 있었다. 정확한 미조회 상태에만 제한 시간의 읽기 재시도를 추가하고 실제 busy/unknown·서비스 admission·정지·해시 검사를 유지했다. 세 번째 전환, 실제 브라우저 대표 검사, STOP 1회와 자산 보존이 통과했다. [시간·최초 실패·복구 근거](FIELD_SESSION.md#replay사용-안내-후속-배포--13541402-kst)

## 여러 지도 실사용 연결 — 배포 전 진단

최초 7행 상태표를 별도 비공개 증거에 고정했다. M00 정지·소유권 PASS, M01 직접 HTTPS와 M02 검토 로그인은 NOT_CONFIGURED, M03 지도 자격 INPUT_REQUIRED, M04 정합/저장 BLOCKED_DEPENDENCY, M05 기존 기능 회귀와 M06 보존/복구는 NOT_RUN이었다. 이후 운영자가 두 입력의 같은 장소·실지도 성격을 확인했다. 원본 신원과 사본 신원을 구분하고 확인되지 않은 capture session/epoch는 비워 둔다.

확정 선행 원인은 장비 HTTPS·검토 저장소·ReviewInputs 연결 부재다. 기존 정합·품질·C1 저장 알고리즘은 변경하지 않았다. 최소 연결 변경은 선택적 직접 TLS(앱 lifespan 1회), 별도 사본 manifest 공급자, HTTP 확장 링크의 HTTPS 이동, 복사 원본 신원 표시, 정지 배포용 시작 STOP 옵션이다.

처음 로컬 회귀 15건의 1 FAIL/1 ERROR는 HTTP 검사 클라이언트 자동 redirect 및 macOS native subprocess의 TMPDIR/PATH에서 발생했다. 실제 TLS 주소를 자동 방문하지 않는 HTTP redirect 검사와 정규화한 시험 환경으로 15건 PASS를 확인했다. 전체 검사 첫 실행은 3677건, FAIL 14/ERROR 61/skip 40이었다. 기존 Mac 기준의 73개 실패 이름과 동일한 항목 외 신규 2개는 app.py 1600줄 제한 위반이었다. HTTPS/default 실행 분기를 별도 실행기로 이동하여 앱 크기 제한을 유지했다. 최초 결과는 덮어쓰지 않는다. Linux exact-SHA CI와 이후 장비 결과를 독립적으로 확인한다.

수정 후 최종 로컬 전체 검사 3677건은 FAIL 12/ERROR 61/skip 40이며, 실패 이름 73개 모두 기존 Mac 기준과 일치한다. 관련 59건 및 JavaScript 763건 PASS, Ruff·Mypy·secret scan·frontend syntax PASS다. exact Linux CI 완료 전 현장 전환하지 않는다.
