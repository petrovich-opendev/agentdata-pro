import { create } from "zustand";
import { apiFetch } from "../api/client";
import type { Document, DocumentDetail } from "../types";

interface DocumentState {
  documents: Document[];
  selectedDocument: DocumentDetail | null;
  uploading: boolean;
  loading: boolean;
  error: string;

  loadDocuments: () => Promise<void>;
  uploadDocument: (file: File) => Promise<void>;
  selectDocument: (id: string) => Promise<void>;
  clearSelectedDocument: () => void;
  deleteDocument: (id: string) => Promise<void>;
  pollDocumentStatus: (id: string) => void;
  clearError: () => void;
}

let pollTimers: Record<string, ReturnType<typeof setInterval>> = {};

export const useDocumentStore = create<DocumentState>((set, get) => ({
  documents: [],
  selectedDocument: null,
  uploading: false,
  loading: false,
  error: "",

  loadDocuments: async () => {
    set({ loading: true });
    try {
      const res = await apiFetch("/api/documents");
      if (res.ok) {
        const data = await res.json();
        set({ documents: data.documents ?? [], loading: false });
      } else {
        set({ loading: false });
      }
    } catch {
      set({ loading: false });
    }
  },

  uploadDocument: async (file: File) => {
    set({ uploading: true, error: "" });
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiFetch("/api/documents/upload", {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        const doc = await res.json();
        set((state) => ({
          documents: [doc, ...state.documents],
          uploading: false,
        }));
        // Start polling for processing status
        if (doc.processing_status !== "done" && doc.processing_status !== "error") {
          get().pollDocumentStatus(doc.id);
        }
      } else {
        const data = await res.json().catch(() => null);
        set({
          uploading: false,
          error: data?.detail ?? `Upload failed (${res.status})`,
        });
      }
    } catch (err) {
      set({
        uploading: false,
        error: err instanceof Error ? err.message : "Upload failed",
      });
    }
  },

  selectDocument: async (id: string) => {
    try {
      const res = await apiFetch(`/api/documents/${id}`);
      if (res.ok) {
        const data = await res.json();
        set({ selectedDocument: data });
      }
    } catch {
      // Non-critical
    }
  },

  clearSelectedDocument: () => set({ selectedDocument: null }),

  deleteDocument: async (id: string) => {
    try {
      const res = await apiFetch(`/api/documents/${id}`, { method: "DELETE" });
      if (res.ok) {
        // Stop polling if active
        if (pollTimers[id]) {
          clearInterval(pollTimers[id]);
          delete pollTimers[id];
        }
        set((state) => ({
          documents: state.documents.filter((d) => d.id !== id),
          selectedDocument:
            state.selectedDocument?.id === id ? null : state.selectedDocument,
        }));
      }
    } catch {
      set({ error: "Failed to delete document" });
    }
  },

  pollDocumentStatus: (id: string) => {
    // Clear existing timer for this doc
    if (pollTimers[id]) clearInterval(pollTimers[id]);

    let attempts = 0;
    const maxAttempts = 60; // ~2 min max

    pollTimers[id] = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(pollTimers[id]);
        delete pollTimers[id];
        return;
      }

      try {
        const res = await apiFetch(`/api/documents/${id}`);
        if (res.ok) {
          const data = await res.json();
          set((state) => ({
            documents: state.documents.map((d) =>
              d.id === id
                ? { ...d, processing_status: data.processing_status }
                : d
            ),
          }));

          if (data.processing_status === "done" || data.processing_status === "error") {
            clearInterval(pollTimers[id]);
            delete pollTimers[id];
            // Refresh selected if viewing this doc
            const selected = get().selectedDocument;
            if (selected?.id === id) {
              set({ selectedDocument: data });
            }
          }
        }
      } catch {
        // Retry silently
      }
    }, 2000);
  },

  clearError: () => set({ error: "" }),
}));
