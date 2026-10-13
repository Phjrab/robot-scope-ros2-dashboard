import base from '../../playwright.config.mjs';
import { fileURLToPath } from 'node:url';
const port = Number(process.env.UI_REGRESSION_PORT || 4199);
const probePort = Number(process.env.UI_PROBE_PORT || 4200);
process.env.UI_REGRESSION_PORT = String(port);
process.env.UI_PROBE_PORT = String(probePort);
export default {
  ...base, testDir: '../../tests/e2e',
  outputDir: '/private/tmp/robot-scope-ui-readability-regression',
  use: { ...base.use, baseURL: `http://127.0.0.1:${port}` },
  webServer: { ...base.webServer, command: 'node tests/e2e/static_server.mjs',
    cwd: fileURLToPath(new URL('../../', import.meta.url)), url: `http://127.0.0.1:${port}`,
    env: { UI_REGRESSION_PORT: String(port), UI_PROBE_PORT: String(probePort) } },
};
