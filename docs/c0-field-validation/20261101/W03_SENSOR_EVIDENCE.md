# C0-W03 비이동 FAST-LIO 관측 증거 — 2026-11-01

**비이동 센서 입력 PASS; 지도 기준 초기 높이·기울기와 저장 지도 지속 정합 → TF → Nav2 연결은 BLOCKED.** 사용자가 현재 정지 상태 유지를 확인한 후 C0-W03 범위에서 관측 세션 한 번과 원상 복구를 수행했다. 이 문서는 기록 시점의 증거이며 이후 현재 상태로 재사용하지 않는다. 좌표값·원시 지도·원시 점군·인증정보는 포함하지 않는다.

## 실행 문맥과 측정

| 항목 | 결과 |
|---|---|
| 배포 실행본 | 코드 SHA `4f90612379705b7b7c8c86cca99941266e3ae611`; 13:03 KST readback에서 PID `24983`, cwd `/home/unitree/robot-scope-releases/robot-scope-4f9061237970`. 문서 Git HEAD와 실행 코드는 별개. |
| 준비 지도 | 3D `map1` ID `49ea555eea2f4ca1adaea223`, revision `c9ad9bcc4c8b7c02a47a0db5822707853110b60cb4b9ef837e42b0c32e3c823e`; 2D `map1_2D` ID `2fc7070075fd522860e67480`, revision `f691b8e98e81de784c89f98127de9f4ccff4aa487c76747b860bdd70a523cc76`. 준비 generation `b64ebca592b64ca7bd614f9eaebcc2b3`, pair valid. 선택은 실제 정합이나 Nav2 실행을 뜻하지 않는다. |
| 교정 | `operational-calibration.json` SHA256 `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226`, 관측 전후 동일. 교정 해시 일치만으로 지도와 중력의 관계나 실제 위치 정확도를 증명하지 않는다. |
| 관측 session | 13:04 KST 관측 start 요청 정확히 1회; session `45a2e046e1df4481810989446024cfc8`, 13:04:35 READY·active·observation_only. 동일 세대를 재확인한 후 13:04:41.854 stop 요청 1회(요청 시 약 25.4초 경과); 최종 STOPPED/inactive, busy·job pending false. 지도 정합 적용 없음. |
| source·동일 시각 | 13:04:36 preparation GET에서 `/cloud_registered`, `camera_init` 점군과 `/Odometry`, `camera_init` → `body` pose의 source stamp가 모두 `1793505875403625726`. observer `8eb7e5411fdba060b155716c466eebe6`; cloud publisher epoch `075808604c62e32b7f9271d53218eed8`, pose publisher epoch `140482e6a4a68a72a2967bee0cc80b29`. 수신 monotonic 차이 약 0.01255초. |
| 신선도·응답 | 직전 source readback의 등록 점군 publisher 1, 약 9.92 Hz, age 0.057초. preparation GET 0.625초, `evidence.valid=true`: 서버의 해당 시점 입력·subscription graph·수신 시간 검사 통과. 사전 준비 GET은 5.479초였으므로 간헐 지연의 완전 해결은 미입증이다. 수신 시각은 관측 host monotonic 기준이며 ROS source clock의 절대 정확도나 메시지별 publisher 귀속을 증명하지 않는다. |
| 본체 참고 자세 | 서버가 교정을 적용한 `camera_init` → `base_link` 참고 자세를 반환했고 `OBSERVATION_FRAME_ONLY_MAP_RELATION_UNVERIFIED`로 표시했다. 관측계의 상대값이므로 map 기준 z·roll·pitch나 지도상 로봇 추정으로 해석하지 않는다. |
| 지도 후보 | z=null (`MAP_ABSOLUTE_Z_UNVERIFIED`), roll/pitch=null (`MAP_GRAVITY_ALIGNMENT_UNVERIFIED`), `map_estimate_reason=NAVIGATION_JOB_NOT_RUNNING`. 입력이 신선해도 map 기준 관계가 확보됐다는 뜻은 아니다. |
| 정합·TF·Nav2 | 운영 matcher 없음, 보정 횟수·잔차·겹침·단일 TF 권한·지도 기반 표시·실제 Nav2 planner 결과 미측정. 저장 지도 지속 정합과 경로계산은 BLOCKED. 품질 잔차·겹침이 측정되더라도 실제 위치 정확도와 구분한다. |

## 전환과 복구

관측 전 확인에서 Nav2 pipeline/goal idle, lease inactive, deadman false, 명령 0, 관측 STOPPED, ownership busy/unknown 없음, bridge active였다. 기존 API와 gate를 통해 bridge stop을 한 번 요청하고 operation `succeeded` 및 systemd inactive를 확인했다. 정확한 세대의 관측을 종료한 후, 정상 gate를 통과해 bridge start를 한 번 요청했다. 최종 13:05:19에는 operation `succeeded`, bridge active/running 및 인증된 상태 ready/connected, status age 0.191초였다. HTTP 202를 완료로 간주하지 않았다.

관측 시작 시 시스템이 odometry source를 `/Odometry`로 선택했다. 관측을 종료한 뒤 odometry만 기존 auto/requested empty 상태로 복구했고, 선택된 odometry는 `/utlidar/robot_odom`으로 돌아왔다. 점군은 `/cloud_registered`의 pinned/persistent/fail_closed 정책과 선택값을 유지했다. 다만 점군 선택의 **in-memory origin은 기존 `persisted`에서 `user`로 변경**됐다. 같은 항목을 세션에서 재선택한 표시 차이이며 저장 source-selection 파일 해시는 전후 동일했다. 이 표시를 원복하기 위한 대시보드 재시작은 하지 않았다.

지도·주석 및 설정 총 **133개 파일의 전후 해시 집합이 동일**했다. source-selection SHA256은 `833ff1ecaaf2b546b89c268ac8758ddd4ce31078de178113efcf464fe5af21ee`. 최종 readback은 같은 지도 조합·generation, geometry null, runtime null/fresh=false, Nav2/goal idle, lease inactive·deadman false·명령 0, 관측 STOPPED, ownership busy/unknown 없음이었다. 이는 API readback이지 물리 정지의 독립 계측이나 실제 경로계산 증거가 아니다.

이번 작업의 관측 시작은 1회이며 Nav2 시작, initial pose, 정합 시작, goal, 자세 또는 물리 이동 명령은 0회다. 비공개 상태 readback은 작업환경에 보관했고 원시 점군은 저장하지 않았다.
