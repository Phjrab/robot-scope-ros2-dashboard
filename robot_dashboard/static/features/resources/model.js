export const valid = (value) => typeof value === 'number' && Number.isFinite(value);
export const format = (value, digits = 1) => valid(value) ? value.toFixed(digits) : '—';
export const gib = (value) => valid(value) ? `${format(value / 1073741824, 2)} GiB` : '—';
export const mbps = (value) => valid(value) ? value * 8 / 1e6 : null;
export const cameraFresh = (camera) => camera.live === true && camera.state === 'ok' && valid(camera.age_s) && camera.age_s <= 3;
export const topicFresh = (topic) => topic.state === 'ok' && valid(topic.age_s) && topic.age_s <= 3;

export function measurements(sample) {
  const temperatures = (sample.thermal || []).map((row) => row.celsius).filter(valid);
  const rows = {
    cpu: { label: 'CPU 평균', value: sample.cpu?.percent, unit: '%' },
    core: { label: '가장 바쁜 코어', value: sample.cpu?.max_core_percent, unit: '%' },
    gpu: { label: 'GPU', value: sample.gpu?.percent, unit: '%' },
    ram: { label: '메모리 사용', value: sample.memory?.percent, unit: '%' },
    temperature: { label: '최고 온도', value: temperatures.length ? Math.max(...temperatures) : null, unit: '°C' },
    power: { label: '보드 전력', value: sample.power?.watts, unit: 'W' },
    rx: { label: '네트워크 RX', value: mbps(sample.network?.rx_bytes_s), unit: 'Mbps' },
    tx: { label: '네트워크 TX', value: mbps(sample.network?.tx_bytes_s), unit: 'Mbps' },
  };
  for (const camera of sample.sensors?.cameras || []) {
    rows[`camera:${camera.id}`] = { label: `${camera.label} 수신`, value: cameraFresh(camera) ? camera.receive_fps : null, unit: 'FPS' };
  }
  for (const topic of sample.sensors?.topics || []) {
    if (topic.category !== 'pointcloud' && !topic.selected) continue;
    rows[`topic:${topic.name}`] = { label: topic.name, value: topicFresh(topic) ? topic.hz : null, unit: 'Hz' };
  }
  return rows;
}

// Comparison windows never bridge a missing interval or overlap a saved baseline.
export function comparisonWindow(history, after = -Infinity) {
  if (!history.length) return [];
  const last = history.at(-1).timestamp_ms;
  const rows = [];
  for (let index = history.length - 1; index >= 0; index--) {
    const row = history[index];
    if (row.timestamp_ms <= after || row.timestamp_ms < last - 30000) break;
    if (rows.length && rows.at(-1).timestamp_ms - row.timestamp_ms > 2500) break;
    rows.push(row);
  }
  return rows.reverse();
}

export function windowReady(rows) {
  return rows.length >= 5 && rows.at(-1).timestamp_ms - rows[0].timestamp_ms >= 10000;
}

export function summarize(rows) {
  const values = {};
  for (const row of rows) {
    for (const [key, measurement] of Object.entries(measurements(row))) {
      values[key] ||= { ...measurement, samples: 0, sum: 0 };
      if (valid(measurement.value)) {
        values[key].sum += measurement.value;
        values[key].samples++;
      }
    }
  }
  for (const row of Object.values(values)) row.value = row.samples ? row.sum / row.samples : null;
  return values;
}

export function guidance(sample, threshold = 80) {
  const rows = [];
  const metric = measurements(sample);
  const known = ['cpu', 'core', 'gpu', 'ram'].every((key) => valid(metric[key].value));
  if (valid(metric.core.value) && metric.core.value >= threshold) rows.push('특정 CPU 코어의 부하가 높습니다. 센서 콜백·SLAM 처리 주기와 작업 분산을 확인하세요.');
  if (valid(metric.gpu.value) && metric.gpu.value >= threshold) rows.push('GPU 부하가 높습니다. 카메라 또는 모델 입력 해상도·FPS를 한 단계 낮추고 수신률과 비교하세요.');
  if (valid(metric.ram.value) && metric.ram.value >= threshold) rows.push('메모리 사용이 높습니다. 이미지·점군 버퍼와 지도 크기를 확인하세요.');
  if (valid(sample.memory?.swap_used_bytes) && sample.memory.swap_used_bytes > 0) rows.push('SWAP을 사용하고 있습니다. 사용량과 처리 지연이 함께 증가하는지 관찰하세요.');
  if (valid(sample.oom_kill_delta) && sample.oom_kill_delta > 0) rows.push('측정 간격 동안 OOM 종료가 발생했습니다. 작업을 늘리기 전에 메모리 사용을 확인하세요.');
  for (const thermal of sample.thermal || []) {
    const trip = (thermal.trips || []).find((item) => thermal.celsius >= item.celsius - 5);
    if (trip) { rows.push(`${thermal.name} 온도가 ${trip.type} 기준 ${format(trip.celsius)}°C에 가까워졌습니다. 냉각과 클럭 변화를 확인하세요.`); break; }
  }
  const interfaces = sample.network?.interfaces || [];
  if (interfaces.some((row) => row.physical && valid(row.link_percent) && row.link_percent >= threshold)) rows.push('유선 링크 사용률이 높습니다. 영상 비트레이트·점군 트래픽과 수신 손실을 확인하세요.');
  if (interfaces.some((row) => ['rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors'].some((key) => valid(row[key]) && row[key] > 0))) rows.push('네트워크 드롭 또는 오류가 증가하고 있습니다. 인터페이스별 카운터를 확인하세요.');
  if (!rows.length) rows.push(known ? '관측한 부하는 참고선 아래입니다. 해상도나 Hz를 하나씩 높이면서 실제 FPS·Hz·지연을 함께 확인하세요.' : '일부 자원을 읽지 못했습니다. 미측정 값과 CPU·네트워크 첫 변화량을 확인하세요.');
  return { rows, known, high: ['core', 'gpu', 'ram'].some((key) => valid(metric[key].value) && metric[key].value >= threshold) || (sample.oom_kill_delta || 0) > 0 };
}

export function csvCell(value) {
  let text = value == null ? '' : String(value);
  if (typeof value === 'string' && /^[\s]*[=+@-]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function exportCsv(history, events) {
  const headers = ['type', 'timestamp_utc', 'hostname', 'seq', 'interval_s', 'cpu_percent', 'max_core_percent', 'gpu_percent', 'gpu_mhz', 'memory_percent', 'memory_used_bytes', 'memory_available_bytes', 'swap_used_bytes', 'temperature_max_c', 'power_w', 'rx_mbps', 'tx_mbps', 'oom_kill_delta', 'cores_json', 'sensors_json', 'interfaces_json', 'note'];
  const lines = [headers.map(csvCell).join(',')];
  for (const sample of history) {
    const m = measurements(sample);
    const values = ['sample', new Date(sample.timestamp_ms).toISOString(), sample.host?.hostname, sample.seq, sample.sample_interval_s,
      m.cpu.value, m.core.value, m.gpu.value, sample.gpu?.frequency_mhz, m.ram.value, sample.memory?.used_bytes,
      sample.memory?.available_bytes, sample.memory?.swap_used_bytes, m.temperature.value, m.power.value, m.rx.value, m.tx.value,
      sample.oom_kill_delta, JSON.stringify(sample.cpu?.cores || []), JSON.stringify(sample.sensors || {}), JSON.stringify(sample.network?.interfaces || []), ''];
    lines.push(values.map(csvCell).join(','));
  }
  for (const event of events) {
    const values = Array(headers.length).fill('');
    values[0] = event.kind; values[1] = new Date(event.timestamp_ms).toISOString();
    values[headers.length - 1] = event.note;
    lines.push(values.map(csvCell).join(','));
  }
  return '\ufeff' + lines.join('\r\n');
}
