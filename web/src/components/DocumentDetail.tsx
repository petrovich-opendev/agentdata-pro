import { X, Download, FileText, AlertTriangle, ArrowDown, ArrowUp, Minus } from "lucide-react";
import { useDocumentStore } from "../stores/documentStore";
import { apiFetch } from "../api/client";
import type { Biomarker } from "../types";

function StatusBadge({ status }: { status: string | null }) {
  switch (status) {
    case "normal":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-900/30 text-emerald-400">
          <Minus className="w-2.5 h-2.5" /> Norm
        </span>
      );
    case "low":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-900/30 text-blue-400">
          <ArrowDown className="w-2.5 h-2.5" /> Low
        </span>
      );
    case "high":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-900/30 text-amber-400">
          <ArrowUp className="w-2.5 h-2.5" /> High
        </span>
      );
    case "critical":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-900/30 text-red-400">
          <AlertTriangle className="w-2.5 h-2.5" /> Critical
        </span>
      );
    default:
      return null;
  }
}

function groupBiomarkersByCategory(biomarkers: Biomarker[]): Record<string, Biomarker[]> {
  const groups: Record<string, Biomarker[]> = {};
  for (const b of biomarkers) {
    const cat = b.category || "Other";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(b);
  }
  return groups;
}

export default function DocumentDetail() {
  const doc = useDocumentStore((s) => s.selectedDocument);
  const clearSelected = useDocumentStore((s) => s.clearSelectedDocument);

  if (!doc) return null;

  const grouped = groupBiomarkersByCategory(doc.biomarkers);
  const abnormal = doc.biomarkers.filter(
    (b) => b.status === "low" || b.status === "high" || b.status === "critical"
  );

  async function handleDownload() {
    if (!doc) return;
    const res = await apiFetch(`/api/documents/${doc.id}/download`);
    if (res.ok) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.original_filename;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl max-h-[85vh] mx-4 bg-[#1e1e3a] border border-[#2a2a4a] rounded-xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#2a2a4a]">
          <div className="flex items-center gap-2 min-w-0">
            <FileText className="w-5 h-5 text-[#818cf8] shrink-0" />
            <h2 className="text-sm font-semibold text-[#e0e0e0] truncate">
              {doc.original_filename}
            </h2>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleDownload}
              className="p-1.5 text-[#6b6b8a] hover:text-[#e0e0e0] hover:bg-[#2d2d5e] rounded-lg transition-colors"
              title="Download original"
            >
              <Download className="w-4 h-4" />
            </button>
            <button
              onClick={clearSelected}
              className="p-1.5 text-[#6b6b8a] hover:text-[#e0e0e0] hover:bg-[#2d2d5e] rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {doc.processing_status !== "done" ? (
            <div className="text-center py-8">
              <div className="flex items-center justify-center gap-1.5 mb-2">
                <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
              <p className="text-sm text-[#6b6b8a]">
                {doc.processing_status === "error"
                  ? "Failed to parse document"
                  : "Analyzing your lab results..."}
              </p>
            </div>
          ) : doc.biomarkers.length === 0 ? (
            <p className="text-sm text-[#6b6b8a] text-center py-8">
              No biomarkers found in this document.
            </p>
          ) : (
            <>
              {/* Summary */}
              {abnormal.length > 0 && (
                <div className="mb-4 p-3 rounded-lg bg-amber-900/10 border border-amber-900/30">
                  <p className="text-xs font-semibold text-amber-400 mb-1">
                    Attention: {abnormal.length} value{abnormal.length > 1 ? "s" : ""} outside reference range
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {abnormal.map((b) => (
                      <span key={b.id} className="text-[11px] text-[#e0e0e0]">
                        {b.name}: {b.value} {b.unit ?? ""}
                        <StatusBadge status={b.status} />
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Biomarker table by category */}
              {Object.entries(grouped).map(([category, markers]) => (
                <div key={category} className="mb-4">
                  <h3 className="text-xs font-semibold text-[#818cf8] uppercase tracking-wider mb-2">
                    {category}
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-[#6b6b8a] border-b border-[#2a2a4a]">
                          <th className="text-left py-1.5 pr-3 font-medium">Biomarker</th>
                          <th className="text-right py-1.5 pr-3 font-medium">Value</th>
                          <th className="text-left py-1.5 pr-3 font-medium">Unit</th>
                          <th className="text-left py-1.5 pr-3 font-medium">Reference</th>
                          <th className="text-center py-1.5 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {markers.map((b) => (
                          <tr
                            key={b.id}
                            className={`border-b border-[#2a2a4a]/50 ${
                              b.status === "critical"
                                ? "bg-red-900/10"
                                : b.status === "high" || b.status === "low"
                                ? "bg-amber-900/5"
                                : ""
                            }`}
                          >
                            <td className="py-1.5 pr-3 text-[#e0e0e0]">{b.name}</td>
                            <td className="py-1.5 pr-3 text-right font-mono text-[#e0e0e0]">
                              {b.value}
                            </td>
                            <td className="py-1.5 pr-3 text-[#6b6b8a]">{b.unit ?? ""}</td>
                            <td className="py-1.5 pr-3 text-[#6b6b8a]">
                              {b.ref_range_text ?? ""}
                            </td>
                            <td className="py-1.5 text-center">
                              <StatusBadge status={b.status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}

              <p className="text-[10px] text-[#4a4a6a] text-center mt-4">
                Total: {doc.biomarkers.length} biomarkers extracted
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
