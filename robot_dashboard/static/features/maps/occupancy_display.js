// Palette and metadata operate on a decoded view of the source bytes.
export const OCCUPANCY_COLORS = Object.freeze({
  unknown: [125, 136, 148], occupied: [20, 25, 28], free: [245, 248, 250],
});
export function occupancyClass(byte) {
  return byte > 127 || byte < 0 ? 'unknown' : byte >= 65 ? 'occupied' : 'free';
}
export function occupancyImage(map, documentObject = document) {
  const binary = atob(map.data_b64);
  if (binary.length !== map.width * map.height) throw new Error('지도 셀 수가 맞지 않습니다.');
  const source = documentObject.createElement('canvas');
  source.width = map.width; source.height = map.height;
  const context = source.getContext('2d');
  const image = context.createImageData(map.width, map.height);
  const counts = { occupied: 0, free: 0, unknown: 0 };
  for (let index = 0; index < binary.length; index++) {
    const state = occupancyClass(binary.charCodeAt(index));
    counts[state]++;
    const x = index % map.width, y = Math.floor(index / map.width);
    image.data.set([...OCCUPANCY_COLORS[state], 255], ((map.height - 1 - y) * map.width + x) * 4);
  }
  context.putImageData(image, 0, 0);
  return { source, counts };
}
export function drawOccupancyGrid(map, canvas, resize) {
  const { width, height, ratio } = resize(canvas);
  const { source } = occupancyImage(map);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#20262e'; ctx.fillRect(0, 0, width, height);
  const scale = Math.min(width / map.width, height / map.height) * .94;
  const drawWidth = map.width * scale, drawHeight = map.height * scale;
  const left = (width - drawWidth) / 2, top = (height - drawHeight) / 2;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(source, left, top, drawWidth, drawHeight);
  const [originX, originY, originYaw] = [0, 1, 2].map(index => Number(map.origin?.[index]) || 0);
  const resolution = Math.max(Number(map.resolution) || 0, 0.0001);
  const cos = Math.cos(originYaw), sin = Math.sin(originYaw);
  const projectWorld = pose => {
    const dx = pose.x - originX, dy = pose.y - originY;
    const x = cos * dx + sin * dy, y = -sin * dx + cos * dy;
    return {
      x: left + x / resolution * scale, y: top + drawHeight - y / resolution * scale,
      heading: -(pose.yaw - originYaw),
      inside: x >= 0 && x <= map.width * resolution && y >= 0 && y <= map.height * resolution,
    };
  };
  return { ctx, viewport: { width, height, ratio, projectWorld, fallbackScale: scale / resolution, mode: 'GRID', frameId: map.frame_id || '' } };
}

let summaryMap = null;
let summaryText = '';
let currentMap = null;
const families = new Map();
export function renderSavedOccupancyDetails(meta, map, api) {
  const host = document.getElementById('savedOccupancyDetails');
  host.hidden = meta?.kind !== 'occupancy2d';
  currentMap = null;
  if (host.hidden) return;
  if (!map || (map.map_id || map.id) !== meta.id || map.revision !== meta.revision) {
    host.textContent = '선택한 2D 지도 확인 중';
    return;
  }
  currentMap = map;
  if (summaryMap !== map) {
    const binary = atob(map.data_b64), counts = { occupied: 0, free: 0, unknown: 0 };
    for (let i = 0; i < binary.length; i++) counts[occupancyClass(binary.charCodeAt(i))]++;
    const percentages = Object.entries(counts).map(([name, count]) => name.toUpperCase() + ' ' + (100 * count / binary.length).toFixed(1) + '%');

    summaryText = [
      'ID ' + meta.id + ' · revision ' + map.revision,
      map.width + '×' + map.height + ' cells · ' + map.resolution + ' m/cell · origin [' + (map.origin || [0, 0, 0]).join(', ') + '] · ' + map.frame_id,
      percentages.join(' · '),

    ].filter(Boolean).join('\n');
    summaryMap = map;
  }
  const base = summaryText;
  const key = meta.id + ':' + map.revision;
  if (!families.has(key)) {
    families.set(key, api('/api/v1/saved-maps/' + encodeURIComponent(meta.id) + '/family')
      .then(payload => {
        if (payload.map_id !== meta.id || payload.map_revision !== map.revision) throw new Error('계보 revision 불일치');
        return payload.families?.find(family => family.occupancy.map_id === meta.id && family.occupancy.map_revision === map.revision);
      }).catch(() => null));
    while (families.size > 2) families.delete(families.keys().next().value);
  }
  host.textContent = base;
  families.get(key).then(family => {
    if (currentMap !== map) return;
    const source = family?.source, conversion = family?.conversion;
    const lineage = source
      ? '원본 PCD ' + source.pcd_map_id + ' · revision ' + source.pcd_revision + ' · ' + source.frame_id +
        '\nZ ' + conversion.z_min + '…' + conversion.z_max + ' m · XY bin ' + conversion.noise_radius +
        ' m · 최소 ' + conversion.min_neighbors + '점 · ' + conversion.background
      : '원본 PCD 계보 미확인';
    host.textContent = base + '\n' + lineage;
  });
}
export function conversionSummary(details) {
  if (!Number.isFinite(details?.source_points)) return '';
  return ' 원본 ' + details.source_points + ' → 유한점 ' + (details.finite_points ?? '미확인') +
    ' → Z 슬라이스 ' + details.z_slice_points + ' → XY 밀도 통과 ' + details.selected_points +
    '점 · occupied ' + details.occupied_cells + '셀.';
}
