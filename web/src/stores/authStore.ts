import { create } from "zustand";

const TOKEN_KEY = "biocoach_access_token";

function isTokenExpired(token: string): boolean {
  try {
    const payload = token.split(".")[1];
    if (!payload) return true;
    const decoded = JSON.parse(atob(payload));
    if (typeof decoded.exp !== "number") return true;
    // Consider expired if less than 10 seconds remaining
    return decoded.exp < Date.now() / 1000 + 10;
  } catch {
    return true;
  }
}

async function silentRefresh(): Promise<string | null> {
  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    if (response.ok) {
      const data = await response.json();
      return data.access_token ?? null;
    }
  } catch {
    // Refresh failed
  }
  return null;
}

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  setToken: (token: string) => void;
  logout: () => Promise<void>;
  loadFromStorage: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  isAuthenticated: false,
  loading: true,

  setToken: (token: string) => {
    localStorage.setItem(TOKEN_KEY, token);
    set({ token, isAuthenticated: true });
  },

  logout: async () => {
    const { token } = get();
    try {
      if (token) {
        await fetch("/api/auth/logout", {
          method: "POST",
          credentials: "include",
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch {
      // Logout best-effort — clear local state regardless
    }
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, isAuthenticated: false });
  },

  loadFromStorage: async () => {
    const storedToken = localStorage.getItem(TOKEN_KEY);

    // Case 1: no token in localStorage — still try refresh via httponly cookie
    if (!storedToken) {
      const newToken = await silentRefresh();
      if (newToken) {
        localStorage.setItem(TOKEN_KEY, newToken);
        set({ token: newToken, isAuthenticated: true, loading: false });
        return;
      }
      set({ loading: false });
      return;
    }

    // Case 2: token exists and not expired — use as-is
    if (!isTokenExpired(storedToken)) {
      set({ token: storedToken, isAuthenticated: true, loading: false });
      return;
    }

    // Case 3: token expired — attempt silent refresh
    const newToken = await silentRefresh();
    if (newToken) {
      localStorage.setItem(TOKEN_KEY, newToken);
      set({ token: newToken, isAuthenticated: true, loading: false });
      return;
    }

    // Refresh failed — clear stale data
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, isAuthenticated: false, loading: false });
  },
}));
