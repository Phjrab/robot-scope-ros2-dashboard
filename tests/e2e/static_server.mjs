import { createReadStream } from 'node:fs';
import { realpath, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const staticRoot = await realpath(join(repositoryRoot, 'robot_dashboard/static'));
const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
};

const server = createServer(async (request, response) => {
  try {
    const rawPath = new URL(request.url || '/', 'http://127.0.0.1').pathname;
    const requested = rawPath === '/'
      ? '/index.html'
      : rawPath.startsWith('/static/') ? rawPath.slice('/static'.length) : rawPath;
    const candidate = await realpath(join(staticRoot, requested));
    if (relative(staticRoot, candidate).startsWith('..')) throw new Error('outside static root');
    const info = await stat(candidate);
    if (!info.isFile()) throw new Error('not a file');
    response.writeHead(200, {
      'Cache-Control': 'no-store',
      'Content-Type': contentTypes[extname(candidate)] || 'application/octet-stream',
      'X-Content-Type-Options': 'nosniff',
    });
    createReadStream(candidate).pipe(response);
  } catch (_) {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('not found');
  }
});

let rejectedWebSockets = 0;
server.on('upgrade', (request, socket) => {
  const origin = String(request.headers.origin || '');
  const host = String(request.headers.host || '');
  const check = spawnSync('python3', [
    '-c',
    'import sys; from robot_dashboard.http_security import is_same_origin; raise SystemExit(0 if is_same_origin(sys.argv[1], sys.argv[2]) else 1)',
    origin,
    host,
  ], { cwd: repositoryRoot, stdio: 'ignore' });
  if (check.status !== 0) rejectedWebSockets += 1;
  socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
});

server.listen(4173, '127.0.0.1');

const attacker = createServer((request, response) => {
  if (request.url === '/ws-rejections') {
    response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    response.end(JSON.stringify({ rejected: rejectedWebSockets }));
    return;
  }
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
  response.end('<!doctype html><title>cross-origin probe</title>');
});
attacker.listen(4174, '127.0.0.1');

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => attacker.close(() => server.close(() => process.exit(0))));
}
