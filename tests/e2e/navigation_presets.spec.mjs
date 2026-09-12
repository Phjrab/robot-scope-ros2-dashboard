import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('Nav2 team presets save, refresh and reload without applying or driving', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  backend.state.navigation.pipeline = { state: 'running', job_id: 'f'.repeat(32), error: '' };
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/#navigation');
  const speed = page.locator('[data-navigation-parameter="desired_linear_vel"]');
  await expect(speed).toBeEnabled();
  await speed.fill('0.5');
  await page.locator('#navigationPresetName').fill('팀 A <복도>');
  await page.locator('#navigationPresetSave').click();
  await expect(page.locator('#navigationPresetMessage')).toContainText('저장했습니다');
  await expect(page.locator('#navigationPreset option:checked')).toHaveText('사용자 · 팀 A <복도>');
  await expect(speed).toHaveValue('0.5');
  await expect(page.locator('#navigationParameterApply')).toBeDisabled();
  expect(backend.state.navigationPresets[0].values.desired_linear_vel).toBe(0.5);

  await speed.fill('0.7');
  await page.locator('#navigationPresetRefresh').click();
  await expect(page.locator('#navigationPresetMessage')).toContainText('목록을 불러왔습니다');
  await expect(speed).toHaveValue('0.7');
  await page.locator('#navigationPresetName').fill('팀 A <복도>');
  await page.locator('#navigationPresetSave').click();
  await expect(page.locator('#navigationPresetMessage')).toContainText('저장 실패');
  await expect(speed).toHaveValue('0.7');
  await expect(page.locator('#navigationPresetName')).toHaveValue('팀 A <복도>');

  await page.reload();
  await expect(page.locator('#navigationPreset option')).toHaveCount(3);
  await expect(speed).toHaveValue('0.25');
  await page.locator('#navigationPreset').selectOption(backend.state.navigationPresets[0].id);
  await page.locator('#navigationPresetLoad').click();
  await expect(speed).toHaveValue('0.5');
  await expect(page.locator('#navigationParameterApply')).toBeDisabled();
  expect(backend.state.requests.filter((r) => r.path.startsWith('/api/v1/navigation/') && r.path !== '/api/v1/navigation/presets')).toEqual([]);
  expect(errors).toEqual([]);
});
