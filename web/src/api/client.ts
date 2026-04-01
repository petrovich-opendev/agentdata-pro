import { useAuthStore } from '../stores/authStore';

let refreshPromise: Promise<string | null> | null = null;

async function refreshToken(): Promise<string | null> {
  const response = await fetch('/api/auth/refresh', { method: 'POST' });
  if (!response.ok) {
    return null;
  }
  const data = await response.json();
  return data.access_token ?? null;
}

export async function apiFetch(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const { token, setToken, logout } = useAuthStore.getState();

  const headers = new Headers(options.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    // Prevent concurrent refresh calls
    if (!refreshPromise) {
      refreshPromise = refreshToken().finally(() => {
        refreshPromise = null;
      });
    }

    const newToken = await refreshPromise;

    if (newToken) {
      setToken(newToken);
      headers.set('Authorization', `Bearer ${newToken}`);
      response = await fetch(url, { ...options, headers });
    } else {
      await logout();
    }
  }

  return response;
}
