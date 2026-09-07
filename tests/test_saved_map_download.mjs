import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { renderSavedMapDownloadState } from '../robot_dashboard/static/features/maps/download.js';

const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');

function node() {
  return {
    textContent: '', href: '', attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; if (name === 'href') this.href = ''; },
  };
}

test('saved map download UI shows catalog and selected sizes with an opaque download URL', () => {
  const countNode = node(); const sizeNode = node(); const linkNode = node();
  const catalog = [{ id: 'a'.repeat(24), size_bytes: 1536 }];
  catalog.totalSizeBytes = 4096;
  renderSavedMapDownloadState({ countNode, sizeNode, linkNode, catalog, selected: catalog[0] });
  assert.equal(countNode.textContent, '1 map · 4.00 KiB');
  assert.equal(sizeNode.textContent, '1.50 KiB');
  assert.equal(linkNode.attributes['aria-disabled'], 'false');
  assert.equal(linkNode.href, `/api/v1/saved-maps/${'a'.repeat(24)}/download`);
});

test('saved map download UI disables bundled fallback maps and tolerates missing sizes', () => {
  const countNode = node(); const sizeNode = node(); const linkNode = node();
  linkNode.href = '/old';
  renderSavedMapDownloadState({ countNode, sizeNode, linkNode, catalog: [], selected: { id: '__fallback_cloud' } });
  assert.equal(countNode.textContent, '0 maps · 0 B');
  assert.equal(sizeNode.textContent, '—');
  assert.equal(linkNode.attributes['aria-disabled'], 'true');
  assert.equal(linkNode.href, '');
});

test('Mapping links to the Saved Maps size and download controls', () => {
  assert.match(indexSource, /class="mapping-download-link" href="#maps"/);
  assert.match(indexSource, /id="savedMapSize"/);
  assert.match(indexSource, /id="savedMapDownload"/);
});
