# 적용 치수 및 추정 항목 보고서

이 모델은 첨부 래스터 도면의 시각화 재구성입니다. 실측 또는 원본 CAD로 검증된 설계/주행 지도가 아닙니다.

## 도면에 직접 명시되거나 계산으로 유도한 치수

| 항목 | 적용값 (m) | 구분 | 근거 | 주의사항 |
|---|---:|---|---|---|
| 전체 가로 | 8.0 | explicit | S01/S03/S04: 8000 mm | Drawing nominal dimension; physical venue not surveyed. |
| 전체 세로 | 6.018 | explicit | S01/S03/S04: 6018 mm | Drawing nominal dimension; physical venue not surveyed. |
| 좌측 직선 구간 길이 | 5.018 | explicit | S01/S03/S04: 5018 mm | Location within global bounds is raster-derived. |
| 벽 높이 | 0.6 | explicit | S01/S04: vertical 600 mm callout | Wall thickness is not specified. |
| 우측 복도 폭 | 1.0 | explicit | S01/S03/S04: 1000 mm across right corridor | 1.0 m clear distance is preserved using zero-thickness wall surfaces; physical wall thickness is unspecified. |
| 경사로 한쪽 수평 길이 | 1.1 | explicit | S02: 1100 mm, supported by S03 3200 mm total | Interpreted as horizontal plan run, not surface length. |
| 교차부 높이 | 0.18 | explicit | S02: 180 mm | Nominal top surface above course datum. |
| 계단 단높이 | 0.06 | explicit | S02: levels 60/120/180 mm | Three risers; two exposed treads plus the top platform. |
| 계단 디딤판 깊이 | 0.25 | explicit | S02: two 250 mm dimensions | Two exposed treads on each side. |
| 경사로 방향 전체 장애물 길이 | 3.2 | explicit | S01/S03/S04: 3200 mm | Includes two ramps and central 1 m platform. |
| 계단 방향 전체 장애물 길이 | 2.0 | explicit | S01/S03/S04: 2000 mm | Includes four 0.25 m treads and central 1 m platform. |
| 중앙 평탄부 한 변 | 1.0 | derived | 3.2 - 2×1.1 = 1.0; also 2.0 - 4×0.25 = 1.0 | Square platform interpretation follows S02/S03. |

## 추정·해석 항목

### A01 · 도면 축척 및 평면 꼭짓점
- 적용값: x=(pixel_x-118)×8/739; y=(657-pixel_y)×6.018/555; 주요 꼭짓점 반올림
- 구분: estimated
- 근거: S03 raster trace, dimensions anchor the bounding box
- 확인 필요: 원본 CAD 또는 현장 실측으로 각 분기/회전 코너 위치 확인. 래스터 판독 오차 미검증, 실측 필요.

### A02 · 중앙 교차부 위치/방향
- 적용값: (3.303, 3.009, 0) m; 대각선 ±45°
- 구분: estimated
- 근거: S03 central diamond and corridor slopes
- 확인 필요: 교차부 정확한 X/Y 위치 및 각도 확인.

### A03 · 일반 복도 및 장애물 폭
- 적용값: 1.0 m nominal
- 구분: derived
- 근거: S03 explicit right corridor 1000; S02/S03 3200/2000/1100/250 derive 1 m platform
- 확인 필요: 우측 외 다른 구간의 정확한 폭은 직접 명시되지 않음. 대부분 래스터를 따르므로 일부 회전부 폭은 다름.

### A04 · 벽 두께와 기준선
- 적용값: 물리 두께 미정; 기본 모델은 양면 surface, 두께 0 m
- 구분: estimated
- 근거: S01/S04 depict walls but no thickness dimension
- 확인 필요: 명시된 1 m 복도 폭과 8×6.018 m 전체 경계를 모두 보존하기 위해 두께를 임의로 넣지 않음. 실제 벽 두께/치수 기준 확인 후 충돌용 솔리드 제작 필요. 바깥쪽 0.04 m 두께를 가정하면 전체 벽 외곽은 약 8.08×6.098 m가 되어 현재 미적용.

### A05 · 바닥판 두께
- 적용값: 0.06 m; top z=0, underside z=-0.06
- 구분: estimated
- 근거: Rendering/mesh thickness only, not specified in drawings
- 확인 필요: 실제 바닥 구조 두께 확인. 주행 기준 높이는 z=0 유지.

### A06 · IN/OUT 구역 크기
- 적용값: 2.0×1.0 m nominal
- 구분: estimated
- 근거: S03 raster trace: x=6..8; y=0..1 / 5.018..6.018
- 확인 필요: 영역의 정확한 크기와 물리적 출입 개구 위치 확인. S01/S04를 따라 외곽벽은 닫힌 형태로 유지.

### A07 · 주차 구역
- 적용값: 1.0×1.0 m; x=7..8, y=2.5..3.5
- 구분: estimated
- 근거: S03 raster trace, red P outline
- 확인 필요: 주차면 실측 크기와 위치 확인.

### A08 · 경사로 1100 해석
- 적용값: 수평 run=1.1 m, rise=0.18 m; surface=1.11463 m; grade=16.364%, angle=9.293°
- 구분: derived
- 근거: S02 with S03 3200 total
- 확인 필요: 1100이 수평 투영인지 실제 경사면 길이인지 원본 CAD로 확인.

### A09 · 신호등
- 적용값: symbol centers=(2.295,3.009)/(4.341,3.009) m; total height 0.84 m; base 0.32×0.32 m
- 구분: estimated
- 근거: S03 blue markers indicate position only; physical fixture shape not specified
- 확인 필요: 실제 신호등 위치/치수/정지선 연동 및 방향 확인. 렌더링용 신호 상태는 시뮬레이션 동작이 아님.

### A10 · 정지선
- 적용값: width=0.045 m; on SW/SE platform edges; black
- 구분: estimated
- 근거: S03 black segments adjacent to signal labels
- 확인 필요: 정지선 폭/정확한 위치/색상 및 신호별 주행 방향 확인.

### A11 · 슬라럼 영역
- 적용값: x=0.10..0.90, y=2.50..3.50 m; no cones created
- 구분: estimated
- 근거: S03 라바콘 슬라럼 label, no cone center dimensions
- 확인 필요: 콘 개수/간격/좌표는 미지정. 기본 모델에 콘을 임의 배치하지 않음.

### A12 · 재질/표시
- 적용값: neutral gray walls/floor; teal ramp; blue IN/OUT and slalom tint; red parking outline
- 구분: estimated
- 근거: S01/S04 gray CAD; S03 semantic text/marking colors
- 확인 필요: 재질과 보조 색상은 시각화용이며 실제 현장 색상/마찰계수가 아님.

### A13 · 전체 바운딩박스와 좌측 세로 배치
- 적용값: left corridor y=0.500..5.518 m
- 구분: derived
- 근거: (6.018-5.018)/2 = 0.500; S03 roughly symmetric
- 확인 필요: 좌측 구간 상하 오프셋 대칭 여부 확인.

### A14 · IN/OUT/P 및 보조 글자
- 적용값: flat mesh labels z≈0.005 m; font sizes 0.10..0.25 m
- 구분: estimated
- 근거: S03 text semantics
- 확인 필요: 문구는 도면 의미를 보존하되 글꼴/배치는 가독성을 위해 조정.
