import { create } from "zustand";
import { apiFetch } from "../api/client";
import type { ChatSession, ChatFolder, ChatSearchResult, Message, SSEEvent } from "../types";

interface DocumentProcessingEntry {
  documentId: string;
  messageId: string;
  status: "uploaded" | "parsing" | "extracting" | "done" | "error";
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: Message[];
  messagesBySession: Record<string, Message[]>;
  streaming: boolean;
  error: string;
  sessionsLoaded: boolean;
  loadingMessages: boolean;
  documentProcessing: Record<string, DocumentProcessingEntry>;

  // Folders
  folders: ChatFolder[];
  expandedFolders: Record<string, boolean>;
  loadFolders: () => Promise<void>;
  createFolder: (name: string) => Promise<void>;
  renameFolder: (id: string, name: string) => Promise<void>;
  deleteFolder: (id: string) => Promise<void>;
  moveChatToFolder: (sessionId: string, folderId: string | null) => Promise<void>;
  toggleFolderExpanded: (id: string) => void;

  // Search
  searchQuery: string;
  searchMode: "title" | "content";
  searching: boolean;
  searchResults: ChatSearchResult[];
  setSearchQuery: (q: string) => void;
  setSearchMode: (mode: "title" | "content") => void;
  performSearch: (query: string, mode: "title" | "content") => Promise<void>;
  clearSearch: () => void;

  loadSessions: () => Promise<void>;
  setActiveSession: (id: string) => void;
  loadMessages: (sessionId: string) => Promise<void>;
  createSession: () => Promise<string | null>;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  sendMessage: (content: string, metadata?: { file_name?: string; file_size?: number; file_type?: string }) => Promise<void>;
  addDocumentProcessing: (file: File, documentId: string) => void;
  abortStream: () => void;
  clearError: () => void;
}

let abortController: AbortController | null = null;
const processingTimers: Record<string, ReturnType<typeof setInterval>> = {};

const PROCESSING_STEPS: Record<string, string> = {
  uploaded: "Загружаю документ...",
  parsing: "Распознаю текст...",
  extracting: "Извлекаю показатели...",
  done: "",
  error: "Ошибка обработки документа",
};

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  messagesBySession: {},
  streaming: false,
  error: "",
  sessionsLoaded: false,
  loadingMessages: false,
  documentProcessing: {},

  // Folders
  folders: [],
  expandedFolders: {},

  // Search
  searchQuery: "",
  searchMode: "title" as const,
  searching: false,
  searchResults: [],

  loadFolders: async () => {
    try {
      const res = await apiFetch("/api/chat/folders");
      if (res.ok) {
        const data = await res.json();
        set({ folders: Array.isArray(data) ? data : (data.folders ?? []) });
      }
    } catch {
      // Non-critical — folders are optional
    }
  },

  createFolder: async (name: string) => {
    try {
      const res = await apiFetch("/api/chat/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (res.ok) {
        const folder = await res.json();
        set((state) => ({ folders: [...state.folders, folder] }));
      }
    } catch {
      set({ error: "Failed to create folder" });
    }
  },

  renameFolder: async (id: string, name: string) => {
    try {
      const res = await apiFetch(`/api/chat/folders/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (res.ok) {
        set((state) => ({
          folders: state.folders.map((f) => (f.id === id ? { ...f, name } : f)),
        }));
      }
    } catch {
      set({ error: "Failed to rename folder" });
    }
  },

  deleteFolder: async (id: string) => {
    try {
      const res = await apiFetch(`/api/chat/folders/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        set((state) => ({
          folders: state.folders.filter((f) => f.id !== id),
          sessions: state.sessions.map((s) =>
            s.folder_id === id ? { ...s, folder_id: null } : s
          ),
        }));
      }
    } catch {
      set({ error: "Failed to delete folder" });
    }
  },

  moveChatToFolder: async (sessionId: string, folderId: string | null) => {
    try {
      const res = await apiFetch(`/api/chat/sessions/${sessionId}/folder`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_id: folderId }),
      });
      if (res.ok) {
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, folder_id: folderId } : s
          ),
        }));
      }
    } catch {
      set({ error: "Failed to move chat" });
    }
  },

  toggleFolderExpanded: (id: string) => {
    set((state) => ({
      expandedFolders: {
        ...state.expandedFolders,
        [id]: !(state.expandedFolders[id] ?? true),
      },
    }));
  },

  setSearchQuery: (q: string) => set({ searchQuery: q }),

  setSearchMode: (mode: "title" | "content") => set({ searchMode: mode }),

  performSearch: async (query: string, mode: "title" | "content") => {
    const trimmed = query.trim();
    if (!trimmed) {
      set({ searchResults: [], searching: false });
      return;
    }
    set({ searching: true });
    try {
      const params = new URLSearchParams({ q: trimmed, mode });
      const res = await apiFetch(`/api/chat/search?${params}`);
      if (res.ok) {
        const data = await res.json();
        set({ searchResults: data.results ?? data ?? [], searching: false });
      } else {
        set({ searching: false });
      }
    } catch {
      set({ searching: false });
    }
  },

  clearSearch: () => set({ searchQuery: "", searchResults: [], searching: false }),

  loadSessions: async () => {
    try {
      const res = await apiFetch("/api/chat/sessions");
      if (res.ok) {
        const data = await res.json();
        const list = data.sessions ?? data ?? [];
        set({ sessions: Array.isArray(list) ? list : [], sessionsLoaded: true });
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
    const updatedCache = { ...messagesBySession };
    if (activeSessionId && messages.length > 0) {
      updatedCache[activeSessionId] = messages;
    }
    const cached = updatedCache[id] ?? [];
    set({
      activeSessionId: id,
      messages: cached,
      messagesBySession: updatedCache,
      loadingMessages: cached.length === 0,
      error: "",
    });
  },

  loadMessages: async (sessionId: string) => {
    try {
      const res = await apiFetch(`/api/chat/sessions/${sessionId}/messages`);
      if (res.ok) {
        const data = await res.json();
        const rawMsgs = data.messages ?? data ?? [];
        const msgs: Message[] = Array.isArray(rawMsgs) ? rawMsgs : [];
        if (get().activeSessionId === sessionId) {
          set((state) => ({
            messages: msgs,
            messagesBySession: { ...state.messagesBySession, [sessionId]: msgs },
            loadingMessages: false,
          }));
        } else {
          set((state) => ({
            messagesBySession: { ...state.messagesBySession, [sessionId]: msgs },
            loadingMessages: false,
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
        const session: ChatSession = { id: data.id, title: data.title ?? null, folder_id: data.folder_id ?? null, created_at: data.created_at ?? new Date().toISOString() };
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

  sendMessage: async (content: string, metadata?: { file_name?: string; file_size?: number; file_type?: string }) => {
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
      ...(metadata && { metadata }),
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

      const finalState = get();
      if (finalState.activeSessionId === sessionId) {
        set((state) => ({
          messagesBySession: {
            ...state.messagesBySession,
            [sessionId]: state.messages,
          },
        }));
      }

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

  addDocumentProcessing: (file: File, documentId: string) => {
    const assistantMsgId = crypto.randomUUID();

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: "",
      created_at: new Date().toISOString(),
      metadata: {
        file_name: file.name,
        file_size: file.size,
        file_type: file.type,
      },
    };

    const assistantMessage: Message = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      metadata: {
        document_processing: documentId,
      },
    };

    const entry: DocumentProcessingEntry = {
      documentId,
      messageId: assistantMsgId,
      status: "uploaded",
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      documentProcessing: {
        ...state.documentProcessing,
        [documentId]: entry,
      },
    }));

    // Start polling
    let attempts = 0;
    const maxAttempts = 60;

    processingTimers[documentId] = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(processingTimers[documentId]);
        delete processingTimers[documentId];
        // Timeout: clean up processing state
        set((state) => {
          const updatedMessages = state.messages.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: "Время обработки истекло. Попробуйте загрузить документ снова.", metadata: {} }
              : m
          );
          const { [documentId]: _, ...restProcessing } = state.documentProcessing;
          return { messages: updatedMessages, documentProcessing: restProcessing };
        });
        return;
      }

      try {
        const res = await apiFetch(`/api/documents/${documentId}`);
        if (!res.ok) return;
        const data = await res.json();
        const newStatus = data.processing_status as DocumentProcessingEntry["status"];

        // Skip if entry was already removed or status unchanged
        const existing = get().documentProcessing[documentId];
        if (!existing || existing.status === newStatus) return;

        if (newStatus === "done") {
          clearInterval(processingTimers[documentId]);
          delete processingTimers[documentId];

          // Use biomarkers from this response (same endpoint, no need for second fetch)
          const biomarkers = data.biomarkers ?? [];
          set((state) => {
            const updatedMessages = state.messages.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: "", metadata: { document_id: documentId, biomarkers } }
                : m
            );
            const { [documentId]: _, ...restProcessing } = state.documentProcessing;
            return { messages: updatedMessages, documentProcessing: restProcessing };
          });
          return;
        }

        if (newStatus === "error") {
          clearInterval(processingTimers[documentId]);
          delete processingTimers[documentId];

          set((state) => {
            const updatedMessages = state.messages.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: PROCESSING_STEPS.error, metadata: {} }
                : m
            );
            const { [documentId]: _, ...restProcessing } = state.documentProcessing;
            return { messages: updatedMessages, documentProcessing: restProcessing };
          });
          return;
        }

        // Intermediate status update (uploaded -> parsing -> extracting)
        set((state) => ({
          documentProcessing: {
            ...state.documentProcessing,
            [documentId]: { ...existing, status: newStatus },
          },
        }));
      } catch {
        // Retry silently on network errors
      }
    }, 2000);
  },

  abortStream: () => {
    abortController?.abort();
    set({ streaming: false });
  },

  clearError: () => set({ error: "" }),
}));
