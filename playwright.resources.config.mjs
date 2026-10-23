import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e', testMatch: 'host_resources.spec.mjs',
  workers: 1, timeout: 20_000,
  use: { baseURL: 'http://127.0.0.1:4289', ...devices['Desktop Chrome'] },
  webServer: { command: 'UI_FIXTURE_PORT=4289 node scripts/ui_fixture_server.mjs',
    url: 'http://127.0.0.1:4289', reuseExistingServer: false },
});
