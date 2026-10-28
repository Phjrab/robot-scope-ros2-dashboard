// The retired standalone page is retained only as a synthetic view harness.
import { readFile } from 'node:fs/promises';
export async function openExperimentFixture(page) {
  const body = await readFile(new URL('./fixtures/experiments.html', import.meta.url), 'utf8');
  await page.route('**/static/experiments.html', route => route.fulfill({ contentType: 'text/html', body }));
  await page.goto('/static/experiments.html');
}
