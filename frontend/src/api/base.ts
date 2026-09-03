/** API root. Local dev uses Vite proxy (/api). Netlify proxies /api to BACKEND_URL at build time. */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const res = await fetch(`${API_BASE}${normalized}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw err;
  }
  return res.json();
}
