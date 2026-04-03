import { useCallback, useState } from "react";
import { X, Plus, Loader2, PackageSearch } from "lucide-react";
import { useAgentStore, type WatchlistItem } from "../stores/agentStore";
import { useLanguageStore } from "../stores/languageStore";

const CATEGORY_OPTIONS = [
  { value: "medication", label_ru: "Лекарства", label_en: "Medications", color: "bg-blue-500/20 text-blue-400" },
  { value: "supplement", label_ru: "БАДы", label_en: "Supplements", color: "bg-emerald-500/20 text-emerald-400" },
  { value: "lab_test", label_ru: "Анализы", label_en: "Lab Tests", color: "bg-purple-500/20 text-purple-400" },
];

function categoryBadge(category: string, isRu: boolean) {
  const opt = CATEGORY_OPTIONS.find((c) => c.value === category);
  if (!opt) return null;
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${opt.color}`}>
      {isRu ? opt.label_ru : opt.label_en}
    </span>
  );
}

function formatDate(dateStr: string | null, isRu: boolean): string {
  if (!dateStr) return isRu ? "не проверялось" : "not checked";
  const d = new Date(dateStr);
  return d.toLocaleDateString(isRu ? "ru-RU" : "en-US", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function WatchlistItemRow({
  item,
  onRemove,
  isRu,
}: {
  item: WatchlistItem;
  onRemove: (id: string) => void;
  isRu: boolean;
}) {
  return (
    <div className="flex items-start justify-between bg-[#0f0f23] rounded-lg px-3 py-2.5 gap-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-xs text-[#e0e0e0] truncate font-medium">
            {item.product_name}
          </p>
          {categoryBadge(item.product_category, isRu)}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-[#6b6b8a]">
          {item.target_price != null && (
            <span>
              {isRu ? "Цель" : "Target"}: {item.target_price} ₽
            </span>
          )}
          {item.best_price != null ? (
            <span className="text-[#22c55e]">
              {isRu ? "Лучшая" : "Best"}: {item.best_price} ₽
              {item.best_source ? ` (${item.best_source})` : ""}
            </span>
          ) : (
            <span>{isRu ? "Цена не найдена" : "No price found"}</span>
          )}
          <span>{isRu ? "Проверено" : "Checked"}: {formatDate(item.last_checked_at, isRu)}</span>
        </div>
      </div>
      <button
        onClick={() => onRemove(item.id)}
        className="p-1 hover:bg-[#2d2d5e] rounded transition-colors shrink-0 mt-0.5"
        title={isRu ? "Удалить" : "Remove"}
      >
        <X className="w-3.5 h-3.5 text-[#6b6b8a]" />
      </button>
    </div>
  );
}

export default function WatchlistPanel() {
  const watchlist = useAgentStore((s) => s.watchlist);
  const watchlistLoading = useAgentStore((s) => s.watchlistLoading);
  const addWatchlistItem = useAgentStore((s) => s.addWatchlistItem);
  const removeWatchlistItem = useAgentStore((s) => s.removeWatchlistItem);
  const locale = useLanguageStore((s) => s.locale);
  const isRu = locale === "ru";

  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] = useState("medication");
  const [newTargetPrice, setNewTargetPrice] = useState("");
  const [adding, setAdding] = useState(false);

  const handleAdd = useCallback(async () => {
    const name = newName.trim();
    if (!name) return;
    setAdding(true);
    try {
      const price = newTargetPrice.trim() ? parseFloat(newTargetPrice) : undefined;
      await addWatchlistItem(name, newCategory, price);
      setNewName("");
      setNewTargetPrice("");
    } finally {
      setAdding(false);
    }
  }, [newName, newCategory, newTargetPrice, addWatchlistItem]);

  return (
    <div>
      <label className="block text-xs font-medium text-[#8888aa] mb-1.5">
        {isRu ? "Список отслеживания" : "Watchlist"}
      </label>

      {watchlistLoading ? (
        <div className="flex items-center gap-2 text-xs text-[#6b6b8a] py-3">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          {isRu ? "Загрузка..." : "Loading..."}
        </div>
      ) : watchlist.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-6 text-center">
          <PackageSearch className="w-8 h-8 text-[#3a3a5a]" />
          <p className="text-xs text-[#6b6b8a]">
            {isRu
              ? "Список отслеживания пуст. Добавьте товары для мониторинга."
              : "Watchlist is empty. Add products to monitor."}
          </p>
        </div>
      ) : (
        <div className="space-y-1.5 mb-3 max-h-60 overflow-y-auto">
          {watchlist.map((item) => (
            <WatchlistItemRow
              key={item.id}
              item={item}
              onRemove={removeWatchlistItem}
              isRu={isRu}
            />
          ))}
        </div>
      )}

      {/* Add item form */}
      <div className="space-y-2 mt-2">
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder={isRu ? "Название товара..." : "Product name..."}
            className="flex-1 min-w-0 rounded-lg bg-[#0f0f23] border border-[#2a2a4a] py-1.5 px-3 text-xs text-[#e0e0e0] placeholder-[#6b6b8a] outline-none focus:border-[#6366f1]"
          />
          <select
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            className="rounded-lg bg-[#0f0f23] border border-[#2a2a4a] py-1.5 px-2 text-xs text-[#e0e0e0] outline-none focus:border-[#6366f1]"
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {isRu ? opt.label_ru : opt.label_en}
              </option>
            ))}
          </select>
        </div>
        <div className="flex gap-2">
          <input
            type="number"
            value={newTargetPrice}
            onChange={(e) => setNewTargetPrice(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder={isRu ? "Целевая цена, ₽" : "Target price, ₽"}
            min="0"
            step="0.01"
            className="flex-1 min-w-0 rounded-lg bg-[#0f0f23] border border-[#2a2a4a] py-1.5 px-3 text-xs text-[#e0e0e0] placeholder-[#6b6b8a] outline-none focus:border-[#6366f1]"
          />
          <button
            onClick={handleAdd}
            disabled={adding || !newName.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#6366f1] hover:bg-[#5558e6] disabled:opacity-40 rounded-lg transition-colors text-xs font-medium text-white"
          >
            {adding ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Plus className="w-3.5 h-3.5" />
            )}
            {isRu ? "Добавить" : "Add"}
          </button>
        </div>
      </div>
    </div>
  );
}
