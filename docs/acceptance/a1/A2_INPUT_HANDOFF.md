# A2에 전달하는 정지 관측 사본

비공개 공유 폴더의 `A2_FIELD_SNAPSHOT_v1.json`은 2026-11-05 11:15 KST에 고정판 `dce1e889`가 읽은 실제 센서 메타데이터와 local pose의 리뷰용 사본이다. SHA256은 `5e7f51613de28be88ee2de946988ad20c96ee5053d821f6bc725b333a38faf19`이다. 두 샘플의 original stamp는 decimal ns 문자열로 보존했다. 아래 표만으로도 표시 가능한 값과 수집하지 않은 값을 구분할 수 있다.

| 항목 | 값과 소비 범위 |
|---|---|
| 입력 | FAST-LIO /cloud_registered, frame camera_init, point_count 353→347, /Odometry camera_init→body. 로컬 추정 자세. |
| 시간·신원 | source clock ROS_HEADER_UNVERIFIED, receipt clock OBSERVER_HOST_MONOTONIC. 원본 float receipt 초·publisher epoch/sequence는 비공개 사본에 보존. integer receipt ns·검증된 clock mapping=null. 동일 source에 한해서 stamp 변화 관측. |
| graph | 각 topic endpoint 1, QoS 관측. LOCAL_SUBSCRIPTION_AND_ROS_GRAPH_ONLY, per_message_publisher_verified=false. graph freshness 한도 3초. asset/관측 TTL=null. 저장한 자료는 HISTORICAL_ONLY. |
| 지도와 교정 | selected map/revision/generation=null. 운영 교정 파일 hash는 [FIELD_SESSION](FIELD_SESSION.md)에 있다. 이 샘플의 sensor-to-map calibration/지면 증거는 null. map1 좌표로 표시 불가. |
| 제공 범위 | local pose와 점 수·메타데이터만 제공. 동일 시각 joints·실제 장애물·YOLO·path·coverage·원본 점 payload=null. wire codec robot-scope-pointcloud-v1/float32le, 전달 사본은 UTF-8 JSON. |

C1 0.2 포트에서 요구하는 frame·map generation·clock mapping을 채울 수 있을 때까지 제품 owner 주입·LIVE 표시를 보류한다. 위 사본은 결손·만료·map 미선택 UI 검사용이며 C1 ingest DTO를 새로 정의하지 않는다. 기존 합성 포트의 독립 검증과 A2 작업은 진행할 수 있다.
