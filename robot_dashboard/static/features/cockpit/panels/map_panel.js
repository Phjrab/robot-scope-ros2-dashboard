const TYPE_COLORS = Object.freeze({ HOME: '#7df0b6', DOCK: '#ffc66d', POI: '#5dded8', INSPECTION_POINT: '#a28bff' });

function stateTone(status) {
  return status === 'LIVE' ? 'is-live' : status === 'CONFLICT' ? 'is-error' : status === 'STALE' ? 'is-warning' : 'is-waiting';
}

function ageLabel(value) {
  return Number.isFinite(value) ? `${Number(value).toFixed(2)} s` : '—';
}

export function createOccupancyRasterCache(options = {}) {
  const documentValue = options.document || globalThis.document;
  const decode = options.decodeBase64 || globalThis.atob?.bind(globalThis);
  let key = '';
  let raster = null;
  let decodes = 0;

  function get(map, navigationEngine) {
    if (!map) return null;
    const nextKey = `${map.id}:${map.revision}`;
    if (key === nextKey && raster) return raster;
    const geometry = navigationEngine.mapGeometry({ ...map, data_b64: undefined });
    const binary = decode?.(String(map.dataB64 || '')) || '';
    if (binary.length !== geometry.width * geometry.height) throw new Error('Occupancy grid cell count mismatch.');
    const canvas = documentValue.createElement('canvas');
    canvas.width = geometry.width; canvas.height = geometry.height;
    const context = canvas.getContext('2d');
    const image = context.createImageData(geometry.width, geometry.height);
    for (let y = 0; y < geometry.height; y += 1) {
      for (let x = 0; x < geometry.width; x += 1) {
        const input = y * geometry.width + x;
        const output = ((geometry.height - 1 - y) * geometry.width + x) * 4;
        const byte = binary.charCodeAt(input);
        const value = byte > 127 ? byte - 256 : byte;
        const color = value < 0 ? [30, 45, 41] : value >= 65 ? [8, 13, 12] : [185, 220, 207];
        image.data[output] = color[0]; image.data[output + 1] = color[1]; image.data[output + 2] = color[2]; image.data[output + 3] = 255;
      }
    }
    context.putImageData(image, 0, 0);
    key = nextKey; raster = Object.freeze({ key, canvas, geometry }); decodes += 1;
    return raster;
  }

  return Object.freeze({ get, reset: () => { key = ''; raster = null; }, diagnostics: () => Object.freeze({ key, decodes }) });
}

function createMapPanelView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const navigationEngine = options.navigationEngine;
  const root = documentValue.createElement('section');
  root.className = 'cockpit-map-panel';
  const header = documentValue.createElement('div'); header.className = 'cockpit-map-header';
  const status = documentValue.createElement('strong'); status.textContent = 'WAITING';
  const identity = documentValue.createElement('span'); identity.textContent = 'NO MAP';
  header.append(status, identity);
  const canvasWrap = documentValue.createElement('div'); canvasWrap.className = 'cockpit-map-canvas-wrap';
  const canvas = documentValue.createElement('canvas'); canvas.setAttribute('aria-label', 'Read-only occupancy map, localization pose, path and annotations');
  const warning = documentValue.createElement('div'); warning.className = 'cockpit-map-warning'; warning.hidden = true;
  canvasWrap.append(canvas, warning);
  const metrics = documentValue.createElement('div'); metrics.className = 'cockpit-map-metrics';
  const annotationList = documentValue.createElement('div'); annotationList.className = 'cockpit-map-annotations';
  root.append(header, canvasWrap, metrics, annotationList);
  options.host.append(root);
  const rasterCache = createOccupancyRasterCache({ document: documentValue });
  let current = null;
  let renderCount = 0;

  function resize() {
    const ratio = Math.min(Number(globalThis.devicePixelRatio) || 1, 2.5);
    const rect = canvas.getBoundingClientRect?.() || {};
    canvas.width = Math.max(1, Math.round((rect.width || canvas.clientWidth || 320) * ratio));
    canvas.height = Math.max(1, Math.round((rect.height || canvas.clientHeight || 220) * ratio));
    if (current) draw(current);
  }

  function polyline(context, layout, poses, color, dashed = false) {
    const projected = poses.map((pose) => { try { return navigationEngine.worldToCanvas(layout, pose); } catch (_) { return null; } }).filter((point) => point?.inside);
    if (projected.length < 2) return;
    context.save(); context.beginPath();
    projected.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
    context.strokeStyle = color; context.lineWidth = 2; if (dashed) context.setLineDash([7, 5]); context.stroke(); context.restore();
  }

  function poseMarker(context, layout, pose, color, label, dashed = false, radiusM = 0) {
    if (!pose) return;
    let point; try { point = navigationEngine.worldToCanvas(layout, pose); } catch (_) { return; }
    if (!point.inside) return;
    context.save(); context.strokeStyle = color; context.fillStyle = color; context.lineWidth = 2;
    if (dashed) context.setLineDash([5, 4]);
    const radius = radiusM > 0 ? Math.max(6, radiusM / layout.resolution * layout.scale) : 6;
    context.beginPath(); context.arc(point.x, point.y, radius, 0, Math.PI * 2); context.stroke();
    const length = Math.max(18, radius + 10);
    context.beginPath(); context.moveTo(point.x, point.y); context.lineTo(point.x + Math.cos(point.heading) * length, point.y + Math.sin(point.heading) * length); context.stroke();
    context.setLineDash([]); context.font = '10px ui-monospace, monospace'; context.fillText(label, point.x + 9, point.y - 9); context.restore();
  }

  function draw(state) {
    const context = canvas.getContext('2d');
    context.fillStyle = '#04100d'; context.fillRect(0, 0, canvas.width, canvas.height);
    if (!state.map || state.conflict) return;
    try {
      const raster = rasterCache.get(state.map, navigationEngine);
      const layout = navigationEngine.mapLayout({ ...state.map, origin: state.map.origin }, canvas.width, canvas.height, 0.045);
      context.imageSmoothingEnabled = false;
      context.drawImage(raster.canvas, layout.left, layout.top, layout.drawWidth, layout.drawHeight);
      polyline(context, layout, state.path, 'rgba(162,139,255,.9)', true);
      if (state.localization.fresh) polyline(context, layout, state.trail, 'rgba(125,240,182,.8)');
      for (const marker of state.markers) {
        const selected = marker.id === state.selectedAnnotationId;
        poseMarker(context, layout, marker.pose, TYPE_COLORS[marker.type] || '#5dded8', `${marker.type} · ${marker.name}`, !selected, selected ? 0.12 : 0);
      }
      poseMarker(context, layout, state.goal, '#a28bff', 'GOAL', true);
      poseMarker(context, layout, state.localization.fresh ? state.localization.pose : state.localization.lastPose,
        state.localization.fresh ? '#7df0b6' : '#ffc66d', state.localization.fresh ? 'ROBOT' : 'LAST KNOWN · STALE', !state.localization.fresh, state.robotRadius);
    } catch (error) {
      warning.hidden = false; warning.textContent = `MAP RENDER ERROR · ${String(error.message || error).slice(0, 160)}`;
    }
  }

  function render(state) {
    current = state; renderCount += 1;
    status.className = stateTone(state.status); status.textContent = state.status;
    identity.textContent = state.map ? `${state.map.name} · ${state.map.id.slice(0, 8)} · rev ${state.map.revision.slice(0, 10)}` : 'NO REVISION-PINNED MAP';
    warning.hidden = !state.conflict && state.status !== 'STALE';
    warning.textContent = state.conflict ? `REVISION CONFLICT · ${state.conflictReason}`
      : state.status === 'STALE' ? `LOCALIZATION ${state.localization.health} · ${state.localization.reason}` : '';
    const rows = [
      ['LOCALIZATION', `${state.localization.state} / ${state.localization.health}`],
      ['ODOMETRY AGE', ageLabel(state.localization.odometryAge)],
      ['TF AGE', ageLabel(state.localization.tfAge)],
      ['NAVIGATION', state.navigationActive ? 'ACTIVE · READ ONLY' : 'IDLE'],
      ['PATH / TRAIL', `${state.path.length} / ${state.trail.length}`],
    ];
    metrics.replaceChildren(...rows.map(([label, value]) => {
      const row = documentValue.createElement('div'); const span = documentValue.createElement('span'); const strong = documentValue.createElement('strong');
      span.textContent = label; strong.textContent = value; row.append(span, strong); return row;
    }));
    annotationList.replaceChildren(...state.markers.map((marker) => {
      const button = documentValue.createElement('button'); button.type = 'button'; button.dataset.mapAnnotationId = marker.id;
      button.className = marker.id === state.selectedAnnotationId ? 'is-selected' : '';
      button.textContent = `${marker.type} · ${marker.name}`; button.title = '3D overlay marker 선택'; return button;
    }));
    draw(state);
  }

  annotationList.addEventListener('click', (event) => {
    const button = event.target.closest?.('button[data-map-annotation-id]');
    if (button) options.onSelectAnnotation?.(button.dataset.mapAnnotationId);
  });
  const resizeObserver = typeof globalThis.ResizeObserver === 'function' ? new globalThis.ResizeObserver(resize) : null;
  resizeObserver?.observe(canvasWrap);
  resize();
  return Object.freeze({
    render, clear: () => { current = null; warning.hidden = false; warning.textContent = 'MAP PANEL INACTIVE'; }, resize,
    destroy: () => { resizeObserver?.disconnect(); root.remove(); rasterCache.reset(); },
    diagnostics: () => Object.freeze({ renderCount, ...rasterCache.diagnostics() }),
  });
}

export function createMapPanel(options = {}) {
  const mapState = options.mapState;
  if (!mapState) throw new TypeError('Map panel requires the shared Cockpit map store.');
  let view = null;
  let release = null;
  let active = false;
  let destroyed = false;
  let activations = 0;
  let deactivations = 0;

  function mount(host) {
    if (destroyed || view) return;
    view = (options.viewFactory || createMapPanelView)({ host, document: options.document, navigationEngine: options.navigationEngine, onSelectAnnotation: mapState.selectAnnotation });
  }
  function activate() {
    if (destroyed || active || !view) return;
    active = true; activations += 1;
    release = mapState.subscribe((state) => view?.render(state));
  }
  function deactivate() {
    if (!active) return;
    active = false; deactivations += 1; release?.(); release = null; view?.clear();
  }
  function destroy() {
    if (destroyed) return;
    deactivate(); destroyed = true; view?.destroy(); view = null;
  }
  function diagnostics() {
    return Object.freeze({ active, destroyed, activations, deactivations, subscribed: Boolean(release), view: view?.diagnostics?.() || null });
  }
  return Object.freeze({ mount, activate, deactivate, destroy, diagnostics });
}
