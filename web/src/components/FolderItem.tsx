// @ts-nocheck
import { useState, useRef } from "react";
import { ChevronDown, ChevronRight, MoreHorizontal, Pencil, Trash2, Check } from "lucide-react";
import { useDroppable } from "@dnd-kit/core";
import { useChatStore } from "../stores/chatStore";
import SessionItem from "./SessionItem";
import ContextMenu, { type MenuItem } from "./ContextMenu";
import type { ChatFolder, ChatSession } from "../types";

interface FolderItemProps {
  folder: ChatFolder;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNavigate: (id: string) => void;
}

export default function FolderItem({
  folder,
  sessions,
  activeSessionId,
  onSelectSession,
  onNavigate,
}: FolderItemProps) {
  const { expandedFolders, toggleFolderExpanded, renameFolder, deleteFolder } = useChatStore();

  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const expanded = (expandedFolders || {})[folder.id] ?? true;

  const { setNodeRef, isOver } = useDroppable({
    id: `folder-${folder.id}`,
    data: { type: "folder", folderId: folder.id },
  });

  const handleRename = () => {
    setEditName(folder.name);
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const submitRename = () => {
    const n = editName.trim();
    if (n && n !== folder.name) {
      renameFolder(folder.id, n);
    }
    setEditing(false);
  };

  const menuItems: MenuItem[] = [
    { label: "Rename", icon: <Pencil className="h-4 w-4" />, onClick: handleRename },
    {
      label: "Delete folder",
      icon: <Trash2 className="h-4 w-4" />,
      onClick: () => deleteFolder(folder.id),
      danger: true,
      divider: true,
    },
  ];

  return (
    <div
      ref={setNodeRef}
      className={"mb-0.5 rounded-lg transition-all " + (isOver ? "ring-1 ring-[#6366f1]/50 bg-[#2d2d5e]/30" : "")}
    >
      <div
        onClick={() => toggleFolderExpanded(folder.id)}
        className="group flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-[#b0b0c8] hover:bg-[#2d2d5e]/40"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[#6b6b8a]" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#6b6b8a]" />
        )}
        <span className="shrink-0">{folder.emoji ?? ""}</span>
        {editing ? (
          <div className="flex flex-1 items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <input
              ref={inputRef}
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onBlur={submitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitRename();
                if (e.key === "Escape") setEditing(false);
              }}
              className="flex-1 rounded bg-[#0f0f23] px-1.5 py-0.5 text-sm text-[#e0e0e0] border border-[#6366f1] outline-none min-w-0"
            />
            <button
              onMouseDown={(e) => e.preventDefault()}
              onClick={(e) => { e.stopPropagation(); submitRename(); }}
              className="p-0.5 text-[#2d8a6e] hover:text-[#4ade80]"
            >
              <Check className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <span className="flex-1 truncate font-medium text-[#e0e0e0]">{folder.name}</span>
        )}
        <span className="text-xs text-[#6b6b8a]">{sessions.length}</span>
        <div className="relative">
          <button
            onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
            className="rounded p-0.5 text-[#6b6b8a] opacity-0 hover:text-[#e0e0e0] hover:bg-[#2d2d5e] group-hover:opacity-100 transition-opacity"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </button>
          {menuOpen && <ContextMenu items={menuItems} onClose={() => setMenuOpen(false)} />}
        </div>
      </div>
      {expanded && (
        <div className="ml-4 border-l border-[#2a2a4a] pl-1">
          {sessions.length === 0 ? (
            <div className="px-2 py-1.5 text-xs text-[#6b6b8a] italic">Drop chats here</div>
          ) : (
            sessions.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                isActive={s.id === activeSessionId}
                onSelect={onSelectSession}
                onNavigate={onNavigate}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
