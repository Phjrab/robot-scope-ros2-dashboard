import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('success keeps real offset separate and never offers corrective motion', async ({ page }) => {
  const backend=await installDashboardBackend(page);
  backend.state.navigation.goal={state:'succeeded',goal_id:'1'.repeat(32),distance_remaining:0,
    precision_evidence:{goal_id:'1'.repeat(32), current:{fresh:true,frame_id:'map',body_frame_id:'base_link',stamp_ns:'1793188723000000000',age_s:.1,error:{xy_m:.308926,yaw_rad:-.472324}},
      result:{state:'succeeded',received_ros_ns:'1793188723000000000'}, stop:{confirmed_now:true}, precision:{satisfied_now:false}}};
  await page.goto('/#navigation');
  await expect(page.locator('#navigationGoalDistance')).toHaveText('0.00');
  await expect(page.locator('#navigationGoalMessage')).toContainText('Nav2 성공');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('XY 0.309 m');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('-27.06°');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('정지 확인: 현재 측정 확인');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('충족: 미충족');
  expect(backend.state.requests.filter(r => r.path.includes('/navigation/goal'))).toEqual([]);
});
