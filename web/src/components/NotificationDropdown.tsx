import { useEffect, useRef } from "react";
import { useAgentStore, type AgentNotification } from "../stores/agentStore";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "только что";
  if (mins < 60) return `${mins} мин назад`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.floor(hours / 24);
  return `${days} д назад`;
}

interface Props {
  onClose: () => void;
}

export default function NotificationDropdown({ onClose }: Props) {
  const notifications = useAgentStore((s) => s.notifications);
  const markAsRead = useAgentStore((s) => s.markAsRead);
  const clearAllNotifications = useAgentStore((s) => s.clearAllNotifications);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full mt-1 w-80 max-h-96 overflow-y-auto bg-[#1a1a3e] border border-[#2a2a4a] rounded-lg shadow-xl z-50"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#2a2a4a]">
        <span className="text-sm font-semibold text-[#e0e0e0]">Уведомления</span>
        {notifications.length > 0 && (
          <button
            onClick={clearAllNotifications}
            className="text-xs text-[#8888aa] hover:text-[#e0e0e0] transition-colors"
          >
            Очистить все
          </button>
        )}
      </div>

      {notifications.length === 0 ? (
        <div className="px-3 py-6 text-center text-sm text-[#4a4a6a]">
          Нет уведомлений
        </div>
      ) : (
        <ul>
          {notifications.map((n: AgentNotification) => (
            <li
              key={n.id}
              onClick={() => {
                if (!n.is_read) markAsRead(n.id);
              }}
              className={`px-3 py-2.5 border-b border-[#2a2a4a] last:border-b-0 cursor-pointer hover:bg-[#2d2d5e]/40 transition-colors ${
                n.is_read ? "opacity-60" : ""
              }`}
            >
              <div className="flex items-start gap-2">
                {!n.is_read && (
                  <span className="mt-1.5 w-2 h-2 rounded-full bg-[#6366f1] shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-[#e0e0e0] truncate">
                    {n.content.title || "Уведомление"}
                  </p>
                  {n.content.body && (
                    <p className="text-xs text-[#8888aa] mt-0.5 line-clamp-2">
                      {n.content.body}
                    </p>
                  )}
                  <p className="text-xs text-[#4a4a6a] mt-1">
                    {timeAgo(n.created_at)}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
