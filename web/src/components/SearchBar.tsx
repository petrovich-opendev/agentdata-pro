// @ts-nocheck
import { useCallback, useEffect, useRef } from "react";
import { Search, X } from "lucide-react";
import { useChatStore } from "../stores/chatStore";

export default function SearchBar() {
  const {
    searchQuery,
    searchMode,
    searching,
    setSearchQuery,
    setSearchMode,
    performSearch,
    clearSearch,
  } = useChatStore();

  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const handleChange = useCallback(
    (value: string) => {
      setSearchQuery(value);
      clearTimeout(debounceRef.current);
      if (!value.trim()) return;
      debounceRef.current = setTimeout(() => {
        performSearch(value, searchMode);
      }, 300);
    },
    [searchMode, setSearchQuery, performSearch]
  );

  const handleModeToggle = useCallback(
    (mode: "title" | "content") => {
      setSearchMode(mode);
      if ((searchQuery || "").trim()) {
        performSearch(searchQuery, mode);
      }
    },
    [searchQuery, setSearchMode, performSearch]
  );

  useEffect(() => {
    return () => clearTimeout(debounceRef.current);
  }, []);

  return (
    <div className="px-2 pb-2">
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-[#6b6b8a]" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Search chats..."
          className="w-full rounded-lg bg-[#0f0f23] py-2 pl-9 pr-8 text-sm text-[#e0e0e0] placeholder-[#6b6b8a] border border-[#2a2a4a] outline-none focus:border-[#6366f1]"
        />
        {searchQuery && (
          <button
            onClick={clearSearch}
            className="absolute right-2 top-2 rounded p-0.5 text-[#6b6b8a] hover:text-[#e0e0e0]"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 text-xs">
        <button
          onClick={() => handleModeToggle("title")}
          className={"rounded px-2 py-0.5 transition-colors " + (searchMode === "title"
            ? "bg-[#2d2d5e] text-[#818cf8]"
            : "text-[#6b6b8a] hover:text-[#b0b0c8]")}
        >
          By title
        </button>
        <button
          onClick={() => handleModeToggle("content")}
          className={"rounded px-2 py-0.5 transition-colors " + (searchMode === "content"
            ? "bg-[#2d2d5e] text-[#818cf8]"
            : "text-[#6b6b8a] hover:text-[#b0b0c8]")}
        >
          In messages
        </button>
        {searching && <span className="text-[#6b6b8a] animate-pulse">...</span>}
      </div>
    </div>
  );
}
