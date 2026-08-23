import { downloadApi } from '../../core/api.js';
import { $ } from '../../core/dom.js';

export function createDiagnosticsExportFeature(options = {}) {
  const request = options.downloadApi || downloadApi;
  const showToast = options.showToast || (() => {});
  const ui = options.ui || {
    button: $('#diagnosticsExportButton'),
    state: $('#diagnosticsExportState'),
    message: $('#diagnosticsExportMessage'),
  };
  let listeners = null;
  let busy = false;
  let destroyed = false;
  let objectUrl = '';

  function render() {
    if (!ui.button) return;
    ui.button.disabled = busy || destroyed;
    ui.state.textContent = destroyed ? 'DESTROYED' : busy ? 'EXPORTING' : 'READY';
    ui.state.className = `panel-state ${destroyed ? 'error' : busy ? 'waiting' : 'ok'}`;
    ui.message.textContent = destroyed
      ? '진단 내보내기 기능이 종료되었습니다.'
      : busy
        ? '공개 projection과 최근 bounded event를 ZIP으로 묶고 있습니다.'
        : '로봇 작업을 중지하지 않고 redacted 진단 ZIP을 생성합니다.';
  }

  function releaseObjectUrl() {
    if (!objectUrl) return;
    URL.revokeObjectURL(objectUrl);
    objectUrl = '';
  }

  async function exportBundle() {
    if (busy || destroyed) return null;
    busy = true;
    render();
    try {
      const bundle = await request('/api/v1/system/diagnostics/export', { method: 'POST' });
      if (destroyed) return null;
      releaseObjectUrl();
      objectUrl = URL.createObjectURL(bundle.blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = bundle.filename;
      link.rel = 'noopener';
      link.hidden = true;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(releaseObjectUrl, 0);
      showToast('Redacted 진단 번들을 다운로드했습니다.');
      return bundle.filename;
    } catch (error) {
      if (!destroyed) showToast(`진단 번들 생성 실패: ${error?.message || '연결 오류'}`, true);
      return null;
    } finally {
      busy = false;
      if (!destroyed) render();
    }
  }

  function start() {
    if (listeners || destroyed) return feature;
    listeners = new AbortController();
    ui.button?.addEventListener('click', exportBundle, { signal: listeners.signal });
    render();
    return feature;
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    listeners?.abort();
    listeners = null;
    releaseObjectUrl();
    render();
  }

  function snapshot() {
    return { busy, destroyed, started: Boolean(listeners) };
  }

  const feature = Object.freeze({ start, destroy, exportBundle, snapshot });
  return feature;
}
