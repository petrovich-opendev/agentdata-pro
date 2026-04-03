import { useCallback, useEffect, useRef, useState } from "react";
import { Send, Square, FileText, Image, X } from "lucide-react";
import { useChatStore } from "../stores/chatStore";
import { useDocumentStore } from "../stores/documentStore";
import DocumentUploadButton from "./DocumentUploadButton";
import { apiFetch } from "../api/client";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(file: File) {
  if (file.type === "application/pdf") {
    return <FileText className="w-4 h-4 text-[#818cf8] shrink-0" />;
  }
  if (file.type.startsWith("image/")) {
    return <Image className="w-4 h-4 text-[#818cf8] shrink-0" />;
  }
  return <FileText className="w-4 h-4 text-[#818cf8] shrink-0" />;
}

function truncateFilename(name: string, maxLen = 24): string {
  if (name.length <= maxLen) return name;
  const ext = name.lastIndexOf(".");
  if (ext === -1) return name.slice(0, maxLen - 3) + "...";
  const extension = name.slice(ext);
  const base = name.slice(0, maxLen - extension.length - 3);
  return base + "..." + extension;
}

interface ChatInputProps {
  droppedFile?: File | null;
  onDroppedFileConsumed?: () => void;
}

export default function ChatInput({ droppedFile, onDroppedFileConsumed }: ChatInputProps) {
  const streaming = useChatStore((s) => s.streaming);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const abortStream = useChatStore((s) => s.abortStream);
  const addDocumentProcessing = useChatStore((s) => s.addDocumentProcessing);
  const uploading = useDocumentStore((s) => s.uploading);
  const docError = useDocumentStore((s) => s.error);
  const clearDocError = useDocumentStore((s) => s.clearError);
  const [input, setInput] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (droppedFile) {
      setPendingFile(droppedFile);
      onDroppedFileConsumed?.();
    }
  }, [droppedFile, onDroppedFileConsumed]);

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const maxHeight = 200;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [input, adjustHeight]);

  useEffect(() => {
    if (!streaming && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [streaming]);

  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    const content = input.trim();
    if ((!content && !pendingFile) || uploading) return;

    const fileToUpload = pendingFile;
    const textToSend = content;

    setInput("");
    setPendingFile(null);

    if (fileToUpload) {
      // Upload file and show processing progress in chat
      const formData = new FormData();
      formData.append("file", fileToUpload);

      try {
        // apiFetch imported at top
        const res = await apiFetch("/api/documents/upload", {
          method: "POST",
          body: formData,
        });
        if (res.ok) {
          const doc = await res.json();
          // Update documentStore
          useDocumentStore.setState((state) => ({
            documents: [doc, ...state.documents],
          }));
          // Add processing messages to chat
          addDocumentProcessing(fileToUpload, doc.id);
        } else {
          const data = await res.json().catch(() => null);
          useDocumentStore.setState({
            error: data?.detail ?? `Upload failed (${res.status})`,
          });
        }
      } catch (err) {
        useDocumentStore.setState({
          error: err instanceof Error ? err.message : "Upload failed",
        });
      }
    }

    if (textToSend) {
      sendMessage(textToSend);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleFileSelect(file: File) {
    setPendingFile(file);
  }

  function removePendingFile() {
    setPendingFile(null);
  }

  return (
    <div className="shrink-0 border-t border-[#2a2a4a] bg-[#0f0f23] px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
      {/* Upload error */}
      {docError && (
        <div className="max-w-3xl mx-auto mb-2 px-3 py-1.5 bg-red-900/20 border border-red-900/30 rounded-lg text-xs text-red-400 flex items-center justify-between">
          <span>{docError}</span>
          <button onClick={clearDocError} className="underline hover:text-red-300 ml-2">
            Dismiss
          </button>
        </div>
      )}

      {/* Pending file chip */}
      {pendingFile && (
        <div className="max-w-3xl mx-auto mb-2 flex items-center gap-2 px-3 py-2 bg-[#1e1e3a] border border-[#3a3a5c] rounded-lg w-fit">
          {getFileIcon(pendingFile)}
          <span className="text-sm text-[#c0c0d0] max-w-[200px] truncate" title={pendingFile.name}>
            {truncateFilename(pendingFile.name)}
          </span>
          <span className="text-xs text-[#6b6b8a]">
            {formatFileSize(pendingFile.size)}
          </span>
          <button
            type="button"
            onClick={removePendingFile}
            className="p-0.5 rounded hover:bg-[#2d2d5e] text-[#6b6b8a] hover:text-[#e0e0e0] transition-colors"
            title="Remove file"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="max-w-3xl mx-auto relative flex items-end gap-1"
      >
        <DocumentUploadButton onFileSelect={handleFileSelect} />

        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message BioCoach..."
            rows={1}
            className="w-full resize-none rounded-xl bg-[#1e1e3a] border border-[#3a3a5c] text-[#e0e0e0] placeholder-[#6b6b8a] px-4 py-3 pr-12 text-base focus:outline-none focus:border-[#6366f1] focus:ring-1 focus:ring-[#6366f1] disabled:opacity-50 transition-colors"
          />
          {streaming ? (
            <button
              type="button"
              onClick={abortStream}
              className="absolute right-2 bottom-2 p-2 rounded-lg bg-[#ef4444] text-white hover:bg-[#dc2626] transition-colors"
              title="Stop generating"
            >
              <Square className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim() && !pendingFile}
              className="absolute right-2 bottom-2 p-2 rounded-lg bg-[#6366f1] text-white hover:bg-[#5558e6] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
      </form>
      <p className="text-center text-[10px] text-[#4a4a6a] mt-2 max-w-3xl mx-auto">
        BioCoach can make mistakes. Verify important information with a healthcare professional.
      </p>
    </div>
  );
}
