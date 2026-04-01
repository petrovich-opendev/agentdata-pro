import { useCallback, useEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react";
import { useChatStore } from "../stores/chatStore";

export default function ChatInput() {
  const streaming = useChatStore((s) => s.streaming);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const abortStream = useChatStore((s) => s.abortStream);
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  // Focus textarea when streaming ends
  useEffect(() => {
    if (!streaming && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [streaming]);

  function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    const content = input.trim();
    if (!content || streaming) return;
    setInput("");
    sendMessage(content);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="shrink-0 border-t border-[#2a2a4a] bg-[#0f0f23] px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
      <form
        onSubmit={handleSubmit}
        className="max-w-3xl mx-auto relative"
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message BioCoach..."
          rows={1}
          disabled={streaming}
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
            disabled={!input.trim()}
            className="absolute right-2 bottom-2 p-2 rounded-lg bg-[#6366f1] text-white hover:bg-[#5558e6] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        )}
      </form>
      <p className="text-center text-[10px] text-[#4a4a6a] mt-2 max-w-3xl mx-auto">
        BioCoach can make mistakes. Verify important information with a healthcare professional.
      </p>
    </div>
  );
}
