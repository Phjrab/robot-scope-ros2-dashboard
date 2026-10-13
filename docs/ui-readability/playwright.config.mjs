import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
const port = Number(process.env.UI_READABILITY_PORT || 4198);
export default defineConfig({
  testDir: '.', testMatch: 'readability.spec.mjs', workers: 1,
  outputDir: '/private/tmp/robot-scope-ui-readability-artifacts',
  timeout: 180_000, expect: { timeout: 6_000 },
  use: { baseURL: `http://127.0.0.1:${port}`, viewport: { width: 1440, height: 900 }, trace: 'retain-on-failure' },
  webServer: { command: 'node docs/ui-readability/fixture-server.mjs', cwd: fileURLToPath(new URL('../../', import.meta.url)), url: `http://127.0.0.1:${port}`, reuseExistingServer: false, timeout: 10_000 },
});
