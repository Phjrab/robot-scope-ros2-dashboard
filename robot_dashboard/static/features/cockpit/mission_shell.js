export const MISSION_PAGE_META = Object.freeze({
  overview: ['Overview', '로봇과 ROS 2 시스템의 전체 상태를 빠르게 확인합니다.'],
  cockpit: ['Mission Control', '센서·지도·카메라를 관측하고 서버의 준비 상태를 확인합니다.'],
  mapping: ['Live LiDAR Mapping', '실시간 점군, 로봇 자세와 매핑 파이프라인을 확인합니다.'],
  maps: ['Saved Maps', '이미 매핑된 3D PCD와 2D 점유 지도를 센서 없이 탐색합니다.'],
  sensors: ['Capture / Perception', '카메라·서버 캡처 세션·shadow perception 상태를 확인합니다.'],
  topics: ['ROS Graph', '발견된 ROS 2 토픽, 타입, 수신률과 지연을 조회합니다.'],
  controls: ['Robot Controls', 'ARM 버튼으로 제어 권한을 얻은 뒤 키보드·게임패드 주행과 허용된 Go2 동작을 실행합니다.'],
  navigation: ['Nav2 Navigation', '저장된 2D 지도에서 초기 위치와 목표를 지정하고 Go2 자율주행을 관리합니다.'],
  missions: ['Missions', '등록한 지도 지점을 순서대로 방문하는 미션을 생성하고 진행 상태를 확인합니다.'],
  'route-planner': ['Route Planner', '주문을 구성하고 서버가 계산한 추천 경로와 수동 안내를 독립 화면에서 확인합니다.'],
  settings: ['Settings', '로봇 유형을 고르고 네트워크에서 연결 대상을 찾은 뒤 ROS 2 데이터 소스를 선택합니다.'],
});

export function missionPageFromHash(windowMode, hash) {
  const requested = String(hash).replace(/^#\/?/, '').trim();
  return !windowMode.dedicated && !Object.hasOwn(MISSION_PAGE_META, requested) ? 'cockpit' : windowMode.pageFromHash(MISSION_PAGE_META);
}

export function syncMissionShell(page, documentValue = document) {
  documentValue.documentElement.dataset.activePage = page;
  const advanced = documentValue.querySelector('.advanced-tools');
  const narrow = globalThis.matchMedia?.('(max-width: 800px)').matches;
  if (advanced && narrow) advanced.open = false;
  else if (advanced && ['overview', 'topics', 'controls', 'missions', 'route-planner', 'settings'].includes(page)) advanced.open = true;
}

export function filterSavedMapEntries(entries, query) {
  const search = String(query || '').trim().toLocaleLowerCase();
  return search ? entries.filter((entry) => [entry.name, entry.file_name, entry.frame_id].some((value) => String(value || '').toLocaleLowerCase().includes(search))) : entries;
}

export function frameProvenance(metadata) {
  return metadata?.data_provenance === 'SYNTHETIC_FIXTURE' ? 'FIXTURE' : metadata?.data_provenance === 'REPLAY' ? 'REPLAY' : 'LIVE';
}

export function setSoftwareStopFeedback(state, message, documentValue = document) {
  const feedback = documentValue.querySelector('#softwareStopFeedback');
  if (feedback) { feedback.textContent = message; feedback.dataset.state = state; }
}
