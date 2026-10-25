# C4 — 한 번의 관측 창에서 필요한 원본·라벨

ROUND4의 `enclosed-chroma-v1`은 실제 GREEN/RED까지 UNKNOWN으로 만들어 **미채택·동결**했다.
다음 한 가지 작업은 아래 묶음을 확보하고 recording 단위로 분리해 독립 검토하는 것이다.
이 문서는 자료 인계 조건이며 장비 접속·촬영·노출 설정 변경 명령이 아니다.

**기존 camera owner의 한 관측 창:** 같은 목표 신호가 전면으로 보이는 RED→GREEN→RED 한
주기를 원래 간격으로 보존한다. 각 상태에서 최소 1초의 지속 구간과 전환 전후 원본이
필요하다. 목표가 바뀌거나 가려진 구간은 별도 표시한다. 옆 crossing, 뒤쪽/잘린 housing,
버스정류장 표지판, 가림·밝은 반사를 같은 창에서 포함하거나 같은 recording의 별도 구간으로
남긴다. 원래 녹화 속도를 유지하고 정지 사진 복제·간격 압축·가짜 epoch로 채우지 않는다.

**원본과 metadata:** 원래 JPEG/RGB와 SHA256, 해상도·채널 encoding, source/camera ID,
recording ID, 실제 producer epoch·sequence·source timestamp와 clock domain/검증 여부,
owner의 최초 receipt/source age를 보존한다. timestamp는 문자열 ns로 유지하고 다른 host의
monotonic 값을 빼지 않는다. exposure time/gain/white balance/auto/settling은 가능한 값만
저장하고 미제공은 `null`로 둔다. 별도 camera open이나 새 capture daemon은 필요하지 않다.
C1의 기존 owner→Frame/TrafficWorker 인계 경계에서 사적 파일로 보존한다.

**사람 검토:** 전체 영상으로 동일 대상·접근 방향을 확인한다. 모든 RED/GREEN 전환 전후
±0.5초, 모든 detector GREEN 반환, 모든 가림/표지판/뒷면 구간을 확인한다. 나머지는 원래
시간 기준 0.2초 간격으로 확인해 미검출도 라벨링한다. 흐림·작은 발광부·포화 때문에 상태를
읽을 수 없으면 UNREADABLE이며, 주변/반대 면의 색을 대신 붙이지 않는다. 자동 검출 박스는
참고용으로만 보고 사람이 bbox·전면 여부를 별도로 검토한다.

라벨 행 형식(미확인 값은 null, 선택 항목은 한 값만 기록):

```json
{"image_sha256":"원본 해시","recording_id":"원본 세션","source_id":"카메라", "sequence":null,"source_stamp_ns":null,"target_id":"사람이 연결한 대상", "bbox_native_xyxy":null,"face":"FRONT/BACK/CLIPPED/NON_SIGNAL/UNCERTAIN", "state":"RED/GREEN/UNREADABLE/NON_SIGNAL","emitter_bbox_native":null, "reviewer":"검토자","split_group":"recording_id"}
```

**분리 기준:** 연속 프레임·한 이미지의 여러 target·동시 paired camera는 같은 recording
그룹으로 묶는다. 기존 25/27 및 255장과 다른 recording을 평가용으로 고정하고, 평가 라벨을
타일·threshold 설정에 사용하지 않는다. 가능한 경우 두 번째 검토자가 전면/색을 확인한다.
원본·가중치는 공개 Git에 올리지 않는다. 이 자료로 전면/비신호 구분의 학습 모델 필요성과
노출 영향을 먼저 판단한다. 기존 가중치가 잘못됐거나 노출 조정만으로 해결된다고 가정하지 않는다.
