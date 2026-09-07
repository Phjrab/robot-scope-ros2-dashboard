import { formatDatasetBytes } from '../datasets/capture.js';

export function renderSavedMapDownloadState({ countNode, sizeNode, linkNode, catalog, selected }) {
  const maps = Array.isArray(catalog) ? catalog : [];
  const count = maps.length;
  const total = Number.isFinite(Number(maps.totalSizeBytes))
    ? Math.max(0, Number(maps.totalSizeBytes))
    : maps.reduce((sum, entry) => sum + Math.max(0, Number(entry?.size_bytes) || 0), 0);
  countNode.textContent = `${count} map${count === 1 ? '' : 's'} · ${formatDatasetBytes(total)}`;
  sizeNode.textContent = formatDatasetBytes(selected?.size_bytes);
  const downloadable = Boolean(selected?.id && selected.id !== '__fallback_cloud');
  linkNode.setAttribute('aria-disabled', downloadable ? 'false' : 'true');
  if (downloadable) linkNode.href = `/api/v1/saved-maps/${encodeURIComponent(selected.id)}/download`;
  else linkNode.removeAttribute('href');
}
