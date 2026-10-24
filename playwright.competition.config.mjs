import { defineConfig, devices } from '@playwright/test';
const port = process.env.COMPETITION_FIXTURE_PORT || '4187';
const baseURL = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: './tests/e2e', testMatch: 'competition_mission.spec.mjs', workers: 1, timeout: 30000,
  expect: {timeout: 8000}, use: {baseURL, ...devices['Desktop Chrome'], trace: 'retain-on-failure'},
  webServer: {command: 'PYTHONPATH=.:tests python3 tests/competition_fixture_server.py', env: {COMPETITION_FIXTURE_PORT: port}, url: baseURL, reuseExistingServer: false},
});
