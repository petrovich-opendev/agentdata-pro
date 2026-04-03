import { Activity, ToggleLeft, ToggleRight } from "lucide-react";
import type { AgentInfo } from "../stores/agentStore";

interface AgentCardProps {
  agent: AgentInfo;
  onToggle: (code: string) => void;
  onClick: (agent: AgentInfo) => void;
}

export default function AgentCard({ agent, onToggle, onClick }: AgentCardProps) {
  return (
    <div
      className="bg-[#1e1e3a] border border-[#2a2a4a] rounded-xl p-5 cursor-pointer hover:border-[#6366f1]/50 transition-all"
      onClick={() => onClick(agent)}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-lg bg-[#2d2d5e] flex items-center justify-center">
          <Activity className="w-5 h-5 text-[#818cf8]" />
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(agent.code);
          }}
          className="p-1 hover:bg-[#2d2d5e] rounded-lg transition-colors"
          title={agent.is_active ? "Deactivate" : "Activate"}
        >
          {agent.is_active ? (
            <ToggleRight className="w-8 h-5 text-[#22c55e]" />
          ) : (
            <ToggleLeft className="w-8 h-5 text-[#6b6b8a]" />
          )}
        </button>
      </div>
      <h3 className="text-sm font-semibold text-[#e0e0e0] mb-1">{agent.name}</h3>
      <p className="text-xs text-[#8888aa] mb-3 line-clamp-2">{agent.description}</p>
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
            agent.is_active
              ? "bg-[#22c55e]/10 text-[#22c55e]"
              : "bg-[#6b6b8a]/10 text-[#6b6b8a]"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              agent.is_active ? "bg-[#22c55e]" : "bg-[#6b6b8a]"
            }`}
          />
          {agent.is_active ? "Active" : "Inactive"}
        </span>
        {agent.last_run && (
          <span className="text-[10px] text-[#6b6b8a]">
            Last: {new Date(agent.last_run).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}
