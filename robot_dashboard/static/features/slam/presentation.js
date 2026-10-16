import { mountSlamDashboard } from './dashboard.js';

// Presentation only: reuse the controller's nodes, listeners and disabled states.
// Navigation never starts/stops a session or changes camera ownership.
export function mountSlamPresentation(doc = document) {
  mountSlamDashboard(doc);
  const panel = doc.getElementById('slamConsole');
  const library = doc.getElementById('slamPackageLibrary');
  if (!panel || !library || panel.dataset.presentation) return;
  panel.dataset.presentation = library.dataset.presentation = 'workspace';
  const win = doc.defaultView;
  const get = id => doc.getElementById(id);
  const mappingNav = doc.querySelector('[data-nav="mapping"]');
  if (mappingNav) {
    mappingNav.title = '지도 만들기 · LiDAR / VSLAM';
    mappingNav.setAttribute('aria-label', mappingNav.title);
    const caption = mappingNav.querySelector('small');
    if (caption) caption.textContent = 'LiDAR / VSLAM';
  }
  const make = (tag, className, ...children) => {
    const node = doc.createElement(tag);
    node.className = className;
    node.append(...children);
    return node;
  };
  const heading = (eyebrow, title, level = 'h3') => make('div', 'slam-section-heading',
    make('div', 'eyebrow', eyebrow), make(level, '', title));
  const details = (label, ...children) => make('details', 'slam-technical',
    make('summary', '', label), ...children);

  const engine = get('slamEngine');
  const views = panel.querySelector('.slam-views');
  const state = get('slamSessionState');
  const header = panel.querySelector('.slam-heading');
  header.classList.add('panel-header', 'compact');
  header.querySelector('.eyebrow').textContent = 'MAPPING WORKSPACE';
  header.querySelector('h2').textContent = '지도 만들기';
  const engineField = engine.closest('label');
  engineField.firstElementChild.textContent = '매핑 방식';
  header.append(make('div', 'slam-workspace-menu', engineField, get('slamRefresh'), state));

  // Group existing controls like the LiDAR session form. Do not clone actions.
  const oldRows = [...panel.querySelectorAll(':scope > .slam-control-row')];
  const form = make('section', 'slam-session-form', heading('SESSION', '관측 설정'),
    make('div', 'slam-form-fields', get('slamTask').closest('label'), get('slamMapName').closest('label')),
    get('slamOperatorConfirmed').closest('label'), get('slamCreate2d').closest('label'),
    make('div', 'slam-session-actions', get('slamStart'), get('slamSave'), get('slamStop')));
  form.setAttribute('aria-label', 'SLAM 세션 설정');
  const diagnostics = make('section', 'slam-session-diagnostics', heading('READINESS', '실행 조건'),
    get('slamCapability'), get('slamSourceIdentity'),
    details('지도 재사용·위치찾기 결과', get('slamLocalizationStatus')));
  const sessionLayout = make('div', 'slam-session-layout', form, diagnostics);
  header.after(get('slamMessage'), sessionLayout);
  oldRows.forEach(row => row.remove());
  const lidarDetails = details('엔진 상태·관측 세션 관리');
  lidarDetails.classList.add('slam-lidar-session');
  panel.append(lidarDetails);

  const viewLabels = [['STEREO INPUT', '입력 영상 · 카메라 자세'], ['GLOBAL MAP', '전역 특징점 지도 · 궤적']];
  [...views.children].forEach((view, index) => {
    const title = view.querySelector('h3');
    title.replaceWith(make('div', 'panel-header compact', heading(...viewLabels[index])));
    const body = make('div', 'slam-view-body', ...[...view.children].slice(1));
    view.append(body);
  });
  const footer = make('div', 'slam-stream-notes', get('slamProvenance'), get('slamHeartbeat'));
  views.after(footer);

  const filter = get('slamPackageFilter');
  filter.querySelector('option[value="all"]').remove();
  filter.value = 'lidar';
  const libraryHeader = library.querySelector('.slam-heading');
  libraryHeader.classList.add('panel-header', 'compact');
  libraryHeader.querySelector('h2').replaceWith(heading('MAP LIBRARY', '저장 지도', 'h2'));
  libraryHeader.append(make('label', 'slam-field slam-library-menu', make('span', '', '지도 종류'), filter));
  const description = library.querySelector(':scope > .slam-muted');
  description.textContent = '지도 종류를 선택해 저장 결과를 확인하고 관리하세요.';
  const sessionLink = library.querySelector('a[href="#mapping"]');
  const nativeDetail = get('slamNativeDetail');
  const rows = get('slamPackageRows');
  const importRow = get('slamPackageImport').closest('.slam-control-row');
  const empty = make('div', 'slam-archive-empty', heading('SAVED VSLAM', '저장 지도를 선택하세요'),
    make('p', '', '목록에서 지도를 선택하면 특징점·궤적 미리보기와 저장 정보를 확인할 수 있습니다.'));
  empty.id = 'slamArchiveEmpty';
  const listEmpty = make('p', 'slam-list-empty', '저장된 VSLAM 지도가 없습니다. 새 지도를 만들거나 ZIP 파일을 가져오세요.');
  const listHeader = make('div', 'panel-header compact', heading('MAP LIBRARY', '저장 지도 목록'));
  const sidebar = make('aside', 'slam-archive-sidebar', listHeader, rows, listEmpty,
    make('div', 'slam-library-tools', importRow, sessionLink));
  const preview = make('section', 'slam-archive-preview',
    make('div', 'panel-header compact', heading('PREVIEW', '저장 지도 보기')),
    empty, nativeDetail);
  const archive = make('div', 'slam-archive-layout', preview, sidebar);
  library.append(archive);
  const localization = details('지도 재사용·위치찾기 결과', get('slamPackageLocalizationStatus'));
  nativeDetail.classList.add('slam-archive-detail');
  const management = nativeDetail.querySelector('.slam-control-row');
  management.classList.add('slam-package-management');
  const selectedManagement = make('section', 'slam-selected-management',
    heading('SELECTED MAP', '선택 지도 관리'), management,
    details('저장 상세 · revision·보정·출처', get('slamPackageDetail')));
  sidebar.querySelector('.slam-library-tools').before(selectedManagement);
  const reuse = nativeDetail.querySelector('details');
  reuse.id = 'slamArchiveReuse';
  reuse.classList.add('slam-technical');
  const support = make('section', 'slam-archive-support', nativeDetail.querySelector('.slam-muted'), reuse, localization);
  sidebar.append(support);
  get('slamPackageImport').setAttribute('aria-label', 'VSLAM 지도 ZIP 가져오기');

  // Both engines share one header and one bounded preview/inspector row.
  // Move the existing nodes so the original LiDAR listeners stay attached.
  const lidarLayout = doc.querySelector('[data-page="maps"] .saved-layout');
  const lidarSidebar = lidarLayout.querySelector('.saved-library-panel');
  const lidarPreviewHeader = lidarLayout.querySelector('.saved-map-panel > .panel-header');
  lidarPreviewHeader.querySelector('.eyebrow').textContent = 'PREVIEW';
  const health = lidarPreviewHeader.querySelector('.panel-header-status');
  health.classList.add('slam-archive-health');
  lidarSidebar.querySelector('.panel-header').after(health);
  const metadata = lidarSidebar.querySelector('.saved-map-detail dl');
  const metadataDetails = details('저장 상세 · revision·출처', metadata);
  lidarSidebar.querySelector('.saved-map-detail').append(metadataDetails);
  archive.before(lidarLayout);
  for (const [inspector, label] of [[lidarSidebar, 'LiDAR 저장 지도 관리'], [sidebar, 'VSLAM 저장 지도 관리']]) {
    inspector.setAttribute('role', 'region');
    inspector.setAttribute('aria-label', label);
    inspector.tabIndex = 0;
  }

  function syncMapping() {
    // The controller chooses this using the active server session first. A
    // second browser may still have LiDAR selected while VSLAM is running.
    const visual = !views.hidden;
    const active = !['IDLE', 'UNKNOWN'].includes(state.textContent.trim());
    panel.closest('[data-page]').dataset.slamView = visual ? 'vslam' : 'lidar';
    if (visual) {
      if (sessionLayout.parentElement !== panel) get('slamMessage').after(sessionLayout);
    } else if (sessionLayout.parentElement !== lidarDetails) {
      lidarDetails.append(sessionLayout);
    }
    lidarDetails.hidden = visual;
    // Keep the active session's stop/save controls reachable on reconnection.
    if (!visual && active) lidarDetails.open = true;
    get('slamCreate2d').closest('label').hidden = visual;
    footer.hidden = !visual;
  }

  function syncLibrary() {
    archive.hidden = rows.hidden;
    empty.hidden = !nativeDetail.hidden;
    selectedManagement.hidden = nativeDetail.hidden;
    support.hidden = nativeDetail.hidden;
    listEmpty.hidden = rows.childElementCount !== 0;
    for (const row of rows.children) {
      if (row.dataset.presentation) continue;
      // Keep package names as text, including separators or HTML-looking names.
      const match = row.textContent.match(/^(.*) · (visual_stereo|visual_inertial) · (\d+) native files$/s);
      if (!match) continue;
      row.dataset.presentation = 'package';
      row.replaceChildren(make('strong', '', match[1]),
        make('small', '', `${match[2] === 'visual_stereo' ? 'Stereo VSLAM' : 'VIO'} · 보관 파일 ${match[3]}개`));
    }
  }
  engine.addEventListener('change', syncMapping);
  filter.addEventListener('change', syncLibrary);
  const observer = new win.MutationObserver(() => { syncMapping(); syncLibrary(); });
  observer.observe(views, { attributes: true, attributeFilter: ['hidden'] });
  observer.observe(state, { childList: true, characterData: true, subtree: true });
  observer.observe(rows, { attributes: true, attributeFilter: ['hidden'], childList: true });
  observer.observe(nativeDetail, { attributes: true, attributeFilter: ['hidden'] });
  win.addEventListener('pagehide', event => { if (!event.persisted) observer.disconnect(); });
  filter.dispatchEvent(new win.Event('change'));
  syncMapping();
  syncLibrary();
}

if (typeof document !== 'undefined') mountSlamPresentation(document);
