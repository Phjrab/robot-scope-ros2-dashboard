import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./tests/integration_i0',testMatch:'cone.product.mjs',workers:1,fullyParallel:false,
 timeout:20_000,expect:{timeout:5_000},use:{baseURL:'http://127.0.0.1:4192',screenshot:'only-on-failure',trace:'retain-on-failure'},
 webServer:{command:'python -m tests.integration_i0.cone_fixture',url:'http://127.0.0.1:4192/extensions',reuseExistingServer:false,timeout:10_000},
});
