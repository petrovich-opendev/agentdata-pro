import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { LogOut, Menu, Bot, PanelLeftClose } from "lucide-react";
import { useAuthStore } from "../stores/authStore";
import { useChatStore } from "../stores/chatStore";
import Sidebar from "../components/Sidebar";
import MessageItem from "../components/MessageItem";
import ChatInput from "../components/ChatInput";

const DISCLAIMER = import.meta.env.VITE_DISCLAIMER as string | undefined;

export default function Chat() {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId?: string }>();

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const logout = useAuthStore((s) => s.logout);

  const messages = useChatStore((s) => s.messages);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const streaming = useChatStore((s) => s.streaming);
  const error = useChatStore((s) => s.error);
  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const loadMessages = useChatStore((s) => s.loadMessages);
  const clearError = useChatStore((s) => s.clearError);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [desktopSidebarVisible, setDesktopSidebarVisible] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/");
    }
  }, [isAuthenticated, navigate]);

  // Sync URL sessionId to store
  useEffect(() => {
    if (sessionId && sessionId !== activeSessionId) {
      setActiveSession(sessionId);
      loadMessages(sessionId);
    }
  }, [sessionId, activeSessionId, setActiveSession, loadMessages]);

  // Update URL when active session changes
  useEffect(() => {
    if (activeSessionId && activeSessionId !== sessionId) {
      navigate(`/chat/${activeSessionId}`, { replace: true });
    }
  }, [activeSessionId, sessionId, navigate]);

  async function handleLogout() {
    useChatStore.getState().abortStream();
    await logout();
    navigate("/");
  }

  const visibleMessages = messages.filter((m) => m.role !== "system");
  const lastMsg = messages[messages.length - 1];
  const showThinking =
    streaming && lastMsg?.role === "assistant" && !lastMsg.content;

  return (
    <div className="h-dvh flex bg-[#0f0f23] text-[#e0e0e0]">
      {/* Desktop sidebar — toggleable */}
      <div className={`hidden md:block ${desktopSidebarVisible ? "" : "!hidden"}`}>
        <Sidebar open={true} onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Mobile sidebar */}
      <div className="md:hidden">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-[#2a2a4a] shrink-0 bg-[#0f0f23]">
          <div className="flex items-center gap-2">
            {/* Mobile menu */}
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 hover:bg-[#2d2d5e] rounded-lg transition-colors md:hidden"
            >
              <Menu className="w-5 h-5" />
            </button>
            {/* Desktop sidebar toggle */}
            <button
              onClick={() => setDesktopSidebarVisible((v) => !v)}
              className="p-1.5 hover:bg-[#2d2d5e] rounded-lg transition-colors hidden md:flex"
              title={desktopSidebarVisible ? "Hide sidebar" : "Show sidebar"}
            >
              <PanelLeftClose className={`w-5 h-5 transition-transform ${desktopSidebarVisible ? "" : "rotate-180"}`} />
            </button>
            <h1 className="text-base font-semibold">BioCoach</h1>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-[#8888aa] hover:bg-[#2d2d5e] hover:text-[#e0e0e0] rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </header>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto">
          {DISCLAIMER && (
            <div className="max-w-3xl mx-auto mt-4 mx-4 p-3 bg-[#2d2d5e]/20 border border-[#2a2a4a] rounded-lg text-xs text-[#8888aa] text-center">
              {DISCLAIMER}
            </div>
          )}

          {visibleMessages.length === 0 && !streaming && (
            <div className="flex flex-col items-center justify-center h-full text-[#4a4a6a]">
              <Bot className="w-16 h-16 mb-4 opacity-30" />
              <p className="text-lg font-medium text-[#6b6b8a] mb-1">How can I help you today?</p>
              <p className="text-sm text-[#4a4a6a]">Ask about nutrition, exercise, sleep, or health</p>
            </div>
          )}

          {visibleMessages.map((msg) => (
            <MessageItem key={msg.id} message={msg} />
          ))}

          {showThinking && (
            <div className="py-5 px-4 md:px-6">
              <div className="max-w-3xl mx-auto flex gap-4">
                <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center bg-[#2d8a6e]">
                  <Bot className="w-3.5 h-3.5 text-white" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-[#e0e0e0] mb-1.5">BioCoach</p>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Error bar */}
        {error && (
          <div className="px-4 py-2 bg-red-900/20 border-t border-red-900/30 text-sm text-red-400 text-center">
            {error}
            <button
              onClick={clearError}
              className="ml-3 underline hover:text-red-300"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Input */}
        <ChatInput />
      </div>
    </div>
  );
}
