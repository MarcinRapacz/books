// Browser-side helper for the refresh mode with httpOnly cookies.
// The access token lives only in memory; the refresh token is an httpOnly cookie the script never sees.
const API_URL = 'http://localhost:1337/api';

let accessToken: string | null = null;

export async function login(identifier: string, password: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/local`, {
    method: 'POST',
    credentials: 'include', // lets the browser store the refresh cookie
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password }),
  });
  if (!res.ok) throw new Error(`Login failed: ${res.status}`);
  accessToken = ((await res.json()) as { jwt: string }).jwt;
}

let pendingRefresh: Promise<boolean> | null = null;

// Single flight: a rotated refresh token is invalid, so two parallel refreshes would log the user out.
function refresh(): Promise<boolean> {
  pendingRefresh ??= (async () => {
    const res = await fetch(`${API_URL}/auth/refresh`, { method: 'POST', credentials: 'include' });
    accessToken = res.ok ? ((await res.json()) as { jwt: string }).jwt : null;
    return res.ok;
  })().finally(() => {
    pendingRefresh = null;
  });
  return pendingRefresh;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () =>
    fetch(`${API_URL}${path}`, {
      ...init,
      credentials: 'include',
      headers: { ...init.headers, ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
    });
  const res = await send();
  // One retry after a refresh: an expired access token is the normal case every 10 minutes.
  if (res.status === 401 && (await refresh())) {
    return send();
  }
  return res;
}

export async function logout(): Promise<void> {
  await apiFetch('/auth/logout', { method: 'POST' });
  accessToken = null;
}
