#!/usr/bin/env node
/** Check every tracked dashboard JavaScript module without a bundler. */

import { readdirSync } from 'node:fs';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const staticRoot = join(repositoryRoot, 'robot_dashboard', 'static');

function collectJavaScript(directory) {
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...collectJavaScript(path));
    else if (entry.isFile() && extname(entry.name) === '.js') files.push(path);
  }
  return files.sort();
}

const files = collectJavaScript(staticRoot);
for (const file of files) {
  const result = spawnSync(process.execPath, ['--check', file], { stdio: 'inherit' });
  if (result.status !== 0) process.exitCode = result.status || 1;
}

if (process.exitCode) process.exit(process.exitCode);
console.log(`checked JavaScript syntax for ${files.length} dashboard modules`);
