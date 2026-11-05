// SYNTHETIC fixture: no ROS, robot or actuator.
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
const html = readFileSync('robot_dashboard/static/index.html', 'utf8');
const section = html.match(/<section class="page-view" data-page="experiments" hidden>[\s\S]*?<\/section>/)[0].replace(' hidden>', '>');
test('manual experiment requires explicit preparation, seed and goal', async ({ page }) => {
  await page.route('**/manual-fixture.html', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: `<link rel="stylesheet" href="/styles.css">${section}<script src="/navigation.js"></script>` }));
  await page.goto('/manual-fixture.html');
  await page.evaluate(async () => {
    const { initializeManual2dExperiment } = await import('/features/experiments/manual_2d/index.js');
    const id = 'a'.repeat(24), revision = 'b'.repeat(64);
    const meta = { id, revision, name:'SYNTHETIC map', kind:'occupancy2d' };
    window.fixture = { maps:[meta], navigation:{ available:true, robot_online:true, pipeline:{state:'idle'}, safety:{can_start:false, blockers:['software_stop_latched']}, goal:{state:'idle'} }, parameters:{revision:'c'.repeat(64)}, available:true, busy:false };
    window.writes = [];
    const api = async path => path.endsWith('/data') ? {map_id:id, revision, frame_id:'map', width:10, height:10, resolution:1, origin:[0,0,0], data_b64:btoa('\0'.repeat(100))} : {map_id:id,map_revision:revision,annotation_revision:'d'.repeat(64),points:[]};
    const mutate = async (path, body) => { window.writes.push({path,body}); const nav = window.fixture.navigation;
      if (path.endsWith('/start')) Object.assign(nav, {mode:'manual_seeded_2d',map:{id,revision},pipeline:{state:'running',job_id:'job1'},safety:{can_set_initial_pose:true,can_stop:true},manual_seed:{state:'waiting_initial_pose',seed_generation:0,source_epoch:1}});
      if (path.endsWith('/initial-pose')) Object.assign(nav, {safety:{can_set_initial_pose:true,can_send_goal:true,can_stop:true},manual_seed:{state:'ready_manual',seed_generation:1,source_epoch:1}});
      return nav; };
    initializeManual2dExperiment({host:document.querySelector('#manual2dExperiment'),api,engine:window.RobotNavigation,context:()=>window.fixture,mutate,refresh:async()=>{}});
    document.dispatchEvent(new CustomEvent('robot-scope:page-change'));
  });
  await expect(page.locator('[data-manual="map-info"]')).toContainText('revision');
  expect(await page.evaluate(() => window.writes.length)).toBe(0);
  await expect(page.locator('[data-manual="prepare"]')).toBeDisabled();
  await page.locator('[data-manual="site"]').check();
  await expect(page.locator('[data-manual="prepare"]')).toBeDisabled();
  await expect(page.locator('[data-manual="stop-notice"]')).toContainText('SOFTWARE STOP CLEAR');
  await expect(page.locator('[data-manual="stop-notice"] a')).toHaveAttribute('href', '#settings');
  expect(await page.evaluate(() => window.writes)).toEqual([]);
  await page.evaluate(() => {
    window.fixture.navigation.safety = {can_start:true, blockers:[]};
    document.dispatchEvent(new CustomEvent('robot-scope:page-change'));
  });
  await expect(page.locator('[data-manual="stop-notice"]')).toBeHidden();
  await page.locator('[data-manual="prepare"]').click();
  const canvas = page.locator('[data-manual="canvas"]');
  async function drag(start) {
    await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width * start, box.y + box.height * .5);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * (start + .1), box.y + box.height * .5);
    await page.mouse.up();
  }
  await drag(.45);
  await page.locator('[data-manual="send"]').click();
  await page.locator('[data-manual="goal"]').click();
  await drag(.5);
  await expect(page.locator('[data-manual="send"]')).toBeEnabled();
  page.once('dialog', dialog => dialog.accept()); await page.locator('[data-manual="send"]').click();
  const writes = await page.evaluate(() => window.writes);
  expect(writes.map(w => w.path)).toEqual(['/api/v1/navigation/start','/api/v1/navigation/initial-pose','/api/v1/navigation/goal']);
  expect(writes[0].body.mode).toBe('manual_seeded_2d'); expect(writes[1].body.job_id).toBe('job1'); expect(writes[1].body.source_epoch).toBe(1); expect(writes[2].body.seed_generation).toBe(1);

  // The process can remain running after the velocity owner deactivates.
  // A previous accepted receipt is not current permission to move.
  await page.evaluate(() => {
    const nav = window.fixture.navigation;
    nav.deactivation_reason = 'navigation localization inputs are stale';
    nav.safety = {can_set_initial_pose:false, can_send_goal:false, can_stop:true};
    nav.manual_seed = {state:'reseed_required', seed_generation:2, source_epoch:1,
      reason:'MANUAL_SESSION_OR_SOURCE_UNAVAILABLE', tf_readback:false,
      receipt:{accepted:true, accepted_ros_ns:'1793863645465697856'}};
    document.dispatchEvent(new CustomEvent('robot-scope:page-change'));
  });
  await expect(page.locator('[data-manual="status"]')).toContainText('주행 제어가 중단됐습니다');
  await expect(page.locator('[data-manual="status"]')).toContainText('navigation localization inputs are stale');
  await expect(page.locator('[data-manual="details"]')).toContainText('초기 위치 수락 기록');
  await expect(page.locator('[data-manual="send"]')).toBeDisabled();
  await expect(page.locator('[data-manual="stop"]')).toBeEnabled();
  expect(await page.evaluate(() => window.writes)).toEqual(writes);
});
