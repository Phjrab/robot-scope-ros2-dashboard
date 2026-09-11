import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';

const ui = {
  select: $('#realsenseProfileSelect'),
  apply: $('#realsenseProfileApply'),
  status: $('#realsenseProfileStatus'),
};

let snapshot = null;
let busy = false;
let generation = 0;
let initialized = false;
let getActivePage = () => '';
let showToast = () => {};
let onApplied = () => {};

function blockerLabel(value) {
  if (value === 'dataset_capture_active') return '데이터셋 녹화를 먼저 중지하세요.';
  if (value === 'remote_status_unavailable') return '탑재 Jetson의 RealSense 설정 상태를 확인할 수 없습니다.';
  return String(value || '').replaceAll('_', ' ');
}

function renderOptions(profiles, selected) {
  if (!ui.select) return;
  const ids = Array.isArray(profiles) ? profiles.map((profile) => String(profile?.id || '')) : [];
  const existing = Array.from(ui.select.options).map((option) => option.value);
  if (ids.join('|') !== existing.join('|')) {
    ui.select.replaceChildren(...(Array.isArray(profiles) ? profiles : []).map((profile) => {
      const option = document.createElement('option');
      option.value = String(profile.id);
      option.textContent = `${profile.width} × ${profile.height}`;
      return option;
    }));
  }
  if (selected && ids.includes(selected)) ui.select.value = selected;
}

function render() {
  if (!ui.select || !ui.apply || !ui.status) return;
  const selected = String(snapshot?.selected?.profile || '');
  renderOptions(snapshot?.profiles, selected);
  const blockers = Array.isArray(snapshot?.blockers) ? snapshot.blockers : [];
  const changed = Boolean(selected && ui.select.value && ui.select.value !== selected);
  ui.select.disabled = busy || !snapshot?.can_apply;
  ui.apply.disabled = busy || !snapshot?.can_apply || !changed;
  ui.status.dataset.state = 'waiting';
  if (busy) {
    ui.status.textContent = 'RealSense relay에 새 해상도를 적용하고 있습니다…';
  } else if (!snapshot) {
    ui.status.dataset.state = 'error';
    ui.status.textContent = '해상도 제어 API에 연결할 수 없습니다.';
  } else if (!snapshot.enabled) {
    ui.status.textContent = '대시보드 해상도 제어가 비활성 상태입니다.';
  } else if (!snapshot.configured || !snapshot.available) {
    ui.status.dataset.state = 'error';
    ui.status.textContent = blockerLabel(blockers[0] || 'remote_status_unavailable');
  } else if (blockers.length) {
    ui.status.textContent = blockerLabel(blockers[0]);
  } else {
    const profile = snapshot.selected;
    const service = String(profile?.service?.active || '').toUpperCase();
    ui.status.dataset.state = 'ok';
    ui.status.textContent = `현재 ${profile.width} × ${profile.height} · ${profile.fps} FPS · Q${profile.jpeg_quality} · ${service}`;
  }
}

async function refresh(force = false) {
  if (!force && getActivePage() !== 'sensors') return snapshot;
  const requestGeneration = ++generation;
  try {
    const next = await api('/api/v1/cameras/realsense/profile');
    if (requestGeneration !== generation) return snapshot;
    snapshot = next;
  } catch (_error) {
    if (requestGeneration !== generation) return snapshot;
    snapshot = null;
  }
  render();
  return snapshot;
}

async function applySelected() {
  if (busy || !snapshot?.can_apply) return;
  const resolution = String(ui.select?.value || '');
  if (!snapshot.profiles?.some((profile) => profile.id === resolution)) return;
  if (!window.confirm(`${resolution} 해상도로 변경하면 RealSense 영상이 잠시 끊겼다가 자동 복구됩니다. 적용할까요?`)) return;
  busy = true;
  render();
  try {
    snapshot = await api('/api/v1/cameras/realsense/profile', {
      method: 'POST',
      body: JSON.stringify({ resolution, confirmed: true }),
    });
    showToast(`RealSense 해상도를 ${resolution}로 적용했습니다.`);
    onApplied();
  } catch (error) {
    showToast(`RealSense 해상도 변경 실패: ${error?.message || '연결 오류'}`, true);
    await refresh(true);
  } finally {
    busy = false;
    render();
  }
}

export function initializeRealSenseProfileFeature(options = {}) {
  if (initialized) return feature;
  initialized = true;
  getActivePage = options.getActivePage || getActivePage;
  showToast = options.showToast || showToast;
  onApplied = options.onApplied || onApplied;
  ui.select?.addEventListener('change', render);
  ui.apply?.addEventListener('click', applySelected);
  setInterval(refresh, 5000);
  render();
  return feature;
}

const feature = Object.freeze({ refresh, render, apply: applySelected });
