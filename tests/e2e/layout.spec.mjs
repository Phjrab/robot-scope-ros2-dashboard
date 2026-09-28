import { test, expect } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

const pages = ['overview', 'mapping', 'maps', 'sensors', 'topics', 'controls', 'navigation', 'missions', 'route-planner', 'settings', 'cockpit'];

// Check clipping as well as document width: overflow:hidden can mask lost controls.
async function clippedControls(page) {
  return page.locator('.page-view.is-active').evaluate(root => {
    const issues = [];
    for (const el of root.querySelectorAll('button, input, select, textarea')) {
      const box = el.getBoundingClientRect();
      if (!box.width || !box.height || getComputedStyle(el).visibility === 'hidden') continue;
      for (let parent = el.parentElement; parent && parent !== root; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        // Fixed safety HUDs belong to the viewport, outside the centered workspace.
        if (style.position === 'fixed') {
          if (box.left < -2 || box.right > innerWidth + 2) issues.push(`${el.getAttribute('aria-label')}: outside viewport`);
          break;
        }
        const overflow = style.overflowX;
        // Horizontal carousels and resizable HUD bodies intentionally scroll.
        if (['auto', 'scroll'].includes(overflow)) break;
        if (['hidden', 'clip'].includes(overflow)) {
          const bounds = parent.getBoundingClientRect();
          if (box.left < bounds.left - 2 || box.right > bounds.right + 2) {
            issues.push(`${el.id || el.getAttribute('aria-label') || el.textContent.trim()}: clipped by ${parent.id || parent.className}`);
            break;
          }
        }
      }
    }
    return issues;
  });
}

for (const width of [320, 390, 768, 1024, 1440, 1920]) {
  test(`layout: all workspaces keep controls inside cards at ${width}px`, async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width, height: 900 });
    const backend = await installDashboardBackend(page);
    await page.goto('/#overview');
    for (const name of pages) {
      await page.evaluate(name => { location.hash = name; }, name);
      await expect(page.locator(`[data-page="${name}"]`)).toBeVisible();
      if (name === 'maps') await page.locator('.saved-map-item').first().click();
      if (name === 'route-planner') {
        await page.locator('#dashboardRoutePlannerHost').getByRole('button', { name: '+ 메뉴 항목 추가', exact: true }).first().click();
        await page.locator('.spatial-route-editor > summary').click();
      }
      await expect.poll(() => clippedControls(page), { message: `${name} at ${width}px` }).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    }
    expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
    expect(backend.mutations('/api/v1/navigation/start')).toHaveLength(0);
  });
}

test('layout: camera controls, conversion fields and planner rows align within their own cards', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installDashboardBackend(page);
  await page.goto('/#sensors');
  await expect(page.locator('#realsenseProfileApply')).toBeVisible();
  const camera = await page.locator('.camera-panel').evaluate(panel => {
    const box = selector => panel.querySelector(selector).getBoundingClientRect();
    const actions = [...panel.querySelectorAll('.camera-media-actions button')].map(el => el.getBoundingClientRect());
    return {
      applyWidth: box('#realsenseProfileApply').width,
      readoutWidth: box('.camera-media-readout').width,
      selectBottom: box('#cameraCaptureFormat').bottom,
      actionBottoms: actions.map(r => r.bottom),
      actionHeights: actions.map(r => r.height),
    };
  });
  expect(camera.applyWidth).toBeGreaterThan(85);
  expect(camera.readoutWidth).toBeGreaterThan(300);
  for (const bottom of camera.actionBottoms) expect(Math.abs(bottom - camera.selectBottom)).toBeLessThanOrEqual(1);
  for (const height of camera.actionHeights) expect(height).toBe(40);

  await page.evaluate(() => { location.hash = 'maps'; });
  const bottoms = await page.locator('.map-conversion-parameters input').evaluateAll(inputs => inputs.map(el => el.getBoundingClientRect().bottom));
  expect(Math.max(...bottoms) - Math.min(...bottoms)).toBeLessThanOrEqual(1);

  await page.evaluate(() => { location.hash = 'route-planner'; });
  const host = page.locator('#dashboardRoutePlannerHost');
  await expect(host.locator('.route-planner-order')).toBeVisible();
  const rows = await host.evaluate(host => {
    const box = selector => host.querySelector(selector).getBoundingClientRect();
    return { order: box('.route-planner-order').top, planning: box('.route-planner-planning').top,
      guidance: box('.route-planner-guidance').width, host: host.clientWidth,
      checkbox: box('.food-production-toolbar input').width };
  });
  expect(Math.abs(rows.order - rows.planning)).toBeLessThanOrEqual(1);
  expect(rows.guidance).toBeGreaterThan(rows.host * .9);
  expect(rows.checkbox).toBeLessThan(24);
});

test('layout: Nav2 compact groups remain separate and Costmaps spans the row', async ({ page }) => {
  await installDashboardBackend(page);
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/#navigation');
    const layout = await page.locator('#navigationParameterGroups').evaluate(root => {
      const rect = selector => root.querySelector(selector).getBoundingClientRect();
      const ids = [...root.querySelectorAll('.navigation-parameter-compact > .navigation-parameter-group')]
        .map(group => group.dataset.navigationParameterGroup);
      const fields = [...root.querySelectorAll('[data-navigation-parameter-group="costmap"] .navigation-parameter-field')]
        .map(field => field.getBoundingClientRect());
      return {
        ids,
        fieldCount: root.querySelectorAll('[data-navigation-parameter]').length,
        controller: rect('[data-navigation-parameter-group="controller"]').toJSON(),
        compact: rect('.navigation-parameter-compact').toJSON(),
        costmap: rect('[data-navigation-parameter-group="costmap"]').toJSON(),
        group: root.getBoundingClientRect().toJSON(),
        costmapFirstRows: fields.slice(0, 3).map(field => field.top),
      };
    });
    expect(layout.ids).toEqual(['core', 'goal', 'planner']);
    expect(layout.fieldCount).toBe(27);
    if (width === 1440) {
      expect(Math.abs(layout.controller.top - layout.compact.top)).toBeLessThanOrEqual(1);
      expect(layout.compact.left).toBeGreaterThan(layout.controller.right - 1);
    } else {
      expect(layout.compact.top).toBeGreaterThanOrEqual(layout.controller.bottom - 1);
    }
    expect(layout.costmap.top).toBeGreaterThanOrEqual(Math.max(layout.controller.bottom, layout.compact.bottom) - 1);
    expect(layout.costmap.width).toBeGreaterThan(layout.group.width * .95);
    expect(layout.costmapFirstRows[0] === layout.costmapFirstRows[1]).toBe(width !== 390);
  }
});

test('layout: map view controls never overlap the legend or custom point budget', async ({ page }) => {
  await installDashboardBackend(page);
  await page.goto('/#mapping');
  for (const width of [320, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.locator('#livePointBudget').selectOption('custom');
    for (const mode of ['cloud', 'projection']) {
      await page.locator('#mapViewMode').selectOption(mode);
      const result = await page.locator('.live-map-stage').evaluate(stage => {
        const controls = stage.querySelector('.scene-controls:not(.is-hidden)').getBoundingClientRect();
        const legend = stage.querySelector('.map-legend').getBoundingClientRect();
        return { overlaps: controls.left < legend.right && controls.right > legend.left && controls.top < legend.bottom && controls.bottom > legend.top };
      });
      expect(result.overlaps, `${mode} at ${width}px`).toBe(false);
      expect(await clippedControls(page)).toEqual([]);
    }
  }
});

for (const standalone of [false, true]) {
  test(`layout: Cockpit top tools do not overlap in ${standalone ? 'standalone' : 'embedded'} mode`, async ({ page }) => {
    test.setTimeout(60_000);
    await installDashboardBackend(page);
    await page.goto(standalone ? '/?workspace=cockpit#cockpit' : '/#cockpit');
    const layout = page.locator('[data-layout-library-action="toggle"]');
    const competition = page.locator('.cockpit-competition-toggle');
    await expect(layout).toBeVisible();
    for (const width of [320, 390, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.locator('#cockpitWorkspace').evaluate(el => el.scrollIntoView({ block: 'start' }));
      for (const expanded of [false, true]) {
        for (const toggle of [layout, competition]) {
          if (await toggle.getAttribute('aria-expanded') !== String(expanded)) {
            await toggle.evaluate(el => el.scrollIntoView({ block: 'start' }));
            await toggle.click();
          }
        }
        const geometry = await page.locator('#cockpitWorkspace').evaluate(workspace => {
          const controls = workspace.querySelector('.cockpit-scene-controls').getBoundingClientRect();
          const panels = ['.cockpit-layout-library', '.cockpit-competition-status'].map(selector => workspace.querySelector(selector).getBoundingClientRect());
          const overlaps = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
          const overlay = workspace.querySelector('.cockpit-overlay-layer').getBoundingClientRect();
          const launcher = workspace.querySelector('.cockpit-sensor-launcher').getBoundingClientRect();
          return {
            overlaps: [overlaps(controls, panels[0]), overlaps(controls, panels[1]), overlaps(panels[0], panels[1])],
            launcherOverlaps: overlaps(overlay, launcher),
            chipGap: overlay.top - workspace.getBoundingClientRect().top,
          };
        });
        expect(geometry.overlaps, `${width}px, expanded=${expanded}`).toEqual([false, false, false]);
        expect(geometry.launcherOverlaps, `${width}px, expanded=${expanded}`).toBe(false);
        expect(geometry.chipGap).toBeGreaterThanOrEqual(40);
        // Trial checks real hit routing without issuing a stop or any robot action.
        await page.locator('[data-cockpit-software-stop]').click({ trial: true });
      }
    }
  });
}
