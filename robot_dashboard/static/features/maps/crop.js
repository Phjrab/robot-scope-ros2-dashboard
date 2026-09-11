const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
export const validSavedMapName = (value) => NAME_RE.test(String(value || ''));
export function suggestedDerivedMapName(source, suffix) {
  const base = String(source?.name || source?.file_name || 'map').replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]+/g, '_');
  const normalized = /^[A-Za-z0-9]/.test(base) ? base : `map_${base}`;
  return `${normalized.slice(0, Math.max(1, 64 - suffix.length))}${suffix}`;
}

function element(id) {
  const value = document.getElementById(id);
  if (!value) throw new Error(`map crop UI is missing ${id}`);
  return value;
}

function decodeGrid(snapshot) {
  const width = Number(snapshot?.width);
  const height = Number(snapshot?.height);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 2 || height < 2) {
    throw new Error('crop source dimensions are invalid');
  }
  const binary = atob(String(snapshot?.data_b64 || ''));
  if (binary.length !== width * height) throw new Error('crop source cell count is invalid');
  return { width, height, cells: Uint8Array.from(binary, (value) => value.charCodeAt(0)) };
}

export function initializeMapCropFeature(options) {
  const ui = {
    canvas: element('mapCropCanvas'), empty: element('mapCropEmpty'), state: element('mapCropState'),
    select: element('mapCropSelect'), cancel: element('mapCropCancel'), save: element('mapCropSave'),
    name: element('mapCropName'), source: element('mapCropSource'), dimensions: element('mapCropDimensions'),
    message: element('mapCropMessage'),
  };
  let source = null;
  let image = null;
  let layout = null;
  let selecting = false;
  let pointer = null;
  let crop = null;
  let saving = false;

  function sourceValue() {
    const value = options.getSource();
    const meta = value?.meta;
    const snapshot = value?.snapshot;
    if (meta?.kind !== 'occupancy2d' || meta?.manageable !== true || meta?.editable !== true) return null;
    if (!snapshot || snapshot.map_id !== meta.id || snapshot.revision !== meta.revision) return null;
    return { meta, snapshot };
  }

  function cellAt(event) {
    if (!source || !layout) return null;
    const bounds = ui.canvas.getBoundingClientRect();
    const x = (event.clientX - bounds.left) * (ui.canvas.width / bounds.width);
    const y = (event.clientY - bounds.top) * (ui.canvas.height / bounds.height);
    if (x < layout.left || y < layout.top || x >= layout.right || y >= layout.bottom) return null;
    return {
      x: Math.max(0, Math.min(source.width - 1, Math.floor((x - layout.left) / layout.scale))),
      y: Math.max(0, Math.min(source.height - 1, source.height - 1 - Math.floor((y - layout.top) / layout.scale))),
    };
  }

  function normalizedCrop(start, end) {
    if (!start || !end) return null;
    const value = {
      min_x: Math.min(start.x, end.x), min_y: Math.min(start.y, end.y),
      max_x: Math.max(start.x, end.x) + 1, max_y: Math.max(start.y, end.y) + 1,
    };
    return value.max_x - value.min_x >= 2 && value.max_y - value.min_y >= 2 ? value : null;
  }

  function draw() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(ui.canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(ui.canvas.clientHeight * ratio));
    if (ui.canvas.width !== width || ui.canvas.height !== height) { ui.canvas.width = width; ui.canvas.height = height; }
    const context = ui.canvas.getContext('2d');
    context.fillStyle = '#06100e'; context.fillRect(0, 0, width, height);
    if (!source || !image) { layout = null; return; }
    const scale = Math.min(width / source.width, height / source.height) * .94;
    const drawWidth = source.width * scale; const drawHeight = source.height * scale;
    const left = (width - drawWidth) / 2; const top = (height - drawHeight) / 2;
    context.imageSmoothingEnabled = false; context.drawImage(image, left, top, drawWidth, drawHeight);
    layout = { left, top, right: left + drawWidth, bottom: top + drawHeight, scale };
    const selected = pointer ? normalizedCrop(pointer.start, pointer.end) : crop;
    if (!selected) return;
    const sx = left + selected.min_x * scale;
    const sy = top + (source.height - selected.max_y) * scale;
    const sw = (selected.max_x - selected.min_x) * scale;
    const sh = (selected.max_y - selected.min_y) * scale;
    context.fillStyle = 'rgba(2,8,7,.66)';
    context.fillRect(left, top, drawWidth, sy - top); context.fillRect(left, sy + sh, drawWidth, top + drawHeight - sy - sh);
    context.fillRect(left, sy, sx - left, sh); context.fillRect(sx + sw, sy, left + drawWidth - sx - sw, sh);
    context.strokeStyle = '#ffc66d'; context.lineWidth = Math.max(2, ratio * 1.5); context.strokeRect(sx, sy, sw, sh);
  }

  function render(message = '') {
    const available = Boolean(source);
    ui.empty.hidden = available;
    ui.select.disabled = !available || saving;
    ui.cancel.disabled = !crop || saving;
    ui.name.disabled = !available || saving;
    ui.save.disabled = !crop || saving || !NAME_RE.test(ui.name.value.trim());
    ui.select.classList.toggle('is-active', selecting);
    ui.select.textContent = selecting ? '지도에서 영역을 드래그하세요' : 'CROP AREA 선택';
    ui.source.textContent = available ? `SOURCE ${source.meta.name}` : 'SOURCE —';
    const width = crop ? crop.max_x - crop.min_x : 0; const height = crop ? crop.max_y - crop.min_y : 0;
    ui.dimensions.textContent = crop ? `${width}×${height} cells · ${(width * source.resolution).toFixed(2)}×${(height * source.resolution).toFixed(2)} m` : '영역 미선택';
    options.setStatePill(ui.state, saving ? 'waiting' : available ? 'ok' : 'waiting', saving ? 'SAVING' : available ? 'READY' : 'NO MAP');
    ui.message.textContent = message || (available ? '경기장 경계를 사각형으로 선택하세요. 원본 지도는 유지됩니다.' : '크롭할 관리 가능 2D 지도를 선택하세요.');
    draw();
  }

  function sync() {
    const value = sourceValue();
    const key = value ? `${value.meta.id}:${value.meta.revision}` : '';
    if (key === source?.key) return render();
    source = null; image = null; crop = null; pointer = null; selecting = false;
    if (!value) return render();
    try {
      const decoded = decodeGrid(value.snapshot);
      const canvas = document.createElement('canvas'); canvas.width = decoded.width; canvas.height = decoded.height;
      const context = canvas.getContext('2d'); const pixels = context.createImageData(decoded.width, decoded.height);
      for (let index = 0; index < decoded.cells.length; index += 1) {
        const valueByte = decoded.cells[index]; const valueCell = valueByte > 127 ? valueByte - 256 : valueByte;
        const color = valueCell < 0 ? [126,137,133] : valueCell >= 65 ? [7,10,9] : [242,246,244];
        const x = index % decoded.width; const y = Math.floor(index / decoded.width);
        const output = ((decoded.height - 1 - y) * decoded.width + x) * 4;
        pixels.data.set([...color, 255], output);
      }
      context.putImageData(pixels, 0, 0); image = canvas;
      source = { key, meta: value.meta, width: decoded.width, height: decoded.height, resolution: Number(value.snapshot.resolution) };
      ui.name.value = suggestedDerivedMapName(value.meta, '_crop');
      render();
    } catch (error) { render(`크롭 준비 실패: ${error.message}`); }
  }

  ui.select.addEventListener('click', () => { selecting = !selecting; pointer = null; if (selecting) crop = null; render(); });
  ui.cancel.addEventListener('click', () => { selecting = false; pointer = null; crop = null; render(); });
  ui.name.addEventListener('input', () => render());
  ui.canvas.addEventListener('pointerdown', (event) => { const cell = selecting && cellAt(event); if (!cell || event.button !== 0) return; event.preventDefault(); pointer = { id: event.pointerId, start: cell, end: cell }; try { ui.canvas.setPointerCapture(event.pointerId); } catch (_) {} draw(); });
  ui.canvas.addEventListener('pointermove', (event) => { if (!pointer || pointer.id !== event.pointerId) return; const cell = cellAt(event); if (cell) pointer.end = cell; event.preventDefault(); draw(); });
  const finish = (event) => { if (!pointer || pointer.id !== event.pointerId) return; const cell = cellAt(event); if (cell) pointer.end = cell; crop = normalizedCrop(pointer.start, pointer.end); pointer = null; selecting = false; try { ui.canvas.releasePointerCapture(event.pointerId); } catch (_) {} render(crop ? '크롭 영역을 확인하고 새 복사본으로 저장하세요.' : '최소 2×2 셀 이상의 영역을 선택하세요.'); };
  ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) => ui.canvas.addEventListener(name, finish));
  ui.save.addEventListener('click', async () => {
    const current = sourceValue(); const name = ui.name.value.trim();
    if (!current || !crop || saving || !NAME_RE.test(name)) return;
    if (!window.confirm(`${crop.max_x - crop.min_x}×${crop.max_y - crop.min_y} 셀로 크롭한 새 지도를 저장할까요?\n원본 지도는 유지됩니다.`)) return;
    saving = true; render('크롭 복사본을 원자적으로 저장하고 있습니다.');
    try {
      const response = await options.api(`/api/v1/saved-maps/${encodeURIComponent(current.meta.id)}/cropped-copy`, { method: 'POST', body: JSON.stringify({ name, source_revision: current.meta.revision, crop }) });
      const result = response?.map; if (!result?.id || !result?.revision) throw new Error('서버가 크롭 결과 identity를 반환하지 않았습니다');
      await options.refreshSavedMaps(); await options.selectSavedMap(result.id, false, true); options.showToast(`${result.name || name} 크롭 지도를 생성했습니다.`);
    } catch (error) { render(`크롭 저장 실패: ${error.message}`); options.showToast(`크롭 저장 실패: ${error.message}`, true); }
    finally { saving = false; sync(); }
  });
  window.addEventListener('resize', draw);
  render();
  return Object.freeze({ sync });
}
