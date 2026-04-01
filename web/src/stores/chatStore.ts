import { create } from "zustand";
import { apiFetch } from "../api/client";
import type { ChatSession, Message, SSEEvent } from "../types";

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: Message[];
  messagesBySession: Record<string, Message[]>;
  streaming: boolean;
  error: string;
  sessionsLoaded: boolean;

  loadSessions: () => Promise<void>;
  setActiveSession: (id: string) => void;
  loadMessages: (sessionId: string) => Promise<void>;
  createSession: () => Promise<string | null>;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  abortStream: () => void;
  clearError: () => void;
}

let abortController: AbortController | null = null;

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  messagesBySession: {},
  streaming: false,
  error: "",
  sessionsLoaded: false,

  loadSessions: async () => {
    try {
      const res = await apiFetch("/api/chat/sessions");
      if (res.ok) {
        const data = await res.json();
        set({ sessions: data.sessions ?? data ?? [], sessionsLoaded: true });
      }
    } catch {
      // Non-critical
    }
  },

  setActiveSession: (id: string) => {
    const { activeSessionId, streaming, messages, messagesBySession } = get();
    if (id === activeSessionId) return;
    if (streaming) {
      abortController?.abort();
      set({ streaming: false });
    }
    // Save current session messages to cache
    const updatedCache = { ...messagesBySession };
    if (activeSessionId && messages.length > 0) {
      updatedCache[activeSessionId] = messages;
    }
    // Restore cached messages for the new session (or empty)
    const cached = updatedCache[id] ?? [];
    set({
      activeSessionId: id,
      messages: cached,
      messagesBySession: updatedCache,
      error: "",
    });
  },

  loadMessages: async (sessionId: string) => {
    try {
      const res = await apiFetch(`/api/chat/sessions/${sessionId}/messages`);
      if (res.ok) {
        const data = await res.json();
        const msgs: Message[] = data.messages ?? data ?? [];
        if (get().activeSessionId === sessionId) {
          set((state) => ({
            messages: msgs,
            messagesBySession: { ...state.messagesBySession, [sessionId]: msgs },
          }));
        } else {
          // Still cache even if user switched away
          set((state) => ({
            messagesBySession: { ...state.messagesBySession, [sessionId]: msgs },
          }));
        }
      }
    } catch {
      // Non-critical
    }
  },

  createSession: async () => {
    try {
      const res = await apiFetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const data = await res.json();
        const session: ChatSession = {
          id: data.id,
          title: data.title ?? null,
          created_at: data.created_at ?? new Date().toISOString(),
        };
        const { activeSessionId, messages, messagesBySession } = get();
        const updatedCache = { ...messagesBySession };
        if (activeSessionId && messages.length > 0) {
          updatedCache[activeSessionId] = messages;
        }
        set({
          sessions: [session, ...get().sessions],
          activeSessionId: session.id,
          messages: [],
          messagesBySession: updatedCache,
          error: "",
        });
        return session.id;
      }
    } catch {
      set({ error: "Failed to create session" });
    }
    return null;
  },

  deleteSession: async (id: string) => {
    try {
      const res = await apiFetch(`/api/chat/sessions/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        set((state) => {
          const { [id]: _, ...restCache } = state.messagesBySession;
          return {
            sessions: state.sessions.filter((s) => s.id !== id),
            messagesBySession: restCache,
          };
        });
      }
    } catch {
      set({ error: "Failed to delete session" });
    }
  },

  renameSession: async (id: string, title: string) => {
    try {
      const res = await apiFetch(`/api/chat/sessions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      if (res.ok) {
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === id ? { ...s, title } : s
          ),
        }));
      }
    } catch {
      set({ error: "Failed to rename session" });
    }
  },

  sendMessage: async (content: string) => {
    const { activeSessionId, streaming } = get();
    if (!content.trim() || streaming) return;

    let sessionId = activeSessionId;

    if (!sessionId) {
      sessionId = await get().createSession();
      if (!sessionId) return;
    }

    set({ error: "" });

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };

    const assistantMessage: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      streaming: true,
    }));

    const controller = new AbortController();
    abortController = controller;

    try {
      const res = await apiFetch("/api/chat/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, session_id: sessionId }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? `Request failed (${res.status})`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;

          let event: SSEEvent;
          try {
            event = JSON.parse(trimmed.slice(6));
          } catch {
            continue;
          }

          if (event.error) {
            set({ error: event.error });
            break;
          }

          if (!event.done && event.token) {
            set((state) => {
              const updated = [...state.messages];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + event.token,
                };
              }
              return { messages: updated };
            });
          }

          if (event.done && event.message_id) {
            set((state) => {
              const updated = [...state.messages];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  id: event.message_id!,
                };
              }
              return { messages: updated };
            });
          }
        }
      }

      // Sync final messages to cache
      const finalState = get();
      if (finalState.activeSessionId === sessionId) {
        set((state) => ({
          messagesBySession: {
            ...state.messagesBySession,
            [sessionId]: state.messages,
          },
        }));
      }

      // Refresh sessions to pick up auto-generated titles
      get().loadSessions();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      const errorMsg =
        err instanceof Error ? err.message : "Failed to send message";
      set((state) => {
        const msgs = [...state.messages];
        const last = msgs[msgs.length - 1];
        if (last?.role === "assistant" && !last.content) {
          return { error: errorMsg, messages: msgs.slice(0, -1) };
        }
        return { error: errorMsg };
      });
    } finally {
      set({ streaming: false });
      abortController = null;
    }
  },

  abortStream: () => {
    abortController?.abort();
    set({ streaming: false });
  },

  clearError: () => set({ error: "" }),
}));
