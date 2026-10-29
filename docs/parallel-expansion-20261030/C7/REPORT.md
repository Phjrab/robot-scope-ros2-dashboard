# C7 — 오프라인 처리량·지연·크기 진단

C7 전용 clone과 `review/20261030-x-c7-capacity-diagnostics`에서 재실행 가능한
진단 CLI를 구현했다. 운영 자동 실행·서비스 변경·로봇 접속은 없다.
보고서는 **읽기 전용 진단이며 주행 허가가 아니다**.

## 소스와 범위

| 역할 | 조사·실행 SHA |
|---|---|
| main | `5154761bba6fa4f171881e61f986901e2b415ed9` |
| C1 | `50600c7bce6f5fae743cd836ca1d8ee68d91b05a` |
| C2 | `7625c87ede2489143c44862d883e10fc1791df28` |
| C3 | `5bf58097f4a67806f5515b931a3b8013d65bf01e` |
| C4 | `7ac0d55b07abd20902d6d756c6b225733613fea7` |
| D1 | `203c144f6b4a90966839c34b603ae12ee676cb12` |
| D2 | `7313f0a31c00ae87ae216b84ca41a23804e91917` |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` |

일반 `git clone --no-hardlinks`로 원격 refs를 한 번 취득하고 고정했다.
원본 main 폴더의 `dashboard-polish.css`, `features/map_editor3d/editor.css`
사용자 변경은 보존했다. AGENTS.md의 명시적 사용자 브랜치 예외를 적용했다.
다른 역할의 코드·main·CI·controller·goal tolerance·최종 방향 정렬은 수정하지
않았다. 하위 채팅을 만들지 않았고 Dots의 native Nav2 5개 시험도 재실행하지 않았다.
C2는 요청 문서를 확인했으며 UI를 재구현하거나 튜닝하지 않았다.

요청된 C1/C2/C3/C4/D2/D3 최신 문서를 읽었다. C1 보고서가 고정한 이전 C3/C4의
0.2 거부는 역사적 결과다. **위 최신 SHA 조합에서는 C4 → C1 0.2 → C3 수용을
재현**했다. collision은 pose/joint/source 부족으로 unavailable이며 이는 올바른
표시 제한이다. 전체 주행 체인이나 drawable collision 성공으로 승격하지 않는다.

`prepare`는 Git export를 읽기 전용으로 만들고, `run`은 총 8,690개
실행·관련 소스 파일을 Git blob과 전후 대조한다. owner import origin도 기록한다.
진단 구현의 파일별 SHA256은 결과에 별도로 포함한다. 결과의 `diagnostic_head`는
측정 시점 HEAD이며 아직 commit 전인 작업본은 소스 해시로 식별한다. 최종 C7
HEAD와 원격 CI는 제출 receipt에 기록한다.

## 실제 한도

| 경계 | 값 | 확인 종류 |
|---|---:|---|
| C1 `messages.canonical`, wire | 131,072 B | 실제 ±1 B 경계 |
| C1 `SceneSnapshotService.ingest`, sample | 16,384 B | 실제 ±1 B 경계, 0.2 정규화 후 포함 |
| D2 compact + C4 reserve | compact 14,336 + 2,048 B | 실제 ±1 B 경계 |
| C1 latest slots | 81,920 B | 5×16,384 수용, 6번째 거부 |
| C1 응답 예산 | sample+health 합계 +16,384 ≤131,072 B | 소스 검사; 별도 reserve만의 포화는 NOT_RUN |
| C4 `_Pipeline` frame | 524,288 B, 기본 JSON 공백 포함 | 소스 검사; 실제 연결은 upstream wire/compact가 먼저 제한 |
| C1/C3 display asset | 각 2,097,152 B / 합계 8,388,608 B / 8개 | C1 경계, 실제 C3 cache 회귀 |
| C1 history | 기본 16, 설정 허용 1..128 | 40회 교체에서 최대 16 |
| C4 worker | 실행 1 + pending 1 | 60입력 burst 실측 |
| C3 | pending 1, packet 1, path history ≤3 | 기존 browser load·unit 재사용 |
| 지도 원본/출력 | 256 MiB, 출력 20M points, chunk 16,384 points | 설정·소스 검사; 최대치 stress는 NOT_RUN |

한도는 변경하지 않았다. C1 sample 검사에서는 원본 wire 크기와 0.2 정규화 후
크기를 모두 확인한다. wire 통과는 service ingest 수용을 뜻하지 않는다.

## “16개 수용” 차이의 정확한 원인

D2 기존 sparse generator와 C1 기존 cone generator를 동일 최신 모듈로 실행했다.
D2 대표 metadata의 processing clock ID/완료 시각도 원래 fixture와 맞췄다.
원본 PointCloud2 bytes SHA256, source/map/schema/clock 신원은 JSON 각 행에 있다.

| compact frame의 서로 겹치지 않는 항목 | sparse 16 | cone 16 | cone − sparse |
|---|---:|---:|---:|
| geometry 값 | 2,160 | 4,715 | +2,555 |
| per-object provenance 값 | 3,472 | 3,504 | +32 |
| input_sources 값 | 860 | 892 | +32 |
| health 값 | 311 | 286 | −25 |
| 기타 필드·키·JSON 구두점 | 5,344 | 5,366 | +22 |
| **합계** | **12,147** | **14,763** | **+2,616** |
| reserve 포함 | 14,195 | 16,811 | |
| 전달 | 수용 | **전체 frame 거부, 427 B 초과** | |

geometry 차이는 실제 좌표·extent의 JSON 표현 크기 차이가 대부분이다. 객체
개수 보장이나 모순으로 해석하지 않는다. cone 15는 13,967+2,048=16,015 B로
수용, 16은 거부다. metadata 값 4,096 B를 추가하면 key 포함 4,130 B가 늘어
cone 12도 거부된다. sparse 16 + 큰 metadata 역시 reserve 때문에 거부된다.

거부된 cone 16 compact 자체는 C1 fresh-service probe에서 수용되지만 **reserve를
포함한 실제 D2 전달은 거부**된다. 이 probe를 전송 우회로 사용하지 않는다.
full cone 16 (28,876 B)은 실제 wire 검증을 통과하고 service ingest에서 거부된다.
압축은 provenance만 바꾸며 모든 geometry를 보존한다. 초과 시 개별 객체를
버리지 않는다. full core 결과는 보관되며 독립 D3 호출에도 전체 geometry를
전달했다. **이것은 C1/C3 또는 운전 경로가 새 입력을 받았다는 뜻이 아니다.**

C1의 크기 예외는 `dropped` 증가 이전에 발생하므로 기존 카운터만으로 거부 수를
셈하면 부족하다. 진단은 exceptions/False/NOT_SENT를 분리한다. 3회 반복 거부 후
기존 sequence/receipt는 그대로이고 500 ms를 넘으면 0.2 slot은 expired/null이다.
지도 reset은 비우고 이전 지도 입력을 거부한다. host clock 불일치는 age null,
unavailable이며 성능 지연으로 계산하지 않는다. source timestamp·TTL을 갱신하거나
0.6초 정합 제한을 재도입하지 않았다.

## 시간·적체·브라우저

모든 Python duration은 같은 `perf_counter_ns`의 시작/종료이고 CPU는
`process_time_ns`다. C4 queue는 실제 host monotonic clock, Node와 browser는
각자의 performance clock이다. 합성 clock은 stale/identity 검사용이며 기존
fixture의 0 ns duration을 실제 처리시간으로 보고하지 않는다. source→host→browser
mapping 부재로 **sensor-to-render latency UNKNOWN**이다. controller 함수 실행,
실제 source 수신·DDS·네트워크 latency는 NOT_RUN이다.

현재 C4 별도 synchronous Runtime의 public port를 관측한 작은 입력 n=3에서
D2 perceive, D3 assess, canonical conversion을 각각 실측했다. 정확한
p50/p95/max·clock·event는 결과 JSON/자동 Markdown에 있다.
ASGI response 측정에는 test app/client setup과 auth 검사도 포함한다.
이는 순수 직렬화·TCP 응답시간이 아니다. 단계가 중첩되므로 서로 더하지 않는다.
`c4_converted_monotonic_ns`는 현재 소스상 converter 호출 전 기록된다. 진단은
실제 converter public call을 따로 감싸 측정한다.

60개 입력의 느린 소비자 시험은 실제 C4 worker/D2에 명시적 gate를 넣었다.
60 수용 = pending 교체 58 + 처리 2, 앞선 처리결과 1개는 superseded,
C1 latest 교체 1개(sequence 60)였다. queue 최대 1, 종료 후 queue 0/latest null.
gate wait와 실제 core 시간이 분리되어 있으며 생산 최대 Hz 시험이 아니다.

기존 C3 browser 시험 11개 PASS, 1,200 packets/30.002 s ≈39.997 Hz,
pending 최대 1, retained packet 1, 관측 history 1(설정 ≤3), max draw 약
5.90 ms, post-GC heap 3,115,620→3,330,300 B(+214,680 B). 브라우저 실행은
다른 C7 수치 작업과 순차 진행했다. 외부 채팅/프로세스 부하는 통제하지 못했다.
렌더 p50/p95는 원래 runner가 저장하지 않아 NOT_MEASURED다. 이전 날짜 VM과
개선율 비교, Jetson 처리량·실시간 안전성 주장은 없다.

C3 기존 cache는 같은 ref 100 polls에 fetch/decode 1회, stream 재연결 및 map
revision 변경 시 각 1회 추가, ref 삭제/dispose 시 entries 0이다. late in-flight
map 변경·오류 재시도 억제는 기존 asset unit을 재사용했다. 새 cache를 만들지
않았다. 8 MiB 총량은 wire-byte 한도이고 decoded heap 상한 보장은 아니다.

## 지도 I/O와 담당자 인계

D1 원본 generator를 400→20,000→200,000 points/source로 키웠다. source 2개,
최대 총 11,200,382 B이며 export는 400,000 points를 보존한다. 작은 D1 solve만
실행했고 큰 지도는 generator transforms를 명시적으로 공급한 **export-only**다.
preview 160점을 원본/solver/collision 입력 대신 사용하지 않았다.

| 담당 경로 | 최소 재현과 관측 | 최소 후속 후보 / 예상 효과 / 검증 상태 |
|---|---|---|
| C1 `expansion_services/catalogue.py` | 200k×2 source list 매번 11,200,382 B read; 160-point preview도 원본 5,600,191 B read | checksum fence를 보존하는 검증된 descriptor snapshot/invalidation 설계 검토. 목록 전송은 약 1.7 KB인데 매번 원본 read. 반복 read 감소 가능; 변경 후 효과 **NOT_MEASURED** |
| C1 `expansion_services/export.py` | full export 약 44.8 MB logical reads; bundle list도 원본·부속 checksum 매번 읽음 | materialization·최종 publication hash fence는 의도된 보존 장치. 무조건 제거 금지. 반복 list 정책만 분리 검토; 구현/속도 개선 주장은 없음 |
| C1 + D2 `scene.py`, `consumer_port.py` | 16 cone reserve 포함 16,811>16,384, 전체 거부 | full geometry 보존 bulk/provenance reference 계약이 필요하면 C1 소유로 정의. 정상 byte 제한으로 분류. C7은 schema/limit 변경 안 함 |
| C1 `scene.py` + C4 `c1_ports.py` | C1 크기 exception은 dropped 미증가; C1SceneSink는 ingest False를 반환받아도 전달하지 않음 | byte rejection·whole-frame outcome의 구조화된 카운터/결과 전달. 최소 재현은 JSON `fences.sink_false_probe`와 aggregate cases. 성능 개선 아닌 관측 가능성 후보 |
| C4 `expansion_runtime/composition.py` | converter completion 이름의 timestamp가 변환 호출 전 | 완료 시점을 실제 변환 후 별도 기록하는 후보. 원본 timestamp/TTL 유지. C7 외부 timer가 실제 conversion 측정, 제품 코드 수정 안 함 |
| C3 `obstacle_scene/c1_assets.js` | 반복 fetch/decode·정리 회귀 PASS | 새 cache 불필요. drawable collision에는 소유자 제공 pose/joints 계약이 필요; 표시용 축약을 안전 geometry로 대체 금지 |
| D1/D3 | source hash/모든 객체 보존, UNKNOWN 유지 | 수치 알고리즘·native 재실행·controller 변경 제안 없음 |

logical bytes는 실제 read/readline 호출을 투명하게 세었다. OS cache/물리 disk
traffic은 측정하지 않았다. Source list·preview는 read 시간에 비례하는 비용이
있지만 현재 짧은 결과를 운영 병목이나 I/O 장애로 단정하지 않는다. 의도된
무결성 검증과 개선 후보를 구분한다.

## 재현과 검증

[실행 절차](../../../experiments/expansion_20261030/c7_capacity/README.md),
[전체 JSON](../../../experiments/expansion_20261030/c7_capacity/results.json),
[자동 Markdown](../../../experiments/expansion_20261030/c7_capacity/results.md),
[첫 baseline](../../../experiments/expansion_20261030/c7_capacity/baseline.json),
[browser 결과](../../../experiments/expansion_20261030/c7_capacity/browser.json).
환경은 macOS arm64, Python 3.13, Node 22.17.1, Chromium 151.0.7922.34다.
패키지 실제 버전·load average·thread 설정·process CPU/RSS를 JSON에 기록했다.
최대 RSS는 프로세스 전체 high-water mark이며 per-stage·브라우저 peak가 아니다.

개발 중 C7 harness의 macOS `/var` symlink 경로를 resolve하고, D1용 request를
지원되는 명시 옵션/seed로 구성했으며, Node getMap 인자를 수정했다. validator를
대체하거나 상대 소스/테스트를 고치지 않았다. 초기 실패는 진단 harness 연결 오류로
수정했고 최종 실행에서는 정상·경계·queue·stale/map/clock을 모두 확인했다.

최종 회귀 수와 원격 CI receipt는 [VALIDATION.md](VALIDATION.md)에 정리한다.
C6는 파일을 독립적으로 읽을 수 있으며 C6 완료를 기다리지 않는다.
