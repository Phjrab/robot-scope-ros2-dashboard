# Robot Scope 인계 갱신 — 2026-10-23

**최신 오프라인 후속:** 동일 지도 정보 갱신 시 연결 유지 수정, 이동·수신 복구
재현, 미수렴 분석 한계와 미배포 2파일 후보는
[OFFLINE_MOTION_FOLLOWUP_20261023.md](OFFLINE_MOTION_FOLLOWUP_20261023.md)를 따른다.

**최신 저장소 통합:** 열린 브랜치와 최근 UI 병합·검사·정리 내역은
[MAIN_INTEGRATION_20261023.md](MAIN_INTEGRATION_20261023.md)를 따른다.
아래 내용은 각 시점의 장비/분석 기록이며 이번 Git 통합은 장비 배포가 아니다.

**전원 종료 전 추가 승인 수집 완료:** 00:39:26–37 KST 기존 LiDAR 입력만10초
passive 구독했다. raw64,000점×3/converted16,000점×3의 원본CDR·전체payload·XYZ와
선택IMU/odom/lowstate를 맥북에 보존했다.55파일19.3MB의 원격/로컬SHA일치,
지도·설정·기존후보까지88파일의 읽기전용사본이 private
`lidar-passive-20261022T1538Z/frozen/`에 있다. manifest SHA는
`5139c1035956290e6360f00c034620fc9275802e29ed0bb995ba108e242bf18a`다.
연속bag/IMU전체archive가 아니며 원래 잃어버린scan의 복원이 아니다.

새3쌍은 converted가 raw의매4번째XYZ/ring/intensity와 정확히 일치하고,
16ring 중0/4/8/12만 남는다. 기존T고정 거리계산에서전체raw도약23.6cm 잔차라
이것만을과거오류원인으로 단정하지 않는다. 새정합/후보채택/정책변경은없다.
수집자식exit0/reap/group부재,00:42:57전후180hash/14owner/기존서비스identity유지를
확인하고장비접근을끝냈다. 센서·서비스restart·제어·TF·카메라·주행·배포·commit/push0회.
상세형식/한계/새자료분석은 위private root의README.md/ANALYSIS.md/FROZEN_RECEIPT를
따른다. 아래의capture0회는그전완료한분석범위의기록으로보존한다.

**이전 후속은 로컬 저장자료 분석이며 새 배포가 아니다.** GitHub main/로컬 HEAD
`e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`를 확인하고 기존 미커밋 변경을 보존했다.
job1f554b10a68d0220b3d26667의23cm는75cm 이내 대응점의 RMS이며, 전체scan RMS는
44.64cm다. 본체 위치오차가 아니다. 계산 입력16,000점과 표시preview8,000점은
별개다. 11records 중9는2의 중복이고, 기존 기준의 비중복 표시는10개다.
4.254m/179.782° 떨어진 후보4도overlap93.65%여서 모호성은 실제 남는다.

최신 scan bytes는 조사한 로컬 보존범위에서 발견하지 못했다. SHA·frame·epoch·stamp만
남았으므로 예전scan으로 대체하거나 최신잔차를 재계산했다고 보고하지 않는다.
정확한 원지도 bytes/array SHA는 일치했고 점간NN 중앙값3.53cm였다. 과거query YAML의
voxel0.5m는 원지도 생성effective값의 증명이 아니며, 원지도 설정/deskew/clock/축과
body extrinsic은 미검증이다. 고정rigid extrinsic만으로 잔차 원인을 확정하지 않는다.

실제pin7파일/adapter를 감사했다. 기존adapter는5cm gate를branch ranking 전에
제거하고, ambiguity 허용 시conditional RMSE로 표시 후보를 고른다. 이 분석에서
정책·문턱·점수·filter 변경은0회다. 확인된제품metric버그가 없어 제품patch도없다.
private `followup/alignment-cause-analysis/REPORT.md`와 JSON/CSV·재현도구를 남겼고
11고유합성시험을 통과했다. 새capture/registration/benchmark·원격쓰기·배포·restart·
STOP·카메라·tracking·제어·주행·commit/push는 모두0회다. 최신설치는 아래00:12의
static UI로 유지한다. 다음 최소 작업은 별도 범위에서 정확한raw/XYZ·effective설정을
먼저 보존하는 것이며, 이번에는 실행하지 않았다.

**2026-10-23 00:12 KST 실제 후속 완료:** GET 전용 과거 job 선택/재조회 UI와
활성/pending sensor 관측의 간접 STOP 차단을 최소 static3파일로 반영했다. service
restart·STOP 없이 원본185hash/owner/battery 확인·새 백업·조건부 복구를 갖췄다.
정상 Maps 화면에서 기존 job1f554b10a68d0220b3d26667의 SUCCEEDED/HISTORICAL_ONLY,
원본 시각/epoch·모호성 경고·RMSE0.230319m/overlap0.90325 표시를 실제 확인했다.
새 합성64단위·4브라우저, runtime 동일64벡터·통합5, retained JSON replay6조건 PASS.
00:12:13 battery54%/age0.011초 fresh,14owner clear, PID75863/NRestarts0 유지,
bridge OFF/disabled, global generation1/tracking generation0다. 추가 정합·tracking·
카메라·제어·주행·commit/push는0회다. 설치3파일 SHA/원본 metadata/복구 경로와
증거는 [LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md) 최신절 및
private `followup/history-retrieval-ui/`를 따른다. 이전 b68d0c6·미배포 준비 기록은
과거 시점이며 최신3파일 설치 상태로 대체한다. 실제 tracking/본체 정확도는 미검증이다.

**23:45 KST 정적 UI 후속 반영:** 아래 23:31의 JS 미배포 상태는 이 기록으로
대체한다. 실제 d16 통합본을 보존한 `global_observation_contract.js` 한 파일만
반영했다. 설치·HTTP SHA256은
`b68d0c6471eb30618a1c4ec020e7bd6c4ad3cc95dd482d59ec7bb55df3e51313`이다.
dashboard PID75863, InvocationID `64042df9601349f1ad68e689ee8a8247`, NRestarts0이
전후 동일하며 restart·STOP·제어·카메라·추가 정합 계산은 없었다.

첫 설치의 사후 소유권 불확실은 원본 SHA/uid/gid/mode/mtime 복구로 끝났다.
불확실 당시 세부 owner 응답은 저장되지 않아 원인은 확정하지 않는다. 현재
원본 복구와 14 owner clear를 조회한 뒤 같은 엄격한 조건으로 1회 재시도해
통과했다. 최종 원본 백업·metadata·조건부 1파일 복구 스크립트는 로봇의
`/home/unitree/robot-scope-deploy/static-contract-20261022T144218Z-7880e8b5/`에 있다.

실제 새 브라우저에서 18일 PCD 25,666점과 관측 패널 표시·콘솔 오류 없음은
확인했다. **완료 job의 실제 결과 표시 PASS는 아니다.** 새 페이지는 기존 pending을
보유하지 않아 저장 job을 자동 채택하지 않으며, 과거 결과 재조회 UI가 없다.
API에는 기존 succeeded/HISTORICAL_ONLY 결과와 AMBIGUOUS_ALTERNATIVES,
RMSE0.230319m·overlap0.90325가 보존된다. 강제 controller 주입이나 새 계산으로
우회하지 않았고 tracking 시작/중지0회다. 기존 정책에 global seed 경과시간 TTL은
없으므로 단순히 오래되었다는 이유의 정책 거절이라고 보고하지 않는다. 실제
추적에는 현재 입력 age≤1초·동일 map/frame/epoch 및 자원 조건이 별도로 필요하다.

오프라인 35개/26개 관련 시험과 retained JSON replay 결과는 앞선 기록 그대로이며
같은 시험·전체 CI·native 계산을 반복하지 않았다. repo 변경은 local-only,
commit/push 없음. 23:44:37 KST battery63%/age0.008초 fresh, bridge OFF/disabled,
14 owner clear, 주간 remaining39%다. 기존 유한 배터리 기록기는 재사용했으며
중복 watcher를 만들지 않았다. 다음 최소 작업은 별도 범위의 읽기 전용 과거 job
선택/재조회 UI 연결이다. 서비스 재시작이나 새 정합은 이 문제의 검증에 필요하지 않다.

**23:31 KST 최신 관측:** 기존 사용자 `계속 진행` 문맥으로 Maps에서 새 live global을
1회 실행했다. job `1f554b10a68d0220b3d26667`, 18일 원본3D 지도25,666점과
새 converted scan16,000점 전체를 사용했다. job20.959초/runner18.356초,
선택 후보RMSE0.230319m/overlap0.90325/inlier14,452, `AMBIGUOUS_ALTERNATIVES`다.
API 결과 보존 성공과 품질·정확도 합격을 구분한다. 기존 ambiguity 설정을 유지했다.
실제 UID1000 scope에서 memory2GiB/swap0/tasks64/runtime120초 admission을 확인했고,
정확한 cgroup/PID 정리와 watcher 종료, 180개 source hash 보존·14owner clear를 확인했다.

실제 UI는 context JSON의 **키 순서만 다른 것을 값 변경으로 오인**하여
`RESULT_CONTRACT_MISMATCH`로 거부했다. tracking 버튼 disabled/시작0회다.
object key 순서만 무관하게 비교하는 로컬 최소 수정(main 관련35시험,
실제 runtime variant26시험, 실제 retained JSON 오프라인 재생)을 검증했다.
서버·freshness·frame/epoch·품질 gate를 우회하거나 새 계산을 반복하지 않았다.

준비한 **runtime 전용 static JS1파일 SHA**는
`b68d0c6471eb30618a1c4ec020e7bd6c4ad3cc95dd482d59ec7bb55df3e51313`이다.
공개 main 파일 전체를 실제 통합 UI 위에 복사하면 안 된다. 원본 SHA
`4b999b1c27a1c276b666a2b0da00eefbf54f3423f9d5d4b7ad0a6287407c5722`를
재확인·새 백업하고 그 파일만 반영/복구하는 준비이며 **미배포·별도 결정 대기**다.
service restart/STOP은 필요하지 않는다. 앞선 승인 질문의 추가 새 scan 항목은
철회했으므로 수정 검증을 이유로 global을 반복하지 않는다. 기존 UI pending은
이미 invalidated되어 새 코드가 과거 job을 자동 채택하지 않는 점도 보존한다.

23:30:29 KST 배터리68% fresh, cloud10Hz, dashboard PID75863/NRestarts0,
bridge OFF/disabled다. 주간 remaining41%. 이번 관측에서 추가 서비스 restart·카메라·
제어·주행·TF·initialpose·goal·commit/push는0회다. tracking과 실제 본체 정확도,
sensor-to-photon 지연은 미검증이다. private 실행/화면/복구 준비는
`lidar-integration-20261022/live-observation-execution/`에 있으며 상세는
[LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md)의 최신절을 따른다.

**23:01 KST 실제 적용:** 사용자 승인 manifest SHA `7055f7ebf1779b39fdd6379db96b4a93c2a6385d3720cefc9279bbc4b888a0dc`
그대로 제품7개+drop-in을 설치하고 dashboard 정상 restart를1회 요청했다.
새 PID75863/InvocationID64042df9601349f1ad68e689ee8a8247, bridgeOFF/disabled다.
초기 사후검사는 PRESERVED_ENVIRONMENT_DRIFT/exit1이었으나 후속 inspect의 환경은
일치했고 재시작 반복 없이 읽기전용 verify-installed가 통과했다. 초기 오류 원인은
미확정이며 RESTART_INTENT journal을 보존했다. 유효 processing budget은disabled,
resource mode=user_scope_v1, startup30/watchdog60유지,14개 소유권busy/unknown없음,
broker예약없음·Hesai/XT16 preview복귀·CPUquota미추가를 확인했다.81초 간격 두 센서
표본 모두fresh였다.23:01:06배터리76%/age0.014초. 원본backup은 원격
`/home/unitree/robot-scope-deploy/ownership-budget-20261022-7055f7eb/backup`,
실행영수증은 private `lidar-integration-20261022/approved-deployment-execution/`.
새 global/tracking POST/native계산·child자원강제적용·주행은미실행이며 별도단계다.
103로컬시험은반복하지 않았고 commit/push도없다. 자세한 시각·설치hash·한계는
[LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md)의 최신절을 따른다.

**22일 배포 전 기록:** 순수 소유권 GET을 새 private 후보에 구현했다. 제어 만료·STOP 출력·
native 취소 없는14컴포넌트 복사와 유효 execution policy를 제공하며26집중+34주변
회귀가 통과했다. 소스manifest는
`2881fdbed61eb81480f6decbcdb8779d4bb6246c4cf70a507a70b59755359334`.
실제 dashboardPID1006의 budget/resource env키는 여전히 없고0.6초는 운영 적용 중이다.
bridgeOFF/disabled와 broker예약 부재는 확인했지만 구버전 dashboard의 미저장 메모리
부재를 그 근거로 추정하지 않는다. 첫 설치에는 현재 현장/미저장 작업 확인과 기존
종료 safety STOP·Hesai/XT16 preview 재시작 범위 승인이 필요하다. 기존 제품5파일과
저장scan 진단 결과를 보존했으며 서비스·센서·native계산·주행은 재실행하지 않았다.
신규 순수 API·실행설정·시험·배포전제는
[LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md)에 남겼다.

## 2026-10-21 기록

**최신 후속:** 처리 budget 해제와 native child 자원 격리를 연결한 로컬 후보는
동결했고82시험 중81pass/1macOS skip·독립 검토 통과다. manifest는
64c589fba4e16102455f88911ebc37ea6adf37c04bb6071beffb2bcddf36c979.
운영 배포/서비스 재시작은0회이며 PID968의 두 env키는 미설정이라 기존0.6초는
아직 적용 중이다. 20:19 조회에서는 기존 preview만 실행되고 관련 작업은 유휴였다.
배포 wrapper의 SLAM 상태 GET에서 간접 control manager.snapshot 경로를 발견해
무작용 소유권 확인 전제는 미해결이다. 제품 후보 통과와 배포 준비를 구분하며
실기 적용은 보류한다. 사용자가 전원 종료를 문의했으며 새 작업을 시작하지 않은
조건의 정상 종료를 안내했다. 최신 재조회는 응답 없어 결과를 주장하지 않았다.
기존 저장 scan 각3회는 재실행 금지, split은 제품 미채택, 본체 정확도·주행 미검증.
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md)의 최신 절에
실제 해시·시험 종류·운영 미적용·조회 부작용 정정·다음 최소 작업을 남겼다.

**과거 19:48 KST:** 사용자 변경에 따라 새 저장 scan 묶음에는 추가 CPU quota/
native thread cap을 두지 않았고, 순차·분리 각3회만 수행했다. 호출 중앙값은
0.821718/0.687252초(분리16.36% 단축), 시작~정리 전체는2.700431/2.892947초
(분리7.13% 증가)였다. 마지막 분리의 미선택 진단값이 사전 동등성 기준을 넘어
전체 실패 상태를 보존했으며 분리 경로는 제품 미채택이다. 0.6초는 현재 사용자
요청의 중단 기준이 아니지만 설치 제품 파일은 아직 바꾸지 않아 실제 설정에는
남아 있다. 유한 watchdog과 분리하는 로컬 후보는 장비 적용과 구분한다.
10cm/15.6cm는 정합 잔차 비교이며 실제 본체 정확도나 전체 실패 기준이 아니다.
메모리2GiB/tasks64/전체 watchdog과 정리를 유지했다. 기존 서비스·preview·broker/
소스 해시는 그대로, bridge OFF/disabled, 새 센서 구독·로봇 명령·배포·commit/push0.
세부 영수증과 정확한 시각/소스/한계는
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md)의 최신 절을 따른다.
이 묶음의 추가 native 실행은 승인 횟수가 남아 있지 않다.

**과거 19:14 KST:** 사용자가 인증과 직접 실행을 승인한 뒤 동일 자원 사전검사가
통과했다. CPU 200%/100ms·메모리 2GiB·swap0·tasks64 및 자식 cgroup 소속을
readback했고 sudo 정책·부모 controller는 바꾸지 않았다. 이어 정확한 저장 seed/
scan 쌍과 고정 소스로 순차 1회·프로세스 분리 1회 진단을 완료했다. 비밀번호는
파일·argv·영수증에 저장하지 않았다. 아래 18:49 거부와 0회 기록은 그 당시 상태다.

호출 wall은 순차 **0.822107초**, 분리 **0.622600초**로 이번 쌍에서 24.27% 감소했지만
둘 다 운영 0.6초를 초과했다. startup/map 준비는 각각 2.716791/2.514348초로 별도다.
시간 외 결과는 일치했고 모든 분기가 전체 16,000점을 채점했다. 선택 RMSE
0.155819m는 10cm 잔차 비교에 미달한다. 연속 추적·본체 pose·정밀 정확도 통과가 아니다.
운영 timeout/freshness·선택 정책·backend·제품 코드는 유지했다.

실행 7.404초 뒤 해당 unit/자식/runner/새 폴더를 정리했고 19:14:44 KST 읽기에서
기존 dashboard/preview/broker PID·명령줄, bridge OFF/disabled, 부모 속성 및 safe
소스 해시 보존과 fresh cloud/odom을 확인했다. 새 구독·기존 서비스 조작·배포·
로봇 제어·TF·initialpose·goal·커밋·push는 없다. 이번 승인 1회씩은 소진됐으므로
반복 실행하지 않는다. 다음 최소 작업은 확보한 coarse→robust 임계 경로와 IPC/
검사 비용의 오프라인 검토다. 상세 영수증·정확한 runtime/pin/runner 기준은
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md)의 최신 절을 따른다.

18:49 KST에 별도 승인된 자원 사전검사 1회 실행을 시도했지만 로봇의 `sudo -n`이
비밀번호 필요로 거부했다. 임시 unit/자식 생성과 native 계산은 0회이며, 배치한
새 runner/폴더는 제거했다. 부모 controller 및 기존 dashboard/preview/broker PID는
그대로고 bridge는 OFF다. 18:50 읽기 정리 확인까지 마쳤다. 권한 변경·비밀번호 입력·
재시도는 없었고 실제 제한 검증은 미완료다. 이후 동일 명령을 바로 실행할 원격
runner는 남아 있지 않으므로 경로·소유권과 관리자 실행 가능 여부부터 다시 확인한다.

18:07~18:11 KST 읽기 재개에서 기존 센서의 fresh 수신, 배터리 74%, dashboard
실행과 제어 bridge OFF를 확인했다. 정확한 기존 seed는 보존된 scan 0의 후보 10
행렬로 확인됐고, 원격·로컬 fixture/원본 scan 해시와 frame/time/session이 일치했다.
이는 과거 센서 후보이며 지금 서 있는 로봇의 몸체 위치나 방향을 확정하지 않는다.
추가 seed 계약 시험 7건은 모두 통과했다. CPU 제한 보장이 없어 원격 정합 계산은
계속 0회이며, 새 배포·서비스·제어·보안 변경은 없다. 자세한 근거는 아래 검증
문서의 최신 읽기 재개 절을 따른다.

아래 10월 19일 인계는 당시 기록으로 보존한다. 그 안의 “비동기 기능 미배포”,
“실제 backend 정합 미실행”, `d7807de` 설치 소스 설명과 마지막 시작 프롬프트는
10월 20일 이후 상태를 나타내지 않는다. 날짜별 근거·로컬 시험 명령·남은 조건은
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md)를 먼저 읽는다.

- 현재 로컬 main의 확인 기준은 `e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`다.
  센서 추적을 포함한 별도 통합 브랜치 기준은
  `d16fca6e2fb0c3528200b8c9bc8400f277ff1f02`다. 이 main에 병합하지 않았다.
- [10월 20일 실행 기록](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d16fca6e2fb0c3528200b8c9bc8400f277ff1f02/docs/integration-acceptance/STAGE3_ARM_RUNTIME_20261020.md)에
  37개 제품 파일 적용과 실제 전역 관측이 기록돼 있다. 로봇 Git HEAD는
  `d7807de8f15fb457942039bb90ab41cf68d384c6`로 남았지만 실행 파일은 이후에
  적용됐다. 10월 21일 17:17:02 KST 영수증에서 제품 37경로와 telemetry router
  1경로가 통합 기준과 일치했다. Git HEAD와 실제 파일 해시를 함께 확인한다.
- 전역 결과는 모호성이 남은 과거 센서 후보다. 실제 짧은 추적은
  `SENSOR_DEADLINE_EXCEEDED`로 유실됐고 명시적 중지·정리를 완료했다.
  본체 pose, 연속 추적과 독립 정답 기반 정확도는 검증되지 않았다.
- 이번 로컬 후속은 Python 142건(141 통과·1 skip), JavaScript 56건 통과다.
  합성 IPC·가짜 observer 시험이며 실제 Open3D 처리 시간이나 현재 장비 상태를
  검증하지 않는다. 0.6초·1초 freshness·전체점 채점·분기 의존성을 유지했다.
  로봇 변경, 새 커밋과 push는 하지 않았다.

후속 담당은 문서의 날짜와 소스 기준부터 대조하고 기존 작업자·미커밋 변경을
보존한다. 통합 코드를 main에 중복 작성하거나 전체 브랜치를 무조건 병합하지
않는다. 성능 문제는 원본 세 분기와 전체점 채점을 유지한 별도 근거가 필요하다.
원격 순차/분리 진단은 CPU 제한 위임 전제를 충족하지 못해 0회로 종료했으며,
실험의 정확한 기존 seed도 그 초기 점검에서는 확인하지 않았다. 이후 위 읽기
재개에서 seed 근거를 확보했다. 자원 전제 실패는 로컬 소프트웨어 검토를
멈출 이유가 아니다. 새 원격 실험·배포·서비스·센서·제어 작업은 현재 허용 범위와
전제를 별도로 확인한다.

# Robot Scope 새 데스크탑 인계 — 2026-10-19 당시 기록

## 소스와 실행본

- 저장소: <https://github.com/Phjrab/robot-scope-ros2-dashboard>, branch `main`.
  새 데스크탑에서는 이 저장소를 작업 폴더에 clone한다. `AGENTS.md`의 단일
  branch 규칙을 따르고 기존 변경을 reset/clean으로 지우지 않는다.
- 최종 기능 소스는 **`1301e95453f0d45f0deade0ccc9ee6e3715fc6d8`**다.
  이후 이 공개 인계 문서를 추가했다. 정확한 게시 HEAD는 GitHub와 `git rev-parse HEAD`로 확인한다.
- 로봇에 실제 설치된 소스는 **`d7807de8f15fb457942039bb90ab41cf68d384c6`**다.
  checkout은 `/home/unitree/robot-scope`, 서비스는 `robot-scope.service`다.
  **GitHub 게시가 로봇 배포 완료를 뜻하지 않는다.**
- 인계 작성 전 작업 트리는 clean이었다. 미커밋 사용자 변경이나 진행 중인
  개발 작업은 없다. 맥북 담당의 종료를 확인한 뒤 새 데스크탑 하나만
  배포·제어 담당이 된다. 로봇 전원과 실행 서비스는 종료하지 않았다.
- 새 데스크탑이 같은 네트워크라는 것은 사용자 제공 정보다. 새 환경의
  인증·도구 설치·실제 로봇 접속 성공은 아직 확인하지 않았다.

## 완료한 작업과 미배포 기능

승인된 dashboard 배포 및 기존 소유 LiDAR 미리보기 재시작은 한 번 완료했다.
소스·설정·보존 데이터 검사를 통과했고, 60초 읽기 관측에서 LiDAR/pose 조회
62건이 모두 응답했다. 저장 3D 지도 표시도 확인했다. 당시 제어 브리지는
inactive/disabled, 자동 시작 OFF였으며 카메라·broker의 실행 주체는 유지됐다.
이는 당시의 관측 기록이다. 현재 상태는 새 담당이 읽기로 다시 확인한다.

새 기능 소스에는 기존 Maps 화면과 분리된 비동기 전역 관측 패널 및
start/get/cancel/export API가 있다. 요청 중복·취소·늦은 완료를 처리하고,
지도 revision·frame·observer epoch가 달라지면 결과를 무효화한다.
기존 subscription에서 명시적으로 요청한 한 장의 XYZ 전체를 display
throttle/cap/filter 전에 보존하고, 원본 binary PCD를 별도로 읽는다.
**새 기능은 로봇에 배포하지 않았고 실제 backend 정합도 실행하지 않았다.**

상세 계약과 환경변수는 [ASYNC_GLOBAL_OBSERVATION.md](ASYNC_GLOBAL_OBSERVATION.md)에 있다.
기본 provider는 `UNAVAILABLE`이다. 고정된 외부 Python·backend source·전체
source hash pin을 서버 설정에 준비해야 한다. 소스 해시 확인은 Open3D
의존성 실행 확인과 다르다. 현재 worker는 시작·import를 포함한 120초 deadline,
취소 시 process group 정리, 64KiB 출력 제한을 둔다. OS 메모리 hard cap은 없다.

## 결과 해석과 남은 검증

- 전체 입력의 범위는 **수신 PointCloud2의 XYZ 전체**다. 원래 센서 패킷이나
  비XYZ 필드 archive가 아니다. raw/converted 입력을 구분하며 upstream 처리와
  source clock은 미검증으로 기록한다. 0점·순서·정확한 ns 문자열을 보존한다.
  비유한 입력은 현재 backend가 명시 거부하며 조용히 제거하지 않는다.
- 결과는 항상 **HISTORICAL_ONLY / T_map_sensor**다. `current_result=null`,
  `body_pose=null`, `tracking_verified=false`다. 과거 캡처를 새 시각으로 바꾸거나
  현재 로봇 마커에 적용하지 않는다. 검증된 sensor-to-body 외부표정,
  동일 epoch odometry 전파 및 새 scan 검증은 별도 후속이다.
- **inlier RMSE ≤0.10m는 잠정 관측 기준이며 정밀 정확도가 아니다.**
  기존 5cm 결과와 수렴·inlier·overlap·geometry 등 다른 gate를 보존한다.
  기존 live 경로의 600ms, 1Hz, 1초 freshness, 150ms receipt pairing은 유지한다.
- 새 raw global backend는 원래 **5cm 선택·ambiguity·stationarity gate**를
  유지한다. 10cm는 저장 잔차 sidecar 비교이며 global 재선택이 아니다.
  `selected_candidate=null`을 잔차만으로 승격하지 않는다.
- 실제 비동기 정합, 현재 본체 pose, 실시간 추적, 독립 정답 기반 정확도와
  주행은 미검증이다. 명목 외부표정을 확정 calibration으로 자동 적용하지 않는다.

## 검증과 재현

기존 Mac 환경은 CPython3.13.2 가상환경이다. system Python이나 Mac 가상환경을
새 데스크탑에서 그대로 사용할 수 있다고 가정하지 않는다. 저장소 requirements와
CI에 지정된 환경을 참고한다. 테스트에는 로컬 Unix socket/localhost 허용이 필요하다.

| 검사 | 게시 전 결과 |
|---|---|
| Python 전체 | 2,410개 실행: 2,400 통과·3 skip·7 오류. 7개는 AST 격리 시험에 새 mixin 이름이 빠진 fixture 오류였다. fixture만 수정한 뒤 해당 모듈 19개 통과. 수정 후 단일 전체 재실행은 하지 않았다 |
| JavaScript | 전체 525개 통과 |
| 합성 브라우저 | 신규 global 3개 + 기존 live 6개, 총 9개 통과 |
| 정적 검사 | Ruff, 설정된 mypy 4모듈, frontend syntax 96모듈, secret/diff 검사 통과 |
| 실제 장비 | 앞서 설치한 d7807de의 입력·화면 확인만 수행. 새 비동기 기능은 미실행 |

브라우저와 새 worker 검사는 합성 fixture다. 실제 카메라·정합 검증으로
취급하지 않는다. 첫 전체 실행의 소켓 권한 제한과 API 목록/파일 길이 실패는
환경 재실행 및 최소 수정으로 해결했다. skip은 optional plotting, rosbags,
Mac에서 실행하지 않는 Linux `/proc` 시험이다. **GitHub CI는 게시된 정확한
HEAD의 Actions 결과를 확인하며 과거 CI 성공으로 대체하지 않는다.**

```sh
python -m unittest discover -s tests -v
npm run test:unit
npx playwright test tests/e2e/global_observation.spec.mjs tests/e2e/live_observation.spec.mjs --reporter=line
python -m ruff check robot_dashboard scripts
python -m mypy --config-file mypy.ini
node scripts/check_frontend_syntax.mjs
python scripts/check_repository_secrets.py
```

## 추가로 필요한 자료와 보존 범위

이 저장소에는 코드·프로젝트 문서·합성 회귀 자료만 게시한다. 원본 지도·센서
점군·bag·카메라 샘플, 비공개 수업 자료·링크, 인증자료는 이번 게시에 포함하지 않는다.

실지도·샘플·미션 이력은 로봇의 `/home/unitree/robot-scope-data/`에 보존되어 있다.
repo/config, `/home/unitree/.config/robot-scope`, systemd 설정, VSLAM 설치와
카메라/session lock을 보존한다. 배포 때 만든 source/config/data 백업은 로봇의
기존 deployment 디렉터리에 남아 있다. 자동 복구나 삭제를 수행하지 않는다.

실제 backend 연결에는 맥북에 별도로 보존한 **검토된 v0.3.1 backend source,
원본 해시 manifest 및 적합한 Python/Open3D 환경**이 필요하다. 그 자료와
과거 실험 재현용 private evidence는 Git에 없고 새 계정으로 전송하지 않았다.
공개 코드·합성 시험 검토에는 필요하지 않다. 필요할 때 사용자 승인 방식으로
별도 준비하며, 인증 개인키나 비공개 자료를 공개 저장소에 추가하지 않는다.

## 다음 첫 작업 / 복사용 시작 프롬프트

> 이 인계 문서를 읽고 Robot Scope를 이어받아줘. 맥북 작업 종료와 단일
> 담당을 확인한 뒤, 새 데스크탑의 인증·접속 및 로컬/로봇 HEAD, 미커밋 변경,
> 서비스 owner와 활성·미저장 세션을 읽기 확인해. 실제 설치 d7807de와
> 미배포 비동기 기능을 구분하고 지도·설정·이력을 보존해. 공개 코드와 해당
> HEAD CI부터 검토하고, private backend가 GitHub에 있다고 가정하지 마.
> 새 배포·재시작·센서·카메라·TF·initialpose·goal·이동은 정확한 변경·백업·복구와
> 현재 현장 조건을 포함한 별도 승인 전 수행하지 마. historical 센서 후보를
> 현재 본체 pose로 표시하거나 잠정 10cm 잔차를 정확도 검증으로 부르지 마.
