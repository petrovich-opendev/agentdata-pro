// @ts-nocheck
import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, X, FolderPlus } from "lucide-react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { useDroppable } from "@dnd-kit/core";
import { useChatStore } from "../stores/chatStore";
import FolderItem from "./FolderItem";
import SessionItem from "./SessionItem";
import SearchBar from "./SearchBar";
import type { ChatSession } from "../types";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

interface SessionGroup {
  label: string;
  sessions: ChatSession[];
}

function groupByDate(sessions: ChatSession[]): SessionGroup[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);
  const monthAgo = new Date(today.getTime() - 30 * 86400000);

  const groups: Record<string, ChatSession[]> = {
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

function UngroupedDropZone({ children }: { children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({
    id: "ungrouped",
    data: { type: "ungrouped" },
  });

  return (
    <div
      ref={setNodeRef}
      className={"flex-1 " + (isOver ? "bg-[#2d2d5e]/20 rounded-lg" : "")}
    >
      {children}
    </div>
  );
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const navigate = useNavigate();

  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const sessionsLoaded = useChatStore((s) => s.sessionsLoaded);
  const loadSessions = useChatStore((s) => s.loadSessions);
  const createSession = useChatStore((s) => s.createSession);

  const folders = useChatStore((s) => s.folders) ?? [];
  const loadFolders = useChatStore((s) => s.loadFolders);
  const createFolder = useChatStore((s) => s.createFolder);
  const moveChatToFolder = useChatStore((s) => s.moveChatToFolder);

  const searchQuery = useChatStore((s) => s.searchQuery) ?? "";
  const searchResults = useChatStore((s) => s.searchResults) ?? [];

  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [draggedSession, setDraggedSession] = useState<ChatSession | null>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  useEffect(() => {
    if (!sessionsLoaded) loadSessions();
  }, [sessionsLoaded, loadSessions]);

  useEffect(() => {
    if (loadFolders) loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    if (creatingFolder && folderInputRef.current) {
      folderInputRef.current.focus();
    }
  }, [creatingFolder]);

  const handleNewChat = useCallback(async () => {
    const id = await createSession();
    if (id) navigate(`/chat/${id}`);
    onClose();
  }, [createSession, navigate, onClose]);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === activeSessionId) {
        onClose();
        return;
      }
      navigate(`/chat/${id}`);
      onClose();
    },
    [activeSessionId, navigate, onClose]
  );

  const handleNavigate = useCallback(
    (id: string) => {
      navigate(`/chat/${id}`);
    },
    [navigate]
  );

  const handleCreateFolder = useCallback(async () => {
    const name = newFolderName.trim();
    if (!name || !createFolder) return;
    await createFolder(name);
    setNewFolderName("");
    setCreatingFolder(false);
  }, [newFolderName, createFolder]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const data = event.active.data.current;
    if (data?.type === "session") {
      setDraggedSession(data.session);
    }
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setDraggedSession(null);
      const { active, over } = event;
      if (!over || !moveChatToFolder) return;

      const overData = over.data.current;
      const activeData = active.data.current;

      if (activeData?.type === "session" && overData?.type === "folder") {
        moveChatToFolder(active.id as string, overData.folderId);
      } else if (activeData?.type === "session" && overData?.type === "ungrouped") {
        moveChatToFolder(active.id as string, null);
      }
    },
    [moveChatToFolder]
  );

  const folderSessions = useMemo(() => {
    const map: Record<string, ChatSession[]> = {};
    for (const f of folders) map[f.id] = [];
    for (const s of sessions) {
      if (s.folder_id && map[s.folder_id]) {
        map[s.folder_id].push(s);
      }
    }
    return map;
  }, [folders, sessions]);

  const ungroupedSessions = useMemo(
    () => sessions.filter((s) => !s.folder_id),
    [sessions]
  );

  const grouped = useMemo(() => groupByDate(ungroupedSessions), [ungroupedSessions]);

  const isSearching = searchQuery.length > 0;

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
            onClick={() => setCreatingFolder(true)}
            className="ml-2 p-1.5 text-[#6b6b8a] hover:text-[#e0e0e0] hover:bg-[#2d2d5e] rounded-lg transition-colors"
            title="New folder"
          >
            <FolderPlus className="w-5 h-5" />
          </button>
          <button
            onClick={onClose}
            className="ml-2 p-1.5 text-[#e0e0e0] hover:bg-[#2d2d5e] rounded-lg md:hidden"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="pt-2">
          <SearchBar />
        </div>

        <DndContext
          sensors={sensors}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <div className="flex-1 overflow-y-auto px-2 pb-4">
            {isSearching ? (
              <div className="mt-2">
                <p className="px-3 py-1 text-[11px] font-semibold text-[#6b6b8a] uppercase tracking-wider">
                  Search Results
                </p>
                {searchResults.length === 0 ? (
                  <p className="text-center text-[#6b6b8a] text-xs mt-4 px-4">
                    No results found
                  </p>
                ) : (
                  searchResults.map((r: any) => {
                    const session = sessions.find((s) => s.id === r.session_id);
                    if (!session) return null;
                    return (
                      <SessionItem
                        key={session.id}
                        session={session}
                        isActive={session.id === activeSessionId}
                        onSelect={handleSelectSession}
                        onNavigate={handleNavigate}
                      />
                    );
                  })
                )}
              </div>
            ) : (
              <>
                {creatingFolder && (
                  <div className="mt-2 mb-1 px-2">
                    <input
                      ref={folderInputRef}
                      type="text"
                      value={newFolderName}
                      onChange={(e) => setNewFolderName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleCreateFolder();
                        if (e.key === "Escape") {
                          setCreatingFolder(false);
                          setNewFolderName("");
                        }
                      }}
                      onBlur={() => {
                        if (!newFolderName.trim()) {
                          setCreatingFolder(false);
                          setNewFolderName("");
                        }
                      }}
                      placeholder="Folder name..."
                      className="w-full rounded-lg bg-[#0f0f23] py-1.5 px-3 text-sm text-[#e0e0e0] placeholder-[#6b6b8a] border border-[#6366f1] outline-none"
                    />
                  </div>
                )}

                {folders.length > 0 && (
                  <div className="mt-2">
                    <p className="px-3 py-1 text-[11px] font-semibold text-[#6b6b8a] uppercase tracking-wider">
                      Folders
                    </p>
                    {folders.map((folder) => (
                      <FolderItem
                        key={folder.id}
                        folder={folder}
                        sessions={folderSessions[folder.id] ?? []}
                        activeSessionId={activeSessionId}
                        onSelectSession={handleSelectSession}
                        onNavigate={handleNavigate}
                      />
                    ))}
                  </div>
                )}

                <UngroupedDropZone>
                  <SortableContext
                    items={ungroupedSessions.map((s) => s.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    {grouped.map((group) => (
                      <div key={group.label} className="mt-3 first:mt-1">
                        <p className="px-3 py-1 text-[11px] font-semibold text-[#6b6b8a] uppercase tracking-wider">
                          {group.label}
                        </p>
                        {group.sessions.map((session) => (
                          <SessionItem
                            key={session.id}
                            session={session}
                            isActive={session.id === activeSessionId}
                            onSelect={handleSelectSession}
                            onNavigate={handleNavigate}
                          />
                        ))}
                      </div>
                    ))}
                  </SortableContext>
                </UngroupedDropZone>
              </>
            )}

            {sessions.length === 0 && sessionsLoaded && !isSearching && (
              <p className="text-center text-[#6b6b8a] text-xs mt-8 px-4">
                No conversations yet. Click "New Chat" to start.
              </p>
            )}
          </div>

          <DragOverlay>
            {draggedSession && (
              <div className="rounded-lg bg-[#2d2d5e] px-3 py-2 text-sm text-white shadow-xl border border-[#6366f1]/50 opacity-90">
                {draggedSession.title ?? "New Chat"}
              </div>
            )}
          </DragOverlay>
        </DndContext>
      </aside>
    </>
  );
}
