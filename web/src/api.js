export async function api(path, options = {}) {
  const response = await fetch('/api' + path, { ...options, headers: { 'X-Pattern-Reborn': 'local-workspace', ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '操作未完成，请检查输入后重试。');
  return data;
}
