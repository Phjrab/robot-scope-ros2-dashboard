// Static assets only. No application startup, ROS, subprocesses or proxy.
import { createServer } from 'node:http';
import { readFile, realpath } from 'node:fs/promises';
import { dirname, extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = await realpath(process.env.UI_BASELINE_STATIC_DIR || join(dirname(fileURLToPath(import.meta.url)), '../robot_dashboard/static'));
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png' };
const server = createServer(async (request, response) => {
  try {
    const path = new URL(request.url, 'http://127.0.0.1').pathname;
    if (path.startsWith('/api/')) { response.writeHead(503); response.end('Fixture API must be intercepted'); return; }
    const file = await realpath(join(root, path === '/' ? 'index.html' : path.replace(/^\/static\//, '')));
    if (relative(root, file).startsWith('..')) throw new Error('outside static root');
    response.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    response.end(await readFile(file));
  } catch { response.writeHead(404); response.end('not found'); }
});
server.listen(4187, '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
