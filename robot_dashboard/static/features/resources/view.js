import { valid, format, gib, mbps, cameraFresh, topicFresh, measurements, comparisonWindow, loadAverages, windowReady, summarize, guidance, exportCsv } from './model.js';

const $ = (id) => document.getElementById(id);
const history = [];
const events = [];
let baseline = null;
let latest = null;
let paused = false;
let timer = null;
let pending = null;
let available = false;
let averageAfter = -Infinity;
const text = (id, value) => { $(id).textContent = value; };
const timeLabel = (timestamp) => new Date(timestamp).toLocaleTimeString('ko-KR', { hour12: false });

function metric(id, value, unit) {
  const target = $(id);
  target.replaceChildren(document.createTextNode(format(value)));
  if (valid(value)) { const small = document.createElement('small'); small.textContent = unit; target.append(small); }
}

function bar(id, value) {
  const target = $(id);
  target.style.width = `${valid(value) ? Math.max(0, Math.min(100, value)) : 0}%`;
  const meter = target.parentElement;
  if (valid(value)) meter.setAttribute('aria-valuenow', String(value)); else meter.removeAttribute('aria-valuenow');
  meter.setAttribute('aria-valuetext', valid(value) ? `${format(value)}%` : '측정 불가');
  const card = target.closest('.metric-card');
  if (card) card.dataset.high = String(valid(value) && value >= Number($('loadThreshold').value));
}

function table(id, rows, empty, span) {
  const target = $(id); target.replaceChildren();
  if (!rows.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = span; td.className = 'empty'; td.textContent = empty; tr.append(td); target.append(tr); return; }
  for (const cells of rows) {
    const tr = document.createElement('tr');
    for (const cell of cells) { const td = document.createElement('td'); if (cell instanceof Node) td.append(cell); else td.textContent = cell; tr.append(td); }
    target.append(tr);
  }
}

function stateLabel(state, fresh) {
  const label = document.createElement('span'); label.className = 'state-label'; label.dataset.live = String(fresh);
  label.textContent = fresh ? '수신 중' : (state || '미확인'); return label;
}

function render(sample) {
  const m = measurements(sample);
  const averages = loadAverages(history, averageAfter);
  for (const key of ['cpu', 'gpu']) {
    const average = averages[key];
    metric(`${key}Value`, average.value, '%'); bar(`${key}Bar`, average.value);
    text(`${key}AverageLabel`, average.ready ? '최근 10초 평균' : average.count ? `평균 수집 중 · ${average.count}회` : '평균 측정 대기');
    text(`${key}Live`, valid(m[key].value) ? `현재 사용률 ${format(m[key].value)}%` : '현재 사용률 —');
  }
  const frequencies = (sample.cpu?.cores || []).filter((row) => row.online && valid(row.frequency_mhz) && row.frequency_mhz > 0).map((row) => row.frequency_mhz);
  const minFrequency = Math.min(...frequencies), maxFrequency = Math.max(...frequencies);
  const cpuClock = !frequencies.length ? '—' : minFrequency === maxFrequency ? `${format(minFrequency, 0)} MHz` : `${format(minFrequency, 0)}–${format(maxFrequency, 0)} MHz`;
  text('cpuDetail', `현재 클럭 ${cpuClock}`);
  text('cpuCoreDetail', `가장 바쁜 코어 ${format(sample.cpu?.max_core_percent)}% · ${sample.cpu?.cores?.filter((row) => row.online).length || 0}개 활성`);
  text('gpuDetail', `현재 클럭 ${valid(sample.gpu?.frequency_mhz) ? `${format(sample.gpu.frequency_mhz, 0)} MHz` : '—'}`);
  metric('ramValue', m.ram.value, '%'); bar('ramBar', m.ram.value);
  text('ramDetail', `${gib(sample.memory?.used_bytes)} / ${gib(sample.memory?.total_bytes)}`);
  metric('networkValue', valid(m.rx.value) && valid(m.tx.value) ? m.rx.value + m.tx.value : null, 'Mbps');
  text('rxValue', format(m.rx.value)); text('txValue', format(m.tx.value));
  metric('temperatureValue', m.temperature.value, '°C'); metric('powerValue', m.power.value, 'W');
  const hottest = [...(sample.thermal || [])].sort((a, b) => b.celsius - a.celsius)[0];
  text('temperatureSensor', hottest?.name || '측정 불가');
  const trip = hottest?.trips?.find((row) => row.type === 'passive') || hottest?.trips?.[0];
  text('temperatureDetail', trip ? `${trip.type} 기준 ${format(trip.celsius)}°C` : '온도 임계값 미확인');
  text('hostModel', sample.host?.model || 'Linux host'); text('hostName', sample.host?.hostname || '—');
  text('lastObserved', `${timeLabel(sample.timestamp_ms)} · ${format(sample.sample_interval_s)}초 간격`);
  text('swapValue', gib(sample.memory?.swap_used_bytes)); text('oomValue', valid(sample.oom_kill_delta) ? `${sample.oom_kill_delta}건` : '—');
  text('cpuPressure', valid(sample.pressure?.cpu) ? `${format(sample.pressure.cpu)}%` : '—');
  text('memoryPressure', valid(sample.pressure?.memory) ? `${format(sample.pressure.memory)}%` : '—');
  const guide = guidance(sample, Number($('loadThreshold').value));
  text('loadStatus', guide.high ? '높은 부하 관측' : guide.known ? '참고선 아래' : '부분 관측');
  text('loadNote', guide.high ? '설정 변경 전후의 수신률도 함께 확인하세요.' : '설정 하나씩 변경하며 부하와 수신률을 비교하세요.');
  $('loadDot').dataset.state = guide.high ? 'high' : guide.known ? 'ok' : 'waiting';
  $('adviceList').replaceChildren(...guide.rows.map((row) => { const li = document.createElement('li'); li.textContent = row; return li; }));
  $('coreList').replaceChildren(...(sample.cpu?.cores || []).map((row) => {
    const div = document.createElement('div'); div.className = 'core-row';
    const label = document.createElement('span'); label.textContent = row.name.toUpperCase();
    const value = document.createElement('span'); value.textContent = row.online ? `${format(row.percent)}%` : 'OFF';
    const track = document.createElement('div'); track.className = 'meter'; track.setAttribute('role', 'meter'); track.setAttribute('aria-label', `${row.name} 사용률`); track.setAttribute('aria-valuemin', '0'); track.setAttribute('aria-valuemax', '100');
    if (valid(row.percent)) track.setAttribute('aria-valuenow', String(row.percent));
    track.setAttribute('aria-valuetext', row.online ? `${format(row.percent)}%` : '코어 꺼짐');
    const fill = document.createElement('span'); fill.style.width = `${valid(row.percent) ? Math.min(100, Math.max(0, row.percent)) : 0}%`;
    if (row.percent >= Number($('loadThreshold').value)) fill.style.background = 'var(--amber)';
    track.append(fill); const freq = document.createElement('small'); freq.textContent = `${format(row.frequency_mhz, 0)} MHz`;
    div.append(label, value, track, freq); return div;
  }));
  if (!sample.cpu?.cores?.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = '코어 측정 불가'; $('coreList').append(p); }
  const sensorRows = [];
  for (const row of sample.sensors?.cameras || []) {
    const fresh = cameraFresh(row);
    sensorRows.push([row.label, stateLabel(row.state, fresh), row.width > 0 && row.height > 0 ? `${row.width} × ${row.height}` : '—', fresh ? `${format(row.receive_fps)} FPS` : '—', valid(row.age_s) ? `${format(row.age_s, 2)} s` : '—']);
  }
  for (const row of sample.sensors?.topics || []) sensorRows.push([`${row.selected ? '● ' : ''}${row.name}`, stateLabel(row.state, topicFresh(row)), row.category, topicFresh(row) ? `${format(row.hz)} Hz` : '—', valid(row.age_s) ? `${format(row.age_s, 2)} s` : '—']);
  table('sensorRows', sensorRows, sample.sensors?.topics_available || sample.sensors?.cameras_available ? '관측 중인 센서가 없습니다.' : 'ROS 관측 미연결 · 단독 모니터에서는 보드 자원만 표시합니다.', 5);
  table('networkRows', (sample.network?.interfaces || []).map((row) => [row.name, `${row.physical ? '물리' : '가상'} · ${row.state || '미확인'}`, `${format(mbps(row.rx_bytes_s))} Mbps`, `${format(mbps(row.tx_bytes_s))} Mbps`, `${format(row.speed_mbps, 0)} Mbps / ${format(row.link_percent)}%`, `${format(row.rx_dropped)} / ${format(row.tx_dropped)} · ${format(row.rx_errors)} / ${format(row.tx_errors)}`]), '네트워크 인터페이스 측정 불가', 6);
  table('processRows', (sample.processes?.items || []).map((row) => [row.name, row.pid, `${format(row.cpu_percent)}%`, gib(row.rss_bytes)]), '프로세스 측정 불가', 4);
  text('processScope', `${sample.processes?.scope || ''} · ${sample.processes?.observed || 0}개 관측${sample.processes?.truncated ? ' · 512개까지 수집' : ''}`);
  const detailRow = (label, value) => { const div = document.createElement('div'); div.className = 'thermal-row'; const span = document.createElement('span'); span.textContent = label; const b = document.createElement('b'); b.textContent = value; div.append(span, b); return div; };
  $('thermalList').replaceChildren(...(sample.thermal || []).map((row) => detailRow(row.name, `${format(row.celsius)}°C`)));
  $('powerList').replaceChildren(...(sample.power?.rails || []).map((row) => detailRow(row.name, `${format(row.watts, 2)} W`)));
  updateComparison(); drawChart();
}

function updateComparison() {
  const current = comparisonWindow(history, baseline?.end);
  $('baselineButton').disabled = !available || !windowReady(comparisonWindow(history));
  $('markButton').disabled = !available;
  $('exportButton').disabled = history.length === 0;
  if (!baseline) return;
  const ready = available && windowReady(current);
  const after = ready ? summarize(current) : {};
  text('comparisonStatus', ready ? `변경 전 ${baseline.count}개 / 변경 후 ${current.length}개 · 서로 겹치지 않는 측정 구간` : '변경 후 10초 이상의 연속 측정을 기다리는 중 · 통신 중단·일시정지 구간은 비교하지 않습니다.');
  const rows = Object.entries(baseline.values).slice(0, 20).map(([key, before]) => {
    const next = after[key]; const difference = valid(before.value) && valid(next?.value) ? next.value - before.value : null;
    const unit = before.unit === '%' ? '%p' : before.unit;
    return [before.label, `${format(before.value)} ${before.unit}`, `${format(next?.value)} ${before.unit}`, valid(difference) ? `${difference > 0 ? '+' : ''}${format(difference)} ${unit}` : '—'];
  });
  table('comparisonRows', rows, '비교 가능한 측정 없음', 4);
}

function clearLive(message, state = 'error') {
  available = false;
  averageAfter = latest?.timestamp_ms ?? -Infinity;
  text('connectionState', message); $('connectionState').dataset.state = state;
  text('loadStatus', message); text('loadNote', '이전 기록은 그래프와 CSV에 남아 있습니다.'); $('loadDot').dataset.state = state;
  for (const id of ['cpuValue', 'gpuValue', 'ramValue', 'networkValue', 'temperatureValue', 'powerValue', 'rxValue', 'txValue', 'swapValue', 'oomValue', 'cpuPressure', 'memoryPressure', 'temperatureSensor', 'lastObserved']) text(id, '—');
  for (const id of ['cpuBar', 'gpuBar', 'ramBar']) bar(id, null);
  for (const key of ['cpu', 'gpu']) { text(`${key}AverageLabel`, '평균 측정 대기'); text(`${key}Live`, '현재 사용률 —'); }
  text('cpuCoreDetail', '코어 측정 없음');
  text('cpuDetail', '실시간 측정 없음'); text('gpuDetail', '실시간 측정 없음'); text('ramDetail', '실시간 측정 없음'); text('temperatureDetail', '실시간 측정 없음');
  table('sensorRows', [], message, 5); table('networkRows', [], message, 6); table('processRows', [], message, 4);
  $('coreList').replaceChildren(); $('thermalList').replaceChildren(); $('powerList').replaceChildren();
  const li = document.createElement('li'); li.textContent = '현재 측정값을 확인할 수 없습니다.'; $('adviceList').replaceChildren(li);
  updateComparison();
}

async function poll() {
  if (paused || document.hidden || pending) return;
  const controller = new AbortController(); pending = controller;
  const timeout = setTimeout(() => controller.abort(), 4500);
  try {
    const response = await fetch('/api/v1/system/resources', { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const sample = await response.json();
    if (sample.schema !== 'robot-scope.resources.v1' || !valid(sample.timestamp_ms) || !valid(sample.seq)) throw new Error('invalid measurement');
    if (paused || document.hidden) return;
    available = true;
    const previous = history.at(-1);
    if (!previous || sample.seq !== previous.seq || sample.timestamp_ms !== previous.timestamp_ms) {
      // A wall-clock correction starts a new history, preventing invalid windows.
      if (previous && sample.timestamp_ms <= previous.timestamp_ms) { history.length = 0; baseline = null; averageAfter = -Infinity; text('baselineLabel', '서버 시간 변경 · 기준을 다시 저장하세요.'); table('comparisonRows', [], '기준을 다시 저장하세요.', 4); }
      history.push(sample);
      while (history.length > 901 || (history.length && history[0].timestamp_ms < sample.timestamp_ms - 900000)) history.shift();
    }
    latest = sample;
    text('connectionState', '● LIVE · 1초'); $('connectionState').dataset.state = 'live'; render(sample);
  } catch (error) {
    if (!paused && !document.hidden) clearLive(`연결 끊김${error.message.startsWith('HTTP') ? ` · ${error.message}` : ''}`);
  } finally {
    clearTimeout(timeout); pending = null;
    if (!paused && !document.hidden) timer = setTimeout(poll, 1000);
  }
}

function stopPolling() { clearTimeout(timer); timer = null; pending?.abort(); }

function addEvent(kind, note) {
  const event = { kind, note, timestamp_ms: latest.timestamp_ms };
  events.push(event); if (events.length > 100) events.shift();
  $('eventLog').replaceChildren(...events.slice(-8).reverse().map((row) => { const span = document.createElement('span'); span.className = 'event-tag'; span.textContent = `${timeLabel(row.timestamp_ms)} · ${row.kind === 'baseline' ? '기준' : '변경'} · ${row.note || '메모 없음'}`; return span; }));
  drawChart();
}

function drawChart() {
  const canvas = $('resourceChart'); const rect = canvas.getBoundingClientRect();
  if (!rect.width) return;
  const dpr = Math.min(devicePixelRatio || 1, 2); canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr);
  const context = canvas.getContext('2d'); if (!context) return; context.scale(dpr, dpr);
  const styles = getComputedStyle(document.documentElement);
  const color = (key) => styles.getPropertyValue(key).trim();
  const width = rect.width, height = rect.height, left = 34, right = width - 8, top = 12, bottom = height - 27;
  context.font = '10px monospace'; context.textAlign = 'right';
  for (const tick of [0, 25, 50, 75, 100]) {
    const y = bottom - tick / 100 * (bottom - top); context.fillStyle = color('--muted'); context.fillText(`${tick}`, left - 9, y + 3);
    context.strokeStyle = color('--line'); context.beginPath(); context.moveTo(left, y); context.lineTo(right, y); context.stroke();
  }
  if (!history.length) { context.fillStyle = color('--muted'); context.textAlign = 'center'; context.fillText('측정값을 기다리고 있습니다', width / 2, height / 2); return; }
  const end = history.at(-1).timestamp_ms, start = end - Number($('historyWindow').value) * 1000;
  const x = (timestamp) => left + (timestamp - start) / (end - start) * (right - left);
  context.textAlign = 'left'; context.fillStyle = color('--muted'); context.fillText(timeLabel(start), left, height - 5);
  context.textAlign = 'right'; context.fillText(timeLabel(end), right, height - 5);
  const thresholdY = bottom - Number($('loadThreshold').value) / 100 * (bottom - top);
  context.setLineDash([3, 5]); context.strokeStyle = color('--muted'); context.beginPath(); context.moveTo(left, thresholdY); context.lineTo(right, thresholdY); context.stroke(); context.setLineDash([]);
  context.save(); context.beginPath(); context.rect(left, top - 2, right - left, bottom - top + 4); context.clip();
  for (const [key, css] of [['cpu', '--green'], ['core', '--amber'], ['gpu', '--purple'], ['ram', '--cyan']]) {
    context.strokeStyle = color(css); context.lineWidth = key === 'core' ? 1 : 1.8; context.beginPath(); let previous = null;
    for (const row of history) {
      if (row.timestamp_ms < start) continue;
      const value = key === 'cpu' ? row.cpu?.percent : key === 'core' ? row.cpu?.max_core_percent : key === 'gpu' ? row.gpu?.percent : row.memory?.percent;
      if (!valid(value)) { previous = null; continue; }
      const y = bottom - Math.max(0, Math.min(100, value)) / 100 * (bottom - top);
      if (!previous || row.timestamp_ms - previous.timestamp_ms > 2500) context.moveTo(x(row.timestamp_ms), y); else context.lineTo(x(row.timestamp_ms), y);
      previous = row;
    }
    context.stroke();
  }
  for (const event of events) {
    if (event.timestamp_ms < start || event.timestamp_ms > end) continue;
    context.setLineDash([2, 5]); context.strokeStyle = color('--muted'); context.beginPath(); context.moveTo(x(event.timestamp_ms), top); context.lineTo(x(event.timestamp_ms), bottom); context.stroke(); context.setLineDash([]);
  }
  context.restore();
}

$('pauseButton').addEventListener('click', () => {
  paused = !paused; $('pauseButton').setAttribute('aria-pressed', String(paused)); text('pauseButton', paused ? '▶ 관측 재개' : 'Ⅱ 일시정지'); stopPolling();
  if (paused) clearLive('일시정지', 'paused'); else { clearLive('재연결 중', 'waiting'); if (!pending) poll(); }
});
$('baselineButton').addEventListener('click', () => {
  const rows = comparisonWindow(history); if (!available || !windowReady(rows)) return;
  baseline = { end: rows.at(-1).timestamp_ms, count: rows.length, values: summarize(rows) };
  const note = $('experimentNote').value.trim(); text('baselineLabel', `${timeLabel(baseline.end)} · ${note || '변경 전 기준'}`);
  addEvent('baseline', note); updateComparison();
});
$('markButton').addEventListener('click', () => { if (available && latest) addEvent('change', $('experimentNote').value.trim()); });
$('exportButton').addEventListener('click', () => {
  if (!history.length) return;
  const blob = new Blob([exportCsv(history, events)], { type: 'text/csv;charset=utf-8' }); const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = `jetson-resources-${new Date().toISOString().replaceAll(':', '-')}.csv`; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('loadThreshold').addEventListener('change', () => { if (available && latest) render(latest); else drawChart(); });
$('historyWindow').addEventListener('change', drawChart);
document.addEventListener('visibilitychange', () => { stopPolling(); if (document.hidden) clearLive('창 비활성 · 관측 중단', 'paused'); else if (!paused && !pending) { clearLive('재연결 중', 'waiting'); poll(); } });
new ResizeObserver(drawChart).observe($('resourceChart'));
new MutationObserver(drawChart).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
window.addEventListener('pagehide', stopPolling);
poll();
