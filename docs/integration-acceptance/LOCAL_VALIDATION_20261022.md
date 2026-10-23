# 2026-10-22 운영 관측 후속 — 설치·실기 정합·UI 계약 확인

## 2026-10-23 00:39 KST 추가 승인 passive 수집 — 맥북 사본 동결 완료

전원 종료 전 실측·보존의 새 사용자 승인으로 기존 발행 입력만10초 구독했다.
이전 절의 새 capture0회는 그전에 완료된 분석 범위다. 센서·서비스·카메라·제어
producer 시작/재시작이나 TF·initialpose·goal·자세·이동 명령은 없다.
raw64k/converted16k 각각3프레임의 원본CDR·전체payload·XYZ와 선택IMU/odom/lowstate,
수신10초 통계를 보존했다. 연속bag 또는 연속IMU archive는 아니다.

수집10.00154초/exit0, timeout PID/PGID193198 회수·그룹 부재 확인. 저장128MiB,
주소공간2GiB, 외부watchdog30초+kill grace5초이며 CPU quota 추가는 없다.
원격55파일19,291,074bytes와 맥북SHA가 모두 일치한다. 모든6개 LiDAR 프레임의
field/stride/endian에 따른 독립 XYZ 디코드가 저장bytes와 같고240,000점 모두finite다.
지도·config·calibration·기존11후보/backend까지88파일의동결사본은 private
`lidar-passive-20261022T1538Z/frozen/`이며 manifest SHA는
`5139c1035956290e6360f00c034620fc9275802e29ed0bb995ba108e242bf18a`, archive SHA는
`e867f4ac665e9b58e7159a86185c45d26f9b0e304350b29ef05ee93dd7c6569b`다.

세쌍 모두 converted는 raw의매4번째XYZ/intensity/ring과정확히일치한다. raw의16ring
중0/4/8/12만남으며 relative point time도 rawtimestamp차와일치한다. source header의
clock영역은서로다르고미검증이다. 현재설정·실행파일·교정CSV해시는private영수증에
있으며 장치flash/보정값은수정하지않았다. TF·FAST-LIO출력은수집0건이다.

수집후00:42:57KST에180sourcehash와14owner clear, dashboardPID75863/NRestarts0,
bridgeOFF/globalgen1/trackinggen0·processing budget disabled/watchdog60유지를
확인한뒤장비접근을끝냈다. 이후에는Mac불변사본만분석했다. 기존T를고정한거리계산
1회(1.526초)는새정합·최적화·후보채택이아니며, 새converted3개잔차22.989–23.054cm,
전체raw16ring도23.561–23.590cm였다. ring감소하나를원인/해결책으로단정하지않는다.
이전잃어버린scan복원·현재pose정답·본체정밀정확도·주행검증은아니다.
private README/ANALYSIS/FROZEN_RECEIPT가정확한source/runtime/config와한계를보존한다.
제품변경·배포·commit/push는없다.

## 2026-10-23 저장 정합 원인 분석 — 로컬만, 새 장비 실행 없음

GitHub `git ls-remote` main과 local HEAD는 모두
`e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`였다. dirty main의 UI·시험·문서 변경을
보존했다. 이번 제품 코드 변경·배포·commit/push는 없다. 아래의 static UI 설치
기록이 최신 실제 배포이며, 이번 보고서를 설치 완료로 간주하지 않는다.

정확한 retained job `1f554b10a68d0220b3d26667` JSON SHA256은
`5116c90775732ba64d80f99420931d19b0bc7bd6cf1eae04487a9a7cdb0e7355`다.
계산scan16,000점의 metadata SHA는
`7994520370eadf422e0844f8d51992c2bae58b9822cb2300def9b1b7e7affe0d`,
epoch `928a4784db7b6b1311a0f2acb053653d`, header stamp `1792678892357536793`이다.
source `/velodyne_points`/`hesai_lidar`는converted 입력이며8,000점preview와 다르다.
SI/clock/frame-axis/deskew/upstream은 독립 검증이 없다. bounded 로컬 inventory와
5개archive에서 최신numeric bytes를 찾지 못했다. 현재로봇tmp의 새조회는 하지 않았고,
19일 scan이나 새capture를 대신 사용하지 않았다. 보존코드의일회성XYZ소비·scope정리
경로와 실행영수증은 일치한다. 최신 scan잔차재계산/대응점분석은 미수행이다.

원본18일PCD SHA `c347faea6fd7a2f353b39f1f69f93cab8f2c6243299f90f87e54b7d8172ce4b8`
와25,666점의float64 XYZ SHA
`2e436c8cd41db44ac7130d81df8b23dd01e4875dd42ffcb1c1dbd18780da5852`는 직접 일치했다.
map-onlyKDtree에서NN중앙값3.53cm/p90=9.64cm다. 이것은scan잔차·표면coverage·
생성voxel·정확도증거가 아니다. 보존query YAML의surf/map0.5m와decimation4 bridge
소스는 그시점근거이며, 원지도작성시effective params/executable/firststate가 없어서
최신입력이나 원지도generation설정으로 단정하지 않는다.

선택index2의conditional RMSE0.230319m(거리gate0.75m), full RMS0.446447m,
capped RMS0.319901m, overlap14452/16000=.90325를 분리했다. 이는단방향최근접거리이며
bodyposeerror가 아니다. 1,548점(9.675%)의gate밖tail은aggregate상RMS1.2509m,
전체제곱오차약75.96%다. 동적물체등으로 판정한것이 아니다.11후보capped항등식은
최대1.11e-16m오차로 일치했다. 55쌍의저장SE3비교에서duplicate경계안은(2,9)뿐이다.
11records/10비중복표시를 구분한다. 후보10은2와17.09cm/2.743°차이,
conditional RMSE차1.024cm다. 후보4는4.254m/179.782°차이에도overlap93.65%,
capped0.329253m다. 복수위치의비슷한점수는확인되나 실제대칭·부분중첩원인확정은아니다.

pin SHA `47ea8760ff6a0522067850a6bd10b330ca8a21c9c5ed12c82a1936ba9541bcef`의
7Python소스와preserved backend가 일치한다. pin은수신후source영수증이며native의존
전체binary pin이아니다. worker SHA `8fb2aed818cf3c99bfbad45ec669fc08ea2f1f322fa00d0b353dbb3f2ca8b662`,
compat SHA `0ae898d09453b59b3daf2bdb6843a2f05c901f8697b44802a1ed801720e1067b`다.
기존adapter는원5cm gate를branch ranking/retention전에제거하며원gate기록을보존한다.
이후allow_ambiguous의conditional RMS최저선택은branch capped순위와다르다.
5/10cm sidecar는comparison-only이고원선택을재생하지않는다.이번에는어떤정책·문턱·
filter·voxel·점수순서도바꾸지않았다. 확인된제품metric버그는없다.

고정proper rigid extrinsic은unrestricted SE3에흡수될수있어그것만을잔차원인으로
단정할수없다. 유한RANSAC/voxelization의수치해동일성을보장하는설명은아니다.
지도작성중누적왜곡·time/deskew·시야변화는미확인이다. covariance고유값비율은
점분포지표이며정합Hessian/국소관측성/정답정확도가아니다. refinement_stationary도
수치update정지이지실제로봇정지증거가아니다.

private `lidar-integration-20261022/followup/alignment-cause-analysis/`에보고서,
JSON/CSV·60초상한재현도구·합성시험·exact SHA manifest를추가했다. input상대경로오류
1회는파일stat에서계산전중단했고, 절대경로수정후map-only/aggregate분석1회가0.833초에
완료됐다. KDtree k2/workers1이고dense N×M/새registration이없다. 합성10시험통과후
all-inlier모순RMS거부를보강해관련2시험통과(1개반복,총11고유시험). 이보강은현재
모든후보에tail이있어결과를바꾸지않으므로계산을반복하지않았다. 전체CI미반복.

새실센서관측·raw캡처·registration·benchmark·원격쓰기·배포·restart·STOP·카메라·
TF·initialpose·goal·tracking·제어·주행은0회다. 기존유한watcher로그만참고했으며
그기록을현재시각으로바꾸거나중복watcher를시작하지않았다. 다음에는별도승인범위에서
정확한rawPointCloud2+XYZ/hash+source-clock/point-time/effective config를먼저보존한뒤
동일자료의공간별잔차를검토해야한다. 지금그새실기를수행하지않았다.

## 2026-10-23 00:12 KST 과거 결과 재조회 UI — 실제 반영·저장 결과 표시 확인

기존 GET status/job 상세만으로 최근 완료 결과 선택·명시적 열기·이전 ID 입력·JSON
내보내기를 연결했다. 새 서버 API·pending 위조·자동 채택/추적은 없다. status의 latest와
이 화면에서 연 결과만 목록에 표시하며, 다른 보존 ID는 직접 입력한다. 최대32개
메모리 보존은 서버 재시작 후 보장되지 않는다는 한계를 화면에 표시했다.

main은 e70ef825이며 기존 미커밋 변경을 보존했다. 실제 d16 통합본+승인된 기존
7개 override+b68d0c6를 바탕으로 runtime 전용 최소 static3파일을 반영했다. 공개
main 파일을 통합본 위에 통째로 복사하지 않았다. 설치·HTTP·최종 SHA256은 다음과 같다.

- `global_observation.js`: `db559f6201f5901f1b77ebcd6715b1e835c3ebcc8791d5f341590b61ff15df33`
- `global_observation_contract.js`: `fc87813876120641e70cfca29e0c82d12b3a16f81346f431d91913c7ee52af77`
- `global_observation_integration.js`: `0d617fcda42b223e14c806f1a31b54907ce25b8eb4471f7caa2ad5f587eb5331`

코드 검토에서 이력 변경의 record 초기화가 활성/pending sensor 관측을 간접 중지할
수 있는 경로를 발견했다. 순수 snapshot callback으로 active·previewSuppressed·
stopRequested·canRetry를 검사하여 진입·선택 해제·최종 응답 시 이력 전환을 차단한다.
세 번째 통합 파일도 기존 최소 정적 반영 범위에 포함됨을 task relay로 확인했으므로
파일 개수만을 이유로 추가 사용자 승인을 요구하지 않았다. 초기 2파일 준비안만
설치하면 안 된다. 기존 ambiguity·편집 지도 경고·compact residual·snapshot/exclusive
연결을 보존했다. 실제 원본 모호성 정책이나 정합 gate를 새로 변경하지 않았다.

최초 source가 GET 도중 도착하는 경우도 완료 직전에 현재 map/source로 재검증한다.
이전 generation은 displayRecord로만 표시하고 tracking record로 전달하지 않는다.
같은 generation의 전달에도 `closed === false`와 `active === null`을 정확히 요구한다.
기존 값·타입·키·배열 순서·map/revision/frame/epoch 검사는 유지한다. 오류/404·새 입력·
map/source/dispose·지연 응답은 이전 결과 재등장을 막으며 failed/cancelled는 성공
결과 없이 실제 상태/reason을 표시한다. 이것이 추적 시작 승인이나 정확도 합격을
뜻하지 않는다.

00:07 preflight에서 fresh battery56%/age0.044초,14owner clear, broker2816/UID1000
camera reserved=false·owned_session=null과 원본185source/config/map/pin hash 및
3파일 uid/gid/mode/mtime/inode/device/HTTP를 확인했다. 00:09:34~35에는 같은 조건을
새로 검사한 뒤 원본3개 bytes/metadata를 새로 백업했다. integration→contract→panel
순서로 같은 filesystem에서 교체했으며, 후보 SHA와 정확한 file identity가 유지된
파일만 역순 복구하는 스크립트를 먼저 보존했다. 원본 백업·영수증·조건부 복구는
`/home/unitree/robot-scope-deploy/static-history-20261022T150833Z-48113132/`에 있다.
atime은 검증 읽기로 바뀔 수 있으므로 atime까지 불변이라고 주장하지 않는다.

실제 Maps 화면을 정상 reload하고 18일 3D PCD25,666점을 선택한 다음 기존 job
`1f554b10a68d0220b3d26667`을 선택/열어 **SUCCEEDED · HISTORICAL_ONLY 실제 표시**를
확인했다. 강제 controller 주입이나 새 계산은 없었다. 원본 지도 revision
`785163484d99f4e00101e8294a110f440311ad46bc52a53e3af8a80abfb8a288`, source stamp
`1792678892357536793`ns, `hesai_lidar`, converted/clock UNVERIFIED, epoch
`928a4784db7b6b1311a0f2acb053653d`가 유지된다. 조회 당시 host receipt age는2924.827초로
표시되며 원본 clock freshness가 아니다. 원본 후보2/11의 RMSE0.2303192101m,
overlap0.90325, AMBIGUOUS_ALTERNATIVES와 대안10개·품질 경고·body pose null을
보존했다. 추적 시작 버튼의 정상 handoff는 준비됐지만 클릭하지 않았다.

새 합성 단위64/64(20 top-level+44 subtests), 합성 브라우저4/4, 기존 관련 JS12/12,
runtime 동일64벡터, 실제 보존 JSON+합성 status wrapper6조건, 실제 runtime 모듈+
합성 sensor API 통합5/5가 통과했다. runtime64는 고유128시험으로 합산하지 않는다.
통합 시험의 합성 sensor start POST2회와 STOP0회는 실제 장비 동작이 아니다.
실제 화면의 JSON과 screenshot/AX·콘솔 warn/error0개를 보존했다. browser per-request
byte trace는 없어 파일+HTTP SHA와 정상 패널 실행을 구분한다. 실제 UI JSON 다운로드는
별도 실행하지 않았으며 export는 합성 브라우저에서 검증했다. Python 제품 변경이
없어 전체 Python/CI를 반복하지 않았고 commit/push도 없다.

00:12:13 최종 읽기에서185hash·3파일 metadata/HTTP·보존 job context/result 불변과
14owner clear를 확인했다. dashboard PID75863/InvocationID
`64042df9601349f1ad68e689ee8a8247`/NRestarts0 유지, bridge OFF/disabled,
broker2816/UID1000 idle, battery54%/age0.011초 fresh다. global generation1,
tracking generation0/WAITING_GLOBAL이므로 추가 global·실제 tracking은0회다.
서비스 restart·STOP·카메라·제어·TF·initialpose·goal·주행도0회다. 기존 유한 battery
recorder를 재기동하거나 중복 watcher를 만들지 않았다. 주간 remaining35%다.

private `lidar-integration-20261022/followup/history-retrieval-ui/`의 manifest,
preflight/install/postflight 영수증, 실제 화면/JSON, 시험·원본·payload·index를 따른다.
이전 immutable archive와 원인 미확정 첫 static 설치/복구 이력은 그대로 보존했다.
초기 NOT_DEPLOYED 준비 manifest는 최종 설치 상태와 구분하여 보존했다. 실제 tracking,
본체 extrinsic·독립 정답 기반 정확도·deskew·원본 clock·sensor-to-photon 지연은 미검증이다.
다음 최소 작업은 새로운 계산이 아니라 필요 시 현재 조건과 기존 정책을 만족하는
별도 sensor tracking 관측이며, 이번 정적 UI 반영은 저장 결과 표시 확인으로 끝낸다.

## 23:45 KST 정적 JS 1파일 설치 — HTTP 확인, 과거 결과 화면 재조회 미완료

23:38 읽기 전용 전제로 원본 JS의 hash·uid1000/gid1000/mode0644/mtime과
183개 source/config/map/pin/초기화 코드가 보존됨을 확인했다. bridge OFF/disabled,
broker PID2816/UID1000·카메라 예약/세션 없음, battery65% fresh였다.
첫 반영 후 aggregate ownership이 불확실하여 원본 한 파일을 즉시 복구했다.
해당 실패의 세부 unknown owner 응답은 저장되지 않았으므로 경합 등 원인은 미확정이다.
복구 hash·HTTP·metadata·서비스 identity 및 현재14 owner clear를 다시 조회한 뒤
같은 조건으로1회 재시도했다. 불확실 상태를 idle로 해석하거나 gate를 낮추지 않았다.

최종 설치/HTTP SHA256:
`b68d0c6471eb30618a1c4ec020e7bd6c4ad3cc95dd482d59ec7bb55df3e51313`.
대상은 runtime 전용 `global_observation_contract.js` 한 파일이며 main 버전의
전체 복사가 아니다. 원본 `4b999b1c27a1c276b666a2b0da00eefbf54f3423f9d5d4b7ad0a6287407c5722`,
uid/gid1000,0644,mtime_ns1792495299206923680과 복구 스크립트를
`/home/unitree/robot-scope-deploy/static-contract-20261022T144218Z-7880e8b5/`에 보존했다.
원복은 대상이 이번 candidate SHA일 때만 정확한 한 파일을 복구하며, 타 사용자
변경을 덮어쓰지 않는다. 원본 backup byte hash도 저장 전 확인했다.

전후 dashboard PID75863, InvocationID `64042df9601349f1ad68e689ee8a8247`,
NRestarts0 유지. 서비스 restart/STOP·카메라·제어·새 정합·tracking0회다.
원래 live global1회/이력과 tracking generation0을 유지했다.

실제 새 IAB 화면에서18일3D PCD25,666점과 전역/센서 관측 패널이 열리고
콘솔 warning/error 수집0건이었다. **기존 succeeded job 결과의 화면 표시 성공은
확인하지 못했다.** reload 뒤 pending이 없어 poll이 저장 latest를 자동 채택하지
않는 별도 UI 한계다. UI는 IDLE/HISTORICAL_ONLY, tracking 시작 disabled이며,
정상 읽기 전용 과거 결과 선택 경로가 없다. API의 같은 job/request·원래
AMBIGUOUS_ALTERNATIVES·RMSE0.230319m/overlap0.90325는 그대로 보존된다.
원래 과거 결과를 현재 pose로 승인하거나 controller 주입·새 scan으로 우회하지 않았다.
수집 가능한 service access log에는 정적 모듈 요청 행이 없어 browser가 파싱한
byte의 별도 네트워크 trace는 미확보다. 파일/HTTP 해시와 실제 패널 로드는 구분한다.

기존 sensor policy는 historical seed 경과시간 TTL을 두지 않는다. 현재 입력
age≤1초·동일 map revision/topic/pipeline/frame/observer/epoch·증가 stamp,
새 capture/응답 freshness·연속3회·변화량 제한·watchdog60초는 유지된다.
현재 화면의 정상 handoff가 없어서 tracking을 시작하지 않았으며 오래된 seed라는
가상의 정책 거절 사유를 만들지 않았다.

기존 main35개·runtime26개 합성 시험(서로 겹침), 실제 retained JSON offline replay
PASS를 반복하지 않았다. 이번에는 실제 설치 hash/HTTP·원본 복구·서비스 identity·
기존 job 재조회·실제 패널 화면을 확인했다. 추가 native/전체 CI0회,
local-only/no commit-push 유지. 23:44:37 KST battery63%/age0.008초 fresh,
14 owner clear, bridge OFF/disabled, 주간 remaining39%. 기존 유한 watcher만 재사용했다.
다음 최소 작업은 읽기 전용 과거 job 선택/재조회 UI 연결이며 이번1파일 범위 밖이다.

## 23:31 KST 새 live scan 1회 — 결과 보존, UI 불일치, tracking 미실행

배포 승인과 별도로 정지 LiDAR 위치 추정·대시보드 검증 안내에 사용자가
`계속 진행`한 직접 문맥을 확인해 기존 담당에서 진행했다. 배포 manifest와
기존 미승인 초안은 수정하지 않았다. 관측 전 주간 remaining44→43%, fresh
배터리72→71%, 180개 source/config/map/pin hash, 14개 순수 소유권 clear,
broker session/reservation 부재와 OS native 작업 부재를 확인했다. UI 초기
`control`/`navigation` GET은 만료·출력 flush 가능성이 있어 무lease·무pending을
먼저 확인했다. Maps 최초 열기/지도 선택은 카메라·ARM·bridge를 시작하지 않았다.

실제 실행본은 계속 **d16fca6 통합 baseline + 앞 절의 7개 제품 override**다.
공개 main e70ef825 전체를 장비에 복사하지 않았다. domain0/CycloneDDS,
backend pin SHA `47ea8760ff6a0522067850a6bd10b330ca8a21c9c5ed12c82a1936ba9541bcef`,
`processing_budget_s=null/disabled`, `resource_mode=user_scope_v1`을 유지했다.

23:21:32 KST 실제 Maps UI에서 **전역 시작 1회**를 실행했다.
job `1f554b10a68d0220b3d26667`, request
`global-9d7eb75279438821ed3aaa0763d7b3cc`다. 18일 3D 지도
`6d2cecc0a5581f82edba57ca` / revision
`785163484d99f4e00101e8294a110f440311ad46bc52a53e3af8a80abfb8a288`,
PCD SHA `c347faea6fd7a2f353b39f1f69f93cab8f2c6243299f90f87e54b7d8172ce4b8`,
frame `camera_init`의 **25,666점 전체**와 `/velodyne_points` converted 입력
`hesai_lidar`의 **16,000점 전체**를 사용했다. preview8,000점으로 계산하지 않았다.
source stamp `1792678892357536793`, epoch
`928a4784db7b6b1311a0f2acb053653d`, scan XYZ SHA
`7994520370eadf422e0844f8d51992c2bae58b9822cb2300def9b1b7e7affe0d`다.
원본 센서 clock/메시지 publisher/deskew/본체 extrinsic은 검증하지 않았다.

API는 `succeeded/worker_active=false/active=null`로 결과를 보존했다.
캡처0.118초, 캡처·준비·초기화·정합·IPC/정리를 포함한 job20.959초,
runner18.356초, backend query13.962초, map preprocess2.178초였다.
11개 중 선택 후보2의 RMSE는 **0.230319m**, overlap **0.90325**,
inlier14,452/16,000이다. `AMBIGUOUS_ALTERNATIVES`와 기존
`allow_ambiguous=true`를 그대로 보존했다. 계산/보존 성공은 품질 합격이나
본체 정확도 검증이 아니며 5cm/10cm는 진단 비교값이다. threshold/freshness/
timeout을 바꾸지 않았다. sensor-to-photon 전체 지연은 측정하지 못했다.

실제 scope `robot-scope-global-4792f0f25efa476c93f73f48619eb2de.scope`에서
UID1000, PID/PGID/SID105579/start_ticks557445, memory2GiB/swap0/tasks64,
RuntimeMax120초, native import 전 proof/ACK, OMP/BLAS/MKL1을 확인했다.
1Hz 표본의 최대 memory.current188,956,672bytes/최대tasks3,
관측 memory.events의 oom/oom_kill/max는0이었다. memory.peak는 지원되지 않아
실제 최대 메모리로 주장하지 않는다. leaf CPU controller/cpu.max는 없고
상위 user.slice의 `max 100000`을 기록했다. 새 CPU quota는 없다.
memory.oom.group0/atomic OOM group kill=false도 그대로 기록했다.

23:21:52 KST부터 정확한 cgroup 부재와 포착한 PID105579/105601/105602 부재,
manager not-found를 함께 확인했다. 유한 watcher는23:25:12 KST
`OBSERVED_SCOPES_CLEAN`/discovery errors0으로 종료했다. raw capture는 consumed/
in_flight=false이며 23:25:30 KST 180개 hash 보존·14 owner busy/unknown 없음,
global history generation1을 확인했다. 기존 verify-installed/rollback wrapper는
generation0을 전제하므로 재실행하거나 history를 지우지 않았다.

**실제 UI는 `RESULT_CONTRACT_MISMATCH`로 완료 결과를 거부했다.** 서버 job과
result의 captured_context 값은 같지만, backend가 object key를 정렬해
`JSON.stringify` 문자열 순서가 달라졌기 때문이다. screenshot/DOM과 실제 저장
JSON으로 재현했다. tracking 버튼은 disabled이고 **tracking 시작/중지0회**다.
API 시작이나 browser 주입으로 UI 검사를 우회하지 않았다.

로컬 main의 `global_observation_contract.js`에서 captured context 비교1곳만
object key 순서에 무관한 재귀 JSON 동등 비교로 바꿨다. 키 누락/추가, 값·타입,
frame/epoch/stamp/profile, 배열 순서와 historical 제한은 유지한다. 합성 회귀는
main global12+주변live23=35개 통과했다. 실제 실행본은 main과 다르므로 별도
runtime payload를 만들어 통합 ambiguity/tracking 코드를 보존했고, 그 variant의
26개 시험도 통과했다. 실제 retained JSON의 오프라인 재생은 수정 전false→수정 후
true, controller record 채택 및 ambiguity 검증true였다. 이는 새 native 계산이나
실제 수정 UI 통과가 아니다. 전체 CI/기존 저장 scan benchmark는 반복하지 않았다.

장비의 실제 JS SHA는 `4b999b1c27a1c276b666a2b0da00eefbf54f3423f9d5d4b7ad0a6287407c5722`,
준비한 runtime payload는 `b68d0c6471eb30618a1c4ec020e7bd6c4ad3cc95dd482d59ec7bb55df3e51313`다.
대상은 `/home/unitree/robot-scope/robot_dashboard/static/features/maps/global_observation_contract.js`
**1파일**이다. 새 설치 전 원본 bytes/owner/mode/mtime를 별도 백업하고, 복구 시
candidate hash가 유지된 그 파일만 원복한다. static-only 반영에는 service restart나
정상 종료의 final STOP이 필요하지 않다. 아직 장비에 반영하지 않았고 별도 결정
대기다. 앞서 묶음 질문의 추가 새 scan 정합 항목은 철회했다. 수정 검증을 위해
완료한 global을 반복하지 않으며, 기존 invalidated UI pending은 자동 복원되지 않는다.

23:30:29 KST 배터리 **68%/age0.015초/fresh**, cloud10.0Hz/age0.011초,
odom184.98Hz/age0.008초, dashboard PID75863/NRestarts0, bridge OFF/disabled다.
주간 remaining41%(used59%)를 확인했다. 기존 유한 배터리 기록기와 이번 기록 도구
잔여 프로세스는 없었다. 이 관측 중 배포/서비스 restart/카메라/주행·자세·모터·ARM·
bridge 활성화·TF·initialpose·goal은0회이며 commit/push도0회다.

private evidence: `lidar-integration-20261022/live-observation-execution/`의
`EXECUTION_SUMMARY.json`, `global-job.json`, `global-api.jsonl`, `scope-watch.jsonl`,
`postflight.json`, `ui-contract-failure.png/.json`, `ui-fix-preparation/`이다.
다음 최소 작업은 static1파일 반영 여부 결정과 기존 결과 기반 UI 연결 검증이다.
tracking 자원·연속성·표시와 독립 정답 기반 본체 정확도는 미검증으로 남긴다.

## 23:01 KST 실제 배포 결과 — 앞선 미적용 기록을 대체

현재 사용자의 정지·무작업·전환 중 새 작업 금지 확인과 배포/실패 시 원본 복구
승인이 trusted relay로 전달됐다. 승인 manifest는 변경하지 않았으며 SHA256은
`7055f7ebf1779b39fdd6379db96b4a93c2a6385d3720cefc9279bbc4b888a0dc`다.
manifest의 `NOT_GRANTED`는 동결 당시 기록이고, 별도 `approval-relay.json`에
이번 승인 범위와 출처를 보존했다. 새 global/tracking POST나 native 계산은
이번 승인에 포함되지 않아 실행하지 않았다.

22:51:44 KST 대상 source/metadata/boot/PID/환경을 재확인하고 정확한 7개 제품과
drop-in을 별도 배포 경로에 준비했다. baseline에 순수 조회가 없으므로 최초
메모리 상태는 `UNKNOWN_OPERATOR_ATTESTED`로 남겼다. 기존 안전 GET 네 경로,
broker capability/peer와 OS 프로세스·기기 FD를 확인했으며 활성 작업/예약은
발견되지 않았다. D435i 장치 FD 소유자는 없었고 읽지 못한 PID도 없었다.
이는 현장의 물리 정지 상태를 소프트웨어가 직접 측정했다는 뜻은 아니다.

실제 변경은 기존 d16fca6 통합 실행본 위 제품 7개와 다음 drop-in 1개다.
공개 main 전체를 장비에 복사하거나 설치 commit을 새 Git commit으로 표현하지 않는다.

- `application/sensor_tracking.py`, `application/ownership_readback.py`
- `api/routers/system.py`
- `relocalization/sensor_tracking_process.py`, `external_global_observation.py`,
  `native_observation_scope.py`, `native_observation_scope_admission.py`
- `/etc/systemd/system/robot-scope.service.d/90-observation-resource-launch.conf`

제품 경로는 `/home/unitree/robot-scope/robot_dashboard/` 기준이다. 7개 설치 SHA와
UID/GID/mode를 승인 manifest와 대조했고 나머지 고정 source/config/map/backend/unit
173개 hash가 보존됐다. 별도 inventory에는 새 native scope 두 경로가 빠져 있어,
7개 전체의 부재→설치는 wrapper의 전후 inspect와 최종 source guard로 검증했다.

22:55:11~22:55:17 KST `deploy` **1회**에서 정상 dashboard restart를 요청했다.
정상 종료의 기존 final signed safety STOP 경로와 소유 Hesai/XT16 preview 재시작을
포함했고 브리지는 OFF/disabled를 유지했다. STOP의 실제 물리 효과는 측정하지 않았다.
새 PID는 **75863/start_ticks399771**, InvocationID는
`64042df9601349f1ad68e689ee8a8247`, active/running·NRestarts0다.
실행 Python은 `/usr/bin/python3.10`이고 기존 ROS domain0/CycloneDDS/backend pin을
유지했다. broker PID2816, owner probe705, MJPEG relay1000도 보존됐다.

초기 wrapper 사후 검사는 **`PRESERVED_ENVIRONMENT_DRIFT`, exit1**로 끝났다.
당시 차이 내용은 수집되지 않아 시작 과정의 일시적 현상이라고 원인을 확정하지
않는다. 뒤이은 `inspect`에서는 보존 환경 차이가 `{}`였고, restart를 반복하지 않고
읽기 전용 `verify-installed`로 설치를 확인했다. 22:59:03 KST 최종 결과는
`INSTALLED_SOURCE_ENV_LOCAL_CONSTRAINTS_AND_BROKER_VERIFIED`다.
기존 journal의 `RESTART_INTENT`와 오류 로그는 수정하지 않았으며 별도
`reconciliation.json`에 후속 검증 성공을 연결했다. rollback은 필요하지 않아 0회다.

실제 프로세스 환경과 메모리에 로드된 정책 모두 다음을 확인했다.

- processing budget: `disabled`, `processing_budget_s=null`, enabled=false.
  기존 0.6초 값은 legacy 설명 필드에만 남고 override는 지원하지 않는다.
- resource mode: `user_scope_v1`; startup30초·operation watchdog60초 유지.
- 순수 GET: HTTP200, `Cache-Control: no-store`, 14 components 중 12 observed/clear,
  선택 구성 2 absent, busy/unknown 없음. globally_atomic/restart_authorized/
  physical_state_verified는 여전히 false다.
- broker session=null/camera reserved=false. 카메라 시작은 0회.
- dashboard와 user 부모 cgroup 값은 배포 전후 동일하며 `cpu.max=max 100000`,
  CPUQuota=infinity다. 새 CPU quota나 부모 controller 변경은 없다.

22:57:09~22:58:30 KST **81.048초 간격의 두 pinned state 표본**과 기존 relay의
30초 배터리 기록으로 사후 상태를 확인했다. 연속 센서 trace 시험은 아니다.
cloud10.00→10.01Hz/age0.085→0.012초,
odom202.30→184.88Hz/age0.008→0.008초로 둘 다 ok였다.
preview는 새 PID75922/parent75863으로 복귀했다. 기존 battery observer만 사용했고
중복 watcher는 만들지 않았다. 배포 전78%, **23:01:06 KST76%/age0.014초/fresh**였으며
수집 구간에 ≤20%나 stale은 없었다. 이 숫자는 날짜 있는 관측값이다.

원격 원본 백업은
`/home/unitree/robot-scope-deploy/ownership-budget-20261022-7055f7eb/backup`이며,
원본 bytes/존재 여부/uid/gid/mode/mtime 기록을 로컬 사본과 해시로 검증했다.
private evidence는 `robot-scope-hardware-validation-private/lidar-integration-20261022/`
`approved-deployment-execution/` 아래 `EXECUTION_SUMMARY.json`,
`remote-evidence/verify-installed-final.json`, 원본 backup, 초기 오류와 승인 영수증이다.
실행 evidence tar SHA256은
`5bb2c80ae8846a27e91f659d3ed82ffb5a910b9463e932aaf57463a6f57944da`다.

기존 로컬 시험은 ownership26+주변34+wrapper43 = **103개 통과**이며 이번에는
동일 suite/전체 CI/저장 scan benchmark를 반복하지 않았다. commit/push는 없다.
남은 별도 승인 대상은 현재 센서의 새 global observation과 새 seed tracking이다.
native child를 실행하지 않았으므로 실제 user-scope admission·memory/tasks 제한과
강제 정리 효과·계산 성능은 미검증이다. 과거 seed를 현재 위치로 재사용하지 않는다.
주행·자세·ARM·bridge 활성화·운영 TF·initialpose·goal·본체 정밀평가는 수행하지 않았다.

## 22:31 KST 이전 로컬 준비 기록 — 아래 미적용 상태는 당시 기록

## 구현과 검증

공개 main은 `e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`, 기존 통합 소스는
`d16fca6e2fb0c3528200b8c9bc8400f277ff1f02`다. 22일 `git ls-remote`로 두 ref를
확인했다. main에 없는 통합 모듈 전체를 다시 복사하지 않았다. 기존 미커밋 문서와
21일의 동결된 제품 5파일·시험·배포 초안을 보존하고 private evidence의 새
`lidar-integration-20261022/ownership-readback-candidate/source`에서 후속을 구현했다.
이 기록은 로컬 구현이며 commit/push 또는 로봇 배포 완료를 뜻하지 않는다.

새 GET `/api/v1/system/ownership-readback`은 기존 system router와 독립
`application/ownership_readback.py` 두 제품 파일로 구성된다. 고정된 실제 manager의
메모리 값과 소유권을 복사하며 control snapshot, lease 만료, STOP enqueue/flush,
adapter status, freshness 재검사, native 취소, 장치 열기와 서비스 명령을 호출하지 않는다.
기존 `/system/service`는 lifecycle blockers→control_snapshot→raw_snapshot→flush로,
`/navigation`과 `/slam/session`은 navigation gateway의 control manager.snapshot으로
이어질 수 있으므로 순수 조회로 재분류하지 않았다.

14개 소유자에는 SLAM 미저장·정리·카메라 예약, Nav START/localization의 실패 후
남은 token, 제어 lease와 대기 출력, 미션·planner preview, 취소 뒤 남은 raw capture,
dataset export, lifecycle 예약, global/relocalization/tracking 작업이 포함된다.
기존 preview 복구 감시와 실제 복구 작업을 구분한다. 락 경합·누락·지원하지 않는
형태는 unknown으로 남긴다. builtin 값만 제한적으로 복사하고 죽은 Thread를
`is_alive()`로 정리하지 않는다. 새 경로는 구버전에서 404이며, 구버전이 무시할 수
있는 query parameter로 위험한 기존 handler를 호출하지 않는다.

응답은 `robot-scope.ownership-readback.v1`, 현재 PID, host monotonic 관측 시각,
`Cache-Control: no-store`를 제공한다. `globally_atomic=false`,
`restart_authorized=false`, `physical_state_verified=false`다. 이는 재시작 허가나
전역 원자적 idle 증명이 아니다. broker·OS 소유권과 현장 조건이 별도로 필요하다.
실제로 구성된 sensor tracking execution policy도 그대로 복사하므로 설치 후
환경 변수만 읽고 유효 정책으로 오인하는 문제를 피한다.

소프트웨어 시험은 **26개 집중 시험 + 주변 34개 회귀 모두 통과**했다. 집중 시험은
기존 저장소 `.venv/bin/python`(Python 3.13, FastAPI 0.142.2), 주변 시험은
Framework Python 3.13으로 실행했다. 실제 manager/coordinator 생성자를 임시
디렉터리와 ROS stub으로 구성하고 producer/Popen·stateful callback을 금지했다.
만료 lease·대기 STOP/actions·generation·stale tracking·raw capture·종료 Thread의
읽기 전후 보존, 반환값 비공유, 경합·unknown·구버전404를 검증했다. 새 GET으로
달라진 API 목록 두 시험을 갱신했으며 mutation 103개는 그대로다. 초기 inventory
실패와 잘못된 unittest 호출/Python의 import 실패 로그는 별도로 남겼다. 전체 CI와
완료된 저장 scan 순차/분리 각3회 진단은 반복하지 않았다. 독립 정적 검토의
잔여 P1/P2는 없었다. 실센서 관측·실제 운영 readback 통과는 이 시험에 포함되지 않는다.

소스 동결 manifest SHA256은
`2881fdbed61eb81480f6decbcdb8779d4bb6246c4cf70a507a70b59755359334`다.
기존 동결 후보 대비 제품 2파일·시험 3파일만 다르며 기존 resource 제품 5파일은 같다.
`system.py` SHA256은
`9bc2f9c898a353462881883aff5fa8cb06aad0e473d56766954212b97aa2800b`,
`ownership_readback.py`는
`4f48e72fa51e75f4ff648cf98dace219de2c8dc73cdeea137a410a903f4bd004`다.

## 현재 운영 근거와 미적용 원인

22:18:14 KST OS/file 읽기에서 실제 `robot_dashboard/*.py` 전부가 보존 d16fca6
baseline과 일치했다. dashboard PID1006, InvocationID
`2e185c832f884d058d5333ae3d57006a`, active/running, NRestarts0이며 bridge는
inactive/dead·PID0·disabled였다. 후속 읽기에서도 같은 프로세스를 확인했다.
기존 새 조회 파일의 부재는 별도 최신 inventory에서 확인했다.

`ROBOT_SCOPE_SENSOR_TRACKING_PROCESSING_BUDGET_S`와
`ROBOT_SCOPE_OBSERVATION_CHILD_RESOURCE_MODE`는 실제 프로세스 환경에서 모두
없었다. 따라서 **운영 seeded 처리 예산 0.6초는 아직 적용 중**이다. 원인은
21일 후보의 배포가 이루어지지 않았기 때문이며 설정 파일만 고쳐 적용했다고
부르지 않는다. dashboard의 실제 `cpu.max=max 100000`, systemd CPUQuota 값은
infinity다. user@1000/user-1000에는 CPU controller가 위임되지 않았으며 user.slice는
`cpu.max=max 100000`이었다. 새 CPU quota를 만들거나 다른 제한을 삭제하지 않았다.

보존된 5파일 후보는 `processing_budget_s=disabled`와 `user_scope_v1`을 함께 요구한다.
seeded 처리 예산만 해제하고 startup30초·operation watchdog60초·owner60초,
기존 global 최대120초·freshness1초·frame/session/epoch/hash 검사를 유지한다.
자식은 UID1000 user scope의 memory2GiB·swap0·tasks64·유한 RuntimeMaxSec를
native import 전에 검증한다. 새 CPU quota는 없고 기존 제품 OMP/BLAS/MKL thread1은
유지한다. 이번 새 readback은 이 실행·안전 계약을 수정하지 않는다.

22:25:22 KST에는 실제 broker PID2816/start_ticks2310, cwd, 3개 코드 해시,
소켓 상대 UID1000/PID를 확인한 뒤 기존 `capability`만 읽었다. camera reserved=false,
session_id/generation=null, broker_owned_session=null이었다. 카메라 예약·preflight·시작은
호출하지 않았다. 이것으로 dashboard 메모리의 미저장 작업이 없다고 추정하지 않는다.

22:29:06 KST 정상 입력은 배터리83%(`/lowstate` age0.004초, `/lf/lowstate`0.014초),
cloud10.0Hz/age0.095초, odometry205.78Hz/age0.007초였다. 이는 기존 입력 API 관측이며
새 코드의 실센서 검증·화면 지연·실제 정지·본체 정확도를 증명하지 않는다.
기존 30초 배터리 watcher는 20분 유한 실행을 정상 종료했다. 추가 부하 전에는 다시
fresh 값을 확인하며 ≤20%는 즉시 기록하고 추가 부하를 보류한다. 누락/stale은 UNKNOWN이다.

## 배포 전제와 다음 최소 작업

현재 baseline에는 새 순수 조회가 없어 최초 재시작 전 미저장 메모리를 직접 읽을 수
없다. 이 한계를 코드가 해결한 것처럼 표시하지 않는다. 첫 설치는 현재 현장 담당자의
활성·미저장 SLAM/Nav/미션/capture/control 작업 부재와 전환 중 새 작업 금지 확인을
명시적 조건으로 하며, broker·OS·기존 안전 경로의 보조 근거와 결합해야 한다.

정상 dashboard 종료는 기존 `shutdown_control()`에서 final signed safety STOP을
발행하는 경로를 포함한다. 그 안전 동작을 제거하지 않는다. 서비스 재시작 시 기존
소유 Hesai·XT16 preview도 재시작된다. 따라서 “제어 출력 0인 재시작”으로 설명하지
않는다. 기존 bridge OFF 및 현재 정지·현장 독립 복구 조건을 전환 승인에 포함한다.

배포 준비는 새 22일 폴더에서만 진행한다. 정확한 7제품 파일과 2개 환경 키,
원본 bytes/존재 여부/권한/mtime 백업, 나머지 소스·설정·지도·backend pin 보호,
고유 restart intent와 응답 불명 시 inspect 절차가 대상이다. rollback은 복원 직전
파일별 drift와 소유 디렉터리를 확인하고, 원래 없는 파일만 제거한다. 구버전 복구 뒤
순수 endpoint가 없어지는 점도 UNKNOWN/operator-attested로 기록해야 한다.

현재 이 문서 작성 시점에는 서비스 변경·카메라 시작·native 계산·0.6초 예산 해제의
운영 반영을 실행하지 않았다. 다음 최소 작업은 검토한 배포 묶음의 현재 전환 승인,
실제 설치 후 PID·새 순수 readback의 유효 policy·broker·기존 입력 확인이다.
주행·자세·모터·ARM·bridge 활성화·TF·initialpose·Nav2 goal은 이번 작업에 포함하지 않는다.
