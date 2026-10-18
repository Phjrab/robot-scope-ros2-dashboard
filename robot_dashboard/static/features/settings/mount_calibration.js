import { api } from '../../core/api.js';

const instances = new WeakMap();
const endpoint = '/api/v1/settings/mount-calibration';
const savedEndpoint = '/api/v1/slam/depth/samples';

// This Settings feature is import-only. Initializing it never acquires a camera,
// constructs demo depth arrays, applies a transform, or starts a robot service.
export function initializeMountCalibrationFeature(options = {}) {
  const document = options.document || globalThis.document;
  const root = document.getElementById('mount-calibration-panel');
  if (!root) return null;
  if (instances.has(root)) return instances.get(root);
  const request = options.api || api;
  const fetchArtifact = options.fetch || globalThis.fetch;
  const $ = (id) => document.getElementById(`mount-calibration-${id}`);
  const listeners = [];
  let destroyed = false;
  let statusController = null;
  let catalogueController = null;
  let importController = null;
  let catalogueVersion = 0;
  let downloadUrl = '';
  const on = (element, event, handler) => {
    element.addEventListener(event, handler);
    listeners.push(() => element.removeEventListener(event, handler));
  };
  const state = { samples: [], selectedId: null, referenceId: null, result: null, version: 0, controller: null, busy: false, heatmaps: new Map(), saved: [], savedSelection: new Set(), savedEvidence: new Map(), importing: false, imageView: true };
  const checks = ['stationary-check', 'wall-check', 'pitch-check'];
  const maxFileBytes = 30 * 1024 * 1024;
  const maxPoints = 100;
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  const validDepth = (value) => finite(value) && value >= 0.1 && value <= 30;
  const selected = () => state.samples.find((sample) => sample.id === state.selectedId);
  const allSynthetic = () => state.samples.length > 0 && state.samples.every((sample) => sample.metadata.synthetic === true);
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };
  const pretty = (number, digits = 3) => finite(number) ? number.toFixed(digits) : '—';
  const angleText = (angle) => finite(angle) ? `${angle > 0 ? '+' : ''}${angle.toFixed(2)}°` : '추정 보류';

  function notify(message, kind = '') {
    const notice = $('notice');
    notice.textContent = message;
    notice.className = `notice ${kind}`;
    notice.hidden = !message;
  }

  function invalidate() {
    const hadResult = Boolean(state.result);
    state.version += 1;
    importController?.abort();
    importController = null;
    state.importing = false;
    if (state.controller) state.controller.abort();
    state.controller = null;
    state.busy = false;
    state.result = null;
    $('results-content').hidden = true;
    $('results-empty').hidden = false;
    $('export-button').disabled = true;
    $('results-body').replaceChildren();
    $('camera-rotation').setAttribute('transform', 'rotate(0 139 67)');
    $('schematic-angle').textContent = '—';
    if (hadResult) notify('입력이 변경되어 이전 결과를 비웠습니다. 현재 조건으로 다시 추정하세요.');
    updateReadiness();
  }

  function pointQuality(sample) {
    if (!sample) return { ok: false, message: '촬영 데이터를 먼저 가져오세요.' };
    const points = sample.points.filter((point) => validDepth(sample.depth_m[point.v * sample.width + point.u]));
    if (points.length < 6) return { ok: false, message: `유효한 벽 점이 ${points.length}개입니다. 최소 6개를 넓게 선택하세요.` };
    let mx = 0, my = 0;
    for (const point of points) { mx += point.u / points.length; my += point.v / points.length; }
    let xx = 0, yy = 0, xy = 0;
    for (const point of points) { xx += (point.u - mx) ** 2; yy += (point.v - my) ** 2; xy += (point.u - mx) * (point.v - my); }
    const trace = xx + yy;
    const discriminant = Math.sqrt(Math.max(0, (xx - yy) ** 2 + 4 * xy ** 2));
    const major = (trace + discriminant) / 2;
    const minor = (trace - discriminant) / 2;
    if (major <= 0 || minor / major < 0.0064) return { ok: false, message: '점들이 한 직선에 가깝습니다. 가로·세로로 분산해 추가하세요.' };
    if (Math.sqrt(minor / points.length) / Math.min(sample.width, sample.height) < 0.012) return { ok: false, message: '점들이 너무 좁게 모여 있습니다. 같은 벽의 넓은 영역을 선택하세요.' };
    return { ok: true, message: `${points.length}개 유효 점 · 화면상 분포 양호. 실제 평면 적합 품질은 추정 후 확인하세요.` };
  }

  function readiness() {
    if (state.samples.length < 2) return '기준과 비교 촬영이 최소 2개 필요합니다.';
    if (!checks.every((id) => $(id).checked)) return '위 세 가지 고정 조건을 모두 확인하세요.';
    const first = state.samples[0];
    if (state.samples.some((sample) => ['serial', 'profile_id', 'frame_id', 'synthetic'].some((key) => sample.metadata[key] !== first.metadata[key]) || sample.width !== first.width || sample.height !== first.height)) return '촬영의 장치·프로파일·좌표 프레임·해상도가 다릅니다. 같은 수집 모드의 샘플을 선택하세요.';
    const invalid = state.samples.find((sample) => !pointQuality(sample).ok);
    if (invalid) return `${invalid.id}: 유효한 점 6개 이상을 넓게 선택하세요.`;
    return '';
  }

  function updateReadiness() {
    const reason = readiness();
    $('saved-import').disabled = destroyed || state.importing || !state.savedSelection.size;
    $('saved-import').textContent = state.importing ? '저장 샘플을 확인하고 있습니다…' : '선택한 저장 샘플 가져오기';
    $('estimate-button').disabled = destroyed || state.busy || state.importing || Boolean(reason);
    $('export-button').disabled = destroyed || state.busy || !state.result || Boolean(reason);
    $('point-u').disabled = !selected();
    $('point-v').disabled = !selected();
    $('point-add').disabled = !selected();
    $('estimate-button').textContent = state.busy ? '평면을 분석하고 있습니다…' : '↗ 상대 피치 추정';
    $('estimate-readiness').textContent = state.busy ? '입력을 바꾸면 현재 계산은 취소됩니다.' : reason || '조건 확인 완료 · 상대 피치를 계산할 수 있습니다.';
    const sample = selected();
    $('undo-button').disabled = !sample || sample.points.length === 0;
    $('clear-button').disabled = !sample || sample.points.length === 0;
  }

  function renderSampleList() {
    $('sample-total').textContent = String(state.samples.length).padStart(2, '0');
    const fragment = document.createDocumentFragment();
    state.samples.forEach((sample, index) => {
      const card = node('div', `sample-card${sample.id === state.selectedId ? ' active' : ''}`);
      const button = node('button', 'sample-select');
      button.type = 'button';
      button.setAttribute('aria-pressed', String(sample.id === state.selectedId));
      button.setAttribute('aria-label', `${sample.id} 촬영 선택`);
      const header = node('div', 'sample-card-head');
      header.append(node('span', 'sample-index', String(index + 1).padStart(2, '0')), node('span', 'sample-name', sample.id));
      const details = node('div', 'sample-details');
      details.append(node('span', '', `${sample.points.length}개 점 선택`), node('span', sample.metadata.synthetic ? 'synthetic-mini' : '', sample.metadata.synthetic ? 'SYNTHETIC' : state.savedEvidence.has(sample.id) ? 'SAVED' : 'IMPORTED'));
      button.append(header, details);
      button.addEventListener('click', () => {
        if (state.selectedId === sample.id) return;
        state.selectedId = sample.id;
        // Viewing another capture changes no measurement input.
        render();
        if (state.result) renderResults(state.result);
      });
      const label = node('label', 'reference-control');
      const radio = document.createElement('input');
      radio.type = 'radio'; radio.name = 'mount-calibration-reference'; radio.value = sample.id;
      radio.checked = sample.id === state.referenceId;
      radio.addEventListener('change', () => {
        state.referenceId = sample.id;
        invalidate(); render();
      });
      label.append(radio, node('span', '', radio.checked ? '기준 촬영으로 사용 중' : '기준 촬영으로 지정'));
      card.append(button, label);
      fragment.append(card);
    });
    $('sample-list').replaceChildren(fragment);
  }

  function buildHeatmap(sample) {
    const cached = state.heatmaps.get(sample.id);
    if (cached) return cached;
    const valid = sample.depth_m.filter(validDepth).sort((a, b) => a - b);
    const lo = valid.length ? valid[Math.floor((valid.length - 1) * 0.02)] : 0;
    const hi = valid.length ? valid[Math.floor((valid.length - 1) * 0.98)] : 0;
    const min = valid.length ? valid[0] : 0;
    const max = valid.length ? valid[valid.length - 1] : 0;
    const range = Math.max(hi - lo, .01);
    const canvas = document.createElement('canvas');
    canvas.width = sample.width; canvas.height = sample.height;
    const context = canvas.getContext('2d');
    const image = context.createImageData(sample.width, sample.height);
    const palette = [[36, 75, 112], [42, 162, 166], [151, 219, 160], [231, 217, 139]];
    for (let i = 0; i < sample.depth_m.length; i += 1) {
      const depth = sample.depth_m[i];
      let color;
      if (!validDepth(depth)) {
        const x = i % sample.width, y = Math.floor(i / sample.width);
        color = (Math.floor(x / 8) + Math.floor(y / 8)) % 2 ? [19, 35, 45] : [27, 45, 55];
      } else {
        const position = Math.max(0, Math.min(1, (depth - lo) / range)) * (palette.length - 1);
        const start = Math.min(palette.length - 2, Math.floor(position));
        const factor = position - start;
        color = palette[start].map((value, channel) => Math.round(value * (1 - factor) + palette[start + 1][channel] * factor));
      }
      image.data[i * 4] = color[0]; image.data[i * 4 + 1] = color[1]; image.data[i * 4 + 2] = color[2]; image.data[i * 4 + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    const heatmap = { canvas, min, max, lo, hi };
    state.heatmaps.set(sample.id, heatmap);
    return heatmap;
  }

  function drawDepth() {
    const sample = selected();
    if (!sample) return;
    const canvas = $('depth-canvas');
    canvas.width = sample.width; canvas.height = sample.height;
    const context = canvas.getContext('2d');
    const heatmap = buildHeatmap(sample);
    const evidence = state.savedEvidence.get(sample.id);
    const showImage = Boolean(state.imageView && evidence?.image);
    context.drawImage(showImage ? evidence.image : heatmap.canvas, 0, 0);
    $('image-toggle').hidden = !evidence?.image;
    $('image-toggle').textContent = showImage ? '깊이 히트맵 보기' : '저장 IR 영상 보기';
    $('depth-legend').hidden = showImage;
    $('canvas-caption').textContent = showImage
      ? '저장 IR1 영상 · 원본 픽셀과 optical-Z 깊이 대응 확인 · 라이브 아님'
      : evidence?.imageError ? `깊이 히트맵 · 대응 영상 미표시: ${evidence.imageError}` : '깊이 히트맵 · 라이브 영상 아님';
    canvas.setAttribute('aria-label', showImage ? '저장된 IR1 영상. 같은 벽 위의 지점을 선택하세요. 원본 픽셀 좌표를 사용합니다.' : '깊이 히트맵. 같은 벽 위의 지점을 선택하거나 픽셀 좌표를 입력하세요.');
    const analysis = state.result?.samples?.find((item) => item.id === sample.id);
    const markerRadius = Math.max(3.5, sample.width / 85);
    sample.points.forEach((point, index) => {
      const validated = analysis?.validated_points?.find((item) => item.u === point.u && item.v === point.v);
      const rejected = validated && (!validated.valid || !validated.inlier);
      context.beginPath(); context.arc(point.u, point.v, markerRadius + 1.2, 0, Math.PI * 2);
      context.fillStyle = rejected ? '#e27f6b' : '#103c41'; context.fill();
      context.strokeStyle = rejected ? '#ffe1c2' : '#edfff7'; context.lineWidth = 1.2; context.stroke();
      context.beginPath(); context.arc(point.u, point.v, 1, 0, Math.PI * 2); context.fillStyle = '#e8fff8'; context.fill();
      const label = String(index + 1);
      context.font = `600 ${Math.max(8, sample.width / 40)}px sans-serif`;
      const textWidth = context.measureText(label).width;
      let x = Math.min(sample.width - textWidth - 7, point.u + markerRadius + 3);
      let y = Math.max(11, point.v - markerRadius - 3);
      context.fillStyle = '#0e2a32df'; context.fillRect(x - 3, y - 9, textWidth + 6, 12);
      context.fillStyle = '#e4fff5'; context.fillText(label, x, y);
    });
    $('depth-min').textContent = `${pretty(heatmap.lo, 2)} m`;
    $('depth-max').textContent = `${pretty(heatmap.hi, 2)} m`;
    $('depth-min').parentElement.title = `색상 범위는 깊이의 2–98 백분위입니다. 실제 최소 ${pretty(heatmap.min)} m`;
    $('depth-max').parentElement.title = `색상 범위는 깊이의 2–98 백분위입니다. 실제 최대 ${pretty(heatmap.max)} m`;
  }

  function renderMetadata() {
    const sample = selected();
    if (!sample) return;
    const meta = sample.metadata;
    const k = sample.intrinsics;
    const metadata = [
      ['출처', meta.synthetic ? '합성 픽스처 · 실제 측정 아님' : state.savedEvidence.has(sample.id) ? '서버 보관 캡처 · 현재 장치 상태 아님' : '가져온 파일 · 실장비 미검증'],
      ['장치 시리얼', meta.serial], ['좌표 프레임', meta.frame_id],
      ['프로파일', meta.profile_id ?? '미제공'], ['촬영 번호', meta.frame_numbers ? `IR1 ${meta.frame_numbers.ir1} / depth ${meta.frame_numbers.depth}` : meta.frame_number ?? '미제공'],
      ['소스 시각', meta.source_timestamp === undefined ? '미제공' : `${meta.source_timestamp}${meta.source_timestamp_unit ? ` ${meta.source_timestamp_unit}` : ''}`], ['클록 도메인', meta.clock_domain ?? '미제공'],
      ['해상도', `${sample.width} × ${sample.height}`], ['fx / fy', `${pretty(k.fx, 1)} / ${pretty(k.fy, 1)}`],
      ['cx / cy', `${pretty(k.cx, 1)} / ${pretty(k.cy, 1)}`], ['깊이 규약', `${meta.depth_semantics ?? '미제공'} · m`],
      ['영상 보정', state.savedEvidence.has(sample.id) ? '보관 파일의 pinhole·동일 픽셀 계약 확인' : meta.rectified === true ? 'rectified = true (신고값)' : '미확인'],
      ['촬영 시각 (UTC)', state.savedEvidence.get(sample.id)?.manifest.captured_at_utc ?? '미제공'],
      ['프레임 시각 차이', finite(meta.synchronization?.source_skew_ms) ? `${meta.synchronization.source_skew_ms} ms` : '미제공'],
    ];
    const fragment = document.createDocumentFragment();
    metadata.forEach(([key, value]) => { const row = node('div'); row.append(node('dt', '', key), node('dd', '', value)); fragment.append(row); });
    $('metadata-list').replaceChildren(fragment);
    const hasFixtureAngle = meta.synthetic === true && finite(meta.fixture_pitch_deg);
    $('fixture-note').textContent = meta.synthetic ? `합성 데이터입니다. ${hasFixtureAngle ? `생성에 사용한 각도 ${angleText(meta.fixture_pitch_deg)}는 테스트 정답 라벨이며, 계산 결과가 아닙니다.` : '파일의 synthetic 표시를 읽었습니다. 실제 카메라 측정으로 검증되지 않았습니다.'}` : state.savedEvidence.has(sample.id) ? '저장 시점의 원본·메타데이터 대응을 확인했습니다. 현재 장치 상태, 실제 평면·피치 전용 조건 또는 몸체 기준 절대 보정을 검증한 것은 아닙니다.' : '메타데이터는 파일에 기록된 값입니다. 실제 장치·동기화·좌표 정합 검증을 대신하지 않습니다.';
  }

  function renderPointList() {
    const sample = selected();
    if (!sample) return;
    const fragment = document.createDocumentFragment();
    sample.points.forEach((point, index) => {
      const button = node('button', 'point-chip', `${index + 1}. (${point.u}, ${point.v}) ×`);
      button.type = 'button'; button.setAttribute('aria-label', `${index + 1}번 점, 픽셀 ${point.u}, ${point.v} 삭제`);
      button.addEventListener('click', () => { sample.points.splice(index, 1); invalidate(); render(); });
      fragment.append(button);
    });
    $('point-list').replaceChildren(fragment);
  }

  function render() {
    renderSampleList();
    const sample = selected();
    $('depth-empty').hidden = Boolean(sample);
    $('depth-canvas').hidden = !sample;
    $('source-badge').hidden = !sample;
    if (!sample) {
      $('point-quality').textContent = 'JSON 촬영 데이터를 가져오거나 합성 데모를 선택하세요.';
      updateReadiness();
      return;
    }
    $('current-sample-label').textContent = `${sample.id}${sample.id === state.referenceId ? ' · 기준 촬영' : ''}`;
    $('image-dimensions').textContent = `${sample.width} × ${sample.height} PX`;
    $('source-badge').textContent = sample.metadata.synthetic ? '합성 데이터 · 실제 측정 아님' : state.savedEvidence.has(sample.id) ? '저장 캡처 · 상대 분석용' : '가져온 깊이 · 미검증';
    $('source-badge').className = `source-badge${sample.metadata.synthetic ? ' synthetic' : ''}`;
    $('point-count').textContent = String(sample.points.length);
    const quality = pointQuality(sample);
    $('point-quality').textContent = quality.message;
    $('point-quality').className = `point-quality ${quality.ok ? 'good' : 'warn'}`;
    $('point-u').max = String(sample.width - 1); $('point-v').max = String(sample.height - 1);
    $('conditions-heading').textContent = allSynthetic() ? '데모 조건 확인' : '촬영 조건 확인';
    $('conditions-description').textContent = allSynthetic() ? '합성 데모의 가정을 읽고 직접 확인하세요. 실제 촬영을 확인한 기록은 아닙니다.' : '실제 촬영 당시의 조건을 확인하세요. 이 선언은 장치 검증을 대신하지 않습니다.';
    renderMetadata(); renderPointList(); drawDepth(); updateReadiness();
  }

  function addPoint(u, v) {
    const sample = selected();
    if (!sample) return;
    if (!Number.isInteger(u) || !Number.isInteger(v) || u < 0 || v < 0 || u >= sample.width || v >= sample.height) { notify('영상 안의 정수 픽셀 좌표를 입력하세요.', 'error'); return; }
    if (sample.points.length >= maxPoints) { notify(`촬영당 최대 ${maxPoints}개 점을 선택할 수 있습니다.`, 'error'); return; }
    const depth = sample.depth_m[v * sample.width + u];
    if (!validDepth(depth)) { notify(`(${u}, ${v})에는 0.1–30 m 범위의 유효한 깊이가 없습니다. 같은 벽의 다른 점을 선택하세요.`, 'error'); return; }
    if (sample.points.some((point) => point.u === u && point.v === v)) { notify('이미 선택한 픽셀입니다. 목록의 × 버튼으로 지울 수 있습니다.'); return; }
    sample.points.push({ u, v });
    notify(''); invalidate(); render();
  }

  function validateImportedSample(raw, index) {
    const label = `샘플 ${index + 1}`;
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error(`${label}: 샘플 객체가 필요합니다.`);
    if (typeof raw.id !== 'string' || !raw.id.trim() || raw.id.length > 200) throw new Error(`${label}: 1–200자 id가 필요합니다.`);
    if (!Number.isInteger(raw.width) || !Number.isInteger(raw.height) || raw.width < 2 || raw.height < 2 || raw.width > 640 || raw.height > 480) throw new Error(`${label}: 해상도는 최대 640 × 480입니다.`);
    if (!raw.intrinsics || !['fx', 'fy', 'cx', 'cy'].every((key) => finite(raw.intrinsics[key])) || raw.intrinsics.fx <= 0 || raw.intrinsics.fy <= 0) throw new Error(`${label}: 유효한 fx, fy, cx, cy가 필요합니다.`);
    if (!Array.isArray(raw.depth_m) || raw.depth_m.length !== raw.width * raw.height || raw.depth_m.some((depth) => depth !== null && !finite(depth))) throw new Error(`${label}: depth_m은 width × height 길이의 미터 단위 배열이어야 합니다. 무효 깊이는 null 또는 0을 사용하세요.`);
    const meta = raw.metadata;
    if (!meta || typeof meta !== 'object' || Array.isArray(meta) || typeof meta.synthetic !== 'boolean' || meta.rectified !== true || !meta.serial || !meta.frame_id) throw new Error(`${label}: metadata.serial, frame_id, rectified:true, synthetic:true/false가 필요합니다.`);
    if (meta.depth_semantics !== 'optical_z') throw new Error(`${label}: metadata.depth_semantics는 optical_z여야 합니다.`);
    if (!meta.profile_id) throw new Error(`${label}: metadata.profile_id가 필요합니다.`);
    if (!meta.synthetic && (meta.source_timestamp === undefined || !meta.clock_domain)) throw new Error(`${label}: 실제 촬영에는 source_timestamp와 clock_domain이 필요합니다.`);
    const points = raw.points ?? [];
    if (!Array.isArray(points) || points.length > maxPoints) throw new Error(`${label}: points는 최대 ${maxPoints}개 점의 배열이어야 합니다.`);
    const seen = new Set();
    for (const point of points) {
      if (!point || !Number.isInteger(point.u) || !Number.isInteger(point.v) || point.u < 0 || point.v < 0 || point.u >= raw.width || point.v >= raw.height) throw new Error(`${label}: 점 좌표는 영상 범위 안의 정수여야 합니다.`);
      const key = `${point.u},${point.v}`;
      if (seen.has(key)) throw new Error(`${label}: 중복된 점 좌표가 있습니다.`);
      seen.add(key);
    }
    // Preserve provenance and explicit distortion fields for the backend's stricter validation.
    return { id: raw.id, width: raw.width, height: raw.height, intrinsics: raw.intrinsics, depth_m: raw.depth_m, points: points.map(({u, v}) => ({u, v})), metadata: meta };
  }

  function releaseImages(evidence = state.savedEvidence) {
    for (const value of evidence.values()) value.image?.close?.();
  }

  function installSamples(samples, referenceId, evidence = new Map()) {
    invalidate();
    releaseImages();
    state.savedEvidence = evidence;
    state.imageView = true;
    state.samples = samples;
    state.referenceId = samples.some((sample) => sample.id === referenceId) ? referenceId : samples[0]?.id ?? null;
    state.selectedId = state.referenceId;
    state.heatmaps.clear();
    checks.forEach((id) => { $(id).checked = false; });
    render();
  }

  function makeDemo() {
    const width = 320, height = 240;
    const intrinsics = { fx: 280, fy: 280, cx: 160, cy: 120, model: 'pinhole' };
    const points = [{u:45,v:38},{u:160,v:35},{u:274,v:40},{u:49,v:120},{u:270,v:120},{u:45,v:200},{u:160,v:204},{u:275,v:200}];
    return [0, 10, -8].map((degrees, index) => {
      const theta = degrees * Math.PI / 180;
      const depth = new Array(width * height);
      for (let v = 0; v < height; v += 1) {
        for (let u = 0; u < width; u += 1) {
          const rayY = (v - intrinsics.cy) / intrinsics.fy;
          const z = 2.2 / (-Math.sin(theta) * rayY + Math.cos(theta));
          // Seed-free deterministic sub-millimetre noise; never hardware data.
          const noise = .00035 * Math.sin(u * 1.27 + v * .73 + index * 2.1);
          depth[v * width + u] = Math.round((z + noise) * 1000000) / 1000000;
        }
      }
      return {
        id: ['데모 A · 기준', '데모 B · 기울임', '데모 C · 반대 방향'][index], width, height, intrinsics: {...intrinsics}, depth_m: depth, points: points.map((point) => ({...point})),
        metadata: { serial: 'SYNTHETIC-NO-DEVICE', frame_id: 'camera_depth_optical_frame', frame_number: index + 1, rectified: true, synthetic: true, profile_id: 'synthetic-depth-320x240-pinhole', depth_semantics: 'optical_z', source_timestamp: `2026-01-01T00:00:0${index}.000Z`, clock_domain: 'synthetic_fixture', stream: 'depth', projection_model: 'pinhole', fixture_pitch_deg: degrees, fixture_wall_distance_m: 2.2 },
      };
    });
  }

  function payload() {
    return { samples: state.samples, reference_id: state.referenceId, robot_stationary_confirmed: $('stationary-check').checked, wall_same_confirmed: $('wall-check').checked, mount_only_pitch_confirmed: $('pitch-check').checked };
  }

  async function requestAnalysis(path) {
    const controller = new AbortController();
    state.controller = controller;
    return request(`${endpoint}/${path}`, { method: 'POST', body: JSON.stringify(payload()), signal: controller.signal });
  }

  function renderResults(result) {
    if (!result || !Array.isArray(result.samples)) throw new Error('서버 결과에 촬영별 분석이 없습니다.');
    state.result = result;
    $('results-empty').hidden = true;
    $('results-content').hidden = false;
    $('export-button').disabled = false;
    const summary = document.createDocumentFragment();
    summary.append(node('span', `result-pill${result.synthetic ? ' synthetic' : ''}`, result.synthetic ? '합성 데모 분석' : '가져온 촬영 분석'), node('span', '', `기준: ${result.reference_id}`), node('strong', '', '상대 피치만 · 본체 외부 파라미터 미검증'));
    $('results-summary').replaceChildren(summary);
    const rows = document.createDocumentFragment();
    const warnings = new Set(Array.isArray(result.warnings) ? result.warnings : []);
    result.samples.forEach((sample) => {
      const tr = node('tr');
      const title = node('td', '', sample.id);
      if (sample.id === result.reference_id) title.append(node('span', 'table-reference', '기준'));
      const normal = Array.isArray(sample.normal_camera) && sample.normal_camera.length === 3 ? `[${sample.normal_camera.map((value) => pretty(value, 4)).join(', ')}]` : '—';
      const held = !finite(sample.relative_pitch_deg);
      tr.append(title, node('td', 'angle-cell', angleText(sample.relative_pitch_deg)), node('td', '', finite(sample.plane_rmse_m) ? `${pretty(sample.plane_rmse_m * 1000, 2)} mm` : '—'), node('td', '', `${sample.inlier_points ?? '—'} / ${sample.valid_points ?? '—'}${finite(sample.inlier_ratio) ? ` (${pretty(sample.inlier_ratio * 100, 0)}%)` : ''}`), node('td', 'normal-cell', normal), node('td', '', held ? '피치 전용 조건 불일치' : sample.id === result.reference_id ? '상대 영점' : '상대 추정값'));
      rows.append(tr);
      if (Array.isArray(sample.warnings)) sample.warnings.forEach((warning) => warnings.add(`${sample.id}: ${warning}`));
    });
    $('results-body').replaceChildren(rows);
    const warningFragment = document.createDocumentFragment();
    warningFragment.append(node('strong', '', '해석 전 확인'));
    const list = node('ul');
    const builtIn = ['부호: +는 같은 벽을 기준으로 카메라가 더 아래를 보는 회전입니다. optical frame은 x 오른쪽, y 아래, z 전방입니다.', '같은 벽의 법선을 비교하므로 실제 로봇 본체 기준 각도·높이·이동량은 산출하지 않습니다.'];
    if (result.pitch_only_consistent === false) builtIn.unshift('피치만 회전했다는 가정과 맞지 않는 촬영이 있어 해당 각도 표시를 보류했습니다.');
    [...builtIn, ...warnings].forEach((warning) => list.append(node('li', '', warning)));
    warningFragment.append(list); $('result-warnings').replaceChildren(warningFragment);
    const activeResult = result.samples.find((sample) => sample.id === state.selectedId);
    const relative = activeResult?.relative_pitch_deg;
    $('camera-rotation').setAttribute('transform', `rotate(${finite(relative) ? Math.max(-45, Math.min(45, relative)) : 0} 139 67)`);
    $('schematic-angle').textContent = finite(relative) ? angleText(relative) : '보류';
    drawDepth();
  }

  const validSavedId = (id) => typeof id === 'string' && /^[a-f0-9]{32}$/.test(id);
  const stableManifest = (value) => JSON.stringify(value, function (_key, item) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return item;
    return Object.fromEntries(Object.keys(item).sort().map((key) => [key, item[key]]));
  });
  function manifestFile(manifest, filename) {
    const file = manifest.files?.[filename];
    if (!file || !Number.isInteger(file.bytes) || file.bytes <= 0 || file.bytes > maxFileBytes || !/^[a-f0-9]{64}$/.test(file.sha256)) throw new Error(`${manifest.sample_id}: ${filename} 보관 정보가 유효하지 않습니다.`);
    return file;
  }
  function validateCatalogue(value) {
    if (!value || !Array.isArray(value.samples) || value.samples.length > 64) throw new Error('저장 목록 형식이 올바르지 않습니다.');
    const seen = new Set();
    for (const entry of value.samples) {
      if (!entry || entry.schema !== 'robot-scope.depth-capture.v1' || !validSavedId(entry.sample_id) || seen.has(entry.sample_id) || entry.synthetic !== false) throw new Error('저장 목록의 샘플 식별자·스키마가 유효하지 않습니다.');
      seen.add(entry.sample_id);
    }
    return value.samples;
  }
  function renderCatalogue() {
    const fragment = document.createDocumentFragment();
    for (const entry of state.saved) {
      const row = node('div', 'saved-sample');
      const label = node('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.value = entry.sample_id;
      checkbox.disabled = entry.compatibility?.available !== true;
      checkbox.checked = state.savedSelection.has(entry.sample_id);
      checkbox.setAttribute('aria-label', `${entry.sample_id} 저장 샘플 선택`);
      checkbox.addEventListener('change', () => {
        invalidate();
        if (checkbox.checked) state.savedSelection.add(entry.sample_id);
        else state.savedSelection.delete(entry.sample_id);
        updateReadiness();
      });
      const description = node('span', '', entry.sample_id);
      description.append(node('small', '', `${entry.captured_at_utc || '촬영 시각 미제공'} · 보관 촬영`));
      description.append(node('small', '', entry.compatibility?.available === true
        ? `${entry.image?.width ?? '—'} × ${entry.image?.height ?? '—'} · 유효 깊이 ${pretty(entry.valid_depth_ratio * 100, 1)}%`
        : `분석용 JSON 없음: ${entry.compatibility?.reason || '지원 여부 미확인'}`));
      const archive = node('a', '', '전체 원본 ZIP');
      archive.href = `${savedEndpoint}/${entry.sample_id}/export`;
      archive.download = `${entry.sample_id}.zip`;
      label.append(checkbox, description);
      row.append(label, archive); fragment.append(row);
    }
    $('saved-list').replaceChildren(fragment);
    updateReadiness();
  }
  async function refreshCatalogue() {
    if (destroyed) return;
    invalidate();
    catalogueController?.abort();
    const controller = new AbortController();
    catalogueController = controller;
    const version = ++catalogueVersion;
    state.saved = []; state.savedSelection.clear(); renderCatalogue();
    $('saved-status').textContent = '저장 목록을 조회하고 있습니다…';
    try {
      const value = await request(savedEndpoint, { signal: controller.signal });
      if (destroyed || version !== catalogueVersion) return;
      state.saved = validateCatalogue(value);
      renderCatalogue();
      $('saved-status').textContent = state.saved.length ? `${state.saved.length}개 보관 샘플 · 현재 센서 상태와 무관합니다.` : '저장 샘플이 없습니다. Mapping에서 정지 Depth 캡처 후 새로고침하세요.';
    } catch (error) {
      if (!destroyed && version === catalogueVersion && error.name !== 'AbortError') $('saved-status').textContent = `목록 조회 실패: ${error.message}`;
    } finally { if (catalogueController === controller) catalogueController = null; }
  }
  async function artifactBytes(manifest, kind, filename, signal) {
    const file = manifestFile(manifest, filename);
    if (typeof fetchArtifact !== 'function') throw new Error('저장 파일 다운로드를 사용할 수 없습니다.');
    const response = await fetchArtifact(`${savedEndpoint}/${manifest.sample_id}/${kind}`, { method: 'GET', cache: 'no-store', signal });
    if (!response.ok) throw new Error(`${filename} 조회 실패 (HTTP ${response.status})`);
    // Headers identify bytes verified by the store under its lock. This works on
    // the robot's HTTP LAN origin without relying on secure-context crypto APIs.
    if (response.headers.get('X-Robot-Scope-Artifact-SHA256') !== file.sha256 || response.headers.get('X-Robot-Scope-Artifact-Bytes') !== String(file.bytes)) throw new Error(`${filename}: 목록과 파일이 달라졌습니다. 목록을 새로고침하세요.`);
    const expectedType = kind === 'image' ? 'image/png' : 'application/json';
    if (response.headers.get('Content-Type')?.split(';', 1)[0] !== expectedType) throw new Error(`${filename}: 파일 형식이 일치하지 않습니다.`);
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength !== file.bytes) throw new Error(`${filename}: 다운로드 크기가 일치하지 않습니다.`);
    return buffer;
  }
  function validateSavedSample(raw, manifest, index) {
    const sample = validateImportedSample(raw, index);
    const meta = sample.metadata, image = manifest.image, alignment = meta.alignment;
    const fail = (reason) => { throw new Error(`${manifest.sample_id}: ${reason}`); };
    if (sample.id !== manifest.sample_id || meta.capture_id !== manifest.sample_id || meta.synthetic !== false) fail('보관 샘플 식별자가 일치하지 않습니다.');
    if (meta.capture_session_id != null && meta.capture_session_id !== manifest.session_id) fail('촬영 세션 식별자가 보관 목록과 일치하지 않습니다.');
    if (!/^[a-f0-9]{64}$/.test(meta.profile_id) || meta.frame_id_source !== 'sdk_logical_optical_not_ros_tf') fail('프로파일 또는 optical frame 출처를 확인할 수 없습니다.');
    if (!image || image.width !== sample.width || image.height !== sample.height || image.frame_id !== meta.frame_id || image.frame_id_source !== meta.frame_id_source) fail('영상 크기·좌표 프레임이 깊이와 일치하지 않습니다.');
    if (sample.depth_m.some((depth) => depth !== null && depth <= 0) || (meta.depth_unit !== undefined && meta.depth_unit !== 'm') || (meta.depth_units !== undefined && meta.depth_units !== 'm')) fail('깊이는 m 단위 optical-Z이며 무효 값은 null이어야 합니다.');
    const timestamps = meta.source_timestamps_ms, frames = meta.frame_numbers, sync = meta.synchronization;
    if (meta.source_timestamp_unit !== 'seconds' || meta.source_timestamp_stream !== 'ir1' || !finite(meta.source_timestamp) || meta.source_timestamp < 0 || !finite(image.timestamp_ms)
      || !finite(timestamps?.ir1) || !finite(timestamps?.depth) || timestamps.ir1 < 0 || timestamps.depth < 0
      || image.timestamp_ms !== timestamps.ir1 || Math.abs(meta.source_timestamp * 1000 - timestamps.ir1) > .001
      || image.timestamp_domain !== meta.clock_domain || meta.timestamp_domain !== meta.clock_domain
      || !['hardware_clock', 'system_time', 'global_time'].includes(String(meta.clock_domain).split('.').at(-1))) fail('소스 시각·단위·클록 도메인이 일치하지 않습니다.');
    const skew = Math.abs(timestamps.ir1 - timestamps.depth);
    if (sync?.frameset_verified !== true || !finite(sync.source_skew_ms) || Math.abs(skew - sync.source_skew_ms) > .001 || !finite(manifest.actual_source_skew_ms) || Math.abs(skew - manifest.actual_source_skew_ms) > .001 || skew > 1 || sync.max_source_skew_ms !== 1
      || !Number.isInteger(frames?.ir1) || frames.ir1 < 0 || !Number.isInteger(frames?.depth) || frames.depth < 0 || image.frame_number !== frames.ir1) fail('영상과 깊이의 프레임·동기화 증거가 일치하지 않습니다.');
    if (meta.rectification_basis !== 'actual_zero_distortion_intrinsics_and_identity_depth_to_ir1_no_resampling' || alignment?.method !== 'verified_identity_depth_to_ir1_no_resampling') fail('원본 픽셀 대응·pinhole 보정 근거를 지원하지 않습니다.');
    for (const intrinsics of [alignment.ir1_intrinsics, alignment.depth_intrinsics]) {
      if (!intrinsics || intrinsics.width !== sample.width || intrinsics.height !== sample.height
        || !['none', 'brown_conrady'].includes(String(intrinsics.model).split('.').at(-1)) || !Array.isArray(intrinsics.coeffs) || intrinsics.coeffs.length !== 5 || intrinsics.coeffs.some((v) => v !== 0)
        || [['fx', 'fx'], ['fy', 'fy'], ['ppx', 'cx'], ['ppy', 'cy']].some(([source, target]) => !finite(intrinsics[source]) || Math.abs(intrinsics[source] - sample.intrinsics[target]) > 1e-9 * Math.max(1, Math.abs(intrinsics[source]), Math.abs(sample.intrinsics[target])))) fail('영상·깊이 내부 파라미터 또는 왜곡 모델이 일치하지 않습니다.');
    }
    const extrinsics = alignment.depth_to_ir1;
    if (!Array.isArray(extrinsics?.rotation) || extrinsics.rotation.length !== 9 || extrinsics.rotation.some((v, i) => !finite(v) || Math.abs(v - ([0, 4, 8].includes(i) ? 1 : 0)) > 1e-8)
      || !Array.isArray(extrinsics?.translation) || extrinsics.translation.length !== 3 || extrinsics.translation.some((v) => !finite(v) || Math.abs(v) > 1e-8)) fail('영상과 깊이 사이의 identity 외부 파라미터를 확인할 수 없습니다.');
    // Export the selected immutable store provenance with analysis input, while
    // keeping the original JSON and image independently available in the ZIP.
    sample.metadata = { ...meta, saved_capture: { schema: manifest.schema, sample_id: manifest.sample_id,
      capture_session_id: manifest.session_id, generation: manifest.generation,
      captured_at_utc: manifest.captured_at_utc, files: manifest.files } };
    return sample;
  }
  async function decodeSavedImage(bytes, signal) {
    const blob = new Blob([bytes], { type: 'image/png' });
    if (signal.aborted) throw new Error('가져오기가 취소되었습니다.');
    if (options.decodeImage) return options.decodeImage(blob);
    if (typeof globalThis.createImageBitmap === 'function') return globalThis.createImageBitmap(blob);
    // Safari fallback keeps the original PNG size; CSS resizing only affects its
    // presentation, while canvas click coordinates remain native pixels.
    const image = document.createElement('img');
    const url = URL.createObjectURL(blob);
    image.src = url;
    try { await image.decode(); return image; }
    finally { URL.revokeObjectURL(url); }
  }
  on($('saved-refresh'), 'click', refreshCatalogue);
  on($('saved-import'), 'click', async () => {
    if (destroyed || state.importing || !state.savedSelection.size) return;
    invalidate(); notify('');
    const version = state.version;
    const controller = new AbortController();
    importController = controller;
    state.importing = true; updateReadiness();
    const entries = state.saved.filter((entry) => state.savedSelection.has(entry.sample_id));
    const evidence = new Map();
    let installed = false;
    try {
      if (entries.length < 1 || entries.length > 12) throw new Error('저장 샘플은 1–12개까지 함께 가져올 수 있습니다.');
      const totalBytes = entries.reduce((total, entry) => total + manifestFile(entry, 'compatibility.json').bytes, 0);
      if (totalBytes > maxFileBytes) throw new Error('선택한 분석용 JSON의 합계는 최대 30 MB입니다.');
      const samples = [];
      for (const entry of entries) {
        if (entry.compatibility?.available !== true) throw new Error('분석용 JSON이 없는 샘플입니다.');
        const bytes = await artifactBytes(entry, 'compatibility', 'compatibility.json', controller.signal);
        if (destroyed || version !== state.version) return;
        const raw = JSON.parse(await new Blob([bytes]).text());
        const sample = validateSavedSample(raw, entry, samples.length);
        if (destroyed || version !== state.version) return;
        const value = { manifest: entry, image: null, imageError: '' };
        evidence.set(sample.id, value);
        if (entry.image?.available) {
          try {
            const imageBytes = await artifactBytes(entry, 'image', 'click.png', controller.signal);
            const image = await decodeSavedImage(imageBytes, controller.signal);
            if ((image.naturalWidth || image.width) !== sample.width || (image.naturalHeight || image.height) !== sample.height) { image.close?.(); throw new Error('원본 영상 크기가 깊이와 다릅니다.'); }
            value.image = image;
          } catch (error) { value.imageError = error.message; }
        } else value.imageError = '보관 영상 없음';
        if (destroyed || version !== state.version) return;
        samples.push(sample);
      }
      // A stale selection or concurrent catalogue replacement must never silently
      // attach another capture's image/metadata to this analysis input.
      const current = validateCatalogue(await request(savedEndpoint, { signal: controller.signal }));
      if (destroyed || version !== state.version) return;
      for (const entry of entries) if (stableManifest(current.find((item) => item.sample_id === entry.sample_id)) !== stableManifest(entry)) throw new Error('가져오는 동안 저장 샘플이 변경·삭제됐습니다. 목록을 새로고침하세요.');
      installSamples(samples, undefined, evidence);
      installed = true;
      const unavailableImages = [...evidence.values()].filter((value) => value.imageError).length;
      notify(`보관 샘플 ${samples.length}개를 가져왔습니다. 촬영 당시의 조건을 다시 확인하세요.${unavailableImages ? ` 대응 영상 ${unavailableImages}개는 표시하지 못해 깊이 히트맵으로 표시합니다.` : ' 원본 IR 영상에서 같은 벽의 점을 선택하세요.'}`, unavailableImages ? '' : 'success');
    } catch (error) {
      if (!destroyed && version === state.version && error.name !== 'AbortError') notify(`저장 샘플 가져오기 실패: ${error.message}`, 'error');
    } finally {
      if (!installed) releaseImages(evidence);
      if (version === state.version) { state.importing = false; importController = null; updateReadiness(); }
    }
  });

  on($('import-button'), 'click', () => $('file-input').click());
  on($('file-input'), 'change', async (event) => {
    // Capture the input and its FileList synchronously: event.currentTarget is
    // cleared after dispatch, and a newer file choice must supersede this read.
    const input = event.currentTarget;
    const files = Array.from(input.files || []);
    input.value = '';
    if (!files.length || destroyed) return;
    invalidate();
    const importVersion = state.version;
    try {
      if (files.reduce((total, file) => total + file.size, 0) > maxFileBytes) throw new Error('선택한 파일의 합계는 최대 30 MB입니다.');
      const samples = [];
      let referenceId;
      for (const file of files) {
        const text = await file.text();
        if (destroyed || importVersion !== state.version) return;
        const parsed = JSON.parse(text);
        const imported = parsed?.input ?? parsed;
        const rawSamples = Array.isArray(imported?.samples) ? imported.samples : [imported];
        if (!rawSamples.length || samples.length + rawSamples.length > 12) throw new Error('촬영은 합계 1–12개까지 가져올 수 있습니다.');
        if (referenceId === undefined) referenceId = imported?.reference_id;
        samples.push(...rawSamples.map((raw, index) => validateImportedSample(raw, samples.length + index)));
      }
      if (new Set(samples.map((sample) => sample.id)).size !== samples.length) throw new Error('각 촬영의 id는 서로 달라야 합니다.');
      if (samples.some((sample) => sample.metadata.synthetic !== samples[0].metadata.synthetic)) throw new Error('합성 데이터와 실제 촬영은 함께 가져올 수 없습니다.');
      installSamples(samples, referenceId);
      notify(`파일 ${files.length}개에서 촬영 ${samples.length}개를 가져왔습니다. 이전 목록을 교체했습니다. 촬영 조건을 다시 확인하세요.`, 'success');
    } catch (error) { if (!destroyed && importVersion === state.version) notify(`가져오기 실패: ${error.message}`, 'error'); }
  });
  on($('image-toggle'), 'click', () => { state.imageView = !state.imageView; drawDepth(); });
  on($('demo-button'), 'click', () => { installSamples(makeDemo()); notify('합성 데모 3개를 불러왔습니다. 실제 카메라 데이터가 아닙니다. 아래 고정 조건을 직접 확인한 뒤 계산하세요.', 'success'); });
  on($('depth-canvas'), 'click', (event) => {
    const sample = selected();
    if (!sample) return;
    const canvas = $('depth-canvas');
    const bounds = canvas.getBoundingClientRect();
    const u = Math.min(sample.width - 1, Math.max(0, Math.floor((event.clientX - bounds.left) * sample.width / bounds.width)));
    const v = Math.min(sample.height - 1, Math.max(0, Math.floor((event.clientY - bounds.top) * sample.height / bounds.height)));
    addPoint(u, v);
  });
  on($('point-form'), 'submit', (event) => { event.preventDefault(); addPoint(Number($('point-u').value), Number($('point-v').value)); });
  on($('undo-button'), 'click', () => { const sample = selected(); if (sample?.points.length) { sample.points.pop(); invalidate(); render(); } });
  on($('clear-button'), 'click', () => { const sample = selected(); if (sample) { sample.points = []; invalidate(); render(); } });
  checks.forEach((id) => on($(id), 'change', () => { invalidate(); render(); }));
  on($('estimate-button'), 'click', async () => {
    const reason = readiness();
    if (destroyed || state.busy) return;
    if (reason) { notify(reason, 'error'); return; }
    invalidate(); notify('');
    const version = state.version;
    state.busy = true; updateReadiness();
    try {
      const result = await requestAnalysis('estimate');
      if (destroyed || version !== state.version) return;
      renderResults(result);
      notify(result.pitch_only_consistent === false ? '분석은 완료했지만 일부 촬영이 피치 전용 조건과 맞지 않습니다. 보류된 결과와 경고를 확인하세요.' : '평면 비교를 완료했습니다. 아래 상대 피치와 적합 품질을 함께 확인하세요.', result.pitch_only_consistent === false ? '' : 'success');
    } catch (error) {
      if (error.name !== 'AbortError' && version === state.version) notify(`추정 실패: ${error.message}${error instanceof TypeError ? ' 대시보드 서버 연결을 확인하세요.' : ''}`, 'error');
    } finally {
      if (version === state.version) { state.busy = false; state.controller = null; updateReadiness(); }
    }
  });
  on($('export-button'), 'click', async () => {
    if (destroyed || state.busy || !state.result || readiness()) return;
    const version = state.version;
    state.busy = true; $('export-button').disabled = true; updateReadiness();
    try {
      // The server recomputes from the current input; cached or imported analysis is never trusted.
      const exported = await requestAnalysis('export');
      if (destroyed || version !== state.version) return;
      if (!exported.input || !exported.analysis) throw new Error('내보내기 응답에 입력 또는 분석이 없습니다.');
      renderResults(exported.analysis);
      const blob = new Blob([JSON.stringify(exported, null, 2)], {type: 'application/json'});
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      const url = URL.createObjectURL(blob);
      downloadUrl = url;
      const link = node('a'); link.href = url; link.download = `relative-pitch-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => { URL.revokeObjectURL(url); if (downloadUrl === url) downloadUrl = ''; }, 1000);
      notify('현재 입력으로 분석을 다시 계산한 JSON 다운로드를 시작했습니다. 실장비 적용 승인을 뜻하지 않습니다.', 'success');
    } catch (error) { if (error.name !== 'AbortError' && version === state.version) notify(`내보내기 실패: ${error.message}`, 'error'); }
    finally { if (version === state.version) { state.busy = false; state.controller = null; $('export-button').disabled = !state.result; updateReadiness(); } }
  });

  async function refreshStatus() {
    if (destroyed) return;
    statusController?.abort();
    const controller = new AbortController();
    statusController = controller;
    try {
      const status = await request(`${endpoint}/status`, { signal: controller.signal });
      if (destroyed || statusController !== controller) return;
      // Future capture availability does not authorize this import-only UI to
      // open devices. A separately validated capture flow must be integrated.
      $('status').textContent = 'IMPORT ONLY · 저장 샘플 / JSON';
      $('status').className = 'panel-state waiting';
    } catch (error) {
      if (destroyed || statusController !== controller || error.name === 'AbortError') return;
      $('status').textContent = '상태 확인 실패 · 파일 가져오기 모드';
      $('status').className = 'panel-state error';
    } finally { if (statusController === controller) statusController = null; }
  }

  const feature = Object.freeze({
    refreshStatus,
    snapshot: () => ({ sampleCount: state.samples.length, selectedId: state.selectedId,
      referenceId: state.referenceId, hasResult: Boolean(state.result), busy: state.busy,
      version: state.version, savedCount: state.saved.length, importing: state.importing, destroyed }),
    destroy: () => {
      if (destroyed) return;
      destroyed = true;
      invalidate();
      statusController?.abort();
      statusController = null;
      catalogueController?.abort();
      catalogueController = null;
      releaseImages();
      state.savedEvidence.clear();
      listeners.splice(0).forEach((remove) => remove());
      state.samples = [];
      state.heatmaps.clear();
      $('sample-list').replaceChildren();
      $('point-list').replaceChildren();
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      downloadUrl = '';
      instances.delete(root);
    },
  });
  instances.set(root, feature);
  checks.forEach((id) => { $(id).checked = false; });
  render();
  void refreshStatus();
  return feature;
}

