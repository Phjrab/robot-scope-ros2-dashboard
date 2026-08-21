export function formatHz(value) {
  return value == null ? '—' : `${Number(value).toFixed(value >= 10 ? 1 : 2)} Hz`;
}

export function safeNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '—';
}
