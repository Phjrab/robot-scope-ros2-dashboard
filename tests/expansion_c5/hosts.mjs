import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
export const root = resolve(import.meta.dirname, '../..');
export const peers = process.env.C5_PEERS || '/private/tmp/robot-scope-c5-sources';
export const urls = {
  main: 'http://127.0.0.1:4265',
  c2: 'http://127.0.0.1:4266',
  c3: 'http://127.0.0.1:4267/experiments/expansion_20261029/c3_scene_ui/fixture.html',
};
export async function startHosts() {
  const children = [
    spawn(process.execPath, ['tests/e2e/static_server.mjs'], { cwd: root, env: { ...process.env, UI_REGRESSION_PORT: '4265', UI_PROBE_PORT: '4268' }, stdio: 'ignore' }),
    spawn(process.execPath, [`${peers}/c2/experiments/expansion_20261029/c2_map_ui/server.mjs`], { env: { ...process.env, C2_PORT: '4266', C2_C1_SERVICE_URL: '' }, stdio: 'ignore' }),
    spawn('python3', [`${peers}/c3/experiments/expansion_20261029/c3_scene_ui/serve.py`, '--port', '4267'], { env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, stdio: 'ignore' }),
  ];
  const stop = () => children.forEach(p => p.kill('SIGTERM'));
  try {
    for (const url of Object.values(urls)) {
      let ready = false;
      for (let i = 0; i < 100; i++) {
        if (children.some(p => p.exitCode !== null)) throw new Error('An owned host failed; do not reuse another host');
        try { ready = (await fetch(url)).ok; } catch { /* starting */ }
        if (ready) break;
        await new Promise(r => setTimeout(r, 50));
      }
      if (!ready) throw new Error(`Host unavailable: ${url}`);
    }
    return stop;
  } catch (error) { stop(); throw error; }
}
