import { expect, test } from '@playwright/test';
import { waitForProposalReadiness } from '../fixtures/planar_prior_integration/readiness_wait.mjs';

async function schedule(page, transitions) {
  await page.setContent('<pre data-prep="details"></pre>');
  await page.evaluate(transitions => {
    const element = document.querySelector('[data-prep="details"]');
    element.textContent = JSON.stringify({ proposal_cleanup: { state: 'MONITORING' }, proposal_display_valid: false });
    for (const [delay, state, valid] of transitions) setTimeout(() => {
      element.textContent = JSON.stringify({ proposal_cleanup: { state }, proposal_display_valid: valid });
    }, delay);
  }, transitions);
}

test('probe observes a short valid window without issuing a request', async ({ page }) => {
  const requests = [];
  page.on('request', request => requests.push(request.url()));
  await schedule(page, [[1950, 'SETTLED', true], [2750, 'SETTLED', false]]);
  await waitForProposalReadiness(page);
  const details = JSON.parse(await page.locator('[data-prep="details"]').textContent());
  expect(details).toEqual({ proposal_cleanup: { state: 'SETTLED' }, proposal_display_valid: true });
  expect(requests).toEqual([]);
});

test('cleanup and valid display must be observed together', async ({ page }) => {
  await schedule(page, [[100, 'MONITORING', true], [500, 'SETTLED', false], [1000, 'SETTLED', true]]);
  await waitForProposalReadiness(page);
  expect(JSON.parse(await page.locator('[data-prep="details"]').textContent())).toEqual({
    proposal_cleanup: { state: 'SETTLED' }, proposal_display_valid: true,
  });
});

test('settled but stale evidence still fails within the original timeout', async ({ page }) => {
  await schedule(page, [[0, 'SETTLED', false]]);
  await expect(waitForProposalReadiness(page)).rejects.toThrow(/Timeout 5000ms exceeded/);
});
