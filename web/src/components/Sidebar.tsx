import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, X, MessageSquare, Trash2, Pencil, Check } from "lucide-react";
import { useChatStore } from "../stores/chatStore";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

interface SessionGroup {
  label: string;
  sessions: { id: string; title: string | null; created_at: string }[];
}

function groupByDate(sessions: { id: string; title: string | null; created_at: string }[]): SessionGroup[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);
  const monthAgo = new Date(today.getTime() - 30 * 86400000);

  const groups: Record<string, { id: string; title: string | null; created_at: string }[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    "Previous 30 Days": [],
    Older: [],
  };

  for (const s of sessions) {
    const d = new Date(s.created_at);
    if (d >= today) groups["Today"].push(s);
    else if (d >= yesterday) groups["Yesterday"].push(s);
    else if (d >= weekAgo) groups["Previous 7 Days"].push(s);
    else if (d >= monthAgo) groups["Previous 30 Days"].push(s);
    else groups["Older"].push(s);
  }

  return Object.entries(groups)
    .filter(([, list]) => list.length > 0)
    .map(([label, list]) => ({ label, sessions: list }));
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const navigate = useNavigate();
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const sessionsLoaded = useChatStore((s) => s.sessionsLoaded);
  const loadSessions = useChatStore((s) => s.loadSessions);
  const createSession = useChatStore((s) => s.createSession);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const renameSession = useChatStore((s) => s.renameSession);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!sessionsLoaded) {
      loadSessions();
    }
  }, [sessionsLoaded, loadSessions]);

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const handleNewChat = useCallback(async () => {
    const id = await createSession();
    if (id) {
      navigate(`/chat/${id}`);
    }
    onClose();
  }, [createSession, navigate, onClose]);

  function handleSelectSession(id: string) {
    if (editingId || deletingId) return;
    if (id === activeSessionId) {
      onClose();
      return;
    }
    // Only navigate — Chat.tsx effect handles setActiveSession + loadMessages
    navigate(`/chat/${id}`);
    onClose();
  }

  function startRename(id: string, currentTitle: string | null) {
    setEditingId(id);
    setEditTitle(currentTitle ?? "");
    setDeletingId(null);
  }

  async function confirmRename() {
    if (editingId && editTitle.trim()) {
      await renameSession(editingId, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle("");
  }

  function cancelRename() {
    setEditingId(null);
    setEditTitle("");
  }

  async function confirmDelete(id: string) {
    await deleteSession(id);
    setDeletingId(null);
    if (id === activeSessionId) {
      const remaining = sessions.filter((s) => s.id !== id);
      if (remaining.length > 0) {
        navigate(`/chat/${remaining[0].id}`);
      } else {
        navigate("/chat");
      }
    }
  }

  const grouped = groupByDate(sessions);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`
          fixed md:relative z-50 top-0 left-0 h-full
          w-[260px] flex flex-col
          bg-[#1e1e3a] border-r border-[#2a2a4a]
          transition-transform duration-200 ease-in-out
          ${open ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        <div className="flex items-center justify-between p-3 border-b border-[#2a2a4a]">
          <button
            onClick={handleNewChat}
            className="flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg border border-[#3a3a5c] text-[#e0e0e0] hover:bg-[#2d2d5e] transition-colors text-sm font-medium"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
          <button
            onClick={onClose}
            className="ml-2 p-1.5 text-[#e0e0e0] hover:bg-[#2d2d5e] rounded-lg md:hidden"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-4 pt-1">
          {grouped.map((group) => (
            <div key={group.label} className="mt-3 first:mt-1">
              <p className="px-3 py-1 text-[11px] font-semibold text-[#6b6b8a] uppercase tracking-wider">
                {group.label}
              </p>
              {group.sessions.map((session) => {
                const isActive = session.id === activeSessionId;
                const isEditing = editingId === session.id;
                const isDeleting = deletingId === session.id;

                return (
                  <div
                    key={session.id}
                    className={`
                      relative flex items-center rounded-lg mb-0.5 group transition-colors
                      ${isActive ? "bg-[#2d2d5e]" : "hover:bg-[#2d2d5e]/40"}
                    `}
                  >
                    {isEditing ? (
                      <div className="flex items-center gap-1 w-full px-2 py-1.5">
                        <input
                          ref={editInputRef}
                          type="text"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") confirmRename();
                            if (e.key === "Escape") cancelRename();
                          }}
                          onBlur={confirmRename}
                          className="flex-1 bg-[#0f0f23] text-sm text-[#e0e0e0] border border-[#6366f1] rounded px-2 py-1 outline-none min-w-0"
                          maxLength={200}
                        />
                        <button
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={confirmRename}
                          className="p-1 text-[#2d8a6e] hover:text-[#4ade80]"
                        >
                          <Check className="w-4 h-4" />
                        </button>
                      </div>
                    ) : isDeleting ? (
                      <div className="flex items-center gap-2 w-full px-3 py-2">
                        <span className="text-xs text-[#b0b0c8] flex-1">Delete?</span>
                        <button
                          onClick={() => confirmDelete(session.id)}
                          className="text-xs text-red-400 hover:text-red-300 font-medium"
                        >
                          Yes
                        </button>
                        <button
                          onClick={() => setDeletingId(null)}
                          className="text-xs text-[#b0b0c8] hover:text-[#e0e0e0]"
                        >
                          No
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => handleSelectSession(session.id)}
                          className="flex-1 text-left px-3 py-2 flex items-center gap-2.5 min-w-0"
                        >
                          <MessageSquare className={`w-4 h-4 shrink-0 ${isActive ? "text-[#818cf8]" : "text-[#6b6b8a]"}`} />
                          <span className={`text-sm truncate ${isActive ? "text-white" : "text-[#b0b0c8]"}`}>
                            {session.title || "New Chat"}
                          </span>
                        </button>
                        <div className={`flex items-center gap-0.5 pr-2 ${isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"} transition-opacity`}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              startRename(session.id, session.title);
                            }}
                            className="p-1 text-[#6b6b8a] hover:text-[#e0e0e0] rounded transition-colors"
                            title="Rename"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeletingId(session.id);
                              setEditingId(null);
                            }}
                            className="p-1 text-[#6b6b8a] hover:text-red-400 rounded transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          ))}

          {sessions.length === 0 && sessionsLoaded && (
            <p className="text-center text-[#6b6b8a] text-xs mt-8 px-4">
              No conversations yet. Click "New Chat" to start.
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
