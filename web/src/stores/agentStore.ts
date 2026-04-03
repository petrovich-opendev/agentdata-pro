import { create } from "zustand";
import { useAuthStore } from "./authStore";

export interface AgentInfo {
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  settings: Record<string, unknown>;
  last_run: string | null;
  next_run: string | null;
}

export interface WatchlistItem {
  id: string;
  product_name: string;
  product_category: string;
  target_price: number | null;
  best_price: number | null;
  best_source: string | null;
  best_url: string | null;
  last_checked_at: string | null;
}

export interface AgentNotification {
  id: number;
  content: { title?: string; body?: string; [key: string]: unknown };
  is_read: boolean;
  created_at: string;
}

interface AgentState {
  agents: AgentInfo[];
  selectedAgent: AgentInfo | null;
  loading: boolean;
  watchlist: WatchlistItem[];
  watchlistLoading: boolean;
  notifications: AgentNotification[];
  notificationsLoading: boolean;
  loadAgents: () => Promise<void>;
  toggleAgent: (code: string) => Promise<void>;
  saveSettings: (code: string, settings: Record<string, unknown>) => Promise<void>;
  setSelectedAgent: (agent: AgentInfo | null) => void;
  loadWatchlist: () => Promise<void>;
  addWatchlistItem: (name: string, category: string, targetPrice?: number) => Promise<void>;
  removeWatchlistItem: (id: string) => Promise<void>;
  loadNotifications: () => Promise<void>;
  markAsRead: (id: number) => Promise<void>;
  clearAllNotifications: () => void;
}

function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agents: [],
  selectedAgent: null,
  loading: false,
  watchlist: [],
  watchlistLoading: false,
  notifications: [],
  notificationsLoading: false,

  loadAgents: async () => {
    set({ loading: true });
    try {
      const res = await fetch("/api/agents/", {
        headers: authHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        const data: AgentInfo[] = await res.json();
        set({ agents: data });
      }
    } finally {
      set({ loading: false });
    }
  },

  toggleAgent: async (code: string) => {
    const agent = get().agents.find((a) => a.code === code);
    if (!agent) return;
    const endpoint = agent.is_active ? "deactivate" : "activate";
    const res = await fetch(`/api/agents/${code}/${endpoint}`, {
      method: "POST",
      headers: authHeaders(),
      credentials: "include",
    });
    if (res.ok) {
      set({
        agents: get().agents.map((a) =>
          a.code === code ? { ...a, is_active: !a.is_active } : a
        ),
        selectedAgent:
          get().selectedAgent?.code === code
            ? { ...get().selectedAgent!, is_active: !agent.is_active }
            : get().selectedAgent,
      });
    }
  },

  saveSettings: async (code: string, settings: Record<string, unknown>) => {
    const res = await fetch(`/api/agents/${code}/config`, {
      method: "PUT",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ settings }),
    });
    if (res.ok) {
      set({
        agents: get().agents.map((a) =>
          a.code === code ? { ...a, settings } : a
        ),
        selectedAgent:
          get().selectedAgent?.code === code
            ? { ...get().selectedAgent!, settings }
            : get().selectedAgent,
      });
    }
  },

  setSelectedAgent: (agent) => set({ selectedAgent: agent }),

  loadWatchlist: async () => {
    set({ watchlistLoading: true });
    try {
      const res = await fetch("/api/agents/price-monitor/watchlist", {
        headers: authHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        set({ watchlist: await res.json() });
      }
    } finally {
      set({ watchlistLoading: false });
    }
  },

  addWatchlistItem: async (name, category, targetPrice) => {
    const res = await fetch("/api/agents/price-monitor/watchlist", {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        product_name: name,
        product_category: category,
        target_price: targetPrice ?? null,
      }),
    });
    if (res.ok) {
      const item: WatchlistItem = await res.json();
      set({ watchlist: [item, ...get().watchlist] });
    }
  },

  removeWatchlistItem: async (id) => {
    const res = await fetch(`/api/agents/price-monitor/watchlist/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
      credentials: "include",
    });
    if (res.ok) {
      set({ watchlist: get().watchlist.filter((w) => w.id !== id) });
    }
  },

  loadNotifications: async () => {
    set({ notificationsLoading: true });
    try {
      const res = await fetch("/api/agents/notifications", {
        headers: authHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        set({ notifications: await res.json() });
      }
    } finally {
      set({ notificationsLoading: false });
    }
  },

  markAsRead: async (id: number) => {
    const res = await fetch(`/api/agents/notifications/${id}/read`, {
      method: "POST",
      headers: authHeaders(),
      credentials: "include",
    });
    if (res.ok) {
      set({
        notifications: get().notifications.map((n) =>
          n.id === id ? { ...n, is_read: true } : n
        ),
      });
    }
  },

  clearAllNotifications: () => {
    const unread = get().notifications.filter((n) => !n.is_read);
    unread.forEach((n) => {
      fetch(`/api/agents/notifications/${n.id}/read`, {
        method: "POST",
        headers: authHeaders(),
        credentials: "include",
      });
    });
    set({
      notifications: get().notifications.map((n) => ({ ...n, is_read: true })),
    });
  },
}));
