import { useCallback, useEffect, useState } from "react";
import { X, Save, Loader2 } from "lucide-react";
import { useAgentStore, type AgentInfo } from "../stores/agentStore";
import { useLanguageStore } from "../stores/languageStore";
import WatchlistPanel from "./WatchlistPanel";

const CATEGORY_OPTIONS = [
  { value: "medication", label_ru: "Лекарства", label_en: "Medications" },
  { value: "supplement", label_ru: "БАДы", label_en: "Supplements" },
  { value: "lab_test", label_ru: "Анализы", label_en: "Lab Tests" },
];

const SCHEDULE_OPTIONS = [
  { value: "on_demand", label_ru: "По запросу", label_en: "On Demand" },
  { value: "daily", label_ru: "Ежедневно", label_en: "Daily" },
  { value: "hourly", label_ru: "Каждый час", label_en: "Hourly" },
];

interface AgentSettingsProps {
  agent: AgentInfo;
  onClose: () => void;
}

export default function AgentSettings({ agent, onClose }: AgentSettingsProps) {
  const saveSettings = useAgentStore((s) => s.saveSettings);
  const loadWatchlist = useAgentStore((s) => s.loadWatchlist);
  const locale = useLanguageStore((s) => s.locale);

  const [city, setCity] = useState<string>(
    (agent.settings.city as string) ?? "Москва"
  );
  const [categories, setCategories] = useState<string[]>(
    (agent.settings.categories as string[]) ?? ["medication", "supplement", "lab_test"]
  );
  const [schedule, setSchedule] = useState<string>(
    (agent.settings.schedule as string) ?? "daily"
  );
  const [notifyTelegram, setNotifyTelegram] = useState<boolean>(
    (agent.settings.notify_telegram as boolean) ?? true
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (agent.code === "price_monitor") {
      loadWatchlist();
    }
  }, [agent.code, loadWatchlist]);

  const toggleCategory = useCallback((cat: string) => {
    setCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await saveSettings(agent.code, {
        city,
        categories,
        schedule,
        notify_telegram: notifyTelegram,
      });
      onClose();
    } finally {
      setSaving(false);
    }
  }, [agent.code, city, categories, schedule, notifyTelegram, saveSettings, onClose]);

  const t = locale === "ru";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#1e1e3a] border border-[#2a2a4a] rounded-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a4a]">
          <h2 className="text-base font-semibold text-[#e0e0e0]">
            {agent.name} — {t ? "Настройки" : "Settings"}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-[#2d2d5e] rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-[#8888aa]" />
          </button>
        </div>

        <div className="p-4 space-y-5">
          {/* City */}
          <div>
            <label className="block text-xs font-medium text-[#8888aa] mb-1.5">
              {t ? "Город" : "City"}
            </label>
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="w-full rounded-lg bg-[#0f0f23] border border-[#2a2a4a] py-2 px-3 text-sm text-[#e0e0e0] placeholder-[#6b6b8a] outline-none focus:border-[#6366f1]"
            />
          </div>

          {/* Categories */}
          <div>
            <label className="block text-xs font-medium text-[#8888aa] mb-1.5">
              {t ? "Категории" : "Categories"}
            </label>
            <div className="flex flex-wrap gap-2">
              {CATEGORY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => toggleCategory(opt.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    categories.includes(opt.value)
                      ? "bg-[#6366f1] text-white"
                      : "bg-[#0f0f23] text-[#8888aa] border border-[#2a2a4a] hover:border-[#6366f1]/50"
                  }`}
                >
                  {t ? opt.label_ru : opt.label_en}
                </button>
              ))}
            </div>
          </div>

          {/* Schedule */}
          <div>
            <label className="block text-xs font-medium text-[#8888aa] mb-1.5">
              {t ? "Расписание" : "Schedule"}
            </label>
            <div className="flex flex-wrap gap-2">
              {SCHEDULE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setSchedule(opt.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    schedule === opt.value
                      ? "bg-[#6366f1] text-white"
                      : "bg-[#0f0f23] text-[#8888aa] border border-[#2a2a4a] hover:border-[#6366f1]/50"
                  }`}
                >
                  {t ? opt.label_ru : opt.label_en}
                </button>
              ))}
            </div>
          </div>

          {/* Telegram notifications */}
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-[#8888aa]">
              {t ? "Уведомления в Telegram" : "Telegram Notifications"}
            </label>
            <button
              onClick={() => setNotifyTelegram(!notifyTelegram)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                notifyTelegram ? "bg-[#6366f1]" : "bg-[#2a2a4a]"
              }`}
            >
              <span
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  notifyTelegram ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>

          {/* Watchlist (price_monitor only) */}
          {agent.code === "price_monitor" && <WatchlistPanel />}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#2a2a4a]">
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-[#6366f1] hover:bg-[#5558e6] text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {t ? "Сохранить" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
