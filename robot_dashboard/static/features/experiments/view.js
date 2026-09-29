import {
  MAX_REPORT_BYTES,
  compareExperimentReports,
  poseMatrix,
  transformPreview,
  validateExperimentReport,
} from './report.js';

const byId = (id) => document.getElementById(id);
const setText = (id, value) => { byId(id).textContent = String(value); };
const number = (value, digits = 3) => Number.isFinite(value) ? value.toFixed(digits) : '—';
const shortHash = (value) => `${value.slice(0, 12)}…${value.slice(-8)}`;
let candidate = null;
let baseline = null;
let candidateGeneration = 0;
let baselineGeneration = 0;

const referenceScene = new window.RobotScene3D(byId('referenceCanvas'), {
  maxPoints: 256, showRobot: false, showTrail: false, autoFitOnFirstCloud: true,
});
const queryScene = new window.RobotScene3D(byId('queryCanvas'), {
  maxPoints: 256, showRobot: false, showTrail: false, autoFitOnFirstCloud: true,
});

function status(message, error = false) {
  const element = byId('experimentStatus');
  element.textContent = message;
  element.classList.toggle('error', error);
}

function poseFromMatrix(matrix) {
  const yaw = Math.atan2(matrix[1][0], matrix[0][0]);
  const pitch = Math.asin(Math.max(-1, Math.min(1, -matrix[2][0])));
  const roll = Math.atan2(matrix[2][1], matrix[2][2]);
  return { x: matrix[0][3], y: matrix[1][3], z: matrix[2][3], roll, pitch, yaw, frameId: 'map' };
}

function poseLabel(pose) {
  return `x ${number(pose.x)} · y ${number(pose.y)} · z ${number(pose.z)} m · `
    + `R ${number(pose.roll * 180 / Math.PI, 1)}° · P ${number(pose.pitch * 180 / Math.PI, 1)}° · Y ${number(pose.yaw * 180 / Math.PI, 1)}°`;
}

function renderCase() {
  if (!candidate) return;
  const item = candidate.cases.find((entry) => entry.id === byId('experimentCase').value);
  if (!item) return;
  const previous = baseline?.cases.find((entry) => entry.id === item.id);
  const initial = poseFromMatrix(item.initial_t_target_source);
  const estimate = {
    ...item.se3.pose,
    roll: item.se3.pose.roll_rad,
    pitch: item.se3.pose.pitch_rad,
    yaw: item.se3.pose.yaw_rad,
    frameId: 'map',
  };
  const truth = item.truth_t_target_source ? poseFromMatrix(item.truth_t_target_source) : null;
  referenceScene.setPointCloud({ points: item.target_preview_points, frame_id: 'map' }, { fit: true });
  queryScene.setPointCloud({
    points: transformPreview(item.source_preview_points, poseMatrix(item.se3.pose)), frame_id: 'map',
  }, { fit: true });
  referenceScene.setSpatialOverlay({ mapId: item.target_sha256, revision: item.target_sha256,
    frameId: 'map', markers: [{ id: 'initial', type: 'INITIAL', name: 'Initial seed', pose: initial }] });
  queryScene.setSpatialOverlay({ mapId: item.target_sha256, revision: item.target_sha256,
    frameId: 'map', markers: [{ id: 'estimate', type: 'ESTIMATE', name: 'Estimate', pose: estimate }] });
  setText('initialPose', poseLabel(initial));
  setText('estimatedPose', poseLabel(estimate));
  setText('truthPose', truth ? poseLabel(truth) : '정답 없음');
  setText('truthError', truth
    ? `${number(item.se3_position_error_m)} m · ${number(item.se3_rotation_error_deg, 2)}° (동일 지도 합성 정답)`
    : '정답 없음 · 정확도 계산 안 함');
  setText('caseDecision', `${item.se3.status} · ${item.se3.reason}`);
  setText('runtimeMetric', `${number(item.se3.metrics.runtime_ms, 1)} ms`);
  setText('qualityMetric', `${number(item.se3.metrics.overlap_ratio * 100, 1)}% · ${item.se3.metrics.rmse_m == null ? 'RMSE 없음' : `${number(item.se3.metrics.rmse_m, 4)} m`}`);
  setText('baselineMetric', previous
    ? `${previous.se3.status} → ${item.se3.status} · Δ ${(item.se3.metrics.runtime_ms - previous.se3.metrics.runtime_ms) >= 0 ? '+' : ''}${number(item.se3.metrics.runtime_ms - previous.se3.metrics.runtime_ms, 1)} ms`
    : '기준선 없음');
  setText('memoryMetric', `${candidate.peak_rss_platform_units ?? '—'} platform units · ${candidate.platform}`);
  setText('se2Metric', item.se2
    ? `${item.se2.status} · ${item.se2.z_roll_pitch} · ${number(item.se2.runtime_ms, 1)} ms`
    : '이 보고서에 SE2 실행 결과 없음');
  setText('dataKind', 'SYNTHETIC · 합성 입력 / 오프라인');
  setText('generatedAt', candidate.generated_at);
  setText('sourceCommit', candidate.source_commit + (candidate.source_tree_dirty ? ' · DIRTY SOURCE' : ''));
  setText('targetDigest', shortHash(item.target_sha256));
  setText('queryDigest', shortHash(item.source_sha256));
  setText('manifestDigest', shortHash(candidate.manifest_sha256));
  setText('moduleDigest', shortHash(candidate.module_sha256));
  setText('benchmarkDigest', shortHash(candidate.benchmark_sha256));
}

function render() {
  if (!candidate) {
    byId('experimentContent').hidden = true;
    return;
  }
  if (baseline) compareExperimentReports(baseline, candidate);
  const select = byId('experimentCase');
  const selected = select.value;
  select.replaceChildren();
  for (const item of candidate.cases) {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = `${item.id} · ${item.se3.status}`;
    select.append(option);
  }
  select.value = candidate.cases.some((item) => item.id === selected) ? selected : candidate.cases[0].id;
  byId('experimentContent').hidden = false;
  renderCase();
  status(`${candidate.case_count}개 합성 사례 · 후보 ${candidate.candidate_count} · false accept ${candidate.false_candidate_count} · ${baseline ? '동일 manifest 기준선 비교' : '단일 결과'} · 실시간 데이터 아님`);
}

async function readFile(file) {
  if (!file || file.size <= 0 || file.size > MAX_REPORT_BYTES) throw new Error('JSON 파일 크기가 허용 범위를 벗어났습니다 (최대 5 MB).');
  return validateExperimentReport(JSON.parse(await file.text()));
}

async function acceptFile(kind, file) {
  const generation = kind === 'candidate' ? ++candidateGeneration : ++baselineGeneration;
  try {
    const report = file ? await readFile(file) : null;
    if (generation !== (kind === 'candidate' ? candidateGeneration : baselineGeneration)) return;
    if (kind === 'candidate') candidate = report;
    else baseline = report;
    render();
  } catch (error) {
    console.error('Offline experiment report rendering failed', error);
    if (kind === 'candidate') candidate = null;
    else baseline = null;
    byId('experimentContent').hidden = true;
    status(error instanceof Error ? error.message : '결과 파일을 읽을 수 없습니다.', true);
  }
}

byId('candidateFile').addEventListener('change', (event) => acceptFile('candidate', event.target.files?.[0]));
byId('baselineFile').addEventListener('change', (event) => acceptFile('baseline', event.target.files?.[0]));
byId('experimentCase').addEventListener('change', renderCase);
