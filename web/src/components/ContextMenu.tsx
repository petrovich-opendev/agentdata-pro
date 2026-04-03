import { useEffect, useRef } from "react";

export interface MenuItem {
  label: string;
  icon?: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
  divider?: boolean;
}

interface ContextMenuProps {
  items: MenuItem[];
  onClose: () => void;
}

export default function ContextMenu({ items, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", keyHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", keyHandler);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full z-50 mt-1 min-w-[180px] rounded-lg border border-[#2a2a4a] bg-[#1e1e3a] py-1 shadow-xl"
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item, i) => (
        <div key={i}>
          {item.divider && <div className="my-1 border-t border-[#2a2a4a]" />}
          <button
            onClick={() => {
              item.onClick();
            }}
            className={
              "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors " +
              (item.danger
                ? "text-red-400 hover:bg-red-900/20"
                : "text-[#b0b0c8] hover:bg-[#2d2d5e] hover:text-[#e0e0e0]")
            }
          >
            {item.icon}
            {item.label}
          </button>
        </div>
      ))}
    </div>
  );
}
