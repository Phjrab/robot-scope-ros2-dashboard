import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'manual_2d_product.spec.mjs',
  workers: 1,
  timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:4192', viewport: { width: 1366, height: 900 } },
  webServer: {
    command: '"${MANUAL_NAVIGATION_TEST_PYTHON:-.venv/bin/python}" -W ignore -m uvicorn manual_navigation_offline_server:app --app-dir tests --lifespan off --host 127.0.0.1 --port 4192',
    url: 'http://127.0.0.1:4192',
    reuseExistingServer: false,
    timeout: 10000,
  },
});
