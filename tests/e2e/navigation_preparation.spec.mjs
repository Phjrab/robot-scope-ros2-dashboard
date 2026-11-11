// DOM and HTTP fixtures only: no ROS, control bridge or robot consumer.
import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';

const cloud = { id: 'a'.repeat(24), revision: 'b'.repeat(64), kind: 'pointcloud3d', name: 'map1' };
const grid = { id: 'c'.repeat(24), revision: 'd'.repeat(64), kind: 'occupancy2d', name: 'map1_2D', frame_id: 'map' };

async function mount(page) {
  await page.evaluate(async ({ cloud, grid }) => {
    const { initializeNavigationPreparation } = await import('/features/navigation/preparation.js');
    window.fixtureContext = { maps: [cloud, grid], map: grid, navigation: { pipeline: { state: 'idle' }, goal: { state: 'idle' } } };
    window.fixtureActions = []; window.fixtureScrolls = 0;
    window.scrollTo = () => { window.fixtureScrolls++; };
    Element.prototype.scrollIntoView = () => { window.fixtureScrolls++; };
    window.preparation = initializeNavigationPreparation({ host: document.querySelector('#host'), map3dSelect: document.querySelector('#cloud'), map2dSelect: document.querySelector('#grid'),
      getOperatorDraft: () => window.fakeOperatorDraft || { status: 'none' },
      api: async (path, options) => { const response = await fetch(path, options); const value = await response.json(); if (!response.ok) throw new Error(value.detail); return value; },
      context: () => window.fixtureContext, onChange: () => {},
      actions: Object.fromEntries(['start', 'initial', 'goal', 'refresh'].map(key => [key, () => window.fixtureActions.push(key)])) });
    window.preparation.render(); await window.preparation.refresh(true);
  }, { cloud, grid });
}

async function fixture(page) {
  const state = { selected: null, pair: null, runtime: null, initialization_handoff: null }, writes = [], reads = [];
  const observation = { state: 'STOPPED', active: false, can_start: true, can_stop: false, reason: '정지' };
  const inputs = { schema: 'robot-scope.navigation-preparation-inputs.v1', pair: null, observation, start_blockers: { items: [], advisory: true },
    evidence: { valid: false, reason: 'OBSERVATION_INACTIVE', cloud: null, pose: null, calibration_sha256: null }, reference_pose: null,
    candidates: Object.fromEntries(['z', 'roll', 'pitch'].map(key => [key, { value: null, frame: 'map', available: false, reason: 'OBSERVATION_INACTIVE', provenance: null }])) };
  let reject = false, failingReads = 0, heldWrites = null, releaseWrite = null;
  let rejectObservation = false;
  let invalidOperationalState = false;
  let proposalState = 'ready', proposalReason = null, proposalRejected = false, wrongProposalSource = false, ambiguousProposal = false, geometryPreview = 'valid', proofMode = 'valid', proposalReads = null, releaseProposalReads = null, heldProposalReadCount = 0;
  let proposalCleanup = { state: 'SETTLED', cancellation_requested: false, worker_active: false, terminal_state: 'succeeded' };
  let confirmedGeometry = { z: .84, roll: .11, pitch: .12 }, currentPrior = null, proposalCount = 0, distinctProposalIds = false, nextProposalRunsOnce = false, currentProposalId = 'f'.repeat(24);
  let handoff = null, confirmMode = 'success', heldConfirm = null, releaseConfirm = null, heldHandoffRead = null, releaseHandoffRead = null;
  let heldInputsRead = null, releaseInputsRead = null;
  await page.route('**/api/v1/observations/fastlio/**', async route => {
    const path = new URL(route.request().url()).pathname, body = route.request().postDataJSON();
    writes.push({ path, method: route.request().method(), body });
    if (rejectObservation) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '다른 작업을 먼저 종료하세요: control_bridge_not_inactive' }) });
    if (path.endsWith('/start')) Object.assign(observation, { state: 'READY', active: true, can_start: false, can_stop: true, session_id: 'a'.repeat(32), reason: '입력 준비 완료' });
    else Object.assign(observation, { state: 'STOPPED', active: false, can_start: true, can_stop: false, session_id: null });
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(observation) });
  });
  await page.route('**/software-preparation.html', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/styles.css"><main style="padding:24px"><label>3D 위치추정 지도<select id="cloud"></select></label><label>2D 경로 계산 지도<select id="grid"><option>${grid.name}</option></select></label><article class="panel navigation-preparation-panel" id="host"></article></main>` }));
  await page.route('**/api/v1/navigation/operational-3d**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method();
    const body = route.request().postDataJSON();
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (method === 'GET') reads.push(path);
    if (path.endsWith('/preparation-inputs')) {
      if (failingReads > 0) { failingReads--; return json({ detail: 'SYNTHETIC_READ_TIMEOUT' }, 503); }
      if (invalidOperationalState) return json({ ...inputs, operational_state: null, operational_state_error: 'CONTEXT_CHANGED' });
      const snapshot = structuredClone({ ...inputs, operational_state: { ...state, pair: state.pair && { ...state.pair, generation: state.selected?.generation, calibration_sha256: inputs.pair?.calibration_sha256 }, activation: state.selected ? 'NEXT_NAVIGATION_START' : 'LEGACY_2D' }, operational_state_error: null });
      if (heldInputsRead) await heldInputsRead;
      return json(snapshot);
    }
    if (method !== 'GET') writes.push({ path, method, body });
    if (path.endsWith('/confirm-geometry')) {
      if (confirmMode === 'reject') return json({ detail: 'GLOBAL_AMBIGUOUS' }, 409);
      const id = 'e'.repeat(32), session = observation.session_id;
      const resolution = currentPrior ? makeProof(currentPrior) : null;
      handoff = { schema: 'robot-scope.proposal-geometry-handoff.v1', handoff_id: id, proposal_id: 'f'.repeat(24),
        state: 'CONFIRMED_OBSERVATION_ACTIVE', reason: null, source: 'proposal_confirmed', frame: 'map',
        bundle_generation: state.selected.generation, observation_session_id: session, job_id: null, expires_in_s: 119,
        policy: { id: currentPrior ? 'robot-scope.proposal-handoff.operator-prior-v1' : 'robot-scope.proposal-handoff.local-v1', ttl_s: 120, max_xy_m: .25, max_yaw_rad: .20 },
        continuity: 'SUPERVISED_GAP_UNMEASURED', stop_receipt: { state: 'NOT_REQUESTED' },
        geometry: { ...confirmedGeometry }, initial_pose_reference: { x: 1, y: 2, yaw: .3 }, operational_application: 'NOT_RUN' };
      state.selected.seed_geometry = { ...handoff.geometry, source: 'proposal_confirmed', handoff: { handoff_id: id, proposal_id: 'f'.repeat(24), bundle_generation: state.selected.generation, calibration_sha256: inputs.pair.calibration_sha256, observation_session_id: session, ...(resolution ? { policy_id: 'robot-scope.proposal-handoff.operator-prior-v1', source_contract_sha256: '8'.repeat(64), operator_prior_resolution: resolution, ...(resolution.grouping_policy ? { operator_prior_current_members: {pose_stamp_ns:'1234',member_checks:currentMembers().member_checks} } : {}) } : {}) } };
      state.initialization_handoff = handoff; state.pair.can_start = false;
      if (heldConfirm) await heldConfirm;
      return confirmMode === 'lost' ? json({ detail: 'SYNTHETIC_RESPONSE_LOST' }, 503) : json(handoff);
    }
    if (path.includes('/initialization-handoffs/')) {
      const snapshot = handoff ? structuredClone(handoff) : null;
      if (heldHandoffRead) await heldHandoffRead;
      return snapshot ? json(snapshot) : json({ detail: 'HANDOFF_NOT_FOUND' }, 404);
    }
    function makeProof(prior) { const proof = { schema:'robot-scope.operator-prior-resolution.v1', prior_id:'9'.repeat(32), operator_prior:structuredClone(prior),
      accepted_monotonic_s:100, expires_monotonic_s:220, prior_anchor_stamp_ns:'123', bundle_generation:inputs.pair.generation,
      observation_session_id:observation.session_id, calibration_sha256:inputs.pair.calibration_sha256, localization_3d:inputs.pair.localization_3d,
      navigation_2d:inputs.pair.navigation_2d, source_contract_sha256:'8'.repeat(64), original_observation_sha256:'7'.repeat(64), candidate_index:0,
      retained_candidate_count:2, eligible_candidate_count:2, matching_candidate_count:1, projection_basis:'NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE',
      classification:'CONDITIONAL_ON_OPERATOR_PRIOR', original_ambiguity_preserved:true, original_ambiguity_unresolved:proofMode !== 'original-unambiguous', global_uniqueness_verified:false, absolute_accuracy_m:null,
      candidate_vs_prior:{xy_distance_m:.1,absolute_wrapped_yaw_rad:.1,within_existing_handoff_reference:true} };
      if (!Object.hasOwn(prior, 'bounds')) Object.assign(proof, { bounds_source:'server_policy', effective_bounds:{xy_m:.25,yaw_rad:.20} });
      if (proofMode.startsWith('group-')) Object.assign(proof, {grouping_policy:'PINNED_V031_SE3_FIRST_REPRESENTATIVE_V1',matching_candidate_count:2,matching_hypothesis_count:proofMode === 'group-two' ? 2 : 1,matching_retained_candidate_count:2,matching_member_indices:[0,1],verified_duplicate_count:1,matching_member_geometry:[{candidate_index:0,z_m:.84,roll_rad:.11,pitch_rad:.12,z_delta_m:0,roll_delta_rad:0,pitch_delta_rad:0},{candidate_index:1,z_m:.85,roll_rad:.12,pitch_rad:.11,z_delta_m:.01,roll_delta_rad:.01,pitch_delta_rad:-.01}]});
      if (proofMode === 'group-ttl-exact' || proofMode === 'group-ttl-next') {
        proof.accepted_monotonic_s = 8.000000000000016;
        proof.expires_monotonic_s = proof.accepted_monotonic_s + 120;
        if (proofMode === 'group-ttl-next') {
          const view = new DataView(new ArrayBuffer(8)); view.setFloat64(0, proof.expires_monotonic_s, false);
          view.setBigUint64(0, view.getBigUint64(0, false) + 1n, false); proof.expires_monotonic_s = view.getFloat64(0, false);
        }
      }
      if (proofMode === 'group-new-proof') proof.prior_id = '4'.repeat(32);
      return proof; }
    function currentMembers() { const outside = proofMode === 'group-outside'; return {pose_stamp_ns:'1234',pose_age_s:proofMode === 'group-aged' ? 1 : 0,xy_distance_m:.1,yaw_delta_rad:.1,within_prior_bounds:true,within_existing_handoff_reference:true,all_members_within_prior_bounds:!outside,member_checks:[{candidate_index:0,xy_distance_m:.1,absolute_wrapped_yaw_rad:.1,within_prior_bounds:true},{candidate_index:1,xy_distance_m:outside ? 1 : .11,absolute_wrapped_yaw_rad:.09,within_prior_bounds:!outside}]}; }

    if (path.includes('/initialization-proposals')) {
      if (method === 'POST') { currentPrior = body?.operator_prior || null; currentProposalId = (++proposalCount > 1 && distinctProposalIds ? 'e' : 'f').repeat(24); }
      if (method === 'POST' && proposalRejected) return json({ detail: 'GLOBAL_BACKEND_UNAVAILABLE' }, 503);
      if (method === 'GET' && proposalReads) { heldProposalReadCount++; await proposalReads; }
      const pose = { x: 1, y: 2, z: .4, roll: .1, pitch: .2, yaw: .3 };
      const proof = currentPrior ? makeProof(currentPrior) : null;
      if (proof && proofMode === 'policy-missing') delete proof.bounds_source;
      if (proof && proofMode === 'policy-changed') proof.effective_bounds.xy_m = .3;
      if (proof && proofMode === 'policy-forged') proof.bounds_source = 'operator_prior';
      if (proof && proofMode === 'multiple') proof.matching_candidate_count = 2;
      if (proof && proofMode === 'original-unambiguous') proof.original_ambiguity_unresolved = false;
      if (proof && proofMode === 'original-mismatch') proof.original_ambiguity_unresolved = false;
      if (proof && proofMode === 'different-prior') proof.operator_prior.pose.x += 1;
      if (proof && proofMode === 'beyond-handoff') Object.assign(proof.candidate_vs_prior, { xy_distance_m:.3, within_existing_handoff_reference:false });
      const result = { schema: 'robot-scope.navigation-initialization-proposal.v1', proposal_id: currentProposalId,
        state: method === 'POST' ? 'capturing' : proposalState, reason: proposalReason,
        pair: inputs.pair, observation_session_id: observation.session_id, operational_application: 'NOT_RUN', absolute_accuracy_m: null,
        imu_hypothesis: method === 'GET' && proposalState === 'ready' ? { frame: 'camera_init', pose_reference: 'FASTLIO_IMU', units: 'metres_degrees', pose, approximate_only: true, requires_reanchor: true } : null,
        body_candidate: method === 'GET' && proposalState === 'ready' ? { frame: 'camera_init', pose_reference: 'base_link', units: 'metres_radians', pose, qualification: 'INFORMATIONAL_LOCALIZATION_MAP_ONLY' } : null,
        navigation_geometry_candidate: method === 'GET' && proposalState === 'ready' && geometryPreview !== 'missing' ? { frame: geometryPreview === 'bad-frame' ? 'camera_init' : 'map', pose_reference: 'base_link', units: 'metres_radians', pose: { z: .84, roll: .11, pitch: .12 } } : null,
        ...(method === 'GET' && proposalState === 'ready' && currentPrior ? { classification:'CONDITIONAL_ON_OPERATOR_PRIOR', operator_prior_resolution: ambiguousProposal ? null : proof, ...(proof?.grouping_policy && proofMode !== 'group-missing-current' ? { current_vs_prior:currentMembers() } : {}) } : {}),
        quality: method === 'GET' && proposalState === 'ready' ? { overlap: .7, rmse_m: .1, hypothesis_overlap_min: .6, operational_initial_overlap_min: .85, ambiguity_unresolved: currentPrior ? proofMode !== 'original-unambiguous' : ambiguousProposal, residual_selection_gate_enabled: false, qualification: 'GLOBAL_HYPOTHESIS_ONLY_NOT_OPERATIONAL_QUALITY' } : null,
        provenance: method === 'GET' && proposalState === 'ready' ? { pose_age_s: proofMode === 'group-bad-age' ? null : 0, capture_age_s: 15, source_contract: { observer_id: '1'.repeat(32), cloud_epoch: (wrongProposalSource ? '4' : '2').repeat(32), pose_epoch: '3'.repeat(32) } } : null,
        cleanup: method === 'POST' ? { state: 'MONITORING', cancellation_requested: false } : proposalCleanup };
      if (method === 'GET' && proposalCount > 1 && nextProposalRunsOnce) {
        nextProposalRunsOnce = false; result.state = 'running'; result.imu_hypothesis = null; result.body_candidate = null;
        result.navigation_geometry_candidate = null; result.quality = null; result.provenance = null;
        delete result.classification; delete result.operator_prior_resolution; delete result.current_vs_prior;
      }
      if (method === 'GET' && proofMode === 'group-new-id') result.proposal_id = 'e'.repeat(24);
      return json(result, method === 'POST' ? 202 : 200);
    }
    if (method === 'GET' && failingReads > 0) { failingReads--; return json({ detail: 'SYNTHETIC_READ_TIMEOUT' }, 503); }
    if (method !== 'GET' && heldWrites) await heldWrites;
    if (reject && method !== 'GET') return json({ detail: 'PAIR_COORDINATE_RELATION_UNVERIFIED' }, 409);
    if (path.endsWith('/pair')) {
      state.selected = { workflow: 'staged_navigation_pair', generation: 'pairgen',
        localization_3d: { map_id: cloud.id, revision: cloud.revision }, navigation_2d: { map_id: grid.id, revision: grid.revision },
        calibration: { verified: true }, seed_geometry: null, map_binding: { source: 'operator_confirmed' } };
      state.pair = { can_start: false };
      inputs.pair = { generation: 'pairgen', valid: true, localization_3d: state.selected.localization_3d, navigation_2d: state.selected.navigation_2d };
    }
    if (path.endsWith('/seed-geometry')) { state.selected.seed_geometry = { ...body, source: 'USER_CONFIRMED_NAV_BASE', confirmed_at: 1793444400 }; state.pair.can_start = true; }
    if (method === 'DELETE') { state.selected = null; state.pair = null; }
    return json(state);
  });
  await page.goto('/software-preparation.html');
  await mount(page);
  return { state, inputs, observation, writes, reads, reject(value) { reject = value; }, rejectObservation(value) { rejectObservation = value; }, failReads(count) { failingReads = count; }, invalidStatus(value) { invalidOperationalState = value; },
    proposalStatus(value, reason = null) { proposalState = value; proposalReason = reason; }, rejectProposal(value) { proposalRejected = value; }, wrongProposalSource(value) { wrongProposalSource = value; }, ambiguousProposal(value) { ambiguousProposal = value; }, geometryPreview(value) { geometryPreview = value; }, proofMode(value) { proofMode = value; },
    cleanup(value) { proposalCleanup = value; },
    handoff() { return handoff; }, confirmMode(value) { confirmMode = value; }, confirmedGeometry(value) { confirmedGeometry = value; },
    holdConfirm() { heldConfirm = new Promise(resolve => { releaseConfirm = resolve; }); },
    releaseConfirm() { releaseConfirm?.(); heldConfirm = null; releaseConfirm = null; },
    holdHandoffRead() { heldHandoffRead = new Promise(resolve => { releaseHandoffRead = resolve; }); },
    releaseHandoffRead() { releaseHandoffRead?.(); heldHandoffRead = null; releaseHandoffRead = null; },
    holdInputsRead() { heldInputsRead = new Promise(resolve => { releaseInputsRead = resolve; }); },
    releaseInputsRead() { releaseInputsRead?.(); heldInputsRead = null; releaseInputsRead = null; },
    async reload() { await page.reload(); await mount(page); },
    holdProposalReads() { proposalReads = new Promise(resolve => { releaseProposalReads = resolve; }); },
    heldProposalReadCount() { return heldProposalReadCount; }, distinctProposalIds() { distinctProposalIds = true; }, runNextProposalOnce() { nextProposalRunsOnce = true; },
    releaseProposalReads() { releaseProposalReads?.(); proposalReads = null; releaseProposalReads = null; },
    holdWrites() { heldWrites = new Promise(resolve => { releaseWrite = resolve; }); },
    releaseWrites() { releaseWrite?.(); heldWrites = null; releaseWrite = null; } };
}

test('map selection is passive, missing geometry is explicit, retry resumes without repeated pair application', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  expect(f.writes).toHaveLength(0);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.getByRole('region', { name: '준비 상태·해결할 항목' })).toContainText('초기 높이·기울기 미확인');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await page.getByRole('button', { name: '초기 높이·기울기 저장' }).click();
  await expect(page.getByRole('region', { name: '준비 상태·해결할 항목' })).toContainText('빈 값은 0으로 처리하지 않습니다');
  expect(f.writes).toHaveLength(1);
  await page.getByLabel('높이 z (m)').fill('0.34');
  await page.getByLabel('roll (rad)', { exact: true }).fill('0.01');
  await page.getByLabel('pitch (rad)', { exact: true }).fill('-0.02');
  await page.getByRole('button', { name: '초기 높이·기울기 저장' }).click();
  await expect.poll(() => page.evaluate(() => window.preparation.canStart())).toBe(true);
  expect(f.writes.map(value => value.path)).toEqual(['/api/v1/navigation/operational-3d/pair', '/api/v1/navigation/operational-3d/seed-geometry']);
  expect(f.writes[1].body).toEqual({ generation: 'pairgen', z: .34, roll: .01, pitch: -.02 });
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await expect(page.locator('[data-prep="steps"]')).toContainText('아래 주행 조작부에서 Nav2를 시작하세요.');
  for (const name of ['Nav2 시작', 'INITIAL POSE 지정', 'GOAL POSE 지정']) await expect(page.locator('#host').getByRole('button', { name, exact: true })).toHaveCount(0);
  await page.evaluate(() => { window.preparation.render(); window.preparation.render(); });
  expect(await page.evaluate(() => window.fixtureScrolls)).toBe(0);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
});

test('user map confirmation is required, consumed and invalidated by revision changes', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  const consent = page.locator('[data-prep="pair-confirmation"]');
  const apply = page.getByRole('button', { name: '① 지도 연결 확인·적용' });
  await expect(consent).not.toBeChecked();
  await expect(apply).toBeDisabled();
  await consent.check();
  await expect(apply).toBeEnabled();
  await page.evaluate(() => {
    window.fixtureContext.map.revision = 'e'.repeat(64);
    window.preparation.render();
  });
  await expect(consent).not.toBeChecked();
  await expect(apply).toBeDisabled();
  expect(f.writes).toHaveLength(0);
  await page.evaluate(revision => { window.fixtureContext.map.revision = revision; window.preparation.render(); }, grid.revision);
  await consent.check();
  await apply.click();
  await expect.poll(() => f.writes.length).toBe(1);
  expect(f.writes[0].body).toEqual({ map_id: cloud.id, map_revision: cloud.revision,
    navigation_map_id: grid.id, navigation_map_revision: grid.revision, pair_confirmation: 'derived_same_coordinates' });
  await expect(consent).not.toBeChecked();
  await expect(page.locator('[data-prep="steps"]')).toContainText('사용자 확인에 따른 지도 연결');
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.reload(); await mount(page);
  await expect(consent).not.toBeChecked();
  expect(f.writes).toHaveLength(1);
});

test('server rejection stays visible and exact pair can be rechecked; active runtime locks maps', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  f.reject(true);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.getByRole('region', { name: '준비 상태·해결할 항목' })).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  f.reject(false);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="selected"]')).toContainText('적용한 준비 구성: map1 / map1_2D');
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'running'; window.preparation.render(); });
  await expect(page.getByLabel('3D 위치추정 지도')).toBeDisabled();
  await expect(page.getByRole('button', { name: '① 지도 연결 확인·적용' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '기존 2D 모드로 복구' })).toBeDisabled();
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'idle'; window.preparation.render(); });
  await page.getByRole('button', { name: '기존 2D 모드로 복구' }).click();
  await expect(page.getByLabel('3D 위치추정 지도')).toHaveValue('');
  expect(f.writes.at(-1).method).toBe('DELETE');
});

test('initial receipt requires explicit match and ready receipt never sends a goal; stale remains visible', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  // The click dispatches an async mutation and follow-up read. Let both settle
  // before changing the fixture, so a queued old read cannot replace the seed.
  await expect(page.locator('[data-prep="clear"]')).toBeEnabled();
  f.state.selected.seed_geometry = { z: .34, roll: 0, pitch: 0, source: 'operator', confirmed_at: 1793444400 };
  f.state.pair.can_start = true;
  await page.evaluate(() => window.preparation.refresh(true));
  await page.evaluate(({ cloud, grid }) => {
    const pin = { map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
      bundle_generation: 'pairgen', localization_generation: 2, runtime_instance_generation: 'process',
      pose: { x: 1, y: 2, z: .34, roll: 0, pitch: 0, yaw: 1 }, stamp_ns: '123' };
    Object.assign(window.fixtureContext.navigation, { map: grid, pipeline: { state: 'running', job_id: 'job' },
      safety: { can_set_initial_pose: true, can_send_goal: false }, operational_localization: {
        ...pin, source: 'STORED_PCD_FASTLIO', fresh: true, ready: false, state: 'WAITING_EXPLICIT_MAP_MATCH', correction_sequence: 0,
        accepted_initial_pose: { ...pin, accepted: true } } });
    window.preparation.render();
  }, { cloud, grid });
  await expect(page.getByRole('button', { name: '정합 시작', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '정합 시작', exact: true }).click();
  expect(f.writes.at(-1).body).toEqual({ map_id: grid.id, map_revision: grid.revision, bundle_generation: 'pairgen', localization_generation: 2, initial_pose_stamp_ns: '123' });
  await page.evaluate(() => {
    const nav = window.fixtureContext.navigation, source = nav.operational_localization;
    source.estimated_pose = { ...source.accepted_initial_pose, pose: { ...source.accepted_initial_pose.pose, x: 1.04 }, stale: false };
    source.state = 'MAP_TRACKING'; source.ready = true; source.correction_sequence = 4;
    nav.safety.can_send_goal = true; window.preparation.render();
  });
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(true);
  await expect(page.locator('[data-prep="steps"]')).toContainText('아래 지도 조작부에서 GOAL POSE를 지정·전송하세요.');
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.evaluate(() => { const source = window.fixtureContext.navigation.operational_localization; source.ready = false; source.estimated_pose.stale = true; source.state = 'MAP_CORRECTION_STALE'; window.preparation.render(); });
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  await expect(page.locator('[data-prep="steps"]')).toContainText('마지막 추정 위치');
  await page.locator('#host').screenshot({ path: 'test-results/navigation-preparation-stale.png' });
  expect(f.writes.filter(write => write.path.endsWith('/goal'))).toHaveLength(0);
});

async function completeOperatorDraftForStageOne(page, fixture) {
  fixture.inputs.pair.calibration_sha256 = 'c'.repeat(64);
  await page.evaluate(() => window.preparation.refresh(true));
  await page.evaluate(({ cloud, grid }) => {
    window.fakeOperatorDraft = { status: 'ready', revision: 1, pose: { x: 1, y: 2, yaw: .1 },
      bundle_generation: window.preparation.state().selected.generation,
      localization_map: { id: cloud.id, revision: cloud.revision }, navigation_map: { id: grid.id, revision: grid.revision } };
    window.preparation.draftChanged();
  }, { cloud, grid });
  await page.getByLabel(/이 초안이 현재 지도에서 정지/).check();
}

test('server checks invalidate only their dependent stages and current execution ignores a previous success', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  f.state.pair = { valid: false, can_start: false, restart_from_step: 1,
    checks: [{ code: 'MAP_PAIR_LINEAGE_CHANGED', current: '변환 계보가 변경됨', required: '현재 연결 검증', remedy: '①부터 다시 확인' }] };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('변환 계보가 변경됨');
  await expect(page.locator('[data-prep="steps"] > li').nth(0)).toHaveAttribute('data-state', '오류');
  f.state.selected.seed_geometry = { z: .34, roll: 0, pitch: 0 };
  f.state.pair = { valid: true, can_start: false, restart_from_step: 2,
    checks: [{ code: 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED', current: '이전 실행에서 사용한 높이', required: '현재 값', remedy: '②에서 재확인' }] };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="steps"] > li').nth(0)).toHaveAttribute('data-state', '사용자 입력 필요');
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 1.');
  await expect(page.locator('[data-prep="issues"]')).toContainText('이전 실행에서 사용한 높이');
  await completeOperatorDraftForStageOne(page, f);
  await expect(page.locator('[data-prep="steps"] > li').nth(0)).toHaveAttribute('data-state', '완료');
  await expect(page.locator('[data-prep="steps"] > li').nth(1)).toHaveAttribute('data-state', '사용자 입력 필요');
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 2.');
  await page.evaluate(({ grid }) => {
    const nav = window.fixtureContext.navigation;
    nav.pipeline = { state: 'running', job_id: 'new-job' }; nav.map = grid;
    nav.goal = { state: 'succeeded', goal_id: 'previous', precision_evidence: { goal_id: 'previous', context: { job_id: 'old-job', map_id: grid.id, map_revision: grid.revision } } };
    window.preparation.render();
  }, { grid });
  await expect(page.locator('[data-prep="steps"] > li').nth(5)).toHaveAttribute('data-state', '미시작');
  expect(f.writes).toHaveLength(1);
});

test('automatic fresh status clears a recovered read failure without losing the current preparation step', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="steps"] > li').nth(0)).toHaveAttribute('data-state', '사용자 입력 필요');
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 1.');
  await completeOperatorDraftForStageOne(page, f);
  await expect(page.locator('[data-prep="steps"] > li').nth(0)).toHaveAttribute('data-state', '완료');
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 2.');
  f.failReads(1);
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('상태 확인 실패');
  await expect(page.locator('[data-prep="details"]')).toContainText('SYNTHETIC_READ_TIMEOUT');
  // The dashboard calls this same refresh from its periodic navigation reads.
  // There is no operator click, pose input, or write retry after the failure.
  await page.evaluate(() => { window.fixturePolling = setInterval(() => window.preparation.refresh(), 100); });
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('상태 확인 실패');
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('현재 준비 상태 수신 실패');
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 2.');
  await expect(page.locator('[data-prep="current"]')).toContainText('사용자 입력 필요');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(f.writes).toHaveLength(1);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.evaluate(() => clearInterval(window.fixturePolling));
});

test('pending apply visibly checks its step and later fresh reads retain action rejection evidence', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  f.holdWrites();
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="current"]')).toHaveText('현재 단계: 1. 지도 연결·사용자 위치 초안 · 확인 중');
  await expect(page.getByRole('button', { name: '① 지도 연결 확인·적용' })).toBeDisabled();
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  f.reject(true); f.releaseWrites();
  await expect(page.locator('[data-prep="issues"]')).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  expect(f.writes).toHaveLength(1);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
});

test('sensor evidence and individual candidates are descriptive and never applied automatically', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측 상태: 정지');
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeEnabled();
  await expect(page.locator('[data-prep="candidates"]')).toContainText('센서 관측이 실행 중이 아닙니다');
  f.inputs.candidates.z.reason = 'MAP_ABSOLUTE_Z_UNVERIFIED';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="candidates"]')).toContainText('지도 기준 본체 높이가 확인되지 않았습니다');
  await page.getByRole('button', { name: '센서 관측 시작' }).click();
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  expect(f.writes.at(-1)).toEqual({ path: '/api/v1/observations/fastlio/start', method: 'POST', body: { confirmed: true } });
  f.inputs.evidence = { valid: true, reason: null, calibration_sha256: 'calibration',
    cloud: { topic: '/cloud_registered', frame_id: 'camera_init', source_stamp_ns: '1234567890123456789', received_monotonic_s: 10, publisher_epoch: 'epoch' },
    pose: { topic: '/Odometry', frame_id: 'camera_init', source_stamp_ns: '1234567890123456789', received_monotonic_s: 10, publisher_epoch: 'epoch' } };
  f.inputs.reference_pose = { frame: 'camera_init', child_frame: 'base_link', source_stamp_ns: '1234567890123456789', position: { z: 1 }, orientation: { roll: 0.1 }, qualification: 'REFERENCE_ONLY' };
  f.inputs.candidates = { z: { value: .34, frame: 'map', available: true, reason: null, provenance: { source: 'validated', source_stamp_ns: '1234567890123456789', age_s: 0,
    map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
    bundle_generation: 'pairgen', runtime_instance_generation: 'process', localization_generation: 2, correction_sequence: 4 } },
    roll: { value: null, frame: 'map', available: false, reason: 'MAP_GRAVITY_ALIGNMENT_UNVERIFIED' }, pitch: { value: null, frame: 'map', available: false, reason: 'NEW_SERVER_REASON' } };
  await page.evaluate(({ cloud, grid }) => {
    const pin = { map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
      bundle_generation: 'pairgen', localization_generation: 2, runtime_instance_generation: 'process', correction_sequence: 4,
      pose: { x: 1, y: 2, z: .34, roll: 0, pitch: 0, yaw: 1 }, stale: false };
    Object.assign(window.fixtureContext.navigation, { map: grid, pipeline: { state: 'running', job_id: 'job' }, safety: { can_send_goal: true },
      operational_localization: { ...pin, source: 'STORED_PCD_FASTLIO', fresh: true, ready: true, estimated_pose: pin } });
  }, { cloud, grid });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="evidence"]')).toContainText('/Odometry');
  await expect(page.locator('[data-prep="evidence"]')).toContainText('센서 시각 기록됨');
  await expect(page.locator('[data-prep="evidence"]')).not.toContainText('1234567890123456789');
  await expect(page.locator('[data-prep="evidence"]')).toContainText('지도 초기값 아님');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('z: 자동 후보 0.34');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('roll: 부족 · 지도 기준 기울기가 확인되지 않았습니다');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('pitch: 부족 · 상세 원인을 확인하지 못했습니다');
  await expect(page.locator('[data-prep="candidates"]')).not.toContainText('NEW_SERVER_REASON');
  await expect(page.locator('[data-prep="details"]')).toContainText('1234567890123456789');
  await expect(page.locator('[data-prep="details"]')).toContainText('NEW_SERVER_REASON');
  await expect(page.locator('[data-prep="details"]')).toContainText('calibration');
  await page.evaluate(() => { window.fixtureContext.navigation.operational_localization.runtime_instance_generation = 'restarted'; window.preparation.render(); });
  await expect(page.locator('[data-prep="candidates"]')).not.toContainText('자동 후보');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('후보 신선도 만료 또는 미확인');
  await expect(page.locator('[data-prep="evidence"]')).toContainText(/조회 요청 후 [1-9]\d*\.\d초 경과/);
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await expect(page.getByLabel('높이 z (m)')).toHaveValue('');
  expect(f.writes.map(write => write.path)).toEqual(['/api/v1/navigation/operational-3d/pair', '/api/v1/observations/fastlio/start']);
  f.inputs.pair.generation = 'other';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="candidates"]')).not.toContainText('자동 후보');
  await page.getByRole('button', { name: '센서 관측 종료' }).click();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측 입력 확인 실패');
  await expect(page.locator('[data-prep="details"]')).toContainText('"state": "STOPPED"');
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeDisabled();
  expect(f.writes.at(-1).body).toEqual({ confirmed: true, session_id: 'a'.repeat(32) });
});

const diagnosticSample = () => ({ schema: 'robot-scope.preparation-diagnostics.v1', failure_stage: 'initial_latest', failure_code: 'OBSERVATION_STALE_OR_SOURCE_INVALID',
  checks: [{ stage: 'initial_latest', sample: 'initial', ready: false, failures: ['POSE_RECEIPT', 'CLOUD_GRAPH'],
    pose: { topic: '/Odometry', frame_id: 'camera_init', child_frame_id: 'body', observer_id: 'observer', publisher_epoch: 'epoch', source_stamp_ns: '12345', receipt_age_s: -0.1, graph_age_s: 0.2, graph_state: 'ok', graph_endpoint_count: 1, graph_publisher_count: 1 },
    cloud: { topic: '/cloud_registered', frame_id: 'camera_init', child_frame_id: null, receipt_age_s: 1.4, graph_age_s: null, graph_state: 'unavailable', graph_endpoint_count: 0, graph_publisher_count: null } }],
  phase_ms: { initial_snapshot: 1.2, initial_capture: 3.4, final_capture: null, total: 5.6 } });

async function diagnosticFixture(page) {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="selected"]')).toContainText('적용한 준비 구성: map1 / map1_2D');
  return f;
}

for (const scenario of ['success', 'missing_receipt', 'source_changed', 'subscription_missing', 'bad_units', 'unknown_states']) {
  test(`preparation diagnostics preserve the actual Python API contract: ${scenario}`, async ({ page }) => {
    const f = await diagnosticFixture(page), before = f.writes.length;
    const selected = { generation: 'pairgen',
      localization_3d: { map_id: cloud.id, revision: cloud.revision },
      navigation_2d: { map_id: grid.id, revision: grid.revision } };
    const response = JSON.parse(execFileSync('python3', ['-B', 'tests/fixtures/preparation_api_response.py'], {
      encoding: 'utf8', timeout: 10000, input: JSON.stringify({ case: scenario, selected }),
      env: { ...process.env, PYTHONPATH: 'tests:.', PYTHONDONTWRITEBYTECODE: '1' },
    }));
    // Keep the UI's synthetic map selection; evidence is the unmodified ASGI response.
    f.inputs.evidence = response.evidence;
    const expected = response.evidence.diagnostics;
    await page.evaluate(() => window.preparation.refresh(true));
    const actual = JSON.parse(await page.locator('[data-prep="details"]').textContent()).preparation_inputs.evidence.diagnostics;
    expect(actual).toEqual(expected);
    if (scenario === 'success') {
      expect(expected.checks).toHaveLength(5);
      await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
    } else {
      await expect(page.locator('[data-prep="issues"]')).toContainText('최초 거절 검사');
      if (scenario === 'source_changed') {
        expect(expected.failure_stage).toBe('context_fence');
        expect(expected.failure_sample.cloud.publisher_epoch).toBe('9'.repeat(32));
        expect(expected.checks.every(check => check.stage !== 'context_fence')).toBe(true);
      }
      if (scenario === 'missing_receipt') expect(expected.failure_sample.pose.receipt_age_s).toBeNull();
      if (scenario === 'subscription_missing') expect(expected.failure_code).toBe('SUBSCRIPTION_EVIDENCE_UNAVAILABLE');
      if (scenario === 'bad_units') {
        expect(expected.failure_sample.cloud.units).toBe('mm');
        expect(expected.checks[0].failures).toContain('CLOUD_UNITS');
      }
      if (scenario === 'unknown_states') {
        expect(expected.failure_sample.pose.state).toBe('initializing');
        expect(expected.failure_sample.cloud.graph_state).toBe('unresolved');
      }
    }
    expect(f.writes).toHaveLength(before);
    expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
    expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  });
}

test('diagnostics describe first rejection independently of final evidence and preserve controls', async ({ page }) => {
  const f = await diagnosticFixture(page);
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
  f.inputs.evidence = { valid: false, reason: 'CONTEXT_CHANGED', cloud: null, pose: null, diagnostics: diagnosticSample() };
  const before = f.writes.length;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('최초 거절 검사(검사 당시): 최초 최신 점군·자세 검사');
  await expect(page.locator('[data-prep="issues"]')).toContainText('자세 수신 시각 조건 미충족');
  await expect(page.locator('[data-prep="issues"]')).toContainText('점군 graph 출처 조건 미충족');
  await expect(page.locator('[data-prep="evidence"]')).toContainText('조회 중 지도 또는 관측 실행이 바뀌었습니다');
  const detail = JSON.parse(await page.locator('[data-prep="details"]').textContent());
  expect(detail.preparation_inputs.evidence.diagnostics.checks[0].pose.receipt_age_s).toBe(-0.1);
  expect(detail.preparation_inputs.evidence.diagnostics.checks[0].cloud.graph_age_s).toBeNull();
  expect(detail.preparation_inputs.evidence.diagnostics.phase_ms.total).toBe(5.6);
  expect(detail.diagnostics_note).toContain('네트워크 왕복이나 lock 전용시간이 아닙니다');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  for (const name of ['Nav2 시작', 'INITIAL POSE 지정', 'GOAL POSE 지정']) await expect(page.locator('#host').getByRole('button', { name, exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '정합 시작', exact: true })).toBeDisabled();
  expect(f.writes).toHaveLength(before);
});

test('optional diagnostics reject unknown schema and bound malformed metadata and failure enums', async ({ page }) => {
  const f = await diagnosticFixture(page), before = f.writes.length;
  f.inputs.evidence = { valid: true, reason: null, diagnostics: { ...diagnosticSample(), failure_stage: null, failure_code: null, checks: [] } };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
  expect(JSON.parse(await page.locator('[data-prep="details"]').textContent()).preparation_inputs.evidence.diagnostics.failure_stage).toBeNull();
  f.inputs.evidence = { valid: false, reason: 'OBSERVATION_STALE_OR_SOURCE_INVALID', diagnostics: { ...diagnosticSample(), schema: 'other', failure_stage: 'initial_latest' } };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
  expect(JSON.parse(await page.locator('[data-prep="details"]').textContent()).preparation_inputs.evidence.diagnostics).toBeUndefined();
  const malformed = diagnosticSample();
  malformed.failure_stage = 'UNKNOWN_STAGE'; malformed.failure_code = 'UNKNOWN_CODE';
  malformed.checks = Array.from({ length: 7 }, (_, i) => ({ ...diagnosticSample().checks[0], ready: i ? 'true' : false,
    failures: ['UNKNOWN_FAILURE', 'POSE_RECEIPT'], pose: { topic: 'x'.repeat(129), frame_id: '<img src=x onerror=alert(1)>', source_stamp_ns: 'NaN', receipt_age_s: NaN, graph_age_s: null, graph_state: 'x'.repeat(129), graph_endpoint_count: -1, graph_publisher_count: 1 } }));
  malformed.phase_ms = { total: -1, initial_capture: '1', response_fence: Infinity, extraneous: 500 };
  Object.assign(malformed.checks[0].pose, { state: '\u0000invalid', units: 'x'.repeat(129), sent_points: -1,
    subscription_session_id: 'x'.repeat(129), graph_fingerprint: 'x'.repeat(129), receipt_after_session_start: 0 });
  malformed.failure_sample = { stage: 'initial_latest', pose: malformed.checks[0].pose, cloud: { points_bytes: 'never displayed' } };
  f.inputs.evidence.diagnostics = malformed;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
  const detail = JSON.parse(await page.locator('[data-prep="details"]').textContent()).preparation_inputs.evidence.diagnostics;
  expect(detail.failure_stage).toBeNull(); expect(detail.failure_code).toBeNull(); expect(detail.checks).toHaveLength(5);
  expect(detail.checks[0].failures).toEqual(['POSE_RECEIPT']); expect(detail.checks[1].ready).toBeNull();
  expect(detail.checks[0].pose).toMatchObject({ topic: null, source_stamp_ns: null, receipt_age_s: null, graph_age_s: null, graph_state: null, graph_endpoint_count: null });
  expect(detail.checks[0].pose).toMatchObject({ state: null, units: null, sent_points: null,
    subscription_session_id: null, graph_fingerprint: null, receipt_after_session_start: null });
  expect(detail.failure_sample).toBeNull();
  expect(detail.phase_ms).toMatchObject({ total: null, initial_capture: null, response_fence: null });
  expect(detail.phase_ms.extraneous).toBeUndefined();
  expect(await page.locator('[data-prep="details"] img').count()).toBe(0);
  expect(f.writes).toHaveLength(before);
});

test('stale diagnostics and late responses cannot describe a changed map selection', async ({ page }) => {
  const f = await diagnosticFixture(page), before = f.writes.length;
  f.inputs.evidence = { valid: false, reason: 'OBSERVATION_STALE_OR_SOURCE_INVALID', diagnostics: diagnosticSample() };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('최초 거절 검사');
  await page.evaluate(() => { window.originalNow = performance.now.bind(performance); Object.defineProperty(performance, 'now', { configurable: true, value: () => window.originalNow() + 11000 }); window.preparation.render(); });
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
  expect(JSON.parse(await page.locator('[data-prep="details"]').textContent()).preparation_inputs.evidence.diagnostics).toBeUndefined();
  await page.evaluate(() => { delete performance.now; });
  f.inputs.pair.generation = 'different-generation';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  f.inputs.pair.generation = 'pairgen';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('최초 거절 검사');
  f.holdInputsRead();
  const readsBefore = f.reads.filter(path => path.endsWith('/preparation-inputs')).length;
  await page.evaluate(() => { window.pendingDiagnosticRead = window.preparation.refresh(true); });
  await expect.poll(() => f.reads.filter(path => path.endsWith('/preparation-inputs')).length).toBeGreaterThan(readsBefore);
  await page.getByLabel('3D 위치추정 지도').selectOption('');
  f.releaseInputsRead();
  await page.evaluate(() => window.pendingDiagnosticRead);
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('최초 거절 검사');
  expect(JSON.parse(await page.locator('[data-prep="details"]').textContent()).preparation_inputs.evidence.diagnostics).toBeUndefined();
  expect(f.writes).toHaveLength(before);
});

test('observation rejection exposes bridge reason and does not retry or bypass the server', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  f.inputs.start_blockers.items = ['CONTROL_BRIDGE_NOT_INACTIVE', 'OWNER_BUSY:navigation'];
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('현재 bridge의 관측용 명령 차단을 확인하지 못했습니다');
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('주행이 센서를 사용 중입니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('CONTROL_BRIDGE_NOT_INACTIVE');
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeDisabled();
  expect(f.writes.filter(write => write.path.includes('/observations/'))).toHaveLength(0);
  f.inputs.start_blockers.items = [];
  await page.evaluate(() => window.preparation.refresh(true));
  f.rejectObservation(true);
  await page.getByRole('button', { name: '센서 관측 시작' }).click();
  await expect(page.locator('[data-prep="observation-error"]')).toContainText('현재 bridge의 관측용 명령 차단을 확인하지 못했습니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('control_bridge_not_inactive');
  expect(f.writes.filter(write => write.path.includes('/observations/'))).toHaveLength(1);
  expect(f.writes.filter(write => /seed-geometry|\/match|\/goal/.test(write.path))).toHaveLength(0);
});

async function proposalFixture(page, { expectReady = true } = {}) {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await page.getByRole('button', { name: '센서 관측 시작' }).click();
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  f.state.selected.generation = 'b'.repeat(32);
  f.state.selected.localization_3d.frame = 'camera_init';
  f.inputs.pair.generation = 'b'.repeat(32);
  f.inputs.pair.calibration_sha256 = 'c'.repeat(64);
  f.inputs.evidence = { valid: true, reason: null,
    cloud: { topic: '/cloud_registered', frame_id: 'camera_init', observer_id: '1'.repeat(32), publisher_epoch: '2'.repeat(32), source_stamp_ns: '123' },
    pose: { topic: '/Odometry', frame_id: 'camera_init', observer_id: '1'.repeat(32), publisher_epoch: '3'.repeat(32), source_stamp_ns: '123' } };
  await page.evaluate(() => window.preparation.refresh(true));
  if (expectReady) {
    await page.evaluate(({cloud,grid}) => { window.fakeOperatorDraft={status:'ready',revision:1,pose:{x:1.2,y:2.3,yaw:.4},bundle_generation:'b'.repeat(32),localization_map:{id:cloud.id,revision:cloud.revision},navigation_map:{id:grid.id,revision:grid.revision}};window.preparation.draftChanged(); }, {cloud,grid});
    await page.getByLabel(/이 초안이 현재 지도에서 정지/).check();
    await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeEnabled();
  } else await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  return f;
}

test('explicit proposal is read-only, distinguishes IMU and body units, and invalidates when the source changes', async ({ page }) => {
  const f = await proposalFixture(page);
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(0);
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  const proposalWrite = f.writes.filter(value => value.path.endsWith('/initialization-proposals'));
  expect(proposalWrite).toHaveLength(1);
  expect(proposalWrite[0].body).toMatchObject({ request_id: expect.stringMatching(/^[a-f0-9]{32}$/), bundle_generation: 'b'.repeat(32), observation_session_id: 'a'.repeat(32), operator_prior: { source:'OPERATOR_CURRENT_MAP_DRAFT', stationary_current_pose_confirmed:true } });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('FAST-LIO IMU 가설 (이력·근사값)');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('위치 m, 각도 도');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 스캔 15.0초 전');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('본체 위치 후보 (정보성)');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('위치 m, 각도 rad');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('운영 초기 기준 0.85는 별도');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('운영 잔차 검사를 통과한 결과나 실제 위치 정확도가 아닙니다');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('운영 보정 위치·Nav2 준비·TF 적용 결과가 아닙니다');
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await expect(page.getByLabel('높이 z (m)')).toHaveValue('');
  await expect(page.getByLabel('roll (rad)', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('pitch (rad)', { exact: true })).toHaveValue('');
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('제안 관측이 오래됐거나 신선도를 확인하지 못했습니다');
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  f.inputs.evidence.cloud.publisher_epoch = 'd'.repeat(32);
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('이전 제안을 사용할 수 없습니다');
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
});

test('proposal rejection and late result never retry or restore invalid data', async ({ page }) => {
  const f = await proposalFixture(page);
  f.rejectProposal(true);
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('전역 위치 제안 기능을 사용할 수 없습니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('GLOBAL_BACKEND_UNAVAILABLE');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
  f.rejectProposal(false); f.holdProposalReads();
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('현재 관측과 지도 문맥을 다시 확인 중');
  f.observation.state = 'STOPPED'; f.observation.active = false;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('이전 제안을 사용할 수 없습니다');
  f.releaseProposalReads();
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(2);
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
});

test('one combined read clears prior readiness when its operational state is invalid', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="selected"]')).toContainText('적용한 준비 구성: map1 / map1_2D');
  f.state.selected.seed_geometry = { z: .34, roll: 0, pitch: 0 };
  f.state.pair.can_start = true;
  await page.evaluate(() => window.preparation.refresh(true));
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(true);
  expect(f.reads.filter(path => path === '/api/v1/navigation/operational-3d')).toHaveLength(0);
  const readCount = f.reads.filter(path => path.endsWith('/preparation-inputs')).length;
  f.invalidStatus(true);
  await page.evaluate(() => window.preparation.refresh(true));
  expect(f.reads.filter(path => path.endsWith('/preparation-inputs'))).toHaveLength(readCount + 1);
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  expect(await page.evaluate(() => window.preparation.state())).toBe(null);
  await expect(page.locator('[data-prep="issues"]')).toContainText('조회 중 지도 또는 관측 실행이 바뀌었습니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('CONTEXT_CHANGED');
  f.invalidStatus(false);
  await page.evaluate(() => window.preparation.refresh(true));
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(true);
});

test('a proposal with different publisher identity is invalidated even if the session is unchanged', async ({ page }) => {
  const f = await proposalFixture(page);
  f.wrongProposalSource(true);
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('제안의 센서 출처가 현재 관측과 달라 사용할 수 없습니다');
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
});

test('cleanup delay and failure remain blocked across context changes until settled and ownership clears', async ({ page }) => {
  const f = await proposalFixture(page);
  f.proposalStatus('stale', 'OBSERVATION_SESSION_CHANGED');
  f.cleanup({ state: 'CANCELLING', cancellation_requested: true, worker_active: true });
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('취소 요청 처리 중 · 작업 종료 미확인');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.inputs.evidence.cloud.publisher_epoch = 'd'.repeat(32);
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('이전 제안을 사용할 수 없습니다');
  f.cleanup({ state: 'CANCEL_PENDING', cancellation_requested: true, worker_active: true });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('취소 후 종료 확인 지연');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.cleanup({ state: 'CANCEL_FAILED', cancellation_requested: false, worker_active: true });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('취소 요청 실패 · 작업 종료 미확인');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.cleanup({ state: 'CLEANUP_UNCONFIRMED', cancellation_requested: true });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('작업 정리 상태 미확인');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.cleanup({ state: 'SETTLED', cancellation_requested: true, worker_active: true, terminal_state: 'cancelled' });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('작업 종료 상태를 확인하지 못했습니다');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.inputs.start_blockers.items = ['OWNER_BUSY:global_observation'];
  await page.evaluate(() => window.preparation.refresh(true));
  f.cleanup({ state: 'SETTLED', cancellation_requested: true, worker_active: false, terminal_state: 'cancelled' });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('작업 종료 확인');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('전역 관측 작업이 사용 중입니다');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  f.inputs.start_blockers.items = [];
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeEnabled();
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
});

async function handoffFixture(page, { mode = 'success', hold = false } = {}) {
  const f = await proposalFixture(page);
  f.confirmMode(mode);
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="conditional-label"]')).toBeVisible();
  await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check();
  await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeEnabled();
  if (hold) f.holdConfirm();
  return f;
}

test('supervised confirmation is one explicit POST, stop remains separate, and the server receipt governs start', async ({ page }) => {
  const f = await handoffFixture(page, { hold: true });
  const button = page.getByRole('button', { name: '제안값 확인·②에 적용' });
  await page.getByLabel(/현장 정지 상태를 직접 감독/).uncheck();
  await expect(button).toBeDisabled();
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  await expect(button).toBeEnabled();
  await button.click();
  await expect(button).toBeDisabled();
  await page.evaluate(() => document.querySelector('[data-prep="confirm-handoff"]').click());
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  const body = f.writes.find(v => v.path.endsWith('/confirm-geometry')).body;
  expect(body).toEqual({ request_id: expect.stringMatching(/^[a-f0-9]{32}$/), bundle_generation: 'b'.repeat(32), observation_session_id: 'a'.repeat(32), confirmed: true, stationary_supervision_acknowledged: true, conditional_prior_acknowledged: true });
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  expect(f.writes.filter(v => /\/observations\/fastlio\/stop|\/navigation\/start|seed-geometry|\/match|\/goal/.test(v.path))).toHaveLength(0);
  f.releaseConfirm();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨 · 관측 종료를 별도로 요청하세요');
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('센서 공백은 측정되지 않습니다');
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('주행 설정이나 실제 위치 정확도가 아닙니다');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await expect(page.getByLabel('높이 z (m)')).toHaveValue('');
  f.handoff().state = 'STOP_PENDING'; f.handoff().stop_receipt.state = 'DISPATCH_ACCEPTED';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('종료 요청 접수 · 종료 미확인');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  f.handoff().state = 'OBSERVATION_STOPPED'; f.handoff().stop_receipt.state = 'INACTIVE_CONFIRMED';
  Object.assign(f.observation, { state: 'STOPPED', active: false, session_id: null, can_stop: false });
  f.inputs.evidence.valid = false; f.state.pair.can_start = true;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('정확한 관측 세대의 종료 확인');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(true);
  for (const name of ['Nav2 시작', 'INITIAL POSE 지정', 'GOAL POSE 지정']) await expect(page.locator('#host').getByRole('button', { name, exact: true })).toHaveCount(0);
  expect(f.writes.filter(v => /\/observations\/fastlio\/stop|\/navigation\/start|seed-geometry|\/match|\/goal/.test(v.path))).toHaveLength(0);
});

test('lost confirmation response restores only server-owned handoff after refresh and reload without another POST', async ({ page }) => {
  const f = await handoffFixture(page, { mode: 'lost' });
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨 · 관측 종료를 별도로 요청하세요');
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  await f.reload();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨 · 관측 종료를 별도로 요청하세요');
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  f.state.initialization_handoff = null;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 서버 상태가 불확실합니다');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
});

test('rejected confirmation never retries and leaves observation stop available', async ({ page }) => {
  const f = await handoffFixture(page, { mode: 'reject' });
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('서로 구분되지 않는 위치 후보가 있습니다');
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  expect(f.writes.filter(v => /\/observations\/fastlio\/stop|\/navigation\/start|seed-geometry|\/match|\/goal/.test(v.path))).toHaveLength(0);
});

test('handoff expiry blocks bootstrap while MATCH_ARMED expiry does not hide current corrected tracking', async ({ page }) => {
  const f = await handoffFixture(page);
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨');
  f.handoff().state = 'OBSERVATION_STOPPED'; f.handoff().stop_receipt.state = 'INACTIVE_CONFIRMED'; f.handoff().expires_in_s = .35;
  Object.assign(f.observation, { state: 'STOPPED', active: false, session_id: null, can_stop: false });
  f.inputs.evidence.valid = false; f.state.pair.can_start = true;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect.poll(() => page.evaluate(() => window.preparation.canStart())).toBe(false);
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('사용 시간 만료');
  f.handoff().state = 'MATCH_ARMED'; f.handoff().job_id = '9'.repeat(32); f.handoff().expires_in_s = 0; f.state.pair.can_start = false;
  f.handoff().match_history = { runtime_instance_generation: 'process', localization_generation: 2, initial_pose_stamp_ns: '123', match_request_id: 'match-1' };
  f.state.runtime_fresh = true;
  f.state.runtime = { runtime_instance_generation: 'process', localization_generation: 2, match_armed: true,
    accepted_initial_pose: { accepted: true, stamp_ns: '123' }, match_receipt: { accepted: true, request_id: 'match-1', localization_generation: 2 } };
  await page.evaluate(({ cloud, grid }) => {
    const pin = { map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
      bundle_generation: 'b'.repeat(32), localization_generation: 2, runtime_instance_generation: 'process',
      pose: { x: 1, y: 2, z: .4, roll: .1, pitch: .2, yaw: .3 }, stale: false };
    Object.assign(window.fixtureContext.navigation, { map: grid, pipeline: { state: 'running', job_id: '9'.repeat(32) }, safety: { can_set_initial_pose: true, can_send_goal: true },
      operational_localization: { ...pin, source: 'STORED_PCD_FASTLIO', fresh: true, ready: true, state: 'MAP_TRACKING', match_armed: true,
        match_receipt: { accepted: true, request_id: 'match-1', localization_generation: 2 }, accepted_initial_pose: { ...pin, accepted: true, stamp_ns: '123' }, estimated_pose: pin } });
  }, { cloud, grid });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('정합 요청 접수 · 실제 보정과 운영 준비는 별도 확인');
  await expect(page.locator('[data-prep="steps"]')).toContainText('실제 정합 추정 위치 수신');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(true);
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('이전 정합 요청 수락 이력');
  const geometry = structuredClone(f.handoff().geometry), reference = structuredClone(f.handoff().initial_pose_reference);
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'stopped'; });
  Object.assign(f.handoff(), { state: 'INVALID', reason: 'HANDOFF_JOB_NOT_RUNNING', geometry: null, initial_pose_reference: null });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 사용 불가');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'running'; });
  Object.assign(f.handoff(), { state: 'MATCH_ARMED', reason: null, geometry, initial_pose_reference: reference });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('정합 요청 접수 · 실제 보정과 운영 준비는 별도 확인');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(true);
  await page.evaluate(() => { window.fixtureContext.navigation.operational_localization.match_armed = false; window.preparation.render(); });
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 실행의 수락은 미확인');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  await page.evaluate(() => { window.fixtureContext.navigation.operational_localization.match_armed = true; window.preparation.render(); });
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(true);
  await page.evaluate(() => { window.fixtureContext.navigation.operational_localization.localization_generation = 3; window.preparation.render(); });
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 실행의 수락은 미확인');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  await page.evaluate(() => { window.fixtureContext.navigation.operational_localization.localization_generation = 2; window.preparation.render(); });
  Object.assign(f.handoff(), { state: 'OUTCOME_UNKNOWN', reason: 'HANDOFF_MATCH_CURRENT_UNCONFIRMED', geometry: null, initial_pose_reference: null });
  f.state.runtime_fresh = false;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 실행의 수락 상태를 확인하지 못했습니다');
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('이전 정합 요청 수락 이력');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  Object.assign(f.handoff(), { state: 'INVALID', reason: 'HANDOFF_RUNTIME_CHANGED' });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 사용 불가');
  Object.assign(f.handoff(), { state: 'MATCH_ARMED', reason: null });
  f.state.runtime_fresh = true;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 사용 불가');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  await expect(page.getByRole('button', { name: '정합 시작', exact: true })).toBeDisabled();
  expect(f.writes.filter(v => /\/navigation\/start|seed-geometry|\/match|\/goal/.test(v.path))).toHaveLength(0);
});

test('restored unknown, stopping and failed job states remain blocked and distinct from tracking', async ({ page }) => {
  const f = await handoffFixture(page);
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨');
  Object.assign(f.handoff(), { job_id: '9'.repeat(32), state: 'OUTCOME_UNKNOWN', reason: 'HANDOFF_JOB_CONTEXT_UNCONFIRMED', geometry: null, initial_pose_reference: null });
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline = { state: 'starting', job_id: null }; });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 상태 불확실');
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 실행 또는 지도 증거가 부족합니다');
  await expect(page.locator('[data-prep="handoff-result"]')).not.toContainText('서버 보관 가설 (지도 좌표)');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  await page.evaluate(({ grid }) => { window.fixtureContext.navigation.pipeline = { state: 'starting', job_id: '9'.repeat(32) }; window.fixtureContext.navigation.map = grid; }, { grid });
  f.handoff().reason = 'HANDOFF_JOB_STARTING';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('새 실행이 시작 중입니다');
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'stopping'; });
  f.handoff().reason = 'HANDOFF_JOB_STOPPING';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('실행이 종료 중입니다');
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'failed'; });
  Object.assign(f.handoff(), { state: 'INVALID', reason: 'HANDOFF_JOB_NOT_RUNNING' });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 사용 불가');
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('이 가설에 연결된 실행이 종료됐습니다');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.job_id = '8'.repeat(32); });
  f.state.initialization_handoff = null;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 서버 상태가 불확실합니다');
  await expect(page.locator('[data-prep="handoff-result"]')).not.toContainText('정합 요청 접수');
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
});

test('job phase INVALID recovers only from a fresh matching server snapshot', async ({ page }) => {
  const f = await handoffFixture(page);
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨');
  const geometry = structuredClone(f.handoff().geometry), reference = structuredClone(f.handoff().initial_pose_reference);
  Object.assign(f.observation, { state: 'STOPPED', active: false, session_id: null, can_stop: false });
  f.inputs.evidence.valid = false;
  await page.evaluate(({ grid }) => { window.fixtureContext.navigation.map = grid; window.fixtureContext.navigation.pipeline = { state: 'running', job_id: '9'.repeat(32) }; }, { grid });
  for (const phase of ['idle', 'stopped', 'failed']) {
    await page.evaluate(phase => { window.fixtureContext.navigation.pipeline.state = phase; }, phase);
    Object.assign(f.handoff(), { job_id: '9'.repeat(32), state: 'INVALID', reason: 'HANDOFF_JOB_NOT_RUNNING', geometry: null, initial_pose_reference: null, expires_in_s: 60, stop_receipt: { state: 'INACTIVE_CONFIRMED' } });
    await page.evaluate(() => window.preparation.refresh(true));
    await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 사용 불가');
    expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
    await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'running'; });
    Object.assign(f.handoff(), { state: 'SNAPSHOTTED', reason: null, geometry, initial_pose_reference: reference });
    await page.evaluate(() => window.preparation.refresh(true));
    await expect(page.locator('[data-prep="handoff-result"]')).toContainText('새 실행에 가설 예약됨');
  }
  Object.assign(f.handoff(), { state: 'OUTCOME_UNKNOWN', reason: 'HANDOFF_JOB_STARTING', geometry: null, initial_pose_reference: null });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 상태 불확실');
  Object.assign(f.handoff(), { state: 'SNAPSHOTTED', reason: null, geometry, initial_pose_reference: reference });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('새 실행에 가설 예약됨');
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  expect(f.writes.filter(v => /\/navigation\/start|seed-geometry|\/match|\/goal/.test(v.path))).toHaveLength(0);
});

for (const terminal of [{ state: 'INVALID', reason: 'HANDOFF_STOP_OUTCOME_UNKNOWN' }, { state: 'EXPIRED', reason: 'HANDOFF_EXPIRED' }]) {
  test(`permanent ${terminal.reason} survives a phase-only invalid and later snapshot`, async ({ page }) => {
    const f = await handoffFixture(page);
    await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
    await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨');
    const geometry = structuredClone(f.handoff().geometry), reference = structuredClone(f.handoff().initial_pose_reference);
    Object.assign(f.handoff(), terminal, { job_id: '9'.repeat(32), geometry: null, initial_pose_reference: null });
    await page.evaluate(({ grid }) => { window.fixtureContext.navigation.map = grid; window.fixtureContext.navigation.pipeline = { state: 'stopped', job_id: '9'.repeat(32) }; }, { grid });
    await page.evaluate(() => window.preparation.refresh(true));
    Object.assign(f.handoff(), { state: 'INVALID', reason: 'HANDOFF_JOB_NOT_RUNNING' });
    await page.evaluate(() => window.preparation.refresh(true));
    await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'running'; });
    Object.assign(f.handoff(), { state: 'SNAPSHOTTED', reason: null, geometry, initial_pose_reference: reference });
    await page.evaluate(() => window.preparation.refresh(true));
    await expect(page.locator('[data-prep="handoff-result"]')).not.toContainText('새 실행에 가설 예약됨');
    await expect(page.locator('[data-prep="handoff-result"]')).toContainText(terminal.state === 'EXPIRED' ? '가설 사용 시간 만료' : '가설 사용 불가');
    expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
    expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  });
}

test('late confirmation and handoff reads cannot revive a changed generation or cleared server record', async ({ page }) => {
  const f = await handoffFixture(page, { hold: true });
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  f.state.selected.generation = 'd'.repeat(32); f.inputs.pair.generation = 'd'.repeat(32);
  await page.evaluate(() => window.preparation.refresh(true));
  f.releaseConfirm();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 지도·가설 문맥이 일치하지 않습니다');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  expect(f.writes.filter(v => /\/navigation\/start|seed-geometry|\/match|\/goal/.test(v.path))).toHaveLength(0);
});

test('a delayed handoff GET cannot restore a record cleared by a newer server snapshot', async ({ page }) => {
  const f = await handoffFixture(page);
  f.holdHandoffRead();
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨');
  await expect.poll(() => f.reads.filter(path => path.includes('/initialization-handoffs/')).length).toBeGreaterThan(0);
  f.state.initialization_handoff = null;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('현재 서버 상태가 불확실합니다');
  f.releaseHandoffRead();
  await expect(page.locator('[data-prep="handoff-result"]')).not.toContainText('가설 확인됨');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
});

test('unsettled worker or ambiguous candidate never enables supervised confirmation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const f = await proposalFixture(page);
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  f.cleanup({ state: 'CANCEL_PENDING', cancellation_requested: true, worker_active: true });
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('취소 후 종료 확인 지연');
  await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeDisabled();
  f.ambiguousProposal(true);
  f.cleanup({ state: 'SETTLED', cancellation_requested: false, worker_active: false, terminal_state: 'succeeded' });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('제안 형식 또는 현재 문맥을 확인하지 못했습니다');
  await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeDisabled();
  const dimensions = await page.getByLabel(/현장 정지 상태를 직접 감독/).evaluate(input => ({ width: input.getBoundingClientRect().width, document: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(dimensions.width).toBeLessThan(35);
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport + 1);
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('uncertain stop and explicit mismatched runtime never restore ready handoff', async ({ page }) => {
  const f = await handoffFixture(page);
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨');
  Object.assign(f.handoff(), { state: 'OUTCOME_UNKNOWN', reason: 'HANDOFF_STOP_OUTCOME_UNKNOWN', stop_receipt: { state: 'OUTCOME_UNKNOWN' }, geometry: null, initial_pose_reference: null });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('종료 결과 불확실');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  Object.assign(f.handoff(), { state: 'OUTCOME_UNKNOWN', reason: 'HANDOFF_MONITOR_PENDING', stop_receipt: { state: 'INACTIVE_CONFIRMED' } });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('관측 종료 경계를 가설 감시기가 확인 중입니다');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  Object.assign(f.handoff(), { state: 'INVALID', reason: 'HANDOFF_MONITOR_UNAVAILABLE' });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 감시 상태가 유실됐거나 확인되지 않습니다');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  Object.assign(f.handoff(), { state: 'INVALID', reason: 'SOURCE_OR_CONTEXT_CHANGED' });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('센서 출처 또는 실행 문맥이 바뀌었습니다');
  Object.assign(f.handoff(), { state: 'INVALID', reason: 'HANDOFF_JOB_NOT_RUNNING' });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('센서 출처 또는 실행 문맥이 바뀌었습니다');
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 사용 불가');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  Object.assign(f.handoff(), { state: 'CONFIRMED_OBSERVATION_ACTIVE', reason: null, stop_receipt: { state: 'NOT_REQUESTED' }, geometry: { z: .4, roll: .1, pitch: .2 }, initial_pose_reference: { x: 1, y: 2, yaw: .3 } });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 사용 불가');
  await expect(page.locator('[data-prep="handoff-result"]')).not.toContainText('서버 보관 가설 (지도 좌표)');
  Object.assign(f.handoff(), { job_id: '9'.repeat(32), state: 'MATCH_ARMED', reason: null, expires_in_s: 0, stop_receipt: { state: 'INACTIVE_CONFIRMED' } });
  await page.evaluate(({ grid }) => { window.fixtureContext.navigation.pipeline = { state: 'running', job_id: '9'.repeat(32) }; window.fixtureContext.navigation.map = { ...grid, id: '8'.repeat(24) }; }, { grid });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('서버의 현재 지도·가설 문맥이 일치하지 않습니다');
  await expect(page.locator('[data-prep="handoff-result"]')).not.toContainText('정합 요청 접수');
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  expect(f.writes.filter(v => /\/navigation\/start|seed-geometry|\/match|\/goal/.test(v.path))).toHaveLength(0);
});

test('snapshot plus accepted runtime initial pose permits only an explicit match while TTL remains', async ({ page }) => {
  const f = await handoffFixture(page);
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('가설 확인됨');
  Object.assign(f.handoff(), { job_id: '9'.repeat(32), state: 'SNAPSHOTTED', reason: null, expires_in_s: 60, stop_receipt: { state: 'INACTIVE_CONFIRMED' } });
  Object.assign(f.observation, { state: 'STOPPED', active: false, session_id: null, can_stop: false });
  f.inputs.evidence.valid = false;
  await page.evaluate(({ cloud, grid }) => {
    const pin = { map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
      bundle_generation: 'b'.repeat(32), localization_generation: 2, runtime_instance_generation: 'process',
      pose: { x: 1, y: 2, z: .4, roll: .1, pitch: .2, yaw: .3 }, stamp_ns: '123' };
    Object.assign(window.fixtureContext.navigation, { map: grid, pipeline: { state: 'running', job_id: '9'.repeat(32) }, safety: { can_set_initial_pose: true, can_send_goal: false },
      operational_localization: { ...pin, source: 'STORED_PCD_FASTLIO', fresh: true, ready: false, state: 'WAITING_EXPLICIT_MAP_MATCH', accepted_initial_pose: { ...pin, accepted: true } } });
  }, { cloud, grid });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('새 실행에 가설 예약됨');
  await expect(page.getByRole('button', { name: '정합 시작', exact: true })).toBeEnabled();
  expect(f.writes.filter(v => v.path.endsWith('/match'))).toHaveLength(0);
  await page.getByRole('button', { name: '정합 시작', exact: true }).click();
  expect(f.writes.filter(v => v.path.endsWith('/match'))).toHaveLength(1);
  expect(f.writes.filter(v => /\/goal|seed-geometry|\/navigation\/start/.test(v.path))).toHaveLength(0);
});

test('proposal map-frame geometry remains read-only until supervised confirmation and server readback', async ({ page }) => {
  const f = await proposalFixture(page);
  f.state.pair.checks = [{ code: 'INITIAL_HEIGHT_TILT_REQUIRED', current: '초기 높이·기울기 미지정', remedy: '기존 직접 입력 안내' }];
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('초기 위치 제안을 계산해 감독 확인 후 적용');
  await expect(page.locator('[data-prep="geometry-applied"]')).toContainText('서버 확인 적용값 없음');
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  const preview = page.locator('[data-prep="geometry-preview"]');
  await expect(preview).toContainText('미적용 · 지도 기준 base_link');
  await expect(preview).toContainText('높이 0.840 m · roll 0.110 rad · pitch 0.120 rad');
  await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeDisabled();
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  for (const label of ['높이 z (m)', 'roll (rad)', 'pitch (rad)']) await expect(page.getByLabel(label, { exact: true })).toHaveValue('');
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check();
  await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeEnabled();
  f.confirmedGeometry({ z: .97, roll: -.21, pitch: .32 });
  await page.getByRole('button', { name: '제안값 확인·②에 적용' }).click();
  const applied = page.locator('[data-prep="geometry-applied"]');
  await expect(applied).toContainText('서버 확인 적용값');
  await expect(applied).toContainText('높이 0.970 m · roll -0.210 rad · pitch 0.320 rad');
  await expect(applied).not.toContainText('0.840');
  await expect(applied).toContainText('관측 종료 확인 필요');
  for (const label of ['높이 z (m)', 'roll (rad)', 'pitch (rad)']) await expect(page.getByLabel(label, { exact: true })).toHaveValue('');
  expect(f.writes.filter(v => v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  expect(f.writes.filter(v => /seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
  f.handoff().expires_in_s = 0;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(applied).toContainText('만료·무효 또는 서버 상태 미확인');
  await expect(applied).not.toContainText('0.970');
});

for (const invalid of ['missing', 'bad-frame', 'ambiguous']) {
  test(`proposal ${invalid} geometry cannot be displayed as ready or confirmed`, async ({ page }) => {
    const f = await proposalFixture(page);
    if (invalid === 'ambiguous') f.ambiguousProposal(true); else f.geometryPreview(invalid);
    await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
    await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
    await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
    await expect(page.locator('[data-prep="geometry-preview"]')).not.toContainText('0.840');
    await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeDisabled();
    await page.locator('[data-prep="confirm-handoff"]').evaluate(button => button.click());
    expect(f.writes.filter(v => /confirm-geometry|seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
  });
}

test('expired or late proposal cannot repopulate geometry or trigger confirmation', async ({ page }) => {
  const f = await proposalFixture(page);
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('0.840');
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
  await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeDisabled();
  f.holdProposalReads();
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect.poll(() => f.reads.filter(p => p.includes('/initialization-proposals/')).length).toBeGreaterThan(1);
  Object.assign(f.observation, { state: 'STOPPED', active: false, session_id: null });
  await page.evaluate(() => window.preparation.refresh(true));
  f.releaseProposalReads();
  await expect(page.locator('[data-prep="geometry-preview"]')).not.toContainText('0.840');
  await expect(page.getByRole('button', { name: '제안값 확인·②에 적용' })).toBeDisabled();
  await f.reload();
  await expect(page.locator('[data-prep="geometry-preview"]')).not.toContainText('0.840');
  expect(f.writes.filter(v => /confirm-geometry|seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
});


test('operator draft requires stationary confirmation before proposal request', async ({page}) => {
 const f=await proposalFixture(page, { expectReady:false });f.proposalStatus('rejected','GLOBAL_AMBIGUOUS');
 await expect(page.locator('[data-prep="steps"] > li').first()).toHaveAttribute('data-state','사용자 입력 필요');
 await expect(page.locator('[data-prep="steps"] > li').first()).toContainText('지도 연결·사용자 위치 초안');
 await page.evaluate(({cloud,grid})=>{window.fakeOperatorDraft={status:'ready',revision:1,pose:{x:1.2,y:2.3,yaw:.4},bundle_generation:'b'.repeat(32),localization_map:{id:cloud.id,revision:cloud.revision},navigation_map:{id:grid.id,revision:grid.revision}};window.preparation.draftChanged();},{cloud,grid});
 await expect(page.locator('[data-prep="prior-status"]')).toContainText('미전송 사용자 초안');
 await expect(page.getByRole('button',{name:'초기 위치 제안 계산'})).toBeDisabled();
 await page.getByLabel(/이 초안이 현재 지도에서 정지/).check();
 await expect(page.getByRole('button',{name:'초기 위치 제안 계산'})).toBeEnabled();
 await expect(page.locator('[data-prep="steps"] > li').first()).toHaveAttribute('data-state','완료');
 await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
 const body=f.writes.find(v=>v.path.endsWith('/initialization-proposals')).body;
 expect(body.operator_prior).toEqual({frame:'map',pose_reference:'base_link',units:'metres_radians',pose:{x:1.2,y:2.3,yaw:.4},source:'OPERATOR_CURRENT_MAP_DRAFT',stationary_current_pose_confirmed:true,navigation_map_id:grid.id,navigation_map_revision:grid.revision,calibration_sha256:'c'.repeat(64)});
 await expect(page.locator('[data-prep="proposal-result"]')).toContainText('구분되지 않는 위치 후보');
 expect(f.writes.filter(v=>/confirm-geometry|seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
 expect(await page.locator('[data-prep="steps"] > li').count()).toBe(6);
 await expect(page.locator('[data-prep="steps"] > li').nth(3)).toContainText('INITIAL POSE 접수·지도 정합');
});

test('changing operator draft while response is delayed invalidates it without retry or automatic confirmation', async ({page})=>{
 const f=await proposalFixture(page, { expectReady:false });
 await page.evaluate(({cloud,grid})=>{window.fakeOperatorDraft={status:'ready',revision:1,pose:{x:1.2,y:2.3,yaw:.4},bundle_generation:'b'.repeat(32),localization_map:{id:cloud.id,revision:cloud.revision},navigation_map:{id:grid.id,revision:grid.revision}};window.preparation.draftChanged();},{cloud,grid});
 await page.getByLabel(/이 초안이 현재 지도에서 정지/).check();
 f.holdProposalReads();await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
 await expect.poll(()=>f.reads.filter(p=>p.includes('/initialization-proposals/')).length).toBeGreaterThan(0);
 await page.evaluate(()=>{window.fakeOperatorDraft.revision++;window.fakeOperatorDraft.pose.x=2;window.preparation.draftChanged();});f.releaseProposalReads();
 await expect(page.locator('[data-prep="proposal-result"]')).toContainText('초안이 바뀌어 이전 제안을 사용할 수 없습니다');
 await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
 expect(f.writes.filter(v=>/confirm-geometry|seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
});


test('conditional prior remains ambiguous and requires separate explicit acknowledgement', async ({page}) => {
 const f=await proposalFixture(page);await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
 await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 판정: 모호성 미해결');
 await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
 await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
 const confirm=page.getByRole('button',{name:'제안값 확인·②에 적용'});await expect(confirm).toBeDisabled();
 await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check();await expect(confirm).toBeEnabled();await confirm.click();
 const write=f.writes.find(v=>v.path.endsWith('/confirm-geometry'));
 expect(write.body.conditional_prior_acknowledged).toBe(true);expect(write.body.operator_prior).toBeUndefined();expect(write.body.operator_prior_resolution).toBeUndefined();
 await expect(page.locator('[data-prep="handoff-result"]')).toContainText('원본 판정: 모호성 미해결');
 expect(f.writes.filter(v=>/seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
});
for (const mode of ['multiple','different-prior','original-mismatch']) {
 test(`conditional ${mode} proof is never promoted to a preview or handoff`, async ({page})=>{
  const f=await proposalFixture(page);f.proofMode(mode);await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
 });
}
test('candidate outside the server policy limit cannot be previewed or confirmed', async ({page})=>{
 const f=await proposalFixture(page);f.proofMode('beyond-handoff');
 await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
 await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
 await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
 expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('nonambiguous original result remains conditional with its original flag unchanged', async ({page})=>{
 const f=await proposalFixture(page);f.proofMode('original-unambiguous');await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
 await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
 const detail=JSON.parse(await page.locator('[data-prep="details"]').textContent());
 expect(detail.initialization_proposal.quality.ambiguity_unresolved).toBe(false);
 expect(detail.initialization_proposal.operator_prior_resolution.original_ambiguity_unresolved).toBe(false);
 await expect(page.locator('[data-prep="proposal-result"]')).toContainText('조건부로 한 후보');
 await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 판정: 비모호');
 await page.getByLabel(/현장 정지 상태를 직접 감독/).check();await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check();
 await page.getByRole('button',{name:'제안값 확인·②에 적용'}).click();
 await expect(page.locator('[data-prep="handoff-result"]')).toContainText('원본 판정: 비모호');
 await expect(page.locator('[data-prep="handoff-result"]')).toContainText('전역 유일성');
 expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
});

for (const reason of ['PRIOR_NO_MATCH', 'PRIOR_MULTIPLE_MATCHES']) {
 test(`conditional ${reason} rejects without preview or confirmation`, async ({page})=>{
  const f=await proposalFixture(page);f.proposalStatus('rejected',reason);
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('#host')).toContainText('서버 기본 검증 한도 위치 0.25 m · 방향 ±0.20 rad (약 ±11.5°)');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText(reason==='PRIOR_NO_MATCH'?'서버 검증 한도 안에 조건을 충족하는 후보가 없습니다':'서버 검증 한도 안에 여러 후보가 있습니다');
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
 });
}

test('active bridge proof enables proposal only while current control guards remain clear', async ({ page }) => {
  const f = await proposalFixture(page);
  f.observation.bridge_guard = { mode: 'active_inhibited', state: 'HELD', source: 'signed_control_bridge', status_age_s: .12 };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeEnabled();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('제어 bridge 켜짐');
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('동작 명령 차단 확인');
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('0.12초 전');
  for (const code of ['CONTROL_BRIDGE_INHIBIT_STALE', 'OWNER_UNKNOWN:control', 'OWNER_BUSY:navigation']) {
    f.inputs.start_blockers.items = [code];
    await page.evaluate(() => window.preparation.refresh(true));
    await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  }
  f.inputs.start_blockers.items = ['CONTROL_BRIDGE_INHIBIT_VIOLATED'];
  Object.assign(f.observation, { state: 'INVALIDATED', reason: 'CONTROL_BRIDGE_INHIBIT_VIOLATED', can_stop: true });
  f.observation.bridge_guard.state = 'INVALID';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  expect(f.writes.filter(value => /initialization-proposals|seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
});

test('old active bridge explains missing inhibit capability and sends no implicit commands', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  f.inputs.start_blockers.items = ['CONTROL_BRIDGE_INHIBIT_UNSUPPORTED'];
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeDisabled();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측용 명령 차단 계약을 지원하지 않습니다');
  f.inputs.start_blockers.items = [];
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeEnabled();
  expect(f.writes.filter(value => value.path.includes('/observations/'))).toHaveLength(0);
});

test('forced refresh after pairing supersedes a late startable observation snapshot', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  const readCount = f.reads.length;
  f.holdInputsRead();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  // The post-write GET has already captured an empty blocker list. Hold the
  // response, not a timer, so this exercises the CI interleaving every time.
  await expect.poll(() => f.reads.length).toBe(readCount + 1);
  f.inputs.start_blockers.items = ['CONTROL_BRIDGE_INHIBIT_UNSUPPORTED'];
  await page.evaluate(() => { window.forcedRefresh = window.preparation.refresh(true); });
  f.releaseInputsRead();
  await page.evaluate(() => window.forcedRefresh);
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeDisabled();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측용 명령 차단 계약을 지원하지 않습니다');
  expect(f.reads.length).toBe(readCount + 2);
  expect(f.writes.map(value => value.path)).toEqual(['/api/v1/navigation/operational-3d/pair']);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
});

test('exact observation stop remains available during a read and refreshes after the late response', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.locator('[data-prep="pair-confirmation"]').check();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await page.getByRole('button', { name: '센서 관측 시작' }).click();
  const stop = page.getByRole('button', { name: '센서 관측 종료' });
  await expect(stop).toBeEnabled();
  await page.evaluate(() => window.preparation.refresh(true));
  const readCount = f.reads.length;
  f.holdInputsRead();
  await page.evaluate(() => { window.pendingRead = window.preparation.refresh(true); });
  await expect.poll(() => f.reads.length).toBe(readCount + 1);
  await expect(stop).toBeEnabled();
  await stop.click();
  await expect.poll(() => f.writes.filter(value => value.path.endsWith('/fastlio/stop')).length).toBe(1);
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측 상태: 정지');
  f.releaseInputsRead();
  await page.evaluate(() => window.pendingRead);
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeEnabled();
  await expect(stop).toBeDisabled();
  expect(f.reads.length).toBe(readCount + 2);
  expect(f.writes.filter(value => value.path.includes('/observations/')).map(value => value.body)).toEqual([
    { confirmed: true }, { confirmed: true, session_id: 'a'.repeat(32) },
  ]);
});

for (const outcome of ['blocked', 'unblocked', 'read-failed']) {
  test(`overlapping preparation refreshes coalesce and keep observation admission closed: ${outcome}`, async ({ page }) => {
    const f = await fixture(page);
    await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
    await page.locator('[data-prep="pair-confirmation"]').check();
    await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
    const start = page.getByRole('button', { name: '센서 관측 시작' });
    await expect(start).toBeEnabled();
    f.inputs.start_blockers.items = outcome === 'unblocked' ? ['CONTROL_BRIDGE_INHIBIT_UNSUPPORTED'] : [];
    const readCount = f.reads.length;
    f.holdInputsRead();
    await page.evaluate(() => { window.firstRefresh = window.preparation.refresh(true); });
    await expect.poll(() => f.reads.length).toBe(readCount + 1);
    f.inputs.start_blockers.items = outcome === 'blocked' ? ['CONTROL_BRIDGE_INHIBIT_UNSUPPORTED'] : [];
    if (outcome === 'read-failed') f.failReads(1);
    await page.evaluate(() => {
      window.refreshSettled = false;
      window.forcedRefresh = Promise.all([window.preparation.refresh(true), window.preparation.refresh(true)])
        .then(() => { window.refreshSettled = true; });
    });
    await expect(start).toBeDisabled();
    expect(await page.evaluate(() => window.refreshSettled)).toBe(false);
    // Exercise the handler guard as well as the native disabled button.
    await start.dispatchEvent('click');
    expect(f.writes.filter(value => value.path.includes('/observations/'))).toHaveLength(0);
    f.releaseInputsRead();
    await page.evaluate(() => window.forcedRefresh);
    expect(f.reads.length).toBe(readCount + 2);
    if (outcome === 'unblocked') await expect(start).toBeEnabled();
    else await expect(start).toBeDisabled();
    if (outcome === 'blocked') await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측용 명령 차단 계약을 지원하지 않습니다');
    if (outcome === 'read-failed') await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측 입력 확인 실패');
    expect(f.writes.map(value => value.path)).toEqual(['/api/v1/navigation/operational-3d/pair']);
    expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  });
}

for (const [state, reason, guardState, message] of [
  ['STARTING', 'OBSERVATION_START_PENDING', 'WAITING', '실제 실행 세대를 기다립니다'],
  ['UNKNOWN', 'OBSERVATION_START_OUTCOME_UNKNOWN', 'INVALID', '시작 결과가 불명입니다'],
  ['STOPPED', 'OBSERVATION_STOP_ACCEPTANCE_UNCONFIRMED', 'HELD', '종료 요청의 수락을 확인하지 못했습니다'],
  ['STOPPED', 'CONTROL_BRIDGE_INHIBIT_RELEASE_PENDING', 'RELEASING', '차단 해제를 확인 중입니다'],
]) test(`bridge uncertain boundary ${state} ${reason} blocks start and proposal without implicit retry`, async ({ page }) => {
  const f = await proposalFixture(page);
  const writesBefore = structuredClone(f.writes); // fixture includes one explicit start
  Object.assign(f.observation, { state, reason, active: false, can_start: false, can_stop: false,
    bridge_guard: { mode: 'active_inhibited', state: guardState, source: 'signed_control_bridge', status_age_s: .1 } });
  f.inputs.start_blockers.items = ['OBSERVATION_SESSION_NOT_STARTABLE'];
  f.inputs.evidence.valid = false;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText(message);
  expect(f.writes).toEqual(writesBefore);
});


test('grouped proof displays actual member differences and confirms only with explicit acknowledgement', async ({page}) => {
  const f=await proposalFixture(page); f.proofMode('group-valid');
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 후보 2개');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('#1 Δz 0.010m');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('전역 유일성·실제 위치 정확도는 확인되지 않았습니다');
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  const confirm=page.getByRole('button',{name:'제안값 확인·②에 적용'});await expect(confirm).toBeDisabled();
  await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check();await expect(confirm).toBeEnabled();await confirm.click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('원래 모호성은 유지');
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(1);
  expect(f.writes.filter(v=>/seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
});
for (const mode of ['group-two','group-missing-current','group-outside','group-aged']) {
  test(`grouped proof ${mode} never confirms`, async ({page}) => {
    const f=await proposalFixture(page);f.proofMode(mode);
    await page.getByLabel(/현장 정지 상태를 직접 감독/).check();await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
    if (mode === 'group-outside') { await expect(page.locator('[data-prep="proposal-result"]')).toContainText('그룹의 모든 후보가'); await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check(); }
    else await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
    await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
    expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  });
}


for (const mode of ['group-ttl-exact', 'group-ttl-next']) {
  test(`conditional proof TTL ${mode} is checked at the exact generated boundary`, async ({page}) => {
    const f=await proposalFixture(page); f.proofMode(mode);
    await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
    const preview=page.locator('[data-prep="geometry-preview"]');
    if (mode === 'group-ttl-exact') {
      await expect(preview).toContainText('미적용');
      await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 후보 2개');
      await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
      await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check();
      await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeEnabled();
    } else {
      await expect(preview).toContainText('미확인 또는 만료');
      await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
    }
    expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  });
}

test('conditional acknowledgements survive a stale read of the same proposal but never bypass freshness', async ({page}) => {
  const f=await proposalFixture(page); f.proofMode('group-valid');
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  const supervision=page.getByLabel(/현장 정지 상태를 직접 감독/), ack=page.locator('[data-prep="conditional-ack"]');
  const confirm=page.getByRole('button',{name:'제안값 확인·②에 적용'});
  await supervision.check();await ack.check();await expect(confirm).toBeEnabled();
  f.holdProposalReads();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
  console.log('CONSENT_OBSERVATION stale',JSON.stringify({supervision:await supervision.isChecked(),ack:await ack.isChecked(),confirmDisabled:await confirm.isDisabled()}));
  await expect(confirm).toBeDisabled();await expect(supervision).toBeChecked();await expect(ack).toBeChecked();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  f.releaseProposalReads();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await expect(supervision).toBeChecked();await expect(ack).toBeChecked();await expect(confirm).toBeEnabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});


async function consentedConditionalProposal(page) {
  const f=await proposalFixture(page);f.proofMode('group-valid');
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  await page.locator('[data-prep="conditional-ack"]').check();
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeEnabled();
  return f;
}

test('conditional acknowledgements clear when a valid-looking new proof replaces the bound proof', async ({page}) => {
  const f=await consentedConditionalProposal(page);f.proofMode('group-new-proof');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('제안 증명이나 현재 문맥이 바뀌어');
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  await expect(page.locator('[data-prep="conditional-ack"]')).not.toBeChecked();
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('conditional acknowledgements clear on source change and an in-flight old read cannot restore them', async ({page}) => {
  const f=await consentedConditionalProposal(page);f.holdProposalReads();
  await expect.poll(()=>f.heldProposalReadCount()).toBeGreaterThan(0);
  f.inputs.evidence.pose.publisher_epoch='4'.repeat(32);
  await page.evaluate(()=>window.preparation.refresh(true));
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  await expect(page.locator('[data-prep="conditional-ack"]')).not.toBeChecked();
  f.releaseProposalReads();
  await expect(page.locator('[data-prep="geometry-preview"]')).not.toContainText('미적용');
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('conditional acknowledgements are never recreated after an explicit uncheck', async ({page}) => {
  const f=await consentedConditionalProposal(page),ack=page.locator('[data-prep="conditional-ack"]');
  await ack.uncheck();f.holdProposalReads();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
  await expect(ack).not.toBeChecked();await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  f.releaseProposalReads();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await expect(ack).not.toBeChecked();await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

for (const contextChange of ['prior', 'calibration', 'map']) {
  test(`conditional acknowledgements clear when the ${contextChange} binding changes`, async ({page}) => {
    const f=await consentedConditionalProposal(page);
    if (contextChange === 'prior') await page.evaluate(() => { window.fakeOperatorDraft.pose.x += .1; window.fakeOperatorDraft.revision++; window.preparation.draftChanged(); });
    if (contextChange === 'calibration') { f.inputs.pair.calibration_sha256='d'.repeat(64);await page.evaluate(()=>window.preparation.refresh(true)); }
    if (contextChange === 'map') { f.state.selected.navigation_2d.revision='2'.repeat(64);await page.evaluate(()=>window.preparation.refresh(true)); }
    await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
    await expect(page.locator('[data-prep="conditional-ack"]')).not.toBeChecked();
    await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
    expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  });
}


test('conditional acknowledgements clear on invalid age metadata in a later read', async ({page}) => {
  const f=await consentedConditionalProposal(page);f.proofMode('group-bad-age');
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  await expect(page.locator('[data-prep="conditional-ack"]')).not.toBeChecked();
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});


test('conditional acknowledgements clear when the proposal identity changes', async ({page}) => {
  const f=await consentedConditionalProposal(page);f.proofMode('group-new-id');
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  await expect(page.locator('[data-prep="conditional-ack"]')).not.toBeChecked();
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('supervision alone is cleared if the ready proof changes before conditional acknowledgement', async ({page}) => {
  const f=await proposalFixture(page);f.proofMode('group-valid');
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="conditional-label"]')).toBeVisible();
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).toBeChecked();
  await expect(page.locator('[data-prep="conditional-ack"]')).not.toBeChecked();
  f.proofMode('group-new-proof');
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});


for (const previousAcknowledged of [false, true]) {
  test(`explicit recalculation after ready proof resets old consent (${previousAcknowledged ? 'acknowledged' : 'unacknowledged'})`, async ({page}) => {
    const f=await proposalFixture(page);f.proofMode('group-valid');f.distinctProposalIds();
    const propose=page.getByRole('button',{name:'초기 위치 제안 계산'}), preview=page.locator('[data-prep="geometry-preview"]');
    const supervision=page.getByLabel(/현장 정지 상태를 직접 감독/), ack=page.locator('[data-prep="conditional-ack"]');
    await propose.click();await expect(preview).toContainText('미적용');
    await supervision.check();if (previousAcknowledged) await ack.check();
    await expect(propose).toBeEnabled();f.holdProposalReads();await propose.click();
    await expect.poll(()=>f.heldProposalReadCount()).toBeGreaterThan(0);
    await expect(supervision).not.toBeChecked();await expect(ack).not.toBeChecked();
    await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
    expect(f.writes.filter(v=>v.path.endsWith('/initialization-proposals'))).toHaveLength(2);
    expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
    f.releaseProposalReads();await expect(preview).toContainText('미적용');
    const detail=JSON.parse(await page.locator('[data-prep="details"]').textContent());
    expect(detail.initialization_proposal.proposal_id).toBe('e'.repeat(24));
    await expect(supervision).not.toBeChecked();await expect(ack).not.toBeChecked();
    await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
    expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  });
}


test('explicit recalculation can progress through running before the new proof is ready', async ({page}) => {
  const f=await proposalFixture(page);f.proofMode('group-valid');f.distinctProposalIds();
  const propose=page.getByRole('button',{name:'초기 위치 제안 계산'}), preview=page.locator('[data-prep="geometry-preview"]');
  await propose.click();await expect(preview).toContainText('미적용');await expect(propose).toBeEnabled();
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();await page.locator('[data-prep="conditional-ack"]').check();
  f.runNextProposalOnce();await propose.click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('제안 계산 중');
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  await expect(preview).toContainText('미적용');
  const detail=JSON.parse(await page.locator('[data-prep="details"]').textContent());
  expect(detail.initialization_proposal.proposal_id).toBe('e'.repeat(24));
  await expect(page.getByLabel(/현장 정지 상태를 직접 감독/)).not.toBeChecked();
  await expect(page.locator('[data-prep="conditional-ack"]')).not.toBeChecked();
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('explicit conditional check crossing freshness expiry remains recorded but cannot confirm while stale', async ({page}) => {
  const f=await proposalFixture(page);f.proofMode('group-valid');
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();
  const ack=page.locator('[data-prep="conditional-ack"]'), confirm=page.getByRole('button',{name:'제안값 확인·②에 적용'});
  f.holdProposalReads();
  // Simulate a slow event handler between the real pointer click and onchange.
  // The UI's own clock and timer still expire; no value or control is auto-filled.
  await page.evaluate(() => document.querySelector('[data-prep="conditional-ack"]').addEventListener('click', () => {
    const until=performance.now()+1100;while (performance.now()<until) {};
  }, {capture:true,once:true}));
  try { await ack.check(); } catch (error) {
    console.log('ACK_ENTRY_OBSERVATION',JSON.stringify({checked:await ack.isChecked(),confirmDisabled:await confirm.isDisabled()}));
    throw error;
  }
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
  console.log('ACK_ENTRY_OBSERVATION',JSON.stringify({checked:await ack.isChecked(),confirmDisabled:await confirm.isDisabled()}));
  await expect(ack).toBeChecked();await expect(confirm).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  f.releaseProposalReads();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await expect(ack).toBeChecked();await expect(confirm).toBeEnabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('explicit conditional acknowledgement is possible after freshness has expired without enabling confirmation', async ({page}) => {
  const f=await proposalFixture(page);f.proofMode('group-valid');
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  const ack=page.locator('[data-prep="conditional-ack"]'),confirm=page.getByRole('button',{name:'제안값 확인·②에 적용'});
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();f.holdProposalReads();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
  await expect(ack).toBeVisible();await expect(ack).not.toBeChecked();await ack.check();
  await expect(ack).toBeChecked();await expect(confirm).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  f.releaseProposalReads();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await expect(ack).toBeChecked();await expect(confirm).toBeEnabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('conditional acknowledgement entered while stale is cleared on later calibration change', async ({page}) => {
  const f=await proposalFixture(page);f.proofMode('group-valid');
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  const supervision=page.getByLabel(/현장 정지 상태를 직접 감독/),ack=page.locator('[data-prep="conditional-ack"]');
  await supervision.check();f.holdProposalReads();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');await ack.check();
  await expect(ack).toBeChecked();await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  f.inputs.pair.calibration_sha256='d'.repeat(64);await page.evaluate(()=>window.preparation.refresh(true));
  await expect(ack).not.toBeChecked();await expect(supervision).not.toBeChecked();f.releaseProposalReads();
  await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

test('operator prior requests use the X Y yaw draft without user-entered uncertainty', async ({page}) => {
  const f=await proposalFixture(page,{expectReady:false});
  await page.evaluate(({cloud,grid})=>{window.fakeOperatorDraft={status:'ready',revision:1,pose:{x:1.2,y:2.3,yaw:.4},bundle_generation:'b'.repeat(32),localization_map:{id:cloud.id,revision:cloud.revision},navigation_map:{id:grid.id,revision:grid.revision}};window.preparation.draftChanged();},{cloud,grid});
  await expect(page.locator('#host')).toContainText('서버 기본 검증 한도 위치 0.25 m · 방향 ±0.20 rad (약 ±11.5°)');
  await expect(page.locator('#host')).toContainText('사용자 위치 불확실성 측정이나 실제 정확도의 보증이 아닙니다');
  await expect(page.getByLabel('위치 불확실 반경 (m)')).toHaveCount(0);
  await expect(page.getByLabel('방향 불확실 ± (도)')).toHaveCount(0);
  await expect(page.locator('[data-prep="prior-status"]')).toContainText('미전송 사용자 초안');
  await expect(page.getByRole('button',{name:'초기 위치 제안 계산'})).toBeDisabled();
  await page.getByLabel(/이 초안이 현재 지도에서 정지/).check();
  await expect(page.getByRole('button',{name:'초기 위치 제안 계산'})).toBeEnabled();
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  const writes=f.writes.filter(v=>v.path.endsWith('/initialization-proposals'));
  expect(writes).toHaveLength(1);
  expect(writes[0].body.operator_prior.pose).toEqual({x:1.2,y:2.3,yaw:.4});
  expect(writes[0].body.operator_prior).not.toHaveProperty('bounds');
  expect(writes[0].body.operator_prior).not.toHaveProperty('bounds_source');
  expect(writes[0].body.operator_prior).not.toHaveProperty('effective_bounds');
  expect(writes[0].body.operator_prior.stationary_current_pose_confirmed).toBe(true);
  expect(f.writes.filter(v=>/confirm-geometry|seed-geometry|\/navigation\/start|initial-pose|\/match|\/goal/.test(v.path))).toHaveLength(0);
});


for (const mode of ['policy-missing','policy-changed','policy-forged']) {
  test(`server bound provenance ${mode} cannot enable confirmation`, async ({page})=>{
    const f=await proposalFixture(page);f.proofMode(mode);
    await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
    await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미확인 또는 만료');
    await expect(page.getByRole('button',{name:'제안값 확인·②에 적용'})).toBeDisabled();
    expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
  });
}

test('server-owned bounds are displayed as a policy, not a user uncertainty measurement', async ({page})=>{
  const f=await proposalFixture(page);f.proofMode('group-valid');
  await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('후보 선택에 적용된 범위 (서버 정책): 위치 0.25 m · 방향 ±0.2 rad');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('사용자 불확실성 측정이나 실제 정확도가 아닙니다');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('전역 유일성·실제 위치 정확도는 확인되지 않았습니다');
  expect(f.writes.filter(v=>v.path.endsWith('/confirm-geometry'))).toHaveLength(0);
});

for (const provenance of ['explicit','legacy']) {
 test(`restored ${provenance} prior shows its verified selection bounds separately from handoff bounds`, async ({page})=>{
  const f=await proposalFixture(page);await page.getByRole('button',{name:'초기 위치 제안 계산'}).click();
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await page.getByLabel(/현장 정지 상태를 직접 감독/).check();await page.getByLabel(/전역 유일성·실제 위치 정확도는 확인되지 않았음/).check();
  await page.getByRole('button',{name:'제안값 확인·②에 적용'}).click();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('후보 선택에 적용된 범위 (서버 정책): 위치 0.25 m · 방향 ±0.2 rad');
  const proof=f.state.selected.seed_geometry.handoff.operator_prior_resolution;proof.operator_prior.bounds={xy_m:.1,yaw_rad:.15};
  if(provenance==='explicit'){proof.bounds_source='operator_prior';proof.effective_bounds={xy_m:.1,yaw_rad:.15};}
  else {delete proof.bounds_source;delete proof.effective_bounds;}
  await f.reload();
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('후보 선택에 적용된 범위 (사용자 입력 범위): 위치 0.1 m · 방향 ±0.15 rad');
  await expect(page.locator('[data-prep="handoff-result"]')).toContainText('별도 handoff 로컬 후보 사용 범위: 120초 · XY 0.25 m · yaw 0.2 rad');
 });
}
