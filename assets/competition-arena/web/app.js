import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const $ = (id) => document.getElementById(id);
const host = $('canvas-host');
const layerState = { floor: true, walls: true, obstacles: true, labels: true, grid: true };
const state = { loaded: false, metadataLoaded: false, error: null, mode: 'perspective', meshes: [], metadata: null };
const scene = new THREE.Scene();
scene.background = new THREE.Color('#edf1e8');
const perspective = new THREE.PerspectiveCamera(38, 1, 0.05, 2000);
const top = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.05, 2000);
let camera = perspective;
let controls;
let renderer;
let model;
let grid;
let selectionBox;
let objectIndex = new Map();
const modelCenter = new THREE.Vector3();
const modelSize = new THREE.Vector3(20, 2, 20);
const bounds = new THREE.Box3();
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let pointerDown;

const formatNumber = (value) => Number.isFinite(value) ? Number(value.toFixed(3)).toLocaleString('ko-KR') : String(value);
const formatValue = (value) => Array.isArray(value) ? value.map(formatValue).join(' × ') : typeof value === 'number' ? formatNumber(value) : typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? '—');
const estimated = (item) => /estimat|assum|infer|approx|unverified|recon|unknown|derived|mixed|추정/i.test(String(item.status ?? item.evidence ?? ''));
const textElement = (tag, text, className = '') => { const element = document.createElement(tag); element.textContent = text; if (className) element.className = className; return element; };

function fail(message, error) {
  state.error = message;
  $('load-status').textContent = '모델을 불러오지 못했습니다';
  document.querySelector('.model-status').classList.add('failed');
  $('error-message').hidden = false;
  $('error-message').textContent = message;
  console.error(message, error ?? '');
}

function categoryOf(object) {
  const category = String(object.userData.category ?? '').toLowerCase();
  const name = object.name.toLowerCase();
  const categoryMap = { floor: 'floor', zone: 'floor', ground: 'floor', wall: 'walls', boundary: 'walls', ramp: 'obstacles', stair: 'obstacles', platform: 'obstacles', signal: 'obstacles', obstacle: 'obstacles', label: 'labels', marking: 'labels', dimension: 'labels', annotation: 'labels' };
  if (categoryMap[category]) return categoryMap[category];
  if (/^wall_|wall|boundary/.test(name) || /wall|boundary/.test(category)) return 'walls';
  if (/^(label_|marking_|dimension_|annotation_)/.test(name) || /label|marking|dimension|annotation/.test(category)) return 'labels';
  if (/^(floor_|zone_|ground_)/.test(name) || /floor|zone|ground/.test(category)) return 'floor';
  if (/^(ramp_|stair_|signal_|obstacle_|cone_|barrier_)/.test(name) || /ramp|stair|signal|obstacle|cone/.test(category)) return 'obstacles';
  if (object.parent && object.parent !== model && object.parent.name) return categoryOf(object.parent);
  return 'obstacles';
}

function applyLayers() {
  for (const mesh of state.meshes) mesh.visible = layerState[mesh.userData.previewLayer] !== false;
  if (grid) grid.visible = layerState.grid;
  clearSelection();
  render();
}

function clearSelection() {
  if (selectionBox) { scene.remove(selectionBox); selectionBox.geometry.dispose(); selectionBox.material.dispose(); selectionBox = null; }
  $('selection-name').textContent = '모델의 객체를 클릭하세요';
  $('selection-details').textContent = '선택한 객체의 원본 좌표와 모델 외접상자를 확인할 수 있습니다.';
  render();
}

function selectMesh(mesh) {
  clearSelection();
  const objectBounds = new THREE.Box3().setFromObject(mesh);
  const size = objectBounds.getSize(new THREE.Vector3());
  const center = objectBounds.getCenter(new THREE.Vector3());
  selectionBox = new THREE.Box3Helper(objectBounds, 0xbf7131);
  selectionBox.material.depthTest = false;
  selectionBox.renderOrder = 100;
  scene.add(selectionBox);
  $('selection-name').textContent = mesh.name || '이름 없는 객체';
  const details = $('selection-details');
  details.replaceChildren();
  const source = objectIndex.get(mesh.name) ?? objectIndex.get(mesh.userData.id);
  if (source) {
    details.append(textElement('p', `${source.status ?? '상태 미기재'} · ${source.category ?? mesh.userData.previewLayer}`));
    if (source.dimensions_m) details.append(textElement('p', `원본 치수 X/Y/Z: ${formatValue(source.dimensions_m)} m`, 'selection-values'));
    if (source.uncertainty) details.append(textElement('p', `불확실성: ${formatValue(source.uncertainty)}`));
  }
  details.append(textElement('p', `외접상자 X/Y/Z: ${formatNumber(size.x)} / ${formatNumber(size.z)} / ${formatNumber(size.y)} m`, 'selection-values'));
  details.append(textElement('p', `외접상자 중심: (${formatNumber(center.x)}, ${formatNumber(-center.z)}, ${formatNumber(center.y)}) m`, 'selection-values'));
  details.append(textElement('p', '위 값은 원본 Z-up 기준이며, 실측값이 아닙니다.'));
  render();
}

function createControls() {
  if (controls) controls.dispose();
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.enableRotate = state.mode !== 'top';
  controls.screenSpacePanning = true;
  controls.minDistance = Math.max(0.3, modelSize.length() * 0.015);
  controls.maxDistance = modelSize.length() * 8;
  controls.maxPolarAngle = state.mode === 'top' ? Math.PI : Math.PI * 0.48;
  controls.minZoom = 0.15;
  controls.maxZoom = 30;
  controls.target.copy(modelCenter);
  controls.addEventListener('change', render);
}

function fitView(mode = state.mode) {
  if (!renderer) return;
  state.mode = mode;
  camera = mode === 'top' ? top : perspective;
  const span = Math.max(modelSize.x, modelSize.z, 1);
  if (mode === 'top') {
    camera.up.set(0, 0, -1);
    camera.position.set(modelCenter.x, bounds.max.y + span * 2, modelCenter.z);
    camera.zoom = 1;
  } else {
    camera.up.set(0, 1, 0);
    const verticalFov = THREE.MathUtils.degToRad(perspective.fov);
    const aspect = Math.max(host.clientWidth / host.clientHeight, 0.2);
    const limitingFov = aspect < 1 ? 2 * Math.atan(Math.tan(verticalFov / 2) * aspect) : verticalFov;
    const distance = Math.max(modelSize.length(), 1) * 0.57 / Math.sin(limitingFov / 2);
    camera.position.copy(modelCenter).add(new THREE.Vector3(0.72, 1.0, 0.87).normalize().multiplyScalar(distance));
  }
  camera.lookAt(modelCenter);
  createControls();
  resize();
  controls.update();
  $('perspective').setAttribute('aria-pressed', String(mode === 'perspective'));
  $('top').setAttribute('aria-pressed', String(mode === 'top'));
  $('view-caption').textContent = mode === 'top' ? '평면 · 정사영' : '입체 · 원근 투영';
  document.querySelector('.gesture-caption').firstChild.textContent = mode === 'top' ? '드래그 이동 · 스크롤 확대' : '드래그 회전 · 우클릭 이동 · 스크롤 확대';
  if (mode === 'top') controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
  render();
}

function resize() {
  if (!renderer) return;
  const width = host.clientWidth;
  const height = host.clientHeight;
  if (!width || !height) return;
  renderer.setSize(width, height, false);
  perspective.aspect = width / height;
  perspective.updateProjectionMatrix();
  const halfHeight = Math.max(modelSize.z / 2, modelSize.x / (2 * perspective.aspect), 0.5) * 1.22;
  top.top = halfHeight;
  top.bottom = -halfHeight;
  top.right = halfHeight * perspective.aspect;
  top.left = -top.right;
  top.updateProjectionMatrix();
  render();
}

function render() { if (renderer) renderer.render(scene, camera); }

function makeMetadataTable(entries) {
  const table = document.createElement('table');
  table.className = 'metadata-table';
  const tbody = document.createElement('tbody');
  for (const [key, value] of entries) {
    const row = document.createElement('tr');
    row.append(textElement('th', key), textElement('td', formatValue(value)));
    tbody.append(row);
  }
  table.append(tbody);
  return table;
}

function makeSection(title) {
  const section = document.createElement('section');
  section.className = 'metadata-section';
  section.append(textElement('h3', title));
  return section;
}

function showMetadata(data) {
  state.metadata = data;
  state.metadataLoaded = true;
  objectIndex = new Map();
  for (const object of data.objects ?? []) {
    if (object.name) objectIndex.set(object.name, object);
    if (object.id) objectIndex.set(object.id, object);
  }
  $('raw-json').textContent = JSON.stringify(data, null, 2);
  const dimensions = Array.isArray(data.dimensions) ? data.dimensions : [];
  const summary = $('dimension-summary');
  summary.replaceChildren();
  for (const item of dimensions.slice(0, 5)) {
    const row = document.createElement('div'); row.className = 'dimension-row';
    row.append(textElement('span', item.label ?? item.id), textElement('strong', `${formatValue(item.value_m ?? item.value)}${item.value_m !== undefined ? ' m' : ''}${estimated(item) ? ' †' : ''}`, estimated(item) ? 'estimated-value' : ''));
    summary.append(row);
  }
  if (dimensions.length === 0) summary.append(textElement('p', '치수 목록은 전체 원본 JSON에서 확인하세요.', 'quiet'));
  const assumptions = Array.isArray(data.assumptions) ? data.assumptions : [];
  const count = dimensions.filter(estimated).length + assumptions.length;
  if (count) summary.append(textElement('p', `† 추정·계산 치수 ${dimensions.filter(estimated).length}개 · 가정 ${assumptions.length}개`, 'quiet'));
  const view = $('metadata-view'); view.replaceChildren();
  if (data.coordinate_system) {
    const section = makeSection('좌표계 · 단위');
    section.append(makeMetadataTable(Object.entries(data.coordinate_system))); view.append(section);
  }
  if (dimensions.length) {
    const section = makeSection(`명시 / 추정 치수 전체 (${dimensions.length})`);
    dimensions.forEach((item, index) => {
      section.append(textElement('h3', `${String(index + 1).padStart(2, '0')}. ${item.label ?? item.id}`));
      section.append(makeMetadataTable(Object.entries(item)));
    });
    view.append(section);
  }
  if (assumptions.length) {
    const section = makeSection(`재구성 가정 전체 (${assumptions.length})`);
    assumptions.forEach((item, index) => {
      section.append(textElement('h3', `${String(index + 1).padStart(2, '0')}. ${item.item ?? item.id ?? '가정'}`));
      section.append(makeMetadataTable(Object.entries(item)));
    });
    view.append(section);
  }
  if (data.objects?.length) {
    const section = makeSection(`모든 객체의 치수 · 위치 (${data.objects.length})`);
    section.append(textElement('p', '세부 위치, 치수, 회전, 추정 상태를 빠짐없이 제공합니다. 객체를 펼쳐 확인하세요.'));
    for (const item of data.objects) {
      const details = document.createElement('details'); details.className = 'raw-details';
      details.append(textElement('summary', `${item.name ?? item.id} · ${item.status ?? ''}`), makeMetadataTable(Object.entries(item)));
      section.append(details);
    }
    view.append(section);
  }
  if (data.sources) { const section = makeSection('입력 자료'); section.append(makeMetadataTable(Array.isArray(data.sources) ? data.sources.map((x, i) => [`자료 ${i + 1}`, x]) : Object.entries(data.sources))); view.append(section); }
  if (data.validation) { const section = makeSection('검증 상태'); section.append(makeMetadataTable(Object.entries(data.validation))); view.append(section); }
}

async function start() {
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.domElement.setAttribute('aria-label', '마우스나 터치로 조작할 수 있는 경기장 3D 모델');
    host.append(renderer.domElement);
  } catch (error) {
    fail('WebGL을 시작하지 못했습니다.\n최신 브라우저에서 하드웨어 가속을 켠 뒤 다시 여세요.', error); return;
  }
  scene.add(new THREE.HemisphereLight(0xfffff4, 0x87927b, 2.3));
  const sun = new THREE.DirectionalLight(0xfff5dd, 3.0);
  sun.position.set(-20, 40, 15);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0002;
  sun.shadow.normalBias = 0.025;
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xe2efff, 1.0); fill.position.set(20, 15, -20); scene.add(fill);
  new ResizeObserver(resize).observe(host);
  resize();
  fetch('../arena.json').then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); }).then(showMetadata).catch((error) => {
    $('dimension-summary').textContent = '치수 자료를 읽을 수 없습니다. arena.json의 위치를 확인하세요.';
    $('raw-json').textContent = String(error);
    $('metadata-view').textContent = 'arena.json을 읽지 못했습니다. 치수와 가정은 검증되지 않았습니다.';
    console.error('Metadata load failed:', error);
  });
  try {
    const gltf = await new GLTFLoader().loadAsync('../arena.glb');
    model = gltf.scene;
    model.name = 'competition_arena';
    scene.add(model);
    model.updateMatrixWorld(true);
    model.traverse((object) => {
      if (!object.isMesh) return;
      object.userData.previewLayer = categoryOf(object);
      object.castShadow = object.userData.previewLayer !== 'labels';
      object.receiveShadow = true;
      state.meshes.push(object);
    });
    if (!state.meshes.length) throw new Error('GLB contains no meshes');
    const swatchNames = { floor: 'floor', walls: 'wall', obstacles: 'obstacle', labels: 'label' };
    for (const [layer, swatchName] of Object.entries(swatchNames)) {
      const sample = state.meshes.find((mesh) => mesh.userData.previewLayer === layer);
      const material = Array.isArray(sample?.material) ? sample.material[0] : sample?.material;
      if (material?.color) document.querySelector(`.swatch.${swatchName}`).style.backgroundColor = `#${material.color.getHexString()}`;
    }
    // The camera bounds intentionally omit decorative label meshes where possible.
    const physicalMeshes = state.meshes.filter((mesh) => mesh.userData.previewLayer !== 'labels');
    for (const mesh of physicalMeshes.length ? physicalMeshes : state.meshes) bounds.union(new THREE.Box3().setFromObject(mesh));
    bounds.getCenter(modelCenter); bounds.getSize(modelSize);
    const span = Math.max(modelSize.x, modelSize.z, 1);
    const gridSize = Math.ceil(span * 1.5 / 2) * 2;
    grid = new THREE.GridHelper(gridSize, gridSize, 0xc5cfba, 0xd7dfce);
    grid.position.set(Math.round(modelCenter.x), bounds.min.y - 0.015, Math.round(modelCenter.z));
    scene.add(grid);
    const backdrop = new THREE.Mesh(new THREE.PlaneGeometry(gridSize * 4, gridSize * 4), new THREE.ShadowMaterial({ color: 0x7b8d6b, opacity: 0.15 }));
    backdrop.rotation.x = -Math.PI / 2;
    backdrop.position.set(modelCenter.x, bounds.min.y - 0.025, modelCenter.z);
    backdrop.receiveShadow = true; scene.add(backdrop);
    sun.position.set(modelCenter.x - span, span * 1.6, modelCenter.z + span * 0.8);
    sun.target.position.copy(modelCenter); scene.add(sun.target);
    Object.assign(sun.shadow.camera, { left: -span, right: span, top: span, bottom: -span, near: 0.1, far: span * 5 });
    sun.shadow.camera.updateProjectionMatrix();
    state.loaded = true;
    $('load-status').textContent = 'arena.glb 불러오기 완료';
    document.querySelector('.model-status').classList.add('ready');
    $('mesh-count').textContent = `${state.meshes.length} meshes`;
    fitView('perspective');
    applyLayers();
  } catch (error) {
    fail('arena.glb를 불러올 수 없습니다.\ncompetition_arena 폴더에서 HTTP 서버를 실행한 뒤 /web/ 주소로 여세요.\n파일을 직접 더블클릭하는 방식은 지원하지 않습니다.', error);
  }
  renderer.domElement.addEventListener('pointerdown', (event) => { pointerDown = { x: event.clientX, y: event.clientY, time: performance.now(), button: event.button }; });
  renderer.domElement.addEventListener('pointerup', (event) => {
    if (!state.loaded || !pointerDown || pointerDown.button !== 0 || Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 5 || performance.now() - pointerDown.time > 600) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(state.meshes.filter((mesh) => mesh.visible), false)[0];
    if (hit) selectMesh(hit.object); else clearSelection();
  });
}

$('perspective').addEventListener('click', () => state.loaded && fitView('perspective'));
$('top').addEventListener('click', () => state.loaded && fitView('top'));
$('reset').addEventListener('click', () => {
  if (!state.loaded) return;
  for (const input of document.querySelectorAll('[data-layer]')) { input.checked = true; layerState[input.dataset.layer] = true; }
  applyLayers(); fitView('perspective');
});
for (const input of document.querySelectorAll('[data-layer]')) input.addEventListener('change', () => { layerState[input.dataset.layer] = input.checked; applyLayers(); });
$('clear-selection').addEventListener('click', clearSelection);
$('show-details').addEventListener('click', () => $('details-dialog').showModal());
$('close-details').addEventListener('click', () => $('details-dialog').close());
$('details-dialog').addEventListener('click', (event) => { if (event.target === $('details-dialog')) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
window.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !$('details-dialog').open) clearSelection(); });
// Read-only diagnostics for smoke tests and integration debugging; no remote requests.
window.__arenaPreview = {
  get loaded() { return state.loaded; },
  get metadataLoaded() { return state.metadataLoaded; },
  get error() { return state.error; },
  get mode() { return state.mode; },
  get meshCount() { return state.meshes.length; },
  get bounds() { return { min: bounds.min.toArray(), max: bounds.max.toArray(), size: modelSize.toArray() }; },
  get layers() { return Object.fromEntries(Object.keys(layerState).map((key) => [key, { enabled: layerState[key], meshes: state.meshes.filter((mesh) => mesh.userData.previewLayer === key).length, visible: state.meshes.filter((mesh) => mesh.userData.previewLayer === key && mesh.visible).length }])); },
  get renderInfo() { return renderer ? { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles } : null; },
  get objectNames() { return state.meshes.map((mesh) => mesh.name); }
};
start();
