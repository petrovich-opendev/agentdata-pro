import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useAgentStore, type AgentInfo } from "../stores/agentStore";
import { useLanguageStore } from "../stores/languageStore";
import AgentCard from "../components/AgentCard";
import AgentSettings from "../components/AgentSettings";

export default function Agents() {
  const navigate = useNavigate();
  const agents = useAgentStore((s) => s.agents);
  const loading = useAgentStore((s) => s.loading);
  const loadAgents = useAgentStore((s) => s.loadAgents);
  const toggleAgent = useAgentStore((s) => s.toggleAgent);
  const locale = useLanguageStore((s) => s.locale);

  const [settingsAgent, setSettingsAgent] = useState<AgentInfo | null>(null);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const t = locale === "ru";

  return (
    <div className="h-dvh flex flex-col bg-[#0f0f23] text-[#e0e0e0]">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-[#2a2a4a] shrink-0">
        <button
          onClick={() => navigate("/chat")}
          className="p-1.5 hover:bg-[#2d2d5e] rounded-lg transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-base font-semibold">
          {t ? "Агенты" : "Agents"}
        </h1>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="w-6 h-6 animate-spin text-[#6366f1]" />
          </div>
        ) : agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-[#6b6b8a]">
            <p className="text-sm">{t ? "Нет доступных агентов" : "No agents available"}</p>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map((agent) => (
              <AgentCard
                key={agent.code}
                agent={agent}
                onToggle={toggleAgent}
                onClick={(a) => setSettingsAgent(a)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Settings modal */}
      {settingsAgent && (
        <AgentSettings
          agent={settingsAgent}
          onClose={() => setSettingsAgent(null)}
        />
      )}
    </div>
  );
}
