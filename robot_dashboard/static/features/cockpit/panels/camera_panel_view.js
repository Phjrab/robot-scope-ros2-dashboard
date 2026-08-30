import { drawPerceptionOverlay } from '../../perception/result_overlay.js';

function metric(documentValue, label) {
  const item = documentValue.createElement('div');
  const name = documentValue.createElement('span');
  name.textContent = label;
  const value = documentValue.createElement('strong');
  value.textContent = '—';
  item.append(name, value);
  return { item, value };
}

export function createCameraPanelView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const root = options.root;
  if (!documentValue || !root) throw new TypeError('CameraPanelView requires document and root.');
  const shell = documentValue.createElement('div');
  shell.className = 'cockpit-camera-panel';
  const header = documentValue.createElement('div');
  header.className = 'cockpit-camera-statusline';
  const label = documentValue.createElement('strong');
  label.textContent = options.label;
  const state = documentValue.createElement('span');
  state.className = 'cockpit-camera-state';
  state.textContent = 'WAITING';
  header.append(label, state);
  const viewport = documentValue.createElement('div');
  viewport.className = 'cockpit-camera-viewport';
  const canvas = documentValue.createElement('canvas');
  canvas.width = 1;
  canvas.height = 1;
  canvas.setAttribute('aria-label', `${options.label} 영상`);
  const perceptionCanvas = documentValue.createElement('canvas');
  perceptionCanvas.className = 'cockpit-perception-overlay';
  perceptionCanvas.width = 1;
  perceptionCanvas.height = 1;
  perceptionCanvas.setAttribute('aria-label', `${options.label} shadow perception overlay`);
  const perceptionHud = documentValue.createElement('div');
  perceptionHud.className = 'cockpit-perception-hud';
  perceptionHud.dataset.state = 'offline';
  perceptionHud.textContent = 'SHADOW · OFFLINE';
  const overlay = documentValue.createElement('div');
  overlay.className = 'cockpit-camera-overlay';
  overlay.textContent = 'WAITING FOR FRAME';
  viewport.append(canvas, perceptionCanvas, perceptionHud, overlay);
  const metrics = documentValue.createElement('div');
  metrics.className = 'cockpit-camera-metrics';
  const fps = metric(documentValue, 'FPS');
  const age = metric(documentValue, 'AGE');
  const resolution = metric(documentValue, 'RES');
  const transport = metric(documentValue, 'TRANSPORT');
  const reconnect = metric(documentValue, 'RECONNECT');
  const wifi = metric(documentValue, 'ROBOT WI-FI');
  const source = metric(documentValue, 'SOURCE');
  const receive = metric(documentValue, 'TRANSPORT RX');
  const decode = metric(documentValue, 'DECODE');
  const clock = metric(documentValue, 'E2E LATENCY');
  metrics.append(
    fps.item,
    age.item,
    resolution.item,
    transport.item,
    reconnect.item,
    wifi.item,
    source.item,
    receive.item,
    decode.item,
    clock.item,
  );
  shell.append(header, viewport, metrics);
  root.append(shell);

  function clearFrame() {
    if (canvas.width !== 1 || canvas.height !== 1) {
      canvas.width = 1;
      canvas.height = 1;
    } else canvas.getContext('2d')?.clearRect(0, 0, 1, 1);
    if (perceptionCanvas.width !== 1 || perceptionCanvas.height !== 1) {
      perceptionCanvas.width = 1;
      perceptionCanvas.height = 1;
    } else perceptionCanvas.getContext('2d')?.clearRect(0, 0, 1, 1);
  }

  function renderFrame(frame) {
    const width = Number(frame.width || frame.canvas?.width || 0);
    const height = Number(frame.height || frame.canvas?.height || 0);
    if (!frame.canvas || width < 2 || height < 2) return false;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    canvas.getContext('2d').drawImage(frame.canvas, 0, 0, width, height);
    return true;
  }

  function render(projected) {
    state.textContent = projected.state;
    state.dataset.state = projected.state.toLowerCase();
    fps.value.textContent = projected.fps;
    age.value.textContent = projected.age;
    resolution.value.textContent = projected.resolution;
    transport.value.textContent = projected.transport;
    reconnect.value.textContent = projected.reconnect;
    wifi.value.textContent = projected.wifi;
    wifi.value.title = projected.clock;
    source.value.textContent = projected.source;
    source.value.title = projected.clock;
    receive.value.textContent = projected.receive;
    receive.value.title = projected.clock;
    decode.value.textContent = projected.decode;
    clock.value.textContent = projected.clock;
    overlay.textContent = projected.overlay;
    overlay.hidden = projected.state === 'LIVE';
    if (projected.state !== 'LIVE') clearFrame();
  }

  function renderPerception(projected) {
    drawPerceptionOverlay(perceptionCanvas, canvas, projected);
    perceptionHud.dataset.state = projected.state.toLowerCase();
    perceptionHud.textContent = `SHADOW · ${projected.state} · ${projected.model} · S${projected.sequence} · ${projected.age} · ${projected.fps} · ${projected.latency}`;
    perceptionHud.hidden = options.sourceId && options.sourceId !== 'realsense_color';
  }

  function destroy() {
    clearFrame();
    shell.remove();
  }

  return Object.freeze({ canvas, renderFrame, render, renderPerception, clearFrame, destroy });
}
