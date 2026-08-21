export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    cache: 'no-store',
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function latestApi(path, seq) {
  const response = await fetch(`${path}?since=${encodeURIComponent(seq)}`, { cache: 'no-store' });
  if (response.status === 204) return null;
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}
