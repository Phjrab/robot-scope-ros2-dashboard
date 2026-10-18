import { createEditor } from './core.js';

// Fail closed during source switches or stale response races.
export function savedCloudEditorSource(meta, snapshot) {
  if (meta?.kind !== 'pointcloud3d' || snapshot?.map_id !== meta.id
      || String(snapshot.revision) !== String(meta.revision) || !snapshot?.points?.length) return null;
  return { kind: 'pointcloud3d', map_id: meta.id, revision: snapshot.revision,
    frame_id: snapshot.frame_id, points: snapshot.points, source_points: snapshot.source_points };
}

// Saved-cloud annotation editor only. No ROS commands or network writes.
export function initializeMapEditor3D({ panel, getSource, is2DDirty = () => false, redraw2D = () => {} }) {
  if (!panel) return null;
  const doc = panel.ownerDocument;
  const make = (tag, text, attrs = {}) => { const e = doc.createElement(tag); if (text) e.textContent = text; Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); return e; };
  const two = panel.querySelector('#mapEditor2D');
  const heading = panel.querySelector('h2'); if (heading) heading.textContent = '지도 편집 · MAP EDITOR';
  const bar = make('div', '', { class: 'map3-mode-row' });
  const mode = make('select', '', { id: 'mapEditorMode', 'aria-label': '지도 편집 모드' });
  for (const [v, text] of [['2d', '2D 점유 지도'], ['3d', '3D 포인트클라우드']]) mode.append(make('option', text, { value: v }));
  bar.append(make('label', '편집 모드 ', { for: 'mapEditorMode' }), mode);
  const notice = make('span', '선택한 모드만 표시합니다.'); bar.append(notice); two.before(bar);
  const root = make('section', '', { id: 'mapEditor3D', 'aria-label': '3D 포인트클라우드 편집' }); root.hidden = true; two.after(root);
  const safety = make('p', '원본 보존 · 새 주석 버전 / 편집된 점군 복사본 · Nav2 / TF / 실시간 지도에 적용하지 않습니다.', { class: 'map3-safety' });
  const tools = make('div', '', { class: 'map3-tools' });
  const status = make('p', '위의 저장 지도 목록에서 3D 지도를 선택한 뒤 불러오세요.', { id: 'map3Status', role: 'status', 'aria-live': 'polite' });
  let editor = null, polygon = [], view = null, source = null, modeValue = '2d', exported = '[]', cachedPreview = null;
  const dirty = () => Boolean(editor && JSON.stringify(editor.regions) !== exported) || polygon.length > 0;
  const run = (fn) => { try { fn(); } catch (e) { status.textContent = e.message; status.dataset.error = 'true'; } };
  const button = (parent, id, label, fn) => { const b = make('button', label, { type: 'button', id }); b.addEventListener('click', () => run(fn)); parent.append(b); return b; };
  const load = button(tools, 'map3Load', '선택한 3D 지도 불러오기', () => {
    const incoming = getSource();
    if (!incoming || incoming.kind !== 'pointcloud3d' || !incoming.points?.length) throw new Error('저장된 3D 지도를 먼저 선택하세요.');
    if (!incoming.map_id || incoming.revision == null || incoming.revision === '' || !incoming.frame_id) throw new Error('지도 ID · revision · frame이 필요합니다. 출처가 불명확한 지도는 편집할 수 없습니다.');
    if (dirty() && !globalThis.confirm('저장하지 않은 3D 주석을 버리고 선택한 지도를 불러올까요?')) return;
    const next = createEditor(incoming); editor = next; source = { ...incoming, points: undefined }; polygon = []; exported = '[]'; cachedPreview = null; fit(); refresh();
  });
  const selection = make('select', '', { id: 'map3Selection', 'aria-label': '영역 내부 또는 외부 제거' });
  for (const [v, text] of [['inside', '다각형 내부 제거'], ['outside', '다각형 외부 제거 · 코스 안 유지']]) selection.append(make('option', text, { value: v })); tools.append(selection);
  const kind = make('select', '', { id: 'map3Kind', 'aria-label': '주석 종류' });
  for (const [v, text] of [['visibility', '표시 숨김 · VISIBILITY'], ['localization', '위치추정 제외 · LOCALIZATION'], ['keepout', '진입금지 주석 · KEEPOUT']]) kind.append(make('option', text, { value: v })); tools.append(kind);
  function number(id, label, value) { const wrap = make('label', label); const input = make('input', '', { id, type: 'number', step: '0.1', value }); wrap.append(input); tools.append(wrap); return input; }
  const low = number('map3ZMin', 'Z min (m)', '-0.5'), high = number('map3ZMax', 'Z max (m)', '2.0');
  const add = button(tools, 'map3Add', '영역 추가', () => {
    if (!editor) throw new Error('3D 지도를 불러오세요.');
    if (!low.value.trim() || !high.value.trim()) throw new Error('높이 범위의 두 값을 입력하세요.');
    editor.addRegion({ kind: kind.value, selection: selection.value, polygon, z_min: Number(low.value), z_max: Number(high.value) }); polygon = []; cachedPreview = null; refresh();
  });
  button(tools, 'map3Cancel', '선택 취소', () => { polygon = []; refresh(); });
  const history = make('div', '', { class: 'map3-tools' });
  const undo = button(history, 'map3Undo', 'UNDO', () => { editor?.undo(); cachedPreview = null; refresh(); });
  const redo = button(history, 'map3Redo', 'REDO', () => { editor?.redo(); cachedPreview = null; refresh(); });
  const reset = button(history, 'map3Reset', 'RESET', () => { if (editor && globalThis.confirm('3D 주석을 모두 초기화할까요? 원본은 유지됩니다.')) { editor.reset(); polygon = []; cachedPreview = null; refresh(); } });
  const previewLabel = make('label', '표시 숨김 미리보기 '); const preview = make('input', '', { id: 'map3Preview', type: 'checkbox' }); previewLabel.append(preview); history.append(previewLabel); preview.addEventListener('change', () => refresh());
  const canvas = make('canvas', '', { id: 'map3Canvas', width: '1100', height: '540', tabindex: '0', 'aria-label': 'XY 평면 다각형 선택. 클릭으로 꼭짓점 추가, Backspace로 마지막 점 제거, Escape로 취소.' });
  const help = make('p', 'TOP DOWN · XY (m) · 클릭으로 꼭짓점 3개 이상 → 높이 범위 → 영역 추가. Backspace: 마지막 점 삭제 / Esc: 선택 취소. 외부 제거는 지정한 Z 범위 안의 다각형 외부 점만 제외합니다. 원본 점은 변경하지 않습니다.');
  const stats = make('p', '', { id: 'map3Stats' }); const regions = make('ol', '', { id: 'map3Regions' });
  const files = make('div', '', { class: 'map3-tools' });
  const save = button(files, 'map3Export', '새 주석 버전 EXPORT', () => {
    if (!editor) return;
    if (polygon.length) throw new Error('선택 중인 다각형을 추가하거나 취소한 뒤 내보내세요.');
    const payload = editor.exportVersion(); const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const a = make('a', '', { href: url, download: `map-annotations-${payload.version_id}.json` }); a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); exported = JSON.stringify(editor.regions); refresh(); status.textContent = '주석 버전을 파일로 내보냈습니다. 서버 저장·런타임 설치는 수행하지 않았습니다.';
  });
  const copyPurpose = make('select', '', { id: 'map3CopyPurpose', 'aria-label': '편집 복사본 목적' });
  copyPurpose.append(make('option', '표시용 복사본 · visibility', { value: 'visibility' }), make('option', '위치추정용 복사본 · localization', { value: 'localization' })); files.append(copyPurpose);
  const copyExport = button(files, 'map3CopyExport', '편집된 점군 COPY · JSON', () => {
    if (!editor) return;
    if (polygon.length) throw new Error('선택 중인 다각형을 추가하거나 취소한 뒤 복사본을 내보내세요.');
    const annotation = editor.exportVersion(); const result = editor.editedCopy(copyPurpose.value);
    const loaded = editor.original.length / 3;
    const complete = Number.isSafeInteger(source.source_points) && source.source_points === loaded;
    const payload = { schema: 'robot-dashboard.edited-cloud-copy', schema_version: 1,
      version_id: annotation.version_id, source: annotation.source, units: 'm', purpose: copyPurpose.value,
      runtime_installed: false, preview_only: !complete, source_scope: complete ? 'complete-normalized-snapshot' : 'sampled-or-unverified-preview',
      source_points: source.source_points ?? null, loaded_points: loaded, output_points: result.points.length / 3,
      note: 'XYZ-only copy of loaded normalized snapshot; original PCD attributes and precision are not preserved. No runtime installation.',
      regions: annotation.regions, points: result.points };
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' }); const url = URL.createObjectURL(blob);
    make('a', '', { href: url, download: `${complete ? 'edited-cloud-copy' : 'PREVIEW-ONLY-cloud-copy'}-${payload.version_id}.json` }).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = `${complete ? '로드된 전체 정규화 점군' : 'PREVIEW ONLY · 샘플 또는 완전성 미확인 점군'} 복사본을 내보냈습니다. 원본 PCD와 런타임은 변경되지 않았습니다.`;
  });
  const fileLabel = make('label', '주석 버전 IMPORT (최대 2 MB) '); const file = make('input', '', { id: 'map3Import', type: 'file', accept: '.json,application/json' }); fileLabel.append(file); files.append(fileLabel);
  file.addEventListener('change', async () => {
    const selected = file.files?.[0], target = editor; file.value = ''; if (!selected) return;
    try {
      if (!target) throw new Error('같은 원본 3D 지도를 먼저 불러오세요.');
      if (selected.size > 2 * 1024 * 1024) throw new Error('가져오기 파일은 2 MB 이하여야 합니다.');
      if (dirty() && !globalThis.confirm('현재 3D 주석을 가져온 버전으로 바꿀까요?')) return;
      const before = JSON.stringify([target.regions, polygon]);
      const data = await selected.text(); if (editor !== target || before !== JSON.stringify([target.regions, polygon])) throw new Error('읽는 동안 지도 선택이 바뀌었습니다. 다시 가져오세요.');
      target.importVersion(data); polygon = []; cachedPreview = null; refresh();
    } catch (e) { status.textContent = e.message; status.dataset.error = 'true'; }
  });
  root.append(safety, tools, history, help, canvas, stats, regions, files, status);
  function fit() {
    const p = editor.original; let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < p.length; i += 3) { minX = Math.min(minX, p[i]); maxX = Math.max(maxX, p[i]); minY = Math.min(minY, p[i + 1]); maxY = Math.max(maxY, p[i + 1]); }
    const scale = Math.min(1000 / Math.max(maxX - minX, 1), 440 / Math.max(maxY - minY, 1));
    view = { cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, scale };
  }
  const project = ([x, y]) => [550 + (x - view.cx) * view.scale, 270 - (y - view.cy) * view.scale];
  function draw() {
    const ctx = canvas.getContext('2d'); ctx.fillStyle = '#07151c'; ctx.fillRect(0, 0, 1100, 540); if (!editor || !view) return;
    ctx.strokeStyle = '#16313d'; ctx.lineWidth = 1; ctx.setLineDash([]);
    for (let x = 50; x < 1100; x += 100) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 540); ctx.stroke(); }
    for (let y = 70; y < 540; y += 100) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(1100, y); ctx.stroke(); }
    ctx.fillStyle = '#9ab8c7'; ctx.font = '14px sans-serif'; ctx.fillText(`XY · grid ${(100/view.scale).toFixed(2)} m · center (${view.cx.toFixed(2)}, ${view.cy.toFixed(2)}) · +Y ↑ / +X →`, 18, 24);
    const p = preview.checked ? cachedPreview.points : editor.original;
    const stride = Math.max(1, Math.ceil(p.length / 3 / 100000));
    ctx.fillStyle = '#79b9c8'; for (let i = 0; i < p.length; i += 3 * stride) { const [x,y] = project([p[i],p[i+1]]); ctx.fillRect(x,y,2,2); }
    for (const r of [...editor.regions, ...(polygon.length ? [{ polygon, kind: kind.value, pending: true }] : [])]) {
      ctx.beginPath(); r.polygon.forEach((p,i) => { const [x,y] = project(p); i ? ctx.lineTo(x,y) : ctx.moveTo(x,y); }); if (!r.pending) ctx.closePath();
      ctx.strokeStyle = { visibility: '#4acdf5', localization: '#c990ff', keepout: '#ffb65d' }[r.kind]; ctx.lineWidth = 2; ctx.setLineDash(r.pending ? [5,5] : []); ctx.stroke(); ctx.setLineDash([]);
      if (!r.pending) {
        ctx.fillStyle = `${ctx.strokeStyle}25`;
        if (r.selection === 'outside') {
          ctx.beginPath(); ctx.rect(0, 0, 1100, 540);
          r.polygon.forEach((p,i) => { const [x,y] = project(p); i ? ctx.lineTo(x,y) : ctx.moveTo(x,y); }); ctx.closePath(); ctx.fill('evenodd');
        } else ctx.fill();
      }
      for (const p of r.polygon) { const [x,y] = project(p); ctx.fillStyle = ctx.strokeStyle; ctx.fillRect(x-3,y-3,6,6); }
    }
  }
  function refresh() {
    if (editor && !cachedPreview) cachedPreview = editor.preview();
    add.disabled = !editor || polygon.length < 3; undo.disabled = !editor?.canUndo; redo.disabled = !editor?.canRedo; reset.disabled = !editor || !editor.regions.length; save.disabled = !editor; copyExport.disabled = !editor; copyPurpose.disabled = !editor; file.disabled = !editor; preview.disabled = !editor;
    copyExport.textContent = editor && source.source_points === cachedPreview.counts.total ? '편집된 점군 COPY · JSON' : 'PREVIEW ONLY 점군 COPY · JSON';
    stats.textContent = editor ? `SOURCE ${source.map_id} · REV ${source.revision} · FRAME ${source.frame_id} · ${cachedPreview.counts.total.toLocaleString()} loaded points${source.source_points > cachedPreview.counts.total ? ` / ${Number(source.source_points).toLocaleString()} source points (sampled)` : ''} · 숨김 ${cachedPreview.counts.visibility} / 위치추정 제외 ${cachedPreview.counts.localization} / 진입금지 ${cachedPreview.counts.keepout} · 선택 ${polygon.length} vertices · COPY ${Number.isSafeInteger(source.source_points) && source.source_points === cachedPreview.counts.total ? '전체 정규화 스냅샷' : 'PREVIEW ONLY'}` : 'NO 3D MAP';
    regions.replaceChildren(); for (const r of editor?.regions || []) regions.append(make('li', `${r.kind} · ${r.selection || 'inside'} · ${r.polygon.length} vertices · Z ${r.z_min}…${r.z_max} m`));
    status.dataset.error = 'false'; status.textContent = editor ? `${dirty() ? '내보내지 않은 초안 · ' : ''}위치추정 제외와 진입금지는 별도 주석입니다. 실제 주행·위치추정에 적용되지 않습니다. 표시 점은 최대 100,000개로 샘플링됩니다.` : '위의 저장 지도 목록에서 3D 지도를 선택한 뒤 불러오세요.'; draw();
  }
  canvas.addEventListener('click', (event) => run(() => { if (!view) return; if (polygon.length >= 256) throw new Error('다각형은 최대 256개 꼭짓점입니다.'); const rect = canvas.getBoundingClientRect(); const x = (event.clientX - rect.left) / rect.width * 1100, y = (event.clientY - rect.top) / rect.height * 540; polygon.push([view.cx + (x-550)/view.scale, view.cy - (y-270)/view.scale]); refresh(); }));
  canvas.addEventListener('keydown', (e) => { if (e.key === 'Escape') polygon = []; else if (e.key === 'Backspace') { e.preventDefault(); polygon.pop(); } else return; refresh(); });
  kind.addEventListener('change', draw);
  function setMode(value) {
    if (!['2d','3d'].includes(value)) throw new Error('Unknown map editor mode');
    modeValue = value; mode.value = value; two.hidden = value !== '2d'; root.hidden = value !== '3d';
    const state = panel.querySelector('#mapEditorState'); if (state) state.hidden = value !== '2d';
    notice.textContent = (dirty() || is2DDirty()) ? '저장하지 않은 초안을 각 모드에 유지합니다. 페이지를 닫기 전 저장 / 내보내세요.' : '선택한 모드만 표시합니다.';
    if (value === '2d') redraw2D(); else refresh();
  }
  mode.addEventListener('change', () => setMode(mode.value));
  globalThis.addEventListener('beforeunload', (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ''; } });
  refresh(); return { setMode, get mode() { return modeValue; } };
}
