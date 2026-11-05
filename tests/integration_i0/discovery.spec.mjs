import {test, expect} from '@playwright/test';
import {installDashboardBackend} from '../e2e/dashboard_backend.mjs';

const off = 'http://127.0.0.1:4194';
const tls = 'https://127.0.0.1:4193';
const state = page => page.locator('[data-slot=status]');

for (const width of [390, 1440]) test(`default OFF dashboard menu and public landing ${width}px`, async ({page}) => {
  await page.setViewportSize({width, height: 1000});
  const backend = await installDashboardBackend(page);
  const extensionRequests = [];
  page.on('request', request => { if (request.url().includes('/api/v1/extensions/')) extensionRequests.push(request.url()); });
  await page.goto(`${off}/#navigation`);
  await expect(page.locator('#navigationStopButton')).toBeVisible();
  if (width > 800) await expect(page.locator('.top-actions a[href="/extensions"]')).toBeVisible();
  const more = page.locator('.advanced-tools');
  if (!await more.evaluate(element => element.open)) await more.locator('summary').click();
  await more.getByRole('link', {name: '확장 기능', exact: true}).click();
  await expect(page).toHaveURL(/\/extensions#multimap$/);
  await expect(page.locator('#expansion-nav button')).toHaveCount(5);
  await expect(page.locator('#expansion-status')).toContainText('FEATURE_DISABLED');
  await page.getByRole('button', {name: '주행 기록 재생', exact: true}).click();
  await expect(page.locator('#expansion-status')).toContainText('로컬 기록 재생');
  await expect(page.locator('input[type=file]')).toHaveCount(0);
  await page.getByRole('button', {name: '성능 진단 안내', exact: true}).click();
  await expect(page.locator('[data-help=diagnostics]')).toContainText('NOT_RUN');
  await expect(page.locator('[data-help=diagnostics]')).toContainText('UNKNOWN');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(extensionRequests).toEqual([]);
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
  expect(backend.mutations('/api/v1/control/stop')).toHaveLength(0);
  await page.getByRole('link', {name: '← Robot Scope'}).click();
  await expect(page.locator('#navigationStopButton')).toBeAttached();
  await page.locator('[data-nav=experiments]').click();
  await expect(page).toHaveURL(/#experiments$/);
  await expect(page.locator('#manual2dExperiment')).toBeVisible();
  await expect(page.locator('#manual2dExperiment h2')).toHaveText('2D 수동 초기 위치 주행');
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
  await page.goto(`${off}/#settings`);
  await page.locator('[data-cockpit-software-stop]').click();
  await expect.poll(() => backend.mutations('/api/v1/control/stop').length).toBe(1);
});

test.describe('actual configured HTTPS owner', () => {
  test.use({baseURL: tls, ignoreHTTPSErrors: true, hasTouch: true});
  test('direct manual XYZ, two-source save/reload and new tab over real TLS', async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 1000});
    const writes = [], errors = [];
    page.on('request', r => { if (r.method() !== 'GET') writes.push(new URL(r.url()).pathname); });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/extensions');
    await expect(page.locator('#expansion-login, #expansion-code, #expansion-logout')).toHaveCount(0);
    await expect(state(page)).toContainText('Catalogue ready');
    expect(writes).toEqual([]);
    for (const name of ['map0', 'map1']) {
      await page.getByRole('checkbox', {name: `Select ${name}`, exact: true}).check();
      await expect(state(page)).toContainText('previews ready');
    }
    const ids = await page.locator('[data-field=anchor] option').evaluateAll(options => Object.fromEntries(options.map(o => [o.textContent, o.value])));
    await page.locator('[data-field=anchor]').selectOption(ids.map0);
    await expect(state(page)).toContainText('previews ready');
    await page.locator('[data-field=view]').selectOption('before');
    await page.locator('[data-pose=x]').fill('0.35');
    await page.locator('[data-pose=x]').press('Tab');
    await page.locator('[data-pose=yaw]').fill('0.18');
    await page.locator('[data-pose=yaw]').press('Tab');
    const previews = await page.evaluate(async ids => Promise.all([ids.map0, ids.map1].map(async id => {
      const response = await fetch(`/api/v1/extensions/multimap/sources/${id}/preview`);
      return (await response.json()).preview.points;
    })), ids);
    await page.locator('.mmf details summary').click();
    for (const index of [0, 1, 2]) {
      await page.locator('[data-field=sourceXYZ]').fill(previews[1].slice(index * 3, index * 3 + 3).join(','));
      await page.locator('[data-field=anchorXYZ]').fill(previews[0].slice(index * 3, index * 3 + 3).join(','));
      await page.locator('[data-action=pair]').click();
    }
    await expect(page.locator('[data-slot=pairs] li').filter({hasText: /[123]\. /})).toHaveCount(3);
    await expect(page.locator('[data-slot=pairs]')).toContainText('Add a fourth dispersed pair');
    await page.locator('[data-action=start]').click();
    await expect(state(page)).toContainText('SOLVED_CANDIDATE');
    await expect(page.locator('[data-slot=diagnostics] tr')).toHaveCount(2);
    await expect(page.locator('[data-slot=diagnostics] td').nth(1)).toContainText('1.00');
    await expect(page.locator('[data-slot=diagnostics] td').nth(2)).toContainText('RMSE');
    await expect(page.locator('[data-action=save]')).toBeDisabled();
    await page.locator('[data-field=view]').selectOption('after');
    await page.locator('[data-field=ack]').check();
    await page.locator('[data-action=accept]').click();
    await expect(state(page)).toContainText('ACCEPTED');
    await page.locator('[data-field=name]').fill('tls_browser_review');
    const receipt = page.waitForResponse(r => r.url().endsWith('/exports') && r.request().method() === 'POST');
    await page.locator('[data-action=save]').click();
    const response = await receipt;
    expect(response.status()).toBe(201);
    await expect(state(page)).toContainText('Saved and listed');
    const manifest = await page.evaluate(async () => {
      const sources = await (await fetch('/api/v1/extensions/multimap/sources')).json();
      const saved = sources.sources.find(source => source.acquisition.display_name === 'tls_browser_review');
      return (await fetch(`/api/v1/extensions/multimap/exports/${saved.map_id}`)).json();
    });
    expect(manifest.point_count).toBe(800);
    expect(manifest.operational_installed).toBe(false);
    await expect(page.locator('[data-slot=saved]')).toContainText(manifest.output_hashes['map.pcd']);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({path: info.outputPath('tls-review-saved-mobile.png'), fullPage: true});
    await page.reload();
    await expect(page.getByRole('checkbox', {name: 'Select tls_browser_review', exact: true})).toBeVisible();
    await page.locator('[data-feature=scene]').tap();
    await expect(page.locator('#expansion-status')).toContainText('UNAVAILABLE');
    await page.context().clearCookies();
    await page.locator('[data-feature=multimap]').click();
    await page.reload();
    await expect(page.getByRole('checkbox', {name: 'Select tls_browser_review', exact: true})).toBeVisible();
    const another = await page.context().newPage();
    await another.goto('/extensions#multimap');
    await expect(another.getByRole('checkbox', {name: 'Select tls_browser_review', exact: true})).toBeVisible();
    await another.close();
    expect(writes.every(path => path.startsWith('/api/v1/extensions/multimap/'))).toBe(true);
    expect(errors).toEqual([]);
  });

  test('local replay and map review open directly after reload without session requests', async ({page}) => {
    const sessions = [];
    page.on('request', request => {
      if (new URL(request.url()).pathname.startsWith('/api/v1/extensions/session')) sessions.push(request.url());
    });
    await page.goto('/extensions#replay');
    await expect(page.locator('.rr-banner')).toContainText('REPLAY');
    await page.reload();
    await expect(page.locator('.rr-banner')).toContainText('REPLAY');
    await page.locator('[data-feature=multimap]').click();
    await expect(state(page)).toContainText('Catalogue ready');
    await page.locator('[data-feature=scene]').click();
    await expect(page.locator('#expansion-status')).toContainText('UNAVAILABLE');
    expect(sessions).toEqual([]);
    await expect(page.locator('input[type=password]')).toHaveCount(0);
  });
});
