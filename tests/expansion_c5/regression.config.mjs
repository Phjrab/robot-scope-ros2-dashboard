import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
export default defineConfig({
 testDir:'../e2e',
 testMatch:['dashboard.spec.mjs','goal_precision.spec.mjs','navigation_goal_urdf.spec.mjs','ui_themes.spec.mjs'],
 fullyParallel:false,workers:1,timeout:20_000,expect:{timeout:5000},
 outputDir:'/private/tmp/c5-regression-artifacts',
 use:{baseURL:'http://127.0.0.1:4275',viewport:{width:1280,height:720},screenshot:'only-on-failure'},
 webServer:{command:'UI_REGRESSION_PORT=4275 UI_PROBE_PORT=4276 node tests/e2e/static_server.mjs',cwd:fileURLToPath(new URL('../..',import.meta.url)),url:'http://127.0.0.1:4275',reuseExistingServer:false,timeout:10000},
});
