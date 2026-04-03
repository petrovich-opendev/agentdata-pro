// @ts-nocheck
import { useState, useRef } from "react";
import { MessageSquare, MoreHorizontal, Pencil, Trash2, FolderInput, FolderOutput, Check } from "lucide-react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useChatStore } from "../stores/chatStore";
import ContextMenu, { type MenuItem } from "./ContextMenu";
import type { ChatSession } from "../types";

interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: (id: string) => void;
  onNavigate: (id: string) => void;
}

export default function SessionItem({ session, isActive, onSelect, onNavigate }: SessionItemProps) {
  const { renameSession, deleteSession, moveChatToFolder, folders } = useChatStore();

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: session.id, data: { type: "session", session } });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const handleRename = () => {
    setEditTitle(session.title ?? "");
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const submitRename = () => {
    const t = editTitle.trim();
    if (t && t !== session.title) {
      renameSession(session.id, t);
    }
    setEditing(false);
  };

  const handleDelete = () => {
    deleteSession(session.id);
    setConfirmDelete(false);
    setMenuOpen(false);
  };

  const menuItems: MenuItem[] = [
    { label: "Rename", icon: <Pencil className="h-4 w-4" />, onClick: handleRename },
  ];

  if (session.folder_id) {
    menuItems.push({
      label: "Remove from folder",
      icon: <FolderOutput className="h-4 w-4" />,
      onClick: () => moveChatToFolder(session.id, null),
    });
  } else if ((folders || []).length > 0) {
    for (const f of (folders || [])) {
      menuItems.push({
        label: (f.emoji ? f.emoji + " " : "") + f.name,
        icon: <FolderInput className="h-4 w-4" />,
        onClick: () => moveChatToFolder(session.id, f.id),
      });
    }
  }

  menuItems.push({
    label: confirmDelete ? "Confirm delete" : "Delete",
    icon: <Trash2 className="h-4 w-4" />,
    onClick: confirmDelete ? handleDelete : () => setConfirmDelete(true),
    danger: true,
    divider: true,
  });

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => { onSelect(session.id); onNavigate(session.id); }}
      className={
        "group relative flex cursor-pointer items-center rounded-lg mb-0.5 transition-colors " +
        (isActive ? "bg-[#2d2d5e] text-white" : "text-[#b0b0c8] hover:bg-[#2d2d5e]/40")
      }
    >
      {editing ? (
        <div className="flex items-center gap-1 w-full px-2 py-1.5">
          <input
            ref={inputRef}
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={submitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitRename();
              if (e.key === "Escape") setEditing(false);
            }}
            onClick={(e) => e.stopPropagation()}
            className="flex-1 bg-[#0f0f23] text-sm text-[#e0e0e0] border border-[#6366f1] rounded px-2 py-1 outline-none min-w-0"
          />
          <button
            onMouseDown={(e) => e.preventDefault()}
            onClick={(e) => { e.stopPropagation(); submitRename(); }}
            className="p-1 text-[#2d8a6e] hover:text-[#4ade80]"
          >
            <Check className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <>
          <div className="flex-1 text-left px-3 py-2 flex items-center gap-2.5 min-w-0">
            <MessageSquare className={"w-4 h-4 shrink-0 " + (isActive ? "text-[#818cf8]" : "text-[#6b6b8a]")} />
            <span className="text-sm truncate">{session.title ?? "New Chat"}</span>
          </div>
          <div className={"relative flex items-center pr-2 " + (isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100") + " transition-opacity"}>
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); setConfirmDelete(false); }}
              className="p-1 text-[#6b6b8a] hover:text-[#e0e0e0] rounded transition-colors"
            >
              <MoreHorizontal className="w-3.5 h-3.5" />
            </button>
            {menuOpen && (
              <ContextMenu items={menuItems} onClose={() => { setMenuOpen(false); setConfirmDelete(false); }} />
            )}
          </div>
        </>
      )}
    </div>
  );
}
