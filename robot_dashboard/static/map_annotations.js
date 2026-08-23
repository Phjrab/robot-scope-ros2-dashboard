(function mapAnnotationModule(global) {
  'use strict';

  const POINT_TYPES = Object.freeze(['POI', 'HOME', 'DOCK', 'INSPECTION_POINT']);
  const POLYGON_TYPES = Object.freeze(['KEEP_OUT', 'SLOW_ZONE', 'WAIT_ZONE']);
  const ALL_TYPES = Object.freeze([...POINT_TYPES, ...POLYGON_TYPES]);
  const TYPE_COLORS = Object.freeze({
    POI: '#5dded8',
    HOME: '#7df0b6',
    DOCK: '#ffc66d',
    INSPECTION_POINT: '#a28bff',
    KEEP_OUT: '#ff7a7f',
    SLOW_ZONE: '#ffc66d',
    WAIT_ZONE: '#5d9dde',
  });
  const HEX24 = /^[0-9a-f]{24}$/;
  const HEX64 = /^[0-9a-f]{64}$/;

  function finite(value, label) {
    const result = Number(value);
    if (!Number.isFinite(result)) throw new TypeError(`${label} must be finite`);
    return result;
  }

  function normalizeName(value) {
    const name = String(value || '').normalize('NFC').trim();
    if (!name || name.length > 64 || !/^[\p{L}\p{N} _\-.()]+$/u.test(name)) {
      throw new TypeError('annotation name is invalid');
    }
    return name;
  }

  function normalizeId(value) {
    if (value == null || value === '') return null;
    const id = String(value);
    if (!HEX24.test(id)) throw new TypeError('annotation id is invalid');
    return id;
  }

  function normalizePoint(value) {
    if (!value || !POINT_TYPES.includes(value.type)) throw new TypeError('point type is invalid');
    return Object.freeze({
      id: normalizeId(value.id),
      type: value.type,
      name: normalizeName(value.name),
      pose: Object.freeze({
        x: finite(value.pose?.x, 'point x'),
        y: finite(value.pose?.y, 'point y'),
        yaw: finite(value.pose?.yaw, 'point yaw'),
      }),
    });
  }

  function normalizePolygon(value) {
    if (!value || !POLYGON_TYPES.includes(value.type)) throw new TypeError('polygon type is invalid');
    if (!Array.isArray(value.vertices) || value.vertices.length < 3 || value.vertices.length > 64) {
      throw new TypeError('polygon vertex count is invalid');
    }
    return Object.freeze({
      id: normalizeId(value.id),
      type: value.type,
      name: normalizeName(value.name),
      vertices: Object.freeze(value.vertices.map((vertex) => Object.freeze({
        x: finite(vertex?.x, 'vertex x'),
        y: finite(vertex?.y, 'vertex y'),
      }))),
    });
  }

  function normalizeDocument(payload, mapId, mapRevision) {
    if (!payload || payload.schema_version !== 1) throw new TypeError('annotation schema is unavailable');
    if (String(payload.map_id || '') !== String(mapId || '')) throw new TypeError('annotation map id changed');
    if (String(payload.map_revision || '') !== String(mapRevision || '')) throw new TypeError('annotation map revision changed');
    const revision = String(payload.annotation_revision || payload.revision || '');
    if (!HEX64.test(revision)) throw new TypeError('annotation revision is invalid');
    const points = Array.isArray(payload.points) ? payload.points.map(normalizePoint) : [];
    const polygons = Array.isArray(payload.polygons) ? payload.polygons.map(normalizePolygon) : [];
    if (points.length > 64 || polygons.length > 32 || points.length + polygons.length > 96) {
      throw new TypeError('annotation count exceeds the UI limit');
    }
    return Object.freeze({
      schema_version: 1,
      map_id: String(mapId),
      map_revision: String(mapRevision),
      annotation_revision: revision,
      revision,
      points: Object.freeze(points),
      polygons: Object.freeze(polygons),
      exists: payload.exists === true,
    });
  }

  function editableCopy(document) {
    return {
      points: document.points.map((point) => ({
        id: point.id,
        type: point.type,
        name: point.name,
        pose: { ...point.pose },
      })),
      polygons: document.polygons.map((polygon) => ({
        id: polygon.id,
        type: polygon.type,
        name: polygon.name,
        vertices: polygon.vertices.map((vertex) => ({ ...vertex })),
      })),
    };
  }

  function requestBody(document, draft) {
    return {
      map_revision: document.map_revision,
      base_annotation_revision: document.annotation_revision,
      points: draft.points.map(normalizePoint).map((point) => ({
        id: point.id,
        type: point.type,
        name: point.name,
        pose: { ...point.pose },
      })),
      polygons: draft.polygons.map(normalizePolygon).map((polygon) => ({
        id: polygon.id,
        type: polygon.type,
        name: polygon.name,
        vertices: polygon.vertices.map((vertex) => ({ ...vertex })),
      })),
    };
  }

  function createFeature(options) {
    const {
      ui, api, showToast, setStatePill, navigationEngine,
      context, drawPoseMarker, drawMap, renderNavigationStatus,
      renderPoseSelection, discardNavigationPose, clearNavigationTool,
      applyNavigationResponse,
    } = options;
    let snapshot = null;
    let draft = null;
    let tool = '';
    let vertices = [];
    let pointer = null;
    let busy = false;
    let dirty = false;
    let generation = 0;
    let hasError = false;

    function displayDocument() {
      return draft || snapshot || { points: [], polygons: [] };
    }

    function editingAllowed() {
      const state = context();
      return Boolean(
        snapshot && draft && state.mapSnapshot &&
        !state.pipelineActive && !state.operationBusy && !busy
      );
    }

    function goalAllowed() {
      return Boolean(snapshot && !dirty && context().goalAllowed && !busy);
    }

    function render() {
      if (!ui.state) return;
      const editable = editingAllowed();
      const type = String(ui.type.value || 'POI');
      const polygon = POLYGON_TYPES.includes(type);
      const drawing = Boolean(tool);
      const annotationDocument = displayDocument();
      const items = [
        ...(annotationDocument.points || []).map((item, index) => ({ ...item, kind: 'point', index })),
        ...(annotationDocument.polygons || []).map((item, index) => ({ ...item, kind: 'polygon', index })),
      ];
      ui.message.classList.toggle('is-error', hasError);
      if (!snapshot) setStatePill(ui.state, 'waiting', 'NO DATA');
      else if (busy) setStatePill(ui.state, 'waiting', 'SAVING');
      else if (dirty) setStatePill(ui.state, 'waiting', 'UNSAVED');
      else setStatePill(ui.state, 'ok', `${items.length} ITEMS`);
      ui.type.disabled = !editable || drawing;
      ui.name.disabled = !editable || drawing;
      ui.draw.disabled = !editable;
      ui.draw.textContent = polygon
        ? (tool === 'zone' ? 'ZONE DRAWING' : 'START ZONE')
        : (tool === 'point' ? 'DRAWING POINT' : 'DRAW POINT');
      ui.draw.classList.toggle('is-active', drawing);
      ui.finish.disabled = tool !== 'zone' || vertices.length < 3;
      ui.cancel.disabled = !drawing;
      ui.discard.disabled = !dirty || busy;
      ui.save.disabled = !dirty || !editable || drawing;
      ui.list.replaceChildren();
      if (!items.length) {
        const empty = global.document.createElement('div');
        empty.className = 'map-annotation-empty';
        empty.textContent = snapshot
          ? '선택한 지도에 저장된 주석이 없습니다.'
          : '지도 주석을 불러오고 있습니다.';
        ui.list.append(empty);
        return;
      }
      for (const item of items) {
        const row = global.document.createElement('div');
        row.className = 'map-annotation-item';
        const swatch = global.document.createElement('span');
        swatch.className = 'map-annotation-swatch';
        swatch.style.color = TYPE_COLORS[item.type] || '#5dded8';
        swatch.style.background = 'currentColor';
        const detail = global.document.createElement('div');
        const title = global.document.createElement('strong');
        title.textContent = item.name;
        const meta = global.document.createElement('small');
        meta.textContent = item.kind === 'point'
          ? `${item.type} · X ${item.pose.x.toFixed(2)} · Y ${item.pose.y.toFixed(2)}`
          : `${item.type} · ${item.vertices.length} VERTICES · DISPLAY ONLY`;
        detail.append(title, meta);
        const actions = global.document.createElement('div');
        actions.className = 'map-annotation-item-actions';
        if (item.kind === 'point') {
          const go = global.document.createElement('button');
          go.type = 'button';
          go.textContent = 'GO';
          go.dataset.action = 'goal';
          go.dataset.id = item.id || '';
          go.disabled = !item.id || !goalAllowed();
          actions.append(go);
        }
        const remove = global.document.createElement('button');
        remove.type = 'button';
        remove.textContent = 'REMOVE';
        remove.dataset.action = 'remove';
        remove.dataset.kind = item.kind;
        remove.dataset.index = String(item.index);
        remove.disabled = !editable || drawing;
        actions.append(remove);
        row.append(swatch, detail, actions);
        ui.list.append(row);
      }
    }

    function draw(context2d, layout, ratio) {
      if (!layout) return;
      const annotationDocument = displayDocument();
      for (const polygon of annotationDocument.polygons || []) {
        const projected = polygon.vertices.map((vertex) => {
          try { return navigationEngine.worldToCanvas(layout, vertex); } catch (_) { return null; }
        }).filter((point) => point?.inside);
        if (projected.length !== polygon.vertices.length || projected.length < 3) continue;
        const color = TYPE_COLORS[polygon.type] || '#5d9dde';
        context2d.save();
        context2d.beginPath();
        projected.forEach((point, index) => index
          ? context2d.lineTo(point.x, point.y)
          : context2d.moveTo(point.x, point.y));
        context2d.closePath();
        context2d.fillStyle = `${color}22`;
        context2d.strokeStyle = color;
        context2d.lineWidth = 1.6 * ratio;
        context2d.setLineDash(polygon.type === 'KEEP_OUT' ? [5 * ratio, 3 * ratio] : []);
        context2d.fill();
        context2d.stroke();
        context2d.setLineDash([]);
        context2d.fillStyle = color;
        context2d.font = `${Math.max(8, 8 * ratio)}px ui-monospace, SFMono-Regular, Menlo, monospace`;
        context2d.fillText(polygon.name, projected[0].x + 5 * ratio, projected[0].y - 5 * ratio);
        context2d.restore();
      }
      if (vertices.length) {
        const projected = vertices.map((vertex) => navigationEngine.worldToCanvas(layout, vertex));
        context2d.save();
        context2d.beginPath();
        projected.forEach((point, index) => index
          ? context2d.lineTo(point.x, point.y)
          : context2d.moveTo(point.x, point.y));
        context2d.strokeStyle = '#ffffff';
        context2d.lineWidth = 1.5 * ratio;
        context2d.setLineDash([4 * ratio, 3 * ratio]);
        context2d.stroke();
        context2d.setLineDash([]);
        for (const point of projected) {
          context2d.beginPath();
          context2d.arc(point.x, point.y, 3 * ratio, 0, Math.PI * 2);
          context2d.fillStyle = '#ffffff';
          context2d.fill();
        }
        context2d.restore();
      }
      for (const point of annotationDocument.points || []) {
        drawPoseMarker(
          context2d, layout, point.pose,
          TYPE_COLORS[point.type] || '#5dded8',
          `${point.type} · ${point.name}`, ratio, point.id == null,
        );
      }
    }

    function reset(message = '저장된 2D 지도를 선택하세요.') {
      generation += 1;
      snapshot = null;
      draft = null;
      tool = '';
      vertices = [];
      pointer = null;
      dirty = false;
      busy = false;
      hasError = false;
      ui.message.textContent = message;
      render();
    }

    async function load(meta, mapGeneration) {
      if (!meta?.id || !meta?.revision) {
        reset('지도 주석 기능을 불러올 수 없습니다.');
        return false;
      }
      const requestGeneration = ++generation;
      snapshot = null;
      draft = null;
      dirty = false;
      hasError = false;
      tool = '';
      vertices = [];
      render();
      try {
        const payload = await api(
          meta.annotations_url || `/api/v1/saved-maps/${encodeURIComponent(meta.id)}/annotations`,
        );
        const state = context();
        if (
          requestGeneration !== generation ||
          mapGeneration !== state.mapLoadGeneration ||
          state.selectedMap?.id !== meta.id
        ) return false;
        snapshot = normalizeDocument(payload, meta.id, meta.revision);
        draft = editableCopy(snapshot);
        hasError = false;
        ui.message.textContent = snapshot.exists
          ? `주석 revision ${snapshot.annotation_revision.slice(0, 10)} · 원본 지도와 별도 저장`
          : '아직 저장된 주석이 없습니다. 지도 위에 첫 항목을 추가하세요.';
        render();
        drawMap();
        return true;
      } catch (error) {
        if (requestGeneration !== generation) return false;
        snapshot = null;
        draft = null;
        hasError = true;
        ui.message.textContent = `주석을 불러오지 못했습니다: ${error.message}`;
        render();
        return false;
      }
    }

    function selection() {
      const type = String(ui.type.value || '');
      if (!ALL_TYPES.includes(type)) throw new Error('주석 종류를 다시 선택하세요.');
      return { type, name: normalizeName(ui.name.value) };
    }

    function startDrawing() {
      if (!editingAllowed()) {
        showToast('Nav2를 STOP하고 편집 가능한 2D 지도를 선택하세요.', true);
        return;
      }
      let selected;
      try { selected = selection(); } catch (error) { showToast(error.message, true); return; }
      clearNavigationTool();
      discardNavigationPose(false);
      vertices = [];
      pointer = null;
      tool = POLYGON_TYPES.includes(selected.type) ? 'zone' : 'point';
      ui.hint.classList.remove('is-error');
      ui.hint.textContent = tool === 'zone'
        ? '영역 꼭짓점을 차례로 누른 뒤 FINISH ZONE을 선택하세요.'
        : 'POI 위치를 누르고 진행 방향으로 드래그하세요.';
      renderPoseSelection();
      render();
      drawMap();
    }

    function cancelDrawing({ render: shouldRender = true } = {}) {
      tool = '';
      vertices = [];
      pointer = null;
      ui.canvas.classList.remove('is-dragging');
      ui.hint.classList.remove('is-error');
      if (shouldRender) {
        render();
        drawMap();
        renderNavigationStatus();
      }
    }

    function beginPointer(event, point) {
      const state = context();
      if (event.button !== 0 || !tool || !state.mapLayout || !editingAllowed()) return false;
      let occupancy = null;
      try { occupancy = point && navigationEngine.occupancyCellAtCanvas(state.mapLayout, state.mapCells, point); } catch (_) {}
      if (!occupancy?.inside || (tool === 'point' && !occupancy.free)) {
        ui.hint.textContent = !occupancy?.inside
          ? '지도 경계 안에서 주석 위치를 선택하세요.'
          : 'POI·HOME·DOCK은 확인된 빈 셀에만 저장할 수 있습니다.';
        ui.hint.classList.add('is-error');
        return true;
      }
      event.preventDefault();
      ui.hint.classList.remove('is-error');
      if (tool === 'zone') {
        const world = navigationEngine.canvasToWorld(state.mapLayout, point);
        if (world && vertices.length < 64) vertices.push({ x: world.x, y: world.y });
        ui.hint.textContent = `${vertices.length}개 꼭짓점 · 최소 3개 필요`;
        render();
        drawMap();
        return true;
      }
      try { ui.canvas.setPointerCapture(event.pointerId); } catch (_) {}
      pointer = { id: event.pointerId, start: point, end: point };
      ui.canvas.classList.add('is-dragging');
      return true;
    }

    function movePointer(event, point) {
      if (!pointer || pointer.id !== event.pointerId) return false;
      if (point) pointer.end = point;
      event.preventDefault();
      return true;
    }

    function finishPointer(event, point) {
      if (!pointer || pointer.id !== event.pointerId) return false;
      if (point) pointer.end = point;
      const pose = navigationEngine.poseFromDrag(
        context().mapLayout, pointer.start, pointer.end, 0,
      );
      pointer = null;
      ui.canvas.classList.remove('is-dragging');
      try { ui.canvas.releasePointerCapture(event.pointerId); } catch (_) {}
      if (!pose || !draft) return true;
      try {
        const selected = selection();
        if (selected.type === 'HOME' && draft.points.some((item) => item.type === 'HOME')) {
          throw new Error('HOME은 지도마다 하나만 저장할 수 있습니다. 기존 HOME을 먼저 제거하세요.');
        }
        draft.points.push({ id: null, type: selected.type, name: selected.name, pose });
        dirty = true;
        hasError = false;
        ui.name.value = '';
        ui.message.textContent = `${selected.type}을(를) 추가했습니다. SAVE ANNOTATIONS로 확정하세요.`;
        cancelDrawing({ render: false });
        render();
        drawMap();
      } catch (error) { showToast(error.message, true); }
      return true;
    }

    function finishZone() {
      if (tool !== 'zone' || vertices.length < 3 || !draft) return;
      try {
        const selected = selection();
        draft.polygons.push({
          id: null, type: selected.type, name: selected.name,
          vertices: vertices.map((vertex) => ({ ...vertex })),
        });
        dirty = true;
        hasError = false;
        ui.name.value = '';
        ui.message.textContent = `${selected.type}을(를) 추가했습니다. 현재는 표시·미션 의미만 가지며 costmap은 바꾸지 않습니다.`;
        cancelDrawing({ render: false });
        render();
        drawMap();
      } catch (error) { showToast(error.message, true); }
    }

    function discardChanges() {
      if (!snapshot || busy) return;
      draft = editableCopy(snapshot);
      dirty = false;
      hasError = false;
      cancelDrawing({ render: false });
      ui.message.textContent = '저장되지 않은 주석 변경을 버렸습니다.';
      render();
      drawMap();
    }

    async function save() {
      if (!editingAllowed() || !dirty) return;
      let body;
      try { body = requestBody(snapshot, draft); } catch (error) {
        showToast(`주석 검증 실패: ${error.message}`, true);
        return;
      }
      busy = true;
      render();
      try {
        const payload = await api(`/api/v1/saved-maps/${encodeURIComponent(snapshot.map_id)}/annotations`, {
          method: 'PATCH', body: JSON.stringify(body),
        });
        snapshot = normalizeDocument(payload, snapshot.map_id, snapshot.map_revision);
        draft = editableCopy(snapshot);
        dirty = false;
        hasError = false;
        ui.message.textContent = `주석을 원자적으로 저장했습니다 · revision ${snapshot.annotation_revision.slice(0, 10)}`;
        showToast('지도 주석을 저장했습니다.');
      } catch (error) {
        hasError = true;
        ui.message.textContent = `주석 저장 실패: ${error.message}`;
        showToast('지도 또는 주석 revision이 바뀌었을 수 있습니다. 지도를 다시 불러오세요.', true);
      } finally {
        busy = false;
        render();
        drawMap();
      }
    }

    async function sendGoal(annotationId) {
      if (!goalAllowed() || !HEX24.test(annotationId || '')) return;
      const point = snapshot.points.find((item) => item.id === annotationId);
      if (!point || !global.confirm(`${point.type} “${point.name}” 위치로 이동할까요? 주변을 비우고 물리 리모컨을 손에 드세요.`)) return;
      busy = true;
      render();
      try {
        const response = await api('/api/v1/navigation/goal/annotation', {
          method: 'POST',
          body: JSON.stringify({
            map_id: snapshot.map_id,
            map_revision: snapshot.map_revision,
            annotation_revision: snapshot.annotation_revision,
            annotation_id: annotationId,
            confirmed: true,
          }),
        });
        applyNavigationResponse(response);
        showToast(`${point.name} 목표를 전송했습니다.`);
        renderNavigationStatus();
      } catch (error) {
        showToast(`주석 목표 전송 실패: ${error.message}`, true);
      } finally {
        busy = false;
        render();
      }
    }

    ui.type.addEventListener('change', () => {
      cancelDrawing({ render: false });
      render();
      drawMap();
    });
    ui.draw.addEventListener('click', startDrawing);
    ui.finish.addEventListener('click', finishZone);
    ui.cancel.addEventListener('click', () => cancelDrawing());
    ui.discard.addEventListener('click', discardChanges);
    ui.save.addEventListener('click', save);
    ui.list.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      if (button.dataset.action === 'goal') {
        void sendGoal(button.dataset.id || '');
        return;
      }
      if (button.dataset.action !== 'remove' || !editingAllowed() || !draft) return;
      const index = Number(button.dataset.index);
      const collection = button.dataset.kind === 'polygon' ? draft.polygons : draft.points;
      if (!Number.isInteger(index) || index < 0 || index >= collection.length) return;
      collection.splice(index, 1);
      dirty = true;
      hasError = false;
      ui.message.textContent = '주석을 제거했습니다. SAVE ANNOTATIONS로 확정하세요.';
      render();
      drawMap();
    });

    return Object.freeze({
      reset, load, draw, render, cancelDrawing, beginPointer, movePointer,
      finishPointer,
      hasDirty: () => dirty,
      hasActiveTool: () => Boolean(tool),
    });
  }

  global.RobotMapAnnotations = Object.freeze({
    POINT_TYPES,
    POLYGON_TYPES,
    ALL_TYPES,
    TYPE_COLORS,
    normalizeName,
    normalizeDocument,
    editableCopy,
    requestBody,
    createFeature,
    isPointType: (type) => POINT_TYPES.includes(type),
    isPolygonType: (type) => POLYGON_TYPES.includes(type),
  });
})(window);
