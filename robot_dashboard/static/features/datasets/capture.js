import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';

export const DATASET_CAPTURE_ACTIVE_STATES = Object.freeze(new Set([
  'starting', 'capturing', 'running', 'stopping', 'finalizing',
]));
export const DATASET_CAPTURE_STOPPABLE_STATES = Object.freeze(new Set([
  'starting', 'capturing', 'running',
]));
export const DATASET_CAMERA_SOURCE_IDS = Object.freeze(['go2_front', 'realsense_color']);
export const DATASET_PAGE_LIMIT = 24;

function datasetObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function datasetNumericTotal(value) {
  if (value == null) return 0;
  if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value : 0;
  if (typeof value !== 'object' || Array.isArray(value)) return 0;
  return Object.values(value).reduce((total, entry) => total + datasetNumericTotal(entry), 0);
}

function datasetOptionalBytes(value) {
  if (value == null) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function datasetPositiveInteger(value) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : null;
}

export function normalizeDatasetSources(value) {
  const entries = value === 'both'
    ? DATASET_CAMERA_SOURCE_IDS
    : Array.isArray(value) ? value : value ? [value] : [];
  const normalized = [];
  for (const entry of entries) {
    const candidate = datasetObject(entry);
    const id = String(candidate.source_id || candidate.id || entry || '').trim();
    if (DATASET_CAMERA_SOURCE_IDS.includes(id) && !normalized.includes(id)) normalized.push(id);
  }
  return normalized;
}

export function normalizeDatasetCapture(payload) {
  const envelope = datasetObject(payload);
  const capture = datasetObject(envelope.capture || envelope.status || envelope);
  const session = datasetObject(capture.session);
  const storage = datasetObject(capture.storage || envelope.storage);
  const freeBytes = capture.free_bytes ?? storage.free_bytes ?? storage.available_bytes;
  const sessionQuotaBytes = capture.session_quota_bytes
    ?? storage.session_quota_bytes
    ?? envelope.session_quota_bytes;
  const minimumFreeBytes = capture.minimum_free_bytes
    ?? storage.minimum_free_bytes
    ?? envelope.minimum_free_bytes;
  const state = String(capture.state || session.state || (capture.active ? 'capturing' : 'idle')).trim().toLowerCase() || 'idle';
  const sessionId = String(capture.session_id || session.session_id || capture.id || session.id || '').trim();
  const sources = normalizeDatasetSources(capture.sources || capture.source || session.sources || session.source);
  const startedAt = String(capture.started_at || session.started_at || '');
  const explicitElapsed = Number(capture.elapsed_s ?? session.elapsed_s);
  return {
    available: envelope.available !== false && capture.available !== false,
    state,
    active: capture.active != null ? Boolean(capture.active) : DATASET_CAPTURE_ACTIVE_STATES.has(state),
    sessionId,
    sources,
    captureHz: Number(capture.capture_hz ?? session.capture_hz) || 0,
    label: String(capture.label || session.label || ''),
    startedAt,
    elapsedS: Number.isFinite(explicitElapsed) && explicitElapsed >= 0 ? explicitElapsed : null,
    saved: datasetNumericTotal(capture.saved ?? capture.saved_samples ?? capture.sample_count ?? session.saved ?? session.sample_count),
    dropped: datasetNumericTotal(capture.dropped ?? capture.dropped_samples ?? capture.drop_counts ?? session.dropped),
    bytes: datasetNumericTotal(capture.bytes_written ?? capture.written_bytes ?? capture.bytes ?? session.bytes_written ?? session.bytes),
    freeBytes: freeBytes == null ? null : datasetNumericTotal(freeBytes),
    sessionQuotaBytes: datasetOptionalBytes(sessionQuotaBytes),
    minimumFreeBytes: datasetOptionalBytes(minimumFreeBytes),
    path: String(capture.output_path || capture.path || session.output_path || session.path || storage.root || envelope.output_path || ''),
    message: String(capture.message || session.message || ''),
    error: String(capture.last_error || capture.error || session.last_error || session.error || ''),
  };
}

export function normalizeDatasetSession(entry) {
  const value = datasetObject(entry);
  const id = String(value.id || value.session_id || '').trim();
  return {
    ...value,
    id,
    label: String(value.label || value.name || id || 'Dataset session'),
    state: String(value.state || 'complete').toLowerCase(),
    sources: normalizeDatasetSources(value.sources || value.source),
    sampleCount: datasetNumericTotal(value.sample_count ?? value.saved ?? value.samples_saved),
    bytes: datasetNumericTotal(value.bytes ?? value.bytes_written),
    path: String(value.output_path || value.path || ''),
    startedAt: String(value.started_at || value.created_at || ''),
    completedAt: String(value.completed_at || value.updated_at || ''),
  };
}

export function normalizeDatasetCatalog(payload) {
  const envelope = datasetObject(payload);
  const values = Array.isArray(payload)
    ? payload
    : Array.isArray(envelope.sessions) ? envelope.sessions
      : Array.isArray(envelope.datasets) ? envelope.datasets
        : Array.isArray(envelope.items) ? envelope.items : [];
  return values.map(normalizeDatasetSession).filter((entry) => entry.id);
}

export function normalizeDatasetDetail(payload, fallback = {}) {
  const envelope = datasetObject(payload);
  const raw = datasetObject(envelope.dataset || envelope.session || envelope);
  const session = normalizeDatasetSession({ ...fallback, ...raw });
  const values = Array.isArray(raw.samples)
    ? raw.samples
    : Array.isArray(envelope.samples) ? envelope.samples : [];
  const samples = values.map((entry, position) => {
    const value = datasetObject(entry);
    const index = Number(value.index ?? value.sample_index ?? value.sequence ?? position);
    return {
      index: Number.isSafeInteger(index) && index >= 0 ? index : position,
      sources: normalizeDatasetSources(value.sources || value.source_ids || value.source || session.sources),
      capturedAt: String(value.captured_at || value.committed_at || value.timestamp || ''),
    };
  });
  const rawPage = datasetObject(raw.page || envelope.page);
  const requestedBefore = datasetPositiveInteger(rawPage.before);
  const oldestIndex = datasetPositiveInteger(rawPage.oldest_index);
  const newestIndex = datasetPositiveInteger(rawPage.newest_index);
  const nextBefore = datasetPositiveInteger(rawPage.next_before);
  const rawLimit = datasetPositiveInteger(rawPage.limit);
  return {
    ...session,
    samples: samples.slice(0, DATASET_PAGE_LIMIT),
    page: {
      limit: Math.min(DATASET_PAGE_LIMIT, rawLimit || DATASET_PAGE_LIMIT),
      before: requestedBefore,
      oldestIndex,
      newestIndex,
      nextBefore,
      hasOlder: Boolean(rawPage.has_older && nextBefore),
    },
  };
}

export function datasetCaptureCanStop(snapshot) {
  const value = datasetObject(snapshot);
  return Boolean(
    value.sessionId
    && (value.active || DATASET_CAPTURE_STOPPABLE_STATES.has(String(value.state || ''))),
  );
}

export function formatDatasetBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let amount = bytes;
  let unit = 'B';
  for (const candidate of units) {
    amount /= 1024;
    unit = candidate;
    if (amount < 1024) break;
  }
  return `${amount.toFixed(amount >= 100 ? 0 : amount >= 10 ? 1 : 2)} ${unit}`;
}

export function datasetImageUrl(sessionId, sampleIndex, sourceId) {
  return `/api/v1/datasets/${encodeURIComponent(sessionId)}/samples/${encodeURIComponent(sampleIndex)}/${encodeURIComponent(sourceId)}.jpg`;
}

export function datasetDetailUrl(sessionId, before = null) {
  const base = `/api/v1/datasets/${encodeURIComponent(sessionId)}`;
  const cursor = datasetPositiveInteger(before);
  return cursor
    ? `${base}?before=${encodeURIComponent(cursor)}&limit=${DATASET_PAGE_LIMIT}`
    : `${base}?limit=${DATASET_PAGE_LIMIT}`;
}

export function datasetExportUrl(exportId) {
  return `/api/v1/datasets/exports/${encodeURIComponent(exportId)}`;
}

export function normalizeModelRegistry(payload) {
  const envelope = datasetObject(payload);
  const active = datasetObject(envelope.active);
  const previous = datasetObject(envelope.previous);
  const allowedStates = new Set(['staged', 'validated', 'active', 'previous', 'rejected']);
  const models = (Array.isArray(envelope.models) ? envelope.models : []).slice(0, 256).map((entry) => {
    const value = datasetObject(entry);
    const modelId = String(value.model_id || '').trim();
    const task = ['lane', 'object', 'depth_summary'].includes(value.task) ? value.task : 'unknown';
    const state = allowedStates.has(value.state) ? value.state : 'rejected';
    return {
      modelId,
      task,
      state,
      packageSha256: String(value.package_sha256 || ''),
      engineSha256: String(datasetObject(value.engine).sha256 || ''),
      reason: String(value.reason || ''),
      isActive: active[task] === modelId,
      isPrevious: previous[task] === modelId,
    };
  }).filter((entry) => /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(entry.modelId));
  return {
    models,
    mode: envelope.activation_surface === 'LOCAL_OPERATOR_ONLY' ? 'LOCAL OPERATOR ONLY' : 'UNAVAILABLE',
  };
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[character]));
}

function datasetSourceLabel(sources) {
  if (sources.includes('go2_front') && sources.includes('realsense_color')) return 'GO2 + REALSENSE';
  if (sources.includes('go2_front')) return 'GO2';
  if (sources.includes('realsense_color')) return 'REALSENSE';
  return '—';
}

function formatDatasetDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remaining = total % 60;
  return hours
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`;
}

function formatDatasetDate(value) {
  const date = new Date(value || '');
  if (!Number.isFinite(date.getTime())) return '시간 정보 없음';
  return date.toLocaleString('ko-KR', { hour12: false });
}

function datasetUi() {
  return {
    globalStatus: $('#datasetGlobalStatus'), globalStatusText: $('#datasetGlobalStatusText'),
    captureState: $('#datasetCaptureState'), sourcePicker: $('#datasetSourcePicker'),
    captureHz: $('#datasetCaptureHz'), sessionLabel: $('#datasetSessionLabel'),
    captureStart: $('#datasetCaptureStart'), captureStop: $('#datasetCaptureStop'),
    captureElapsed: $('#datasetCaptureElapsed'), captureSaved: $('#datasetCaptureSaved'),
    captureDropped: $('#datasetCaptureDropped'), captureBytes: $('#datasetCaptureBytes'),
    captureFree: $('#datasetCaptureFree'), captureQuota: $('#datasetCaptureQuota'),
    captureReserve: $('#datasetCaptureReserve'), captureSources: $('#datasetCaptureSources'),
    capturePath: $('#datasetCapturePath'), captureMessage: $('#datasetCaptureMessage'),
    openFolder: $('#datasetOpenFolder'), sessionCount: $('#datasetSessionCount'),
    refreshFolders: $('#datasetRefreshFolders'), sessionList: $('#datasetSessionList'),
    libraryPanel: $('#datasetLibraryPanel'), selectedTitle: $('#datasetSelectedTitle'),
    selectedPath: $('#datasetSelectedPath'), selectedSamples: $('#datasetSelectedSamples'),
    selectedMeta: $('#datasetSelectedMeta'), pageNewest: $('#datasetPageNewest'),
    pageNewer: $('#datasetPageNewer'), pageOlder: $('#datasetPageOlder'),
    pageStatus: $('#datasetPageStatus'), sampleGallery: $('#datasetSampleGallery'),
    exportSession: $('#datasetExportSession'), exportStatus: $('#datasetExportStatus'),
    modelMode: $('#modelRegistryMode'), modelList: $('#modelRegistryList'),
    modelRefresh: $('#modelRegistryRefresh'),
  };
}

export function createDatasetFeature(options = {}) {
  const request = options.api || api;
  const showToast = options.showToast || (() => {});
  const download = options.download || ((url, filename) => {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = 'noopener';
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  });
  const clock = options.now || Date.now;
  const ui = options.ui || datasetUi();
  let captureSnapshot = null;
  let captureApiAvailable = false;
  let captureBusy = false;
  let capturePollGeneration = 0;
  let sessionsPollGeneration = 0;
  let detailPollGeneration = 0;
  let sessions = [];
  let selectedSessionId = '';
  let selectedDetail = null;
  let selectedPageBefore = null;
  let selectedPageHistory = [];
  let selectedGalleryKey = '';
  let detailBusy = false;
  let detailError = '';
  let exportBusy = false;
  let exportMessage = '완료된 세션만 내보낼 수 있습니다.';
  let modelRegistry = { models: [], mode: 'UNAVAILABLE' };
  let modelPollGeneration = 0;
  let started = false;
  let active = false;
  let destroyed = false;
  let listeners = null;
  let capturePollTimer = 0;
  let elapsedRenderTimer = 0;
  let sessionsPollTimer = 0;

  function elapsedSeconds(now = clock()) {
    if (!captureSnapshot) return 0;
    const isActive = Boolean(captureSnapshot.active || DATASET_CAPTURE_ACTIVE_STATES.has(captureSnapshot.state));
    if (captureSnapshot.elapsedS != null) {
      const updatedAt = Number(captureSnapshot.receivedAt || now);
      return Math.max(0, captureSnapshot.elapsedS + (isActive ? Math.max(0, now - updatedAt) / 1000 : 0));
    }
    const startedAt = Date.parse(captureSnapshot.startedAt || '');
    return isActive && Number.isFinite(startedAt) ? Math.max(0, (now - startedAt) / 1000) : 0;
  }

  function selectedSourceControl() {
    return ui.sourcePicker.querySelector('input[name="datasetCameraSource"]:checked')?.value || 'go2_front';
  }

  function setSourceControl(value, disabled) {
    const selected = value === 'both' ? 'both' : DATASET_CAMERA_SOURCE_IDS.includes(value) ? value : 'go2_front';
    ui.sourcePicker.querySelectorAll('input[name="datasetCameraSource"]').forEach((input) => {
      input.checked = input.value === selected;
      input.disabled = disabled;
      input.closest('label')?.classList.toggle('is-selected', input.checked);
      input.closest('label')?.classList.toggle('is-disabled', disabled);
    });
  }

  function renderCapture(now = clock()) {
    const snapshot = captureSnapshot || normalizeDatasetCapture({ available: captureApiAvailable });
    const isActive = Boolean(snapshot.active || DATASET_CAPTURE_ACTIVE_STATES.has(snapshot.state));
    const elapsed = formatDatasetDuration(elapsedSeconds(now));
    const stateLabels = {
      idle: 'READY', starting: 'STARTING', capturing: 'CAPTURING', running: 'CAPTURING',
      stopping: 'FINALIZING', finalizing: 'FINALIZING', complete: 'COMPLETE', completed: 'COMPLETE',
      failed: 'ERROR', error: 'ERROR', unavailable: 'UNAVAILABLE',
    };
    const stateClass = isActive
      ? 'active'
      : ['failed', 'error'].includes(snapshot.state) ? 'error'
        : ['complete', 'completed'].includes(snapshot.state) ? 'complete'
          : captureApiAvailable ? 'ready' : 'unavailable';
    ui.captureState.className = `dataset-server-badge ${stateClass}`;
    ui.captureState.replaceChildren(
      document.createElement('span'),
      document.createTextNode(stateLabels[snapshot.state] || String(snapshot.state || 'CHECKING').toUpperCase()),
    );
    ui.captureElapsed.textContent = elapsed;
    ui.captureSaved.textContent = Math.floor(snapshot.saved).toLocaleString();
    ui.captureDropped.textContent = Math.floor(snapshot.dropped).toLocaleString();
    ui.captureBytes.textContent = formatDatasetBytes(snapshot.bytes);
    ui.captureFree.textContent = snapshot.freeBytes == null ? '—' : formatDatasetBytes(snapshot.freeBytes);
    ui.captureQuota.textContent = snapshot.sessionQuotaBytes == null ? '—' : formatDatasetBytes(snapshot.sessionQuotaBytes);
    ui.captureReserve.textContent = snapshot.minimumFreeBytes == null ? '—' : formatDatasetBytes(snapshot.minimumFreeBytes);
    ui.captureSources.textContent = datasetSourceLabel(snapshot.sources);
    ui.capturePath.textContent = snapshot.path || '서버 저장 경로를 확인할 수 없습니다.';
    ui.capturePath.title = snapshot.path || '';
    const locked = isActive || captureBusy;
    const selectedValue = snapshot.sources.length > 1 ? 'both' : snapshot.sources[0];
    setSourceControl(isActive && selectedValue ? selectedValue : selectedSourceControl(), locked);
    ui.captureHz.disabled = locked;
    ui.sessionLabel.disabled = locked;
    if (isActive && snapshot.captureHz) ui.captureHz.value = String(snapshot.captureHz);
    if (isActive && snapshot.label) ui.sessionLabel.value = snapshot.label;
    ui.captureStart.disabled = !captureApiAvailable || isActive || captureBusy;
    ui.captureStop.disabled = !captureApiAvailable || captureBusy || !datasetCaptureCanStop(snapshot);
    ui.openFolder.disabled = !snapshot.sessionId && !selectedSessionId && !sessions.length;
    const defaultMessage = !captureApiAvailable
      ? '데이터셋 캡처 API를 기다리고 있습니다.'
      : isActive
        ? `${datasetSourceLabel(snapshot.sources)} · ${snapshot.captureHz || '—'} Hz로 dashboard host에 저장 중입니다.`
        : '카메라와 저장 주기를 선택하면 dashboard host에서 캡처를 시작할 수 있습니다.';
    ui.captureMessage.textContent = snapshot.error || snapshot.message || defaultMessage;
    ui.captureMessage.classList.toggle('error', Boolean(snapshot.error));
    ui.globalStatus.hidden = !isActive;
    ui.globalStatusText.textContent = `${elapsed} · ${Math.floor(snapshot.saved).toLocaleString()} saved`;
  }

  async function refreshCapture() {
    if (destroyed) return null;
    const generation = ++capturePollGeneration;
    try {
      const normalized = normalizeDatasetCapture(await request('/api/v1/datasets/capture'));
      if (destroyed || generation !== capturePollGeneration) return null;
      const wasActive = Boolean(captureSnapshot?.active);
      const previousSession = captureSnapshot?.sessionId || '';
      captureApiAvailable = normalized.available;
      captureSnapshot = { ...normalized, receivedAt: clock() };
      renderCapture();
      if ((wasActive && !normalized.active) || (normalized.sessionId && normalized.sessionId !== previousSession)) {
        void refreshSessions({ preferredId: normalized.sessionId });
      }
      return captureSnapshot;
    } catch (error) {
      if (destroyed || generation !== capturePollGeneration) return null;
      captureApiAvailable = false;
      captureSnapshot = {
        ...normalizeDatasetCapture({ available: false, state: 'unavailable', error: error.message }),
        receivedAt: clock(),
      };
      renderCapture();
      return null;
    }
  }

  async function startCapture() {
    if (destroyed || captureBusy || captureSnapshot?.active) return;
    const captureHz = Number(ui.captureHz.value);
    if (!Number.isFinite(captureHz) || captureHz < 0.2 || captureHz > 5) {
      showToast('캡처 주기는 0.2 Hz에서 5 Hz 사이로 입력하세요.', true);
      ui.captureHz.focus();
      return;
    }
    const body = {
      sources: selectedSourceControl(),
      capture_hz: captureHz,
      label: ui.sessionLabel.value.trim(),
    };
    captureBusy = true;
    renderCapture();
    try {
      const response = await request('/api/v1/datasets/capture/start', {
        method: 'POST', body: JSON.stringify(body),
      });
      if (destroyed) return;
      const normalized = normalizeDatasetCapture(response);
      if (normalized.sessionId || normalized.active) {
        captureApiAvailable = normalized.available;
        captureSnapshot = { ...normalized, receivedAt: clock() };
      }
      showToast('서버 데이터셋 캡처를 시작했습니다. 페이지를 이동해도 계속 저장됩니다.');
      await refreshCapture();
    } catch (error) {
      if (!destroyed) showToast(`데이터셋 캡처 시작 실패: ${error.message}`, true);
    } finally {
      captureBusy = false;
      if (!destroyed) renderCapture();
    }
  }

  async function stopCapture() {
    const sessionId = captureSnapshot?.sessionId || '';
    if (destroyed || captureBusy || !sessionId) return;
    captureBusy = true;
    renderCapture();
    try {
      await request('/api/v1/datasets/capture/stop', {
        method: 'POST', body: JSON.stringify({ session_id: sessionId }),
      });
      if (destroyed) return;
      showToast('데이터셋 캡처 중지를 요청했습니다. 저장 파일을 마무리하고 있습니다.');
      await refreshCapture();
    } catch (error) {
      if (!destroyed) showToast(`데이터셋 캡처 중지 실패: ${error.message}`, true);
    } finally {
      captureBusy = false;
      if (!destroyed) renderCapture();
    }
  }

  function renderSessions() {
    ui.sessionCount.textContent = `${sessions.length.toLocaleString()} sessions`;
    if (!sessions.length) {
      ui.sessionList.innerHTML = '<div class="dataset-library-empty">저장된 데이터셋 폴더가 없습니다.</div>';
      if (!selectedSessionId) renderSelected();
      return;
    }
    ui.sessionList.innerHTML = sessions.map((session) => `
      <button class="dataset-session-item${session.id === selectedSessionId ? ' is-active' : ''}" type="button" data-dataset-session-id="${escapeHtml(session.id)}">
        <strong title="${escapeHtml(session.label)}">${escapeHtml(session.label)}</strong>
        <small>${escapeHtml(datasetSourceLabel(session.sources))} · ${escapeHtml(formatDatasetDate(session.startedAt))}</small>
        <b>${Math.floor(session.sampleCount).toLocaleString()}</b>
      </button>`).join('');
  }

  function pageRange(detail) {
    const indices = detail.samples.map((sample) => datasetPositiveInteger(sample.index)).filter((index) => index != null);
    return {
      oldest: detail.page.oldestIndex || (indices.length ? Math.min(...indices) : null),
      newest: detail.page.newestIndex || (indices.length ? Math.max(...indices) : null),
    };
  }

  function renderPagination(detail = selectedDetail) {
    const current = detail && detail.id === selectedSessionId ? detail : null;
    const page = current?.page;
    const range = current ? pageRange(current) : { oldest: null, newest: null };
    const newestPage = !page?.before;
    ui.pageNewest.disabled = detailBusy || !current || newestPage;
    ui.pageNewer.disabled = detailBusy || !current || !selectedPageHistory.length;
    ui.pageOlder.disabled = detailBusy || !current || !page?.hasOlder || !page?.nextBefore;
    if (detailBusy) ui.pageStatus.textContent = '최대 24개 샘플을 불러오는 중…';
    else if (detailError) ui.pageStatus.textContent = detailError;
    else if (range.oldest && range.newest) ui.pageStatus.textContent = `#${range.oldest.toLocaleString()}–#${range.newest.toLocaleString()} · 최대 ${DATASET_PAGE_LIMIT}개/페이지`;
    else ui.pageStatus.textContent = current ? '이 페이지에 표시할 샘플이 없습니다.' : '최신 24개 샘플 미리보기';
  }

  function replaceGallery(key, html) {
    if (selectedGalleryKey === key) return false;
    selectedGalleryKey = key;
    ui.sampleGallery.innerHTML = html;
    return true;
  }

  function renderSelected() {
    const detail = selectedDetail;
    if (!detail || detail.id !== selectedSessionId) {
      ui.selectedTitle.textContent = detailError
        ? '데이터셋을 불러오지 못했습니다.'
        : selectedSessionId ? '데이터셋 폴더 불러오는 중…' : '선택된 데이터셋 없음';
      ui.selectedPath.textContent = '—';
      ui.selectedSamples.textContent = '0';
      ui.selectedMeta.textContent = detailError || (selectedSessionId ? '세션 상세 정보를 요청하고 있습니다.' : '세션을 선택하세요.');
      ui.exportSession.disabled = true;
      ui.exportStatus.textContent = exportMessage;
      replaceGallery(
        detailError ? `error:${selectedSessionId}:${detailError}` : `loading:${selectedSessionId}`,
        `<div class="dataset-library-empty">${detailError ? '세션 상세 정보를 확인할 수 없습니다.' : '저장 이미지 목록을 기다리고 있습니다.'}</div>`,
      );
      renderPagination(null);
      return;
    }
    ui.selectedTitle.textContent = detail.label;
    ui.selectedPath.textContent = detail.path || '서버 경로 비공개';
    ui.selectedPath.title = detail.path || '';
    ui.selectedSamples.textContent = Math.floor(detail.sampleCount ?? detail.samples.length).toLocaleString();
    ui.selectedMeta.textContent = detailError || `${datasetSourceLabel(detail.sources)} · ${formatDatasetBytes(detail.bytes)} · ${String(detail.state || 'complete').toUpperCase()}`;
    const finalized = detail.state === 'completed' || detail.state === 'complete';
    ui.exportSession.disabled = exportBusy || !finalized;
    ui.exportStatus.textContent = exportBusy
      ? '서버에서 archive와 SHA-256 manifest를 생성하고 있습니다.'
      : exportMessage;
    renderPagination(detail);
    const cards = [];
    const visibleSamples = [...detail.samples].sort((left, right) => right.index - left.index).slice(0, DATASET_PAGE_LIMIT);
    for (const sample of visibleSamples) {
      const sources = sample.sources.length ? sample.sources : detail.sources;
      for (const sourceId of sources) {
        const url = datasetImageUrl(detail.id, sample.index, sourceId);
        cards.push(`<a class="dataset-sample-card" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" aria-label="샘플 ${sample.index} ${escapeHtml(sourceId)} 원본 이미지 열기">
          <img src="${escapeHtml(url)}" alt="샘플 ${sample.index} · ${escapeHtml(sourceId)}" loading="lazy" decoding="async">
          <span><strong>#${sample.index}</strong><small>${escapeHtml(sourceId === 'go2_front' ? 'GO2' : 'REALSENSE')}</small></span>
        </a>`);
      }
    }
    const galleryKey = [detail.id, detail.page.before || 'newest', ...visibleSamples.flatMap((sample) => [sample.index, ...sample.sources])].join('|');
    replaceGallery(galleryKey, cards.length ? cards.join('') : '<div class="dataset-library-empty">이 페이지에서 확인할 수 있는 이미지가 아직 없습니다.</div>');
  }

  async function exportSelectedSession() {
    if (destroyed || exportBusy || !selectedDetail || ui.exportSession.disabled) return null;
    const sessionId = selectedDetail.id;
    exportBusy = true;
    exportMessage = '내보내기 진행 중';
    renderSelected();
    try {
      const result = datasetObject(await request(
        `/api/v1/datasets/${encodeURIComponent(sessionId)}/export`,
        { method: 'POST', body: JSON.stringify({}) },
      ));
      if (!/^[0-9a-f]{32}$/.test(String(result.export_id || ''))) throw new Error('export id가 유효하지 않습니다.');
      if (!/^[0-9a-f]{64}$/.test(String(result.sha256 || ''))) throw new Error('archive hash가 유효하지 않습니다.');
      exportMessage = `READY · ${formatDatasetBytes(result.bytes)} · SHA256 ${String(result.sha256).slice(0, 12)}…`;
      download(datasetExportUrl(result.export_id), String(result.filename || 'robot-scope-dataset.zip'));
      showToast('완료된 Dataset archive 다운로드를 시작했습니다.');
      return result;
    } catch (error) {
      exportMessage = `EXPORT FAILED · ${String(error.message || error)}`;
      showToast(`Dataset export 실패: ${error.message}`, true);
      return null;
    } finally {
      exportBusy = false;
      if (!destroyed) renderSelected();
    }
  }

  function renderModels() {
    ui.modelMode.textContent = modelRegistry.mode;
    if (!modelRegistry.models.length) {
      ui.modelList.innerHTML = '<div class="dataset-library-empty">등록된 모델이 없거나 registry를 사용할 수 없습니다.</div>';
      return;
    }
    ui.modelList.innerHTML = modelRegistry.models.map((model) => {
      const effectiveState = model.isActive ? 'active' : model.isPrevious ? 'previous' : model.state;
      const hash = model.engineSha256 || model.packageSha256;
      return `<article class="model-registry-item" data-state="${escapeHtml(effectiveState)}">
        <header><strong>${escapeHtml(model.modelId)}</strong><b>${escapeHtml(effectiveState.toUpperCase())}</b></header>
        <code>${escapeHtml(model.task.toUpperCase())} · ${escapeHtml(hash ? `${hash.slice(0, 16)}…` : 'NO ENGINE')}</code>
        <small>${escapeHtml(model.reason || 'Activation requires the local target operator tool.')}</small>
      </article>`;
    }).join('');
  }

  async function refreshModels() {
    const generation = ++modelPollGeneration;
    try {
      const next = normalizeModelRegistry(await request('/api/v1/models'));
      if (destroyed || generation !== modelPollGeneration) return null;
      modelRegistry = next;
      renderModels();
      return next;
    } catch (_) {
      if (destroyed || generation !== modelPollGeneration) return null;
      modelRegistry = { models: [], mode: 'UNAVAILABLE' };
      renderModels();
      return null;
    }
  }

  async function refreshDetail(sessionId = selectedSessionId, { before = selectedPageBefore, history = selectedPageHistory } = {}) {
    if (destroyed || !sessionId) return null;
    const requestedBefore = datasetPositiveInteger(before);
    const requestedHistory = Array.isArray(history) ? [...history] : [];
    const generation = ++detailPollGeneration;
    detailBusy = true;
    detailError = '';
    renderSelected();
    try {
      const fallback = sessions.find((entry) => entry.id === sessionId)
        || (captureSnapshot?.sessionId === sessionId ? {
          id: sessionId, label: captureSnapshot.label || sessionId, sources: captureSnapshot.sources,
          sample_count: captureSnapshot.saved, bytes: captureSnapshot.bytes, path: captureSnapshot.path,
          state: captureSnapshot.state,
        } : {});
      const detail = normalizeDatasetDetail(await request(datasetDetailUrl(sessionId, requestedBefore)), fallback);
      if (destroyed || generation !== detailPollGeneration || sessionId !== selectedSessionId) return null;
      if (requestedBefore && !detail.page.before) detail.page.before = requestedBefore;
      selectedPageBefore = detail.page.before;
      selectedPageHistory = requestedHistory;
      selectedDetail = detail;
      return detail;
    } catch (error) {
      if (destroyed || generation !== detailPollGeneration || sessionId !== selectedSessionId) return null;
      detailError = String(error.message || '세션 상세 정보를 확인할 수 없습니다.');
      return null;
    } finally {
      if (!destroyed && generation === detailPollGeneration && sessionId === selectedSessionId) {
        detailBusy = false;
        renderSelected();
      }
    }
  }

  function selectSession(sessionId, { scroll = false } = {}) {
    const nextId = String(sessionId || '');
    if (destroyed || !nextId) return;
    selectedSessionId = nextId;
    selectedDetail = null;
    selectedPageBefore = null;
    selectedPageHistory = [];
    selectedGalleryKey = '';
    detailBusy = false;
    detailError = '';
    detailPollGeneration += 1;
    renderSessions();
    renderSelected();
    if (scroll) ui.libraryPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    void refreshDetail(nextId, { before: null, history: [] });
  }

  async function navigatePage(direction) {
    if (destroyed || detailBusy || !selectedDetail || !selectedSessionId) return null;
    if (direction === 'newest') return refreshDetail(selectedSessionId, { before: null, history: [] });
    if (direction === 'newer') {
      if (!selectedPageHistory.length) return null;
      const history = [...selectedPageHistory];
      const before = history.pop() ?? null;
      return refreshDetail(selectedSessionId, { before, history });
    }
    if (direction === 'older') {
      const before = selectedDetail.page.nextBefore;
      if (!selectedDetail.page.hasOlder || !before) return null;
      return refreshDetail(selectedSessionId, { before, history: [...selectedPageHistory, selectedPageBefore] });
    }
    return null;
  }

  async function refreshSessions({ preferredId = '', forceDetail = false } = {}) {
    if (destroyed || (!active && !preferredId)) return null;
    const generation = ++sessionsPollGeneration;
    try {
      const nextSessions = normalizeDatasetCatalog(await request('/api/v1/datasets'));
      if (destroyed || generation !== sessionsPollGeneration) return null;
      const previousSummary = sessions.find((entry) => entry.id === selectedSessionId);
      const previousSampleCount = previousSummary?.sampleCount ?? selectedDetail?.sampleCount ?? null;
      sessions = nextSessions;
      const desired = preferredId || selectedSessionId;
      const nextId = sessions.some((entry) => entry.id === desired)
        ? desired : sessions[0]?.id || captureSnapshot?.sessionId || '';
      const selectionChanged = nextId !== selectedSessionId;
      selectedSessionId = nextId;
      const selectedSummary = sessions.find((entry) => entry.id === nextId);
      const sampleCountChanged = previousSampleCount != null && selectedSummary != null
        && selectedSummary.sampleCount !== previousSampleCount;
      if (selectionChanged) {
        selectedDetail = null;
        selectedPageBefore = null;
        selectedPageHistory = [];
        selectedGalleryKey = '';
        detailError = '';
      } else if (selectedDetail && selectedSummary) {
        selectedDetail = { ...selectedDetail, ...selectedSummary, samples: selectedDetail.samples, page: selectedDetail.page };
      }
      renderSessions();
      renderSelected();
      const newestPageChanged = selectedPageBefore == null && sampleCountChanged;
      if (nextId && (selectionChanged || !selectedDetail || forceDetail || newestPageChanged)) {
        void refreshDetail(nextId, {
          before: selectionChanged ? null : selectedPageBefore,
          history: selectionChanged ? [] : selectedPageHistory,
        });
      }
      renderCapture();
      return sessions;
    } catch (error) {
      if (destroyed || generation !== sessionsPollGeneration) return null;
      if (!sessions.length) ui.sessionList.innerHTML = `<div class="dataset-library-empty">데이터셋 폴더 목록을 불러오지 못했습니다: ${escapeHtml(error.message)}</div>`;
      return null;
    }
  }

  async function openWebFolder() {
    const preferredId = captureSnapshot?.sessionId || selectedSessionId;
    await refreshSessions({ preferredId });
    if (destroyed) return;
    const nextId = preferredId || sessions[0]?.id;
    if (nextId) selectSession(nextId, { scroll: true });
  }

  function syncSourcePicker() {
    setSourceControl(selectedSourceControl(), Boolean(captureSnapshot?.active || captureBusy));
  }

  function bindEvents() {
    listeners = new AbortController();
    const signal = listeners.signal;
    ui.captureStart.addEventListener('click', startCapture, { signal });
    ui.captureStop.addEventListener('click', stopCapture, { signal });
    ui.openFolder.addEventListener('click', openWebFolder, { signal });
    ui.refreshFolders.addEventListener('click', () => refreshSessions({ preferredId: selectedSessionId, forceDetail: true }), { signal });
    ui.sourcePicker.addEventListener('change', syncSourcePicker, { signal });
    ui.captureHz.addEventListener('change', () => {
      const value = Number(ui.captureHz.value);
      if (Number.isFinite(value)) ui.captureHz.value = String(Math.min(5, Math.max(0.2, value)));
    }, { signal });
    ui.sessionList.addEventListener('click', (event) => {
      const button = event.target.closest('[data-dataset-session-id]');
      if (button) selectSession(button.dataset.datasetSessionId);
    }, { signal });
    ui.pageNewest.addEventListener('click', () => navigatePage('newest'), { signal });
    ui.pageNewer.addEventListener('click', () => navigatePage('newer'), { signal });
    ui.pageOlder.addEventListener('click', () => navigatePage('older'), { signal });
    ui.exportSession.addEventListener('click', exportSelectedSession, { signal });
    ui.modelRefresh.addEventListener('click', refreshModels, { signal });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) void refreshCapture();
      if (!document.hidden && active) void refreshSessions({ preferredId: selectedSessionId });
    }, { signal });
  }

  function activate() {
    if (destroyed || active) return;
    active = true;
    void refreshCapture();
    void refreshSessions({ preferredId: selectedSessionId });
    void refreshModels();
    sessionsPollTimer = window.setInterval(() => {
      if (!document.hidden) void refreshSessions({ preferredId: selectedSessionId });
    }, 10_000);
  }

  function deactivate() {
    if (!active) return;
    active = false;
    if (sessionsPollTimer) window.clearInterval(sessionsPollTimer);
    sessionsPollTimer = 0;
    sessionsPollGeneration += 1;
    detailPollGeneration += 1;
    modelPollGeneration += 1;
    detailBusy = false;
  }

  function start() {
    if (started || destroyed) return feature;
    started = true;
    bindEvents();
    renderCapture();
    void refreshCapture();
    capturePollTimer = window.setInterval(refreshCapture, 1_500);
    elapsedRenderTimer = window.setInterval(renderCapture, 1_000);
    return feature;
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    destroyed = true;
    listeners?.abort();
    listeners = null;
    if (capturePollTimer) window.clearInterval(capturePollTimer);
    if (elapsedRenderTimer) window.clearInterval(elapsedRenderTimer);
    capturePollTimer = 0;
    elapsedRenderTimer = 0;
    capturePollGeneration += 1;
    sessionsPollGeneration += 1;
    detailPollGeneration += 1;
    captureSnapshot = null;
    captureApiAvailable = false;
    captureBusy = false;
    sessions = [];
    selectedSessionId = '';
    selectedDetail = null;
    selectedPageBefore = null;
    selectedPageHistory = [];
    selectedGalleryKey = '';
    detailBusy = false;
    detailError = '';
    exportBusy = false;
    exportMessage = '완료된 세션만 내보낼 수 있습니다.';
    modelRegistry = { models: [], mode: 'UNAVAILABLE' };
  }

  function snapshot() {
    return {
      capture: captureSnapshot ? { ...captureSnapshot } : null,
      sessions: sessions.map((entry) => ({ ...entry })),
      selectedSessionId,
      selectedPageBefore,
      modelRegistry: { ...modelRegistry, models: modelRegistry.models.map((entry) => ({ ...entry })) },
      lifecycle: { started, active, destroyed },
    };
  }

  const feature = Object.freeze({
    start, activate, deactivate, destroy, refresh: refreshCapture, refreshSessions, refreshModels,
    render: renderCapture, startCapture, stopCapture, selectSession, navigatePage,
    exportSelectedSession, snapshot,
    normalizeCapture: normalizeDatasetCapture,
    normalizeCatalog: normalizeDatasetCatalog,
    normalizeDetail: normalizeDatasetDetail,
    formatBytes: formatDatasetBytes,
    imageUrl: datasetImageUrl,
    detailUrl: datasetDetailUrl,
    exportUrl: datasetExportUrl,
    canStop: datasetCaptureCanStop,
  });
  return feature;
}
