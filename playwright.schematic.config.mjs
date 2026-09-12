import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e', testMatch: 'schematic_real.spec.mjs', workers: 1, timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:4189', viewport: { width: 1366, height: 768 }, trace: 'retain-on-failure' },
  webServer: { command: '.venv/bin/python -m uvicorn schematic_offline_server:app --app-dir tests --host 127.0.0.1 --port 4189', url: 'http://127.0.0.1:4189', reuseExistingServer: false, timeout: 10000 },
});
