import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./tests/integration_i0', testMatch:'*.spec.mjs', workers:1, fullyParallel:false,
  timeout:20_000, expect:{timeout:5_000},
  use:{baseURL:'http://127.0.0.1:4191',extraHTTPHeaders:{'x-i0-synthetic-fixture':'local-test-only'},
    screenshot:'only-on-failure',trace:'retain-on-failure'},
  webServer:[
    {command:'python -m tests.integration_i0.fixture --all --port 4191',
      url:'http://127.0.0.1:4191/extensions',reuseExistingServer:false,timeout:10_000},
    {command:'python -m tests.integration_i0.review_fixture --port 4193',
      url:'https://127.0.0.1:4193/extensions',ignoreHTTPSErrors:true,reuseExistingServer:false,timeout:10_000},
    {command:'python -m tests.integration_i0.review_fixture --off --port 4194',
      url:'http://127.0.0.1:4194/extensions',reuseExistingServer:false,timeout:10_000},
  ],
});
