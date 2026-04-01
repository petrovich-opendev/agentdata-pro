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

    if (!storedToken) {
      set({ loading: false });
      return;
    }

    if (!isTokenExpired(storedToken)) {
      set({ token: storedToken, isAuthenticated: true, loading: false });
      return;
    }

    // Token is expired — attempt silent refresh
    try {
      const response = await fetch("/api/auth/refresh", { method: "POST" });
      if (response.ok) {
        const data = await response.json();
        const newToken: string | undefined = data.access_token;
        if (newToken) {
          localStorage.setItem(TOKEN_KEY, newToken);
          set({ token: newToken, isAuthenticated: true, loading: false });
          return;
        }
      }
    } catch {
      // Refresh failed — fall through to unauthenticated state
    }

    // Refresh failed or no new token — clear stale data
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, isAuthenticated: false, loading: false });
  },
}));
