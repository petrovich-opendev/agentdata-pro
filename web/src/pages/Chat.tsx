import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { LogOut, Menu, Bot, PanelLeftClose, Cpu, Bell } from "lucide-react";
import { useAuthStore } from "../stores/authStore";
import { useChatStore } from "../stores/chatStore";
import { useLanguageStore } from "../stores/languageStore";
import { useAgentStore } from "../stores/agentStore";
import NotificationDropdown from "../components/NotificationDropdown";
import Sidebar from "../components/Sidebar";
import MessageItem from "../components/MessageItem";
import ChatInput from "../components/ChatInput";
import DocumentDetail from "../components/DocumentDetail";

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
  const loadingMessages = useChatStore((s) => s.loadingMessages);
  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const loadMessages = useChatStore((s) => s.loadMessages);
  const clearError = useChatStore((s) => s.clearError);

  const locale = useLanguageStore((s) => s.locale);
  const setLocale = useLanguageStore((s) => s.setLocale);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);

  const notifications = useAgentStore((s) => s.notifications);
  const loadNotifications = useAgentStore((s) => s.loadNotifications);
  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const [droppedFile, setDroppedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);

  const ALLOWED_TYPES = ["application/pdf", "image/jpeg", "image/png"];
  const MAX_SIZE = 20 * 1024 * 1024;

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.types.includes("Files")) {
      setIsDragOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setIsDragOver(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    dragCounter.current = 0;
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (!ALLOWED_TYPES.includes(file.type)) {
      useChatStore.setState({ error: "Допустимые форматы: PDF, JPG, PNG" });
      return;
    }
    if (file.size > MAX_SIZE) {
      useChatStore.setState({ error: "Максимальный размер файла — 20 МБ" });
      return;
    }
    setDroppedFile(file);
  }, []);
  const [panelVisible, setPanelVisible] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);

  const scrollToBottom = useCallback(() => {
    if (!userScrolledUp.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    const el = scrollAreaRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      userScrolledUp.current = distFromBottom > 150;
    };
    el.addEventListener("scroll", handleScroll);
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (streaming) {
      scrollToBottom();
    }
  }, [messages, streaming, scrollToBottom]);

  useEffect(() => {
    const last = messages[messages.length - 1];
    if (last?.role === "user") {
      userScrolledUp.current = false;
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length]);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/");
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    if (sessionId && sessionId !== activeSessionId) {
      setActiveSession(sessionId);
      loadMessages(sessionId);
    }
  }, [sessionId, activeSessionId, setActiveSession, loadMessages]);

  useEffect(() => {
    if (activeSessionId && activeSessionId !== sessionId) {
      navigate(`/chat/${activeSessionId}`, { replace: true });
    }
  }, [activeSessionId]);  // eslint-disable-line react-hooks/exhaustive-deps


  // Poll notifications every 30s
  useEffect(() => {
    if (!isAuthenticated) return;
    loadNotifications();
    const interval = setInterval(loadNotifications, 30_000);
    return () => clearInterval(interval);
  }, [isAuthenticated, loadNotifications]);

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
      {/* Desktop sidebar */}
      <div className={`hidden md:block ${panelVisible ? "" : "!hidden"}`}>
        <Sidebar open={true} onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Mobile sidebar */}
      <div className="md:hidden">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Main chat area */}
      <div
        className="flex-1 flex flex-col min-w-0 relative"
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-[#2a2a4a] shrink-0 bg-[#0f0f23]">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 hover:bg-[#2d2d5e] rounded-lg transition-colors md:hidden"
            >
              <Menu className="w-5 h-5" />
            </button>
            <button
              onClick={() => setPanelVisible((v) => !v)}
              className="p-1.5 hover:bg-[#2d2d5e] rounded-lg transition-colors hidden md:flex"
              title={panelVisible ? "Hide sidebar" : "Show sidebar"}
            >
              <PanelLeftClose className={`w-5 h-5 transition-transform ${panelVisible ? "" : "rotate-180"}`} />
            </button>
            <h1 className="text-base font-semibold">BioCoach</h1>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setLocale(locale === "ru" ? "en" : "ru")}
              className="px-3 py-1.5 text-sm text-[#8888aa] hover:bg-[#2d2d5e] hover:text-[#e0e0e0] rounded-lg transition-colors"
            >
              {locale === "ru" ? "RU" : "EN"}
            </button>
            <div className="relative">
              <button
                onClick={() => setNotifOpen((v) => !v)}
                className="relative flex items-center gap-1.5 px-3 py-1.5 text-sm text-[#8888aa] hover:bg-[#2d2d5e] hover:text-[#e0e0e0] rounded-lg transition-colors"
                title="Уведомления"
              >
                <Bell className="w-4 h-4" />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-[#6366f1] text-[10px] font-bold text-white px-1">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                )}
              </button>
              {notifOpen && <NotificationDropdown onClose={() => setNotifOpen(false)} />}
            </div>
            <button
              onClick={() => navigate("/agents")}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-[#8888aa] hover:bg-[#2d2d5e] hover:text-[#e0e0e0] rounded-lg transition-colors"
              title={locale === "ru" ? "Агенты" : "Agents"}
            >
              <Cpu className="w-4 h-4" />
            </button>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-[#8888aa] hover:bg-[#2d2d5e] hover:text-[#e0e0e0] rounded-lg transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </header>

        {/* Messages area */}
        <div ref={scrollAreaRef} className="flex-1 overflow-y-auto">
          {DISCLAIMER && (
            <div className="max-w-3xl mx-auto mt-4 mx-4 p-3 bg-[#2d2d5e]/20 border border-[#2a2a4a] rounded-lg text-xs text-[#8888aa] text-center">
              {DISCLAIMER}
            </div>
          )}

          {visibleMessages.length === 0 && !streaming && (
            loadingMessages ? (
              <div className="flex flex-col items-center justify-center h-full text-[#4a4a6a]">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-[#4a4a6a]">
                <Bot className="w-16 h-16 mb-4 opacity-30" />
                <p className="text-lg font-medium text-[#6b6b8a] mb-1">How can I help you today?</p>
                <p className="text-sm text-[#4a4a6a]">Ask about nutrition, exercise, sleep, or health</p>
              </div>
            )
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

        {/* Drag overlay */}
        {isDragOver && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#0f0f23]/80 border-2 border-dashed border-[#6366f1] rounded-lg pointer-events-none">
            <p className="text-lg font-medium text-[#818cf8]">Перетащите файл сюда</p>
          </div>
        )}

        {/* Input */}
        <ChatInput droppedFile={droppedFile} onDroppedFileConsumed={() => setDroppedFile(null)} />
      </div>

      {/* Document detail modal */}
      <DocumentDetail />
    </div>
  );
}
