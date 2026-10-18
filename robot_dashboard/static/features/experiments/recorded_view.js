import { createRecordedLoader, matrixPose, recordedState, replayGeometry } from './recorded_report.js';
const el = (id) => document.getElementById(id);
const put = (id, value) => { el(id).textContent = value; };
const num = (v, n = 3) => Number.isFinite(v) ? v.toFixed(n) : '—';
const poseText = (p) => `X ${num(p.x)} · Y ${num(p.y)} · Z ${num(p.z)} m / R ${num(p.roll * 180 / Math.PI, 2)}° · P ${num(p.pitch * 180 / Math.PI, 2)}° · Y ${num(p.yaw * 180 / Math.PI, 2)}°`;
const metricText = (m) => m ? `${m.reference_points.toLocaleString()}점 기준 · RMSE ${num(m.rmse_m, 5)} m · overlap ${num(m.overlap_ratio * 100, 1)}% · gate ${m.correspondence_gate_m} m · query→reference` : '미제공';
let report = null;
const scene = new window.RobotScene3D(el('recordedCanvas'), {
  maxPoints: 100000, pointSize: .018, pointColor: '#50adc7', showRobot: false,
  worldFrameTrail: true, heightColor: false,
  robotPoseLabel: 'OFFLINE · REFERENCE ONLY',
});
scene.configureOfficialRobot({ poseOrigin: 'base', adaptiveScale: false, scale: 1 });
function modelState() {
  const s = scene.getOfficialRobotModelStatus();
  put('recordedModel', s.state === 'ready'
    ? 'Unitree Go2 · 공식 URDF 기반 경량 모델 · 1:1 m · 장착 센서 형상 없음'
    : `근사 도형 fallback · ${s.state} · 정밀 CAD 아님`);
}
function render(fit = false) {
  if (!report) return;
  const aligned = el('recordedAlignment').value === 'after';
  const geometry = replayGeometry(report, aligned);
  scene.setPointCloud({ points: report.target.points, frame_id: report.target.frame_id,
    data_provenance: report.data_kind === 'RECORDED_SENSOR' ? 'REPLAY' : 'SYNTHETIC_FIXTURE' }, { fit });
  scene.setPointCloudOverlay({ points: geometry.query, frame_id: report.target.frame_id, color: '#ffad54' });
  scene.options.robotPoseLabel = geometry.poseKind === 'QUERY_ORIGIN_REFERENCE'
    ? 'QUERY ORIGIN · BODY UNVERIFIED' : 'BODY CANDIDATE · UNVERIFIED';
  scene.setRobotVisible(Boolean(report.result) && el('recordedRobot').checked);
  scene.setRobotPose(report.result ? geometry.pose : null);
  scene.setTrail(geometry.trajectory.map(([x, y, z]) => ({ x, y, z, frameId: report.target.frame_id })));
  scene.setStatus({ online: null, snapshot: true, message: `${report.result?.status || 'NO_RESULT'} · OFFLINE DIAGNOSTIC` });
  el('recordedCenter').disabled = !report.result;
  put('recordedKind', `${report.data_kind} · ${recordedState(report)} · DIAGNOSTIC_ONLY`);
  put('recordedPoseCaveat', geometry.poseKind === 'QUERY_ORIGIN_REFERENCE'
    ? '모델은 query 세션 원점의 방향을 보여주는 참고 형상입니다. source→Go2 본체 변환이 없어 실제 본체 위치·자세로 해석할 수 없습니다.'
    : `미검증 body 후보 · ${report.body_relation.provenance} · 운영 자세로 적용하지 않습니다.`);
  const q = report.result;
  put('recordedDecision', q ? `${q.status} · ${q.reason}` : 'NO_RESULT · 지도와 원본 query만 표시');
  put('recordedPose', q ? poseText(matrixPose(q.T_target_source, report.target.frame_id)) : '변환 없음');
  put('recordedConvergence', q ? `${q.converged ? '수렴' : '미수렴'} · ${q.iterations}회 · 수렴과 수용 판정은 별개` : '없음');
  put('recordedTrajectory', `${report.trajectory.points.length}개 기록점 · ${report.trajectory.estimand} · 본체 궤적 미검증`);
  put('recordedSolver', metricText(q?.solver_metrics));
  put('recordedFull', metricText(q?.full_reference_metrics));
  put('recordedQualification', report.qualification);
  put('recordedFrames', `target ${report.target.frame_id} [${report.target.session_id}] ← source ${report.source.frame_id} [${report.source.session_id}] · ${geometry.coordinateMode}`);
  put('recordedTimestamp', `${report.source.stamp_ns} ns · ${report.source.clock_domain}`);
  put('recordedHashes', `target ${report.target.sha256} / query ${report.source.sha256}`);
  put('recordedDates', `${report.captured_at} / ${report.generated_at}`);
  put('recordedCommit', report.source_commit);
  put('recordedCounts', `지도 ${report.target.points.length}/${report.target.original_count} · query ${report.source.points.length}/${report.source.original_count}`);
  modelState();
}
const accept = createRecordedLoader((value, state, error) => {
  report = value;
  el('recordedContent').hidden = !report;
  put('recordedStatus', error ? `${state} · ${error}` : `${state} · ${report ? '로컬 기록 표시 · 현재 센서 연결 없음' : '저장 기록을 선택하세요.'}`);
  el('recordedStatus').classList.toggle('error', Boolean(error));
  scene.clearPointCloud(); scene.setRobotPose(null); scene.setRobotVisible(false); scene.setTrail([]);
  if (report) {
    el('recordedAlignment').value = report.result ? 'after' : 'before';
    el('recordedAlignment').disabled = !report.result;
    scene.resize(); render(true);
    scene.loadOfficialRobotModel().then(() => { if (report) modelState(); }).catch(() => { if (report) modelState(); });
  }
});
el('recordedFile').addEventListener('change', (e) => accept(e.target.files?.[0]));
el('clearRecorded').addEventListener('click', () => { el('recordedFile').value = ''; accept(null); });
el('recordedAlignment').addEventListener('change', () => render());
el('recordedRobot').addEventListener('change', () => render());
el('recordedFit').addEventListener('click', () => scene.fitToPointCloud());
el('recordedCenter').addEventListener('click', () => scene.centerOnPose());
