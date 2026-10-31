import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

async function prepare(page, { yaw = 0 } = {}) {
  const backend = await installDashboardBackend(page);
  // Match SavedMapCatalog._occupancy_snapshot: /data has map_id, not id.
  const map = { map_id: backend.mapId, revision: backend.mapRevision, name: 'Synthetic UI verification',
    frame_id: 'map', width: 64, height: 48, resolution: .05, origin: [.2, -.4, yaw],
    data_b64: Buffer.alloc(64 * 48).toString('base64') };
  backend.on(`/api/v1/saved-maps/${backend.mapId}/data`, ({ json }) => json(map));
  Object.assign(backend.state.navigation, { pipeline: { state: 'running', job_id: '2'.repeat(32) },
    map: { id: map.map_id, revision: map.revision }, localization: { state: 'localized', pose: { x: 2.8, y: .3, yaw: .1 } },
    safety: { can_set_initial_pose: true, can_send_goal: true, blockers: [] } });
  backend.on('/api/v1/navigation/goal', ({ body, json }) => {
    backend.state.navigation.goal = { state: 'active', goal_id: '3'.repeat(32), pose: body.pose,
      precision_evidence: { goal_id: '3'.repeat(32), context: { map_id: body.map_id, map_revision: body.map_revision } } };
    return json(backend.state.navigation);
  });
  await page.addInitScript(() => {
    window.navLabels = [];
    const fillRect = CanvasRenderingContext2D.prototype.fillRect;
    const fillText = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillRect = function(x, y, w, h) {
      if (this.canvas.id === 'navigationMapCanvas' && x === 0 && y === 0 && w === this.canvas.width && h === this.canvas.height) window.navLabels = [];
      return fillRect.call(this, x, y, w, h);
    };
    CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
      if (this.canvas.id === 'navigationMapCanvas') window.navLabels.push(text);
      return fillText.call(this, text, ...args);
    };
  });
  await page.goto('/#navigation');
  await expect(page.locator('#navigationGoalPoseTool')).toBeEnabled();
  await page.evaluate(() => {
    window.navModelDraws = [];
    const original = window.RobotScene3D.prototype.drawRobotMapPreview;
    window.RobotScene3D.prototype.drawRobotMapPreview = function(ctx, pose, project, color) {
      const result = original.call(this, ctx, pose, project, color);
      window.navModelDraws.push({ drawn: result, pose: { ...pose }, color, status: this.getOfficialRobotModelStatus(),
        projected: project(pose), front: project({ x: pose.x + Math.cos(pose.yaw) * .4, y: pose.y + Math.sin(pose.yaw) * .4 }) });
      window.navModelDraws = window.navModelDraws.slice(-100);
      return result;
    };
  });
  return backend;
}

async function drag(page, mode, end = [.59, .41]) {
  await page.locator(mode === 'initial' ? '#navigationInitialPoseTool' : '#navigationGoalPoseTool').click();
  const canvas = page.locator('#navigationMapCanvas');
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width * .5, box.y + box.height * .5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * end[0], box.y + box.height * end[1], { steps: 5 });
  await page.mouse.up();
  return canvas;
}

async function lastDraw(page, color) {
  await expect.poll(() => page.evaluate(c => window.navModelDraws.filter(d => d.drawn && d.color === c).length, color)).toBeGreaterThan(0);
  return page.evaluate(c => window.navModelDraws.filter(d => d.drawn && d.color === c).at(-1), color);
}

test('Navigation initial is a dot, robot and goal use URDF; explicit send and stale map defense remain intact', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  const backend = await prepare(page);
  const robot = await lastDraw(page, '#7df0b6');
  expect(robot.pose).toEqual({ x: 2.8, y: .3, yaw: .1, mode: 'robot' });
  const canvas = await drag(page, 'initial');
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('INITIAL · 입력 중');
  expect(await page.evaluate(() => window.navModelDraws.some(draw => draw.color === '#5dded8'))).toBe(false);
  await canvas.screenshot({ path: 'test-results/navigation-urdf-initial.png' });
  await page.locator('#navigationPoseDiscard').click();
  await drag(page, 'goal');
  const goal = await lastDraw(page, '#ffc66d');
  expect(goal.status.url).toBe('/static/assets/go2/go2-official-lite.json');
  expect(goal.status.model).toBe(robot.status.model);
  expect(goal.front.x).toBeGreaterThan(goal.projected.x);
  expect(goal.front.y).toBeLessThan(goal.projected.y);
  expect(backend.state.requests.filter(r => /navigation\/(goal|initial-pose)$/.test(r.path))).toEqual([]);
  await canvas.screenshot({ path: 'test-results/navigation-urdf-goal-staged.png' });
  page.once('dialog', d => d.dismiss());
  await page.locator('#navigationPoseSend').click();
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
  page.once('dialog', d => d.accept());
  await page.locator('#navigationPoseSend').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/goal').length).toBe(1);
  expect(backend.mutations('/api/v1/navigation/goal')[0].body).toEqual({ map_id: backend.mapId, map_revision: backend.mapRevision,
    pose: { x: goal.pose.x, y: goal.pose.y, yaw: goal.pose.yaw }, confirmed: true });
  const sent = await lastDraw(page, '#a28bff');
  expect(sent.pose).toEqual({ x: goal.pose.x, y: goal.pose.y, yaw: goal.pose.yaw });
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('GOAL · ACTIVE');
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('ROBOT');
  await expect(page.locator('#navigationPoseSend')).toBeDisabled();
  await canvas.screenshot({ path: 'test-results/navigation-urdf-goal-active.png' });
  await page.reload();
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('GOAL · ACTIVE');
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('ROBOT');
  for (const state of ['canceling', 'canceled', 'succeeded', 'failed']) {
    backend.state.navigation.goal.state = state;
    await expect.poll(() => page.evaluate(() => window.navLabels)).toContain(`GOAL · ${state.toUpperCase()}`);
  }
  backend.state.navigation.goal.state = 'canceled';
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('GOAL · CANCELED');
  await drag(page, 'goal', [.41, .59]);
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('GOAL · STAGED');
  await canvas.screenshot({ path: 'test-results/navigation-urdf-overlap.png' });
  await page.locator('#navigationPoseDiscard').click();
  backend.state.navigation.goal.precision_evidence.context.map_revision = 'old-revision';
  await expect.poll(() => page.evaluate(() => window.navLabels.some(t => t.startsWith('GOAL ·')))).toBe(false);
  backend.state.navigation.goal.precision_evidence.context.map_revision = backend.mapRevision;
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('GOAL · CANCELED');
  backend.state.navigation.goal.precision_evidence.context.map_id = 'other-map';
  await expect.poll(() => page.evaluate(() => window.navLabels.some(t => t.startsWith('GOAL ·')))).toBe(false);
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(1);
});

test('unloaded official asset uses fallback then automatically redraws Goal URDF', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/static/assets/go2/go2-official-lite.json', async route => { await gate; await route.continue(); });
  const backend = await prepare(page);
  const canvas = await drag(page, 'goal');
  await expect.poll(() => page.evaluate(() => window.navModelDraws.some(d => !d.drawn))).toBe(true);
  await expect.poll(() => page.evaluate(() => window.navLabels)).toContain('GOAL · STAGED');
  await canvas.screenshot({ path: 'test-results/navigation-urdf-loading-fallback.png' });
  release();
  await lastDraw(page, '#ffc66d');
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
});

test('asset failure keeps editable goal marker and never sends a goal', async ({ page }) => {
  await page.route('**/static/assets/go2/go2-official-lite.json', route => route.abort());
  const backend = await prepare(page);
  const canvas = await drag(page, 'goal');
  await expect.poll(() => page.evaluate(() => window.navModelDraws.some(d => !d.drawn && d.status.state === 'error'))).toBe(true);
  await expect(page.locator('#navigationPoseSend')).toBeEnabled();
  await canvas.screenshot({ path: 'test-results/navigation-urdf-error-fallback.png' });
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
});

test.describe('rotated nonsquare map on narrow HiDPI screen', () => {
  test.use({ viewport: { width: 390, height: 1000 }, deviceScaleFactor: 2 });
  test('goal front follows the drag in light theme after resize', async ({ page }) => {
    const backend = await prepare(page, { yaw: .7 });
    await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
    const canvas = await drag(page, 'goal', [.64, .35]);
    const before = await lastDraw(page, '#ffc66d');
    expect(before.pose.yaw).toBeGreaterThan(.7);
    expect(before.front.x).toBeGreaterThan(before.projected.x);
    expect(before.front.y).toBeLessThan(before.projected.y);
    expect(await page.evaluate(() => devicePixelRatio)).toBe(2);
    await canvas.screenshot({ path: 'test-results/navigation-urdf-mobile-light.png' });
    await page.evaluate(() => { window.navModelDraws = []; });
    await page.setViewportSize({ width: 600, height: 1000 });
    const after = await lastDraw(page, '#ffc66d');
    expect(after.pose).toEqual(before.pose);
    expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
  });
});
