import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('navigation health distinguishes inactive and unknown values from real zero measurements', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  const metrics = { cloud_frequency_hz: 0, cloud_jitter_s: 0, cloud_age_s: 0, runtime_health_age_s: 0,
    odometry_frequency_hz: 0, odometry_jitter_s: 0, odometry_age_s: 0, tf_age_s: 0, map_to_odom_age_s: 0, odom_to_base_age_s: 0,
    translation_jump_count: 0, heading_jump_count: 0, accepted_points: 0, input_points: 0, costmap_clear_count: 0, fresh_sequence_count: 0 };
  backend.state.navigation.pipeline = { state: 'idle', job_id: null };
  backend.state.navigation.localization_health = { state: 'UNAVAILABLE', reason_code: 'NAVIGATION_INACTIVE', metrics };
  await page.goto('/#navigation');
  const row = name => page.locator('#navigationHealthMetrics > div').filter({ has: page.getByText(name, { exact: true }) });
  await expect(page.locator('#navigationHealthReason')).toContainText('NAVIGATION_INACTIVE');
  await expect(row('POINTCLOUD').locator('strong')).toHaveText('—');
  await expect(row('POINTCLOUD').locator('small')).toContainText('age —');
  await expect(row('TF AGE').locator('strong')).toHaveText('—');
  await expect(row('FAST-LIO JUMPS').locator('strong')).toHaveText('— / —');
  await expect(row('SCAN POINTS').locator('strong')).toHaveText('— / —');
  await expect(row('COSTMAP CLEARS').locator('strong')).toHaveText('—');
  backend.state.navigation.pipeline = { state: 'running', job_id: '2'.repeat(32) };
  backend.state.navigation.localization_health = { state: 'READY', reason_code: 'HEALTHY', metrics };
  await expect(page.locator('#navigationHealthReason')).toContainText('HEALTHY');
  await expect(row('POINTCLOUD').locator('strong')).toHaveText('0.00 Hz');
  await expect(row('POINTCLOUD').locator('small')).toContainText('age 0.000 s');
  await expect(row('TF AGE').locator('strong')).toHaveText('0.000 s');
  await expect(row('FAST-LIO JUMPS').locator('strong')).toHaveText('0 / 0');
  await expect(row('SCAN POINTS').locator('strong')).toHaveText('0 / 0');
  await expect(row('COSTMAP CLEARS').locator('strong')).toHaveText('0');
  backend.state.navigation.localization_health = { state: 'READY', reason_code: 'HEALTHY', metrics: { ...metrics,
    cloud_frequency_hz: null, cloud_age_s: '', tf_age_s: false, translation_jump_count: '0', heading_jump_count: [],
    accepted_points: 1.5, input_points: 12, costmap_clear_count: {}, fresh_sequence_count: null } };
  await expect(row('POINTCLOUD').locator('strong')).toHaveText('—');
  await expect(row('POINTCLOUD').locator('small')).toContainText('age —');
  await expect(row('TF AGE').locator('strong')).toHaveText('—');
  await expect(row('FAST-LIO JUMPS').locator('strong')).toHaveText('— / —');
  await expect(row('SCAN POINTS').locator('strong')).toHaveText('— / 12');
  await expect(row('COSTMAP CLEARS').locator('strong')).toHaveText('—');
  await expect(row('COSTMAP CLEARS').locator('small')).toHaveText('fresh sequence —');
  expect(backend.state.requests.filter(request => request.method !== 'GET')).toEqual([]);
});
