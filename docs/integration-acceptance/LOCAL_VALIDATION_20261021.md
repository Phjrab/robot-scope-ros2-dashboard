# 로컬 통합 후속 검증 — 2026-10-21

## 최신 후속 — 운영 처리 예산 후보 동결, 실기 배포 보류

20:20 KST 로컬 resource-launch 후보를 동결했다. 기준 실행 소스는 d16fca6,
저장소 main은 e70ef825다. 제품 다섯 파일(owner/process/external runner와 신규
scope/admission 두 파일) 및 시험 두 파일만 다르며 worker/adapter/legacy bytes는
같다. manifest SHA256은
`64c589fba4e16102455f88911ebc37ea6adf37c04bb6071beffb2bcddf36c979`,
patch는 `01f90f4bc0e7aa877e362da26ae66bfb26b4004dce73cbed822916b24d503dd5`다.
기존 미커밋 변경과 원본 snapshot·과거 진단 영수증을 보존했다. commit/push는 없다.

후보는 명시적인 processing-budget disabled와 child-resource user_scope_v1을
함께 요구한다. seeded 처리 예산만 해제하고 startup30초, align watchdog60초,
owner 전체60초, 기존 global 최대120초 및 freshness1초는 유지한다. 각 native
자식은 기존 UID1000 user manager의 고유 scope로 실행하며 native import 전에
실제 memory2GiB/swap0/tasks64·PID/cgroup·worker hash·manager runtime을
확인하고 부모 ACK를 받아야 한다. 추가 CPUQuota는 없고 기존 제품 OMP/BLAS/MKL
thread1은 보존한다. scope OOM group0은 atomic group kill로 부르지 않는다.
정리 실패는 소유 handle/입력을 보존하고 새 작업을 차단한다. 본체 pose·운영 TF·
initialpose·goal·주행에 연결하지 않는다. 선행 stdlib OS probe는 실제 후보 배포의
증거가 아니다.

합성/stdlib 모의 자원 회귀18개, 기존 global15개, sensor49개 중48개 통과·macOS
FD inventory1개 skip으로 총82개 중81pass/1skip이다. 독립 검토에서 제품 후보의
필수 수정 사항은 없고 AST/patch 적용 검사도 통과했다. 전체 CI와 저장 scan 수치
진단은 재실행하지 않았다. 실센서/native admission·첫 UI 관측·연속 추적·독립 정확도는
이 후보로 검증하지 않았다.

20:13 실제 디스크의 기준 해시와 두 설정 키 미설정을 읽었다. 20:19:51 추가 조회에서
같은 dashboard PID968/NRestarts0, bridge inactive/disabled, global generation0·
active/latest null, SLAM active_session null, camera reserved/reservation_unknown false,
매핑 pipeline/operation idle, 미션·dataset capture/export 비활성을 받았다. 기존
Hesai/XT16 preview만 실행 중이었다. 이는 시각이 있는 읽기이며 현재 현장 상태의
보장이나 로드된 후보 bytes 증명이 아니다. **운영 처리 예산0.6초는 아직 적용 중이며
해제 배포는 하지 않았다.**

배포 wrapper의 정적 검토에서 `/system/service`·`/navigation`뿐 아니라
`/slam/session`도 navigation context를 통해 control manager.snapshot에 닿아 만료
STOP을 enqueue할 수 있음을 확인했다. 20:19에 받은 SLAM 응답은 원본 영수증을
그대로 보존하되 무작용 조회로 분류하지 않는다. 실제 제어 출력 수를 그 조회만으로
0이라고 증명하지 않는다. 기존 세션을 임의 정리하지 않는 소유권 확인 대안을
확정하기 전 배포 wrapper는 차단 상태로 둔다. 초기 wrapper의8개 모의 통과는 이
간접 경로 문제의 실기 통과가 아니다. 제품 후보 통과와 배포 도구 준비를 구분한다.
최종 wrapper는 해당 GET을 제거하고 소유권 확인 미해결 사유로 모든 실행 전
차단한다. 배포 fresh mtime/rollback 원 mtime, 서비스 시작 실패 상태의 보호 파일·
boot 확인, 재시작 intent 디렉터리 fsync를 보완해 모의12개·compile이 통과했다.
두 manifest는 finalized=false/BLOCKED이며 blocked approval manifest SHA는
`b9a0c6bddb8fea23fa42001cd884845965c27157aaf2d4c498a14e6504a222bf`다.
이 로컬 검증을 운영 적용 가능 상태로 승격하지 않는다.

사용자가 전원 종료 가능 여부를 물었다. 새 계산/센서 세션·서비스 재시작은 실행하지
않았고 마지막 정상 확인 뒤 새 수집·저장을 사용자가 시작하지 않았다면 정상 종료할
수 있다고 안내했다. 최신 재조회는 응답이 없어 결과를 주장하지 않고 해당 읽기 SSH
연결만 종료했다. 전원을 다시 켠 뒤 현재 소유권·소스/config를 재확인하고, 정확한
배포/백업/복구·preview 재시작·현재 정지 관측 범위를 한 번 묶어 승인받는 것이 다음
최소 작업이다. 예전 지도 시작 위치·저장 seed를 현재 pose로 재사용하지 않는다.

private 근거는 `lidar-integration-20261021/tracking-resource-launch-candidate-20261021/`,
`product-target-readonly-20261021T111319Z.json`,
`deployment-owner-inventory-20261021T111953Z.json` 및
`deployment-preparation-20261021/`에 분리 보존한다. 인증값은 문서·manifest·argv·
환경변수·로그에 저장하지 않았다.

## 최신 후속 — 2026-10-21 19:48 KST, CPU quota 없는 저장 scan 반복

사용자는 0.6초 처리 예산의 임시 해제와 새 실험의 별도 CPU 제한 미설정을
지정했다. 아래 과거의 “0.6초 유지/초과”는 당시 실행 조건이며 현재 요청의
활성 중단 기준으로 재사용하지 않는다. 제품 배포 파일은 이번에도 변경하지
않아 실제 설치 코드의 0.6초는 아직 남아 있다. 예산 해제와 유한 watchdog을
분리하는 로컬 후보를 별도로 준비하며, 적용 완료로 표시하지 않는다.
10cm는 저장 정합 잔차 비교값이고 본체 정확도나 전체 성공/실패 기준이 아니다.

승인된 새 묶음에서 순차/분리 각 3회만 실행했다. 순서는 순차→분리→분리→
순차→순차→분리이며 정확한 seed/지도/scan/pin, 전체16,000점 scoring 및
coarse→robust·plane 원 seed 계약을 보존했다. 이전 1회씩의 영수증은 수정하지
않았다. 이번 묶음의 추가 실행 횟수는 소진됐다.

| 방식, 각3회 | 시작·지도 준비 중앙값 | 검증/IPC/계산 호출 중앙값 | 시작~정리 전체 중앙값 |
| --- | ---: | ---: | ---: |
| 순차 | 1.628125초 | 0.821718초 | 2.700431초 |
| 프로세스 분리 | 1.930847초 | 0.687252초 | 2.892947초 |

분리는 호출 중앙값16.36% 단축, 새 프로세스 시작/지도 준비/정리 포함 전체는
7.13% 증가였다. OS 캐시는 통제하지 않았다. 모든6회는 결과와 자식 exit0을
얻었지만 마지막 분리 실행의 미선택 coarse 진단 rotation_increment_rad가
0에서2.1073424255e-8로 달라 사전1e-8 동등성 비교 두 곳을 위반했다. 따라서
원본 FAILED_CLOSED_NO_RETRY/exit2를 유지한다. 허용치를 사후 완화하지 않았다.
선택 분기는 모두 plane이며 선택 transform 원소 최대차8.88e-16,
RMSE 최대차1.11e-16m였다. 선택 RMSE0.155819m는 정합 잔차다. 이번 근거로
분리 경로를 제품에 채택하거나 본체 위치·물리 정확도 검증을 주장하지 않는다.

실제 격리 unit은 robot-scope-repeat-envelope-20261021-01.service였다.
cpu.max=`max 100000`, OMP/OpenBLAS/MKL 추가 cap 없음, 메모리2GiB·swap0·
tasks64·OOM group1 및 startup4/active55/stop1초 경계를 readback했다.
수치 runner 내부52초 전체 watchdog과 호출별5초 수집 watchdog도 유지했다.
systemd-run 관측16.982초(service runtime16.949초), staging~정리17.145초였다. 145개 자원 표본의
memory.current 최대172,994,560 bytes, thread 포함 tasks 최대59였고
memory/pids max·OOM event는0이었다. kernel peak 파일이 없어 진짜 peak로
부르지 않는다. aggregate CPU busy60.49%, 해당 cgroup 평균3.063 core 상당;
CPU 개수는 미수집이다. GPU raw load 표본은0이며 단위/짧은 활동은 미검증이다.

기존 preview31회 표본에서 cloud9.94~10.01Hz/age0.004~0.137초,
odometry183.54~263.53Hz/age0.002~0.038초였다. 화면 전체 지연이나 인과적
영향 없음의 증거가 아니다. 19:48:24 KST 읽기에서 기존 dashboard PID968/
NRestarts0, Hesai·XT16·broker 프로세스와 safe route 소스 해시가 같았다.
bridge inactive/disabled, global active/latest와 body_pose/current_result는 null.
unit/cgroup/자식/새 runner·cache·폴더는 정리됐다. 서비스 재시작·새 센서 구독·
카메라·TF·initialpose·goal·로봇 명령·제품 배포·commit/push는0이다.

정확한 영수증은 private `lidar-integration-20261021/repeat-diagnostic-20261021T104239Z`
아래에 있다. runner SHA256은 ca54ac24bdb77526fd6a354cb9411a46120ec8f9dd8ce265e87e96e20f20c074,
정확한 seed는8c50bf4755e5542d3a1278f4b54d5ef7c043988a765be380b009ec1ea029ba48,
source pin은47ea8760ff6a0522067850a6bd10b330ca8a21c9c5ed12c82a1936ba9541bcef이다.
Python은 기존 stage3-runtime-20261019/venv/bin/python을 재사용했다. 진단 도구의
오프라인 회귀20건 통과와 독립 실행기 검토를 보존했다. 실제 센서 scan은 새로
구독하지 않았고 결과는 저장된 camera_init←hesai_lidar 관측이다.

## 인증 승인 후 저장 scan 순차·프로세스 분리 1회씩 완료 — 19:05~19:14 KST

사용자가 인증을 제공하고 직접 실행을 승인했다. 기존 `sudo -n` 실패를 우회해
정책을 수정하지 않고, 같은 runner/설정으로 인증을 받아 사전검사 1회를 수행했다.
19:05:20 KST에 CPU 200%/period100ms, memory2147483648 bytes, swap0, tasks64,
OOM group1 및 inert 자식의 동일 leaf cgroup 소속이 통과했다. manager의
User=unitree, Delegate=no, KillMode=control-group, startup4초/active55초/stop1초도
일치했고 해당 unit·자식·배치 파일을 정리했다. 비밀번호는 로컬 getpass와 암호화된
SSH stdin을 통해 메모리에서 전달했으며 파일·argv·환경변수·영수증에 넣지 않았다.
이전 승인안/거부 영수증을 덮어쓰지 않았고 sudo/polkit·부모 controller 변경은 없다.

그 뒤 승인된 새 격리 경로
`/home/unitree/robot-scope-diagnostics/stage3-runtime-20261019/process-isolation-20261021-01/`
및 `robot-scope-seed-envelope-20261021-01.service`의 충돌 부재를 재확인했다.
19:14:03~19:14:11 KST에 저장 scan 순차 1회·분리 1회만 수행했고 재시도는 0회다.
systemd 실행은 7.404352초, 배치~정리는 7.579407초였다. 사전검사와 계산 unit은
같은 이름을 쓰되 앞 실행의 unit/cgroup/폴더 소멸을 확인한 후 다음 실행했다.

### 정확한 입력·소스·계약

- 과거 scan0 candidate10의 원래 seed를 같은 epoch의 scan1에만 적용했다.
  seed float64-LE hash는 `8c50bf4755e5542d3a1278f4b54d5ef7c043988a765be380b009ec1ea029ba48`.
  원래 frame, map revision, observer/epoch, 두 source stamp와 모든 scan 16,000점/
  map 25,666점 및 파일 해시는 아래 seed 확인 절과 같다. 현재 pose로 쓰지 않았다.
- runtime은 보존된 stage3 `venv/bin/python`; backend archive
  `0e4abbc70de139fdef45e90b6958d0f1f7c997a52b7ffb24bee718355bd12593`,
  source pin `47ea8760ff6a0522067850a6bd10b330ca8a21c9c5ed12c82a1936ba9541bcef`.
  worker `14b2cb08f865dc12a95b98b819bca07b9572d2be2dc28d4df04e8dc6ec12580a`,
  adapter `0ae898d09453b59b3daf2bdb6843a2f05c901f8697b44802a1ed801720e1067b`.
- 새 private runner hash는
  `0db33c37c160bcf421fb620f301f316104a4dc959008f4a5594e24b632c84f6a`.
  hash/resource/seed/frame/stamp admission을 수치 import 전에 수행하고 호출 전후에도
  확인했다. preserved helper의 threaded 실행 함수는 호출하지 않았다. 분리는
  프로세스별 observer를 사용하며 coarse→robust 의존성과 원래 seed의 plane 분기를
  유지했다. 모든 분기의 score는 전체 scan/원본 map이다.
- OMP/OPENBLAS/MKL threads는 각각1, bytecode 쓰기 금지, cache/tmp는 자신의 새
  폴더로 한정했다. dashboard DDS·config·broker·카메라·제품/backend는 변경하지 않았다.

### 시간·동등성·잔차 결과

| 단 한 번의 진단 | startup/map 준비 | 준비 후 검증 완료 wall | worker wall |
| --- | ---: | ---: | ---: |
| 순차 | 2.716791초 | 0.822107초 | 0.803580초 |
| 프로세스 분리 | 2.514348초 | 0.622600초 | 0.604154초 |

진단 호출 wall에는 부모 source/seed/file 재확인, IPC, 자식 재확인/정합 및 부모
결과 검사/재확인이 포함된다. native import·map/observer 준비는 startup으로
분리해서 명시한다. 제품 owner 전체 호출을 실행한 것이 아니므로 제품 통과로
해석하지 않는다. 진단 결과 채집 상한은 과거 진단과 같은5초이고 **운영0.6초는
변경하지 않았다. 두 방식 모두0.6초를 초과했다.** 한 쌍에서24.27% 줄었으나
반복 안정성이나 전체 제품 예산 여유를 입증하지 않는다. 검사/IPC를 운영 예산
밖으로 옮긴 변경은 없다.

시간 필드를 제외한 결과에서233개 float의 최대 차이는0, 다른 필드 불일치도0이다.
선택은 같은 plane 후보이며 RMSE0.155819216568m로10cm 잔차 비교는 미달한다.
기존 adapter가 유지하던 잔차 비교/선택 정책과 다른 geometry·stationarity·ambiguity
gate를 바꾸지 않았다. 이 로컬 세 분기 결과의 top gate는 비어 있지만, 원래 전역
seed의 AMBIGUOUS_ALTERNATIVES 기록을 소거하거나 정확한 위치로 승격하지 않았다.
오프라인 정합 잔차는 물리 정확도나 body pose 증거가 아니다.

### 자원·정리·보존 및 다음 최소 작업

71개 자원 표본에서 memory.current 최대241811456 bytes(약230.6MiB), pids.current
최대3이었다. 이 kernel의 memory.peak/pids.peak는 없어 실제 최대치로 주장하지
않는다. OOM/메모리 max/pids max 이벤트는0이었다. 전체 준비·실행 구간 CPU quota
throttling은6회/17377us다. OOM·task 고갈·강제 group-kill 부하시험은 하지 않았다.
관측된 coordinator/세 자식의 PID-starttime 네 쌍 모두 정확한 leaf cgroup이었다.
세 자식은 exit0으로 회수됐고 unit/leaf cgroup/runner·자신의 cache/tmp·빈 폴더를
제거했다. 기존 지도·capture·source·잠금은 보존했다.

19:14:44 KST 최종 읽기에서는 dashboard PID968/NRestarts0, 기존 preview/broker
PID·명령줄, bridge inactive/disabled, 부모 속성과 safe source hash가 그대로였다.
기존 cloud10Hz/age0.047초, odometry180.31Hz/age0.009초가 fresh였다. global owner의
active/latest job은 없었다. tracking/control GET·WebSocket·새 센서 구독은 없으며,
기존 서비스 재시작·배포·카메라/bridge 조작·자세/이동/ARM·TF·initialpose·goal도0회다.

private 계약 시험8개가 통과했다. 제한/UID/cgroup 오류, seed/stamp/epoch/population
변경 거부, coarse score 실패 시 원래 seed 유지, coarse→robust/plane 입력과 전체점
score, IPC 크기/deadline, admission 실패 시 계산 미시작을 포함한다. 기존 전체
142+7 Python/56 JS 검증은 반복하지 않았다. 제품 코드·commit/push는 없다.

private 근거 폴더는 `lidar-integration-20261021/` 아래
`resource-preflight-execution-20261021T100410Z/`와
`process-diagnostic-execution-20261021T101134Z/`다. 후자에 runner/test 사본,
prepared manifest, 전후 읽기, 실행/정리, closeout-summary.json과 RESULT.ko.md를
보존했다. 이전 인증 실패와 승인 제안 원본은 그대로다.

다음 최소 작업은 이미 얻은 분리 coarse0.0827초+robust0.5074초와 IPC/검사 비용의
오프라인 임계 경로 검토다. 이번 승인1회씩은 소진됐으므로 추가 native 계산은
실행하지 않았다. 분기·전체점·deadline/freshness 정책을 완화하지 않는다. body
extrinsics, source clock, 현재 pose, 연속 추적과 독립 정답 정확도는 계속 미검증이다.

## 별도 승인된 자원 사전검사 실행 시도 — 18:46~18:50 KST

사용자가 로컬 승인안의 동일 runner/설정에 한정한 임시 서비스 자원 사전검사
1회를 승인했다. 실제 scan 계산은 승인에 포함되지 않았다. 직전 읽기에서 5개
부모 chain의 controller/limit/소유권/unit 속성은 18:31 제안 근거와 모두 같았고,
대상 unit·cgroup·작업 폴더는 없었다. 기존 센서는 fresh, global 작업은 없고,
dashboard PID 968/재시작 0회, bridge inactive/disabled 상태였다.

18:49:05 KST 승인된 새 경로에 runner 한 파일만 배치했다. SHA-256은
`ef656a6a41ee9f023a13e3e84d36425c81f0dd402a7257e6a520f84d2b3008c8`,
소유권 UID/GID 1000, 파일 0600/새 폴더 0700을 확인했다. 검토한 argv로
`robot-scope-seed-envelope-20261021-01.service` 생성/실행을 한 번 시도했지만
`sudo -n`이 exit 1, `sudo: a password is required`로 거부했다. 이전 sudo 목록
조회 성공은 NOPASSWD 실행 보장이 아니었다. 자동 승인 심사 거절이 아니라 로봇의
sudo 인증 조건이며, 비밀번호 입력·sudo -v·정책/권한 변경·추가 실행 시도는 없다.

따라서 unit 생성 0회, runner 실제 실행 0회, 0.2초 inert 자식 생성 0회다.
CPU 200%/100ms·memory 2GiB·swap 0·pids 64의 실제 적용/child containment는
검증하지 못했다. native/Open3D/정합/scan 처리·새 구독·기존 서비스 변경·로봇 제어는
수행하지 않았다. 이전 로컬 admission 4건 통과를 실기 제한 검증으로 승격하지 않는다.

상태 조회에서 대상 unit은 not-found, transient config/cgroup은 부재했고 잔존
소유 PID가 없었다. 새 runner는 자신의 hash/소유권을 대조한 뒤 제거하고 빈 새
폴더도 제거했다. 다섯 부모 chain과 기존 dashboard/bridge 속성은 전후 일치했다.
18:50:04 KST 최종 읽기에서 dashboard 968, 기존 Hesai wrapper 2638/native 2758,
XT16 bridge 2689, SLAM broker 2783 PID가 그대로였고, 대상 unit/cgroup/작업 폴더는
모두 없었다. cloud 10.0Hz/age 0.030초, odometry 180.41Hz/age 0.012초로 fresh였다.

private 영수증은 `resource-preflight-execution-20261021T094633Z/`의
`before-readonly.json`, `execution-and-cleanup.json`, `after-readonly.json`이다.
원래 승인 제안과 해시는 수정하지 않고 실행 결과를 별도 보존했다. 커밋·push는 없다.
남은 조건은 관리자 실행 경로와 실제 임시 자원 제한 readback이다. 이번에 생성한
원격 runner는 남아 있지 않으며 새 배치/실행을 자동 반복하지 않는다. 실제 순차/
분리 scan 계산은 계속 0회이고 별도 승인 대상이다.

## 후속 읽기 재개와 정확한 저장 seed 확인 — 18:07~18:11 KST

앞선 로컬 작업 뒤 사용자가 기존 읽기 범위의 재개를 요청했다. 사용자가 보고한
현재 조건은 서 있는 정지 상태와 이전 자세 유지다. 이 현장 보고를 지도 좌표·
방향 수치 seed나 물리적 정지의 독립 측정으로 대체하지 않았다. 기존 담당 하나가
작업했으며 원격 쓰기·native 정합·서비스 변경·새 센서 구독·제어는 하지 않았다.

18:07:45 KST에 실행 구현 4경로의 해시 일치를 확인한 뒤 기존 health/state/global
GET만 읽었다. tracking/control GET, WebSocket과 모든 변경 API는 호출하지 않았다.
dashboard는 PID 968 active/running, 재시작 0회이며 control bridge는
inactive/disabled였다. global active/latest는 null이고 native 진단 worker는
조회한 관련 프로세스 목록에 없었다. 도메인 0/CycloneDDS는 그대로다.

| 기존 입력 | 수신 지표 / age | 해석 |
| --- | --- | --- |
| `/velodyne_points` | 9.99Hz / 0.011초 | fresh, 전체 source 16,000점, `hesai_lidar` frame |
| `/utlidar/robot_odom` | 175.63Hz / 0.009초(mapping 지표) | fresh, pose 표시는 `odom` → `base_link`; 지도상 본체 정답 아님 |
| `/imu/body` | state ok / 0.029초 | 기존 수신 상태 확인 |
| `/lowstate` | state ok / 0.038초 | 배터리 74%; `/lf/lowstate`도 74%, age 0.030초 |

이는 17:17 stale 기록 이후의 별도 한 시각 관측이다. `mapping.state=mapping`은
cloud/odom 수신 상태 계산이며 FAST-LIO 매핑 작업 시작이나 실이동의 증거가 아니다.
실제 프로필 파일의 `odometry_stale_after_s=8.0`과 해당 파일을 지정한 실행 인자도
확인했다. 파일 읽기를 실행 중 객체의 모든 유효 설정 readback으로 취급하지 않는다.

정확한 기존 seed는 당시 실행 스크립트를 실행하지 않고 읽어 추적했다.
`arm_pipeline_parallel_prototype_20261020.py`의 SHA-256은 기존 실행 기록과 같은
`8755016db7c1929066b486e5043a0bd27a2380b0650990e76ead84ef7939bdbe`였다.
그 스크립트의 `_inputs()`는 아래 결과의 scan 0 / candidate 10 행렬을 읽고,
같은 epoch의 저장 scan 1에 사용한다. 새 seed 계산이나 현재 자세 추정은 없다.

- 원격 fixture 기준 경로:
  `/home/unitree/robot-scope-diagnostics/stage3-runtime-20261019/arm-check-debba9c-20261020/docs/replay-fixtures/stage3-20261019/`.
- seed 원본: `results/ambiguity-on.json`의
  `/scans/0/backend_result/candidates/10/map_from_scan`.
  JSON 파일 SHA-256은 `23c39d66ebe31985908f6be3971233472f2316a1b8ce5a9a4aa3266019991fe0`다.
- 정확한 4×4 행렬을 행 우선 little-endian float64로 저장한 SHA-256은
  `8c50bf4755e5542d3a1278f4b54d5ef7c043988a765be380b009ec1ea029ba48`다.
  전체 행렬은 private seed 영수증에 보존했다. 의미는 과거 scan 0의
  `T_map_sensor`, 즉 `camera_init` ← `hesai_lidar`다.
- 지도는 `map_20261018_162315.pcd` 전체 25,666점이다. 원본 PCD hash는
  `c347faea6fd7a2f353b39f1f69f93cab8f2c6243299f90f87e54b7d8172ce4b8`,
  전체 XYZ hash는 `2e436c8cd41db44ac7130d81df8b23dd01e4875dd42ffcb1c1dbd18780da5852`다.
- scan 0/1은 각각 전체 16,000점이며 stamp는
  `1792406869346463680` / `1792406869446533680`이다.
  epoch는 `e9960d3a47bc939f4261a19a55c33217`, observer는
  `f5663a23b8eae36682d843befb51a537`로 같다. source clock은 미검증이다.
- 18:10:58 KST 원격 보존 fixture 8파일과 원래 capture 경로의 manifest/scan
  0/scan 1을 읽어 로컬 Git 보존본과 비교했다. 모두 해시가 일치했고, 원격 JSON의
  candidate 번호와 행렬 바이트 hash도 일치했다. 로컬 `_inputs()` 검증에서는
  세 scan 모두 raw PointCloud2 XYZ와 저장 XYZ의 전체 행 대응까지 확인했다.

현재 입력의 observer/epoch는 이 저장 capture와 다르다. 과거 seed를 지금의 fresh
tracking 결과로 재표시하거나 원래 stamp를 갱신하지 않았다. seed 후보에는 원래
`AMBIGUOUS_ALTERNATIVES`가 남고 RMSE는 0.1549523360m다. 0.10m 잔차 비교를
통과하지 않으며 본체 정확도 증거도 아니다.

private 로컬 검증 자료에 `archived_seed_contract.py`, `verify_archived_seed.py`,
`test_archived_seed_contract.py`를 추가했다. 아래 명령의 7건이 모두 통과했고
실패·오류·skip은 0건이다. 정확한 seed 보존, 다른 rigid 행렬 거부, result frame/
stamp 변경, epoch/점 모집단 변경, scan 순서·stale/정수 변환 timestamp, 다른 후보나
모호성 삭제, 미검증 증거를 검증 완료로 재표기하는 경우를 검사했다. fixture 원본은
바꾸지 않았고 registration/backend/Open3D는 실행하지 않았다.

```sh
python -B verify_archived_seed.py
python -B -m unittest test_archived_seed_contract -v
```

앞선 Python 142건과 JavaScript 56건을 같은 조건에서 반복하지 않았다. 새 7건은
추가 계약 시험이다. 새 근거는 private 폴더의 `resume-readonly-20261021T090745Z.json`,
`seed-readback-20261021T090816Z/` 아래 source/seed 영수증·시험 로그에 보존했다.
기존 로컬 변경을 보존했고 커밋·push·배포는 없다.

원격 순차/분리 진단은 계속 0회다. 정확한 seed 조건은 이번에 확인됐지만 CPU
제한 보장은 여전히 확보되지 않았다. 17:14의 CPU cgroup 위임 실패를 우회하거나
현재 권한이 바뀌었다고 추정하지 않았다. 지금 추가 승인 없이 실행할 원격 변경은
없다. 향후 원격 계산을 다시 제안하려면 새 격리 경로의 runner 내용/해시, 정확한
CPU·memory·pids 상한과 강제 방법, 전체 60초/순차 1회·분리 1회 한계, 서비스 영향,
owned child/임시 경로 정리·복구안을 구체화하고 현재 허용 범위와 대조해야 한다.
시스템·보안·cgroup 설정 변경은 이번 범위에 포함되지 않는다.

## 앞선 로컬 검증의 범위와 근거

이번 후속은 기존 코드 분석, 합성 회귀와 인계 문서 정리다. 원격 쓰기·실험·배포·
서비스 변경·새 센서 구독·로봇 이동/자세/제어·보안 변경은 수행하지 않았다.
커밋과 push도 하지 않았다. 아래 로봇 상태는 이미 보존한 시각의 읽기 영수증을
대조한 것이며, 이번 로컬 검증 중 새로 장비를 조회하지 않았다.

## 소스와 실행본 구별

| 기준 | 확인 내용 | 해석 |
| --- | --- | --- |
| 로컬 main | `e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`, 시작 시 clean | 추적 모듈이 없는 main을 통합 브랜치로 덮어쓰지 않았다. 기존 별도 UI branch도 변경하지 않았다. |
| 통합 소스 | `codex/maps-localization-integration`, `d16fca6e2fb0c3528200b8c9bc8400f277ff1f02` | 로컬 Git object에서 별도 시험용 소스 스냅샷을 추출했다. checkout 변경·병합·새 worktree는 없다. |
| 10월 19일 로봇 배포 | `d7807de8f15fb457942039bb90ab41cf68d384c6` | 기존 PROGRESS/HANDOFF의 비동기 기능 미배포 설명이 적용되던 시점이다. |
| 10월 20일 적용 | 37개 제품 경로와 backend 연결 환경 항목 4개를 백업 후 적용, dashboard 재시작 | 로봇 Git HEAD는 `d7807de`로 남았다. 파일 적용 배포를 Git checkout 완료로 표현하지 않는다. |
| 10월 21일 17:17:02 KST 읽기 기록 | 제품 37경로 및 telemetry router 1경로 해시가 통합 기준과 일치 | `d7807de` HEAD만으로 실행 파일이 옛 버전이라고 단정하면 안 된다. 이후 변경 여부는 이 기록으로 알 수 없다. |

통합 소스의 [10월 20일 실행 보고서](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d16fca6e2fb0c3528200b8c9bc8400f277ff1f02/docs/integration-acceptance/STAGE3_ARM_RUNTIME_20261020.md)와
[수치 요약](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d16fca6e2fb0c3528200b8c9bc8400f277ff1f02/docs/integration-acceptance/STAGE3_ARM_RUNTIME_EVIDENCE_20261020.json)이
10월 19일 일반 인계보다 뒤의 근거다. 기존 문서를 삭제하지 않고 상단에 날짜를
명시한 갱신을 추가했다. 이번 검증을 main 병합이나 GitHub 게시로 취급하지 않는다.

17:17:02 기록에서 dashboard는 active/running(PID 968, 재시작 0회), 제어 bridge는
inactive/disabled였다. 새 global job은 없고 `body_pose/current_result=null`,
`tracking_verified=false`였다. 운영 DDS는 domain 0/CycloneDDS로 기록돼 있다.
LiDAR 입력은 fresh였지만 odometry·IMU·lowstate는 약 4.4초 stale이었으며,
`mapping.state=cloud_only`였다. 이는 수신 상태 계산이며 매핑 worker 실행이나
물리적 이동의 증거가 아니다. 저장 배터리 87%도 stale 값이어서 현재 잔량으로
보고하지 않는다. 별도 `robot_pose.state=ok`에 대해서는 로컬
`config/go2-onboard.json`의 odometry 표시 유효기간 8초와 일반 수신 지표의
3초 한계가 다름을 확인했다. 이 차이로 해당 표시 조합을 설명할 수 있지만,
이번 영수증에는 실행 프로필의 유효값이 없어 원인을 확정하지 않는다.
이를 추적의 1초 freshness 통과로 해석하거나 표시 한계를 변경하지 않았다.

## 0.6초 경로 분석과 변경 판단

검토 기준은 위 통합 SHA의
[sensor_tracking_process.py](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d16fca6e2fb0c3528200b8c9bc8400f277ff1f02/robot_dashboard/relocalization/sensor_tracking_process.py),
[sensor_tracking_worker.py](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d16fca6e2fb0c3528200b8c9bc8400f277ff1f02/robot_dashboard/relocalization/sensor_tracking_worker.py),
[sensor_tracking.py](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d16fca6e2fb0c3528200b8c9bc8400f277ff1f02/robot_dashboard/application/sensor_tracking.py)다.

1. 지도 로딩·native import는 `start()`의 별도 최대 30초 구간이다.
   `align()`은 호출 직후 monotonic 시각에 0.6초를 더해 deadline을 만든다.
   동일 observer의 중복 호출은 대기열 대신 `SENSOR_PROCESS_BUSY`로 거부한다.
2. align 예산에는 map/frame/epoch/stamp·전체 배열 해시·rigid seed 검사,
   source pin 확인, scan 파일 쓰기, framed IPC와 자식 연산이 들어간다.
3. 자식은 coarse → robust → plane 순으로 실행한다. robust는 coarse 결과를,
   plane은 원래 seed를 사용한다. 매 분기의 score에는 전체 scan이 들어간다.
   기존 coarse fit용 voxel/cap은 전체점 score 모집단 감소와 구별한다.
4. 부모는 수신 중과 수신 직후 deadline을 확인하고 결과의 identity·policy·
   envelope 검증 뒤에도 다시 확인한다. 예산을 넘은 결과는 수락하지 않는다.
   예외 시 owned process group 종료·회수와 임시 경로 정리를 수행한다.
   종료·회수 시간은 별도이므로 HTTP 반환이 반드시 0.6초 이내라는 뜻은 아니다.
   동기식 파일 검사 자체를 OS가 0.6초에 선점한다는 보장도 없다.
5. owner는 별도로 수신 후 1초 freshness, 단조 증가 stamp/receipt, map/source
   변경, pose jump를 검사한다. 세 fresh scan 확인 전 pose를 공개하지 않는다.

10월 20일 기록의 ARM 로컬 align 0.803313444초는 native 분기·전체점 채점
진단값이며 운영 성공이 아니다. 그 값만으로도 0.6초보다 길다. 이번 합성 시험은
어느 native 분기가 그 시간을 차지하는지 측정하지 않았다. 기존 스레드 시제품도
안정적 통과나 원본 observer 동시 사용 안전성을 입증하지 못해 제품 미반영이다.
부모 pin 검사를 제거하거나 검증을 예산 밖으로 옮길 근거도 없다.

따라서 이번에는 제품 알고리즘을 수정하지 않았다. 검토된 원본 backend와
source pin, 세 분기 의존성, 전체점 채점, 64KiB 봉투 제한, 0.6초·1초 제한,
모호성·수렴·geometry gate를 유지했다. 5/10cm 잔차 비교도 정확도 판정이나
모호성 해제가 아니다. 새 2개 회귀는 제품 tree 밖의 로컬 시험 자료로 보존했다.

## 실제 실행한 로컬 검증

환경은 macOS, CPython 3.13.2 및 Node v22.17.1이다. 아래 첫 네 Python 명령과
JavaScript 명령은 수정하지 않은 `d16fca6` 소스 스냅샷에서 실행했다.
기존 가상환경을 재사용했고 의존성 설치나 SDK 변경은 하지 않았다.

| 명령 | 실행 | 통과 | 실패/오류 | skip |
| --- | ---: | ---: | ---: | ---: |
| `python -m unittest discover -s tests -p 'test_sensor_tracking*.py' -v` | 26 | 25 | 0 | 1 |
| `python -m unittest discover -s tests -p 'test_global_observation*.py' -v` | 31 | 31 | 0 | 0 |
| `python -m unittest discover -s tests -p 'test_external_global_observation.py' -v` | 15 | 15 | 0 | 0 |
| `python -m unittest discover -s tests -p 'test_observation_*.py' -v` | 68 | 68 | 0 | 0 |
| `python test_deadline_stage_boundaries.py` (로컬 검증 자료) | 2 | 2 | 0 | 0 |
| `node --test tests/test_sensor_tracking.mjs tests/test_global_observation.mjs tests/test_live_observation.mjs` | 56 | 56 | 0 | 0 |

Python 총 142건 중 141 통과, 1 skip이며 JavaScript 56건은 모두 통과했다.
skip은 macOS에 `/proc/self/fd`가 없어 Linux FD inventory 시험을 실행하지
못한 한 건이다. 실제 Open3D와 원본 backend를 실행한 시험은 아니다.
시험 후 스냅샷의 일반 파일 763개를 Git archive 원본 바이트와 대조해
불일치 0건을 확인했다. 문서 3개의 공백·로컬 링크 13개와 tracked source의
secret scan도 통과했다.

추가 회귀는 기존 fake IPC worker와 통제된 monotonic clock을 사용한다.
pin preflight에서 0.601초가 소비되면 IPC write 0회로 거부되는지, 결과 검증에서
0.601초가 소비되면 반환·sequence/stamp 갱신 없이 닫히는지 확인했다.
각 시험의 owned fake 자식은 정리됐다. 실제 archived seed는 사용하지 않았다.
스냅샷·시험 파일·전체 로그·해시 영수증은 private 로컬 검증 폴더에 보존하며
실센서 원본이나 비공개 backend 소스를 이번 문서에 복사하지 않는다.

이번에는 제품 코드를 바꾸거나 커밋하지 않아 전체 Python/브라우저 suite를
반복하지 않았다. 기존 Ubuntu CI를 이번 macOS 시험이나 d16fca6의 새 CI 확인으로
대체하지 않는다. 10월 20일 보고서의 CI 수치는 그 안에 명시된 debba9c 기준이다.
이번 후속에서는 새 GitHub CI 조회도 하지 않았다.

## 남은 조건과 다음 최소 작업

- 원격 프로세스 분리 진단은 10월 21일 17:14:44 KST 자원 전제에서 중단됐다.
  UID 1000에 위임된 cgroup은 memory/pids만 제공하고 CPU hard cap이 없었다.
  순차 0회·분리 0회, 새 경로와 cgroup 생성 0회다. 첫 실패 후 exact archived
  seed 확인도 진행하지 않았다. 권한·서비스를 고쳐 우회하지 않았다.
- 재개하려면 현재 허용 범위에서 CPU/memory/pids 제한을 실제로 보장하는
  실행 경계, 기존 seed의 원본 위치·정확한 4×4 값과 입력/소스 해시를 먼저
  확인해야 한다. 이를 충족하기 전 native 진단 계산은 시작하지 않는다.
  위 18:07~18:11 읽기 재개에서 seed/입력 근거는 확보했으며 자원 보장은 남았다.
- 성능 개선을 판단할 최소 근거는 같은 입력·seed·pin으로 분기별 refinement와
  full-score 및 부모 preflight/IPC/validation 비용을 구별한 기록이다.
  이번에는 새 native 측정이나 성능 개선을 주장하지 않는다.
- tracking GET이 검증 과정에서 owner를 무효화할 수 있는 점과 parameterless
  stop의 generation 경합은 별도 설계 검토 대상으로 남는다. 이번에는 읽기 API를
  더 호출하거나 freshness 무효화 동작을 약화하지 않았다.
- 현재 본체 pose, 안정적 0.6초 추적, source clock/body extrinsic, 독립 정답 기반
  정확도 및 주행 적용은 여전히 미검증이다.
