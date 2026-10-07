import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'ui_redesign.spec.mjs',
  workers: 1,
  outputDir: '/private/tmp/robot-scope-ui-playwright-artifacts',
  timeout: 60_000,
  expect: { timeout: 5_000 },
  use: { baseURL: 'http://127.0.0.1:4187', viewport: { width: 1440, height: 900 }, trace: 'retain-on-failure' },
  webServer: {
    command: 'node scripts/ui_fixture_server.mjs',
    url: 'http://127.0.0.1:4187',
    reuseExistingServer: false,
  },
});
