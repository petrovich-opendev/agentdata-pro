import { useEffect } from "react";
import {
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Trash2,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useDocumentStore } from "../stores/documentStore";
import type { Document } from "../types";

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "done":
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
    case "error":
      return <AlertCircle className="w-3.5 h-3.5 text-red-400" />;
    case "parsing":
    case "extracting":
    case "uploaded":
      return <Loader2 className="w-3.5 h-3.5 text-[#818cf8] animate-spin" />;
    default:
      return <FileText className="w-3.5 h-3.5 text-[#6b6b8a]" />;
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "done": return "Parsed";
    case "error": return "Error";
    case "parsing": return "Parsing...";
    case "extracting": return "Extracting...";
    case "uploaded": return "Queued";
    default: return status;
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface DocumentListProps {
  expanded: boolean;
  onToggle: () => void;
}

export default function DocumentList({ expanded, onToggle }: DocumentListProps) {
  const documents = useDocumentStore((s) => s.documents);
  const loading = useDocumentStore((s) => s.loading);
  const loadDocuments = useDocumentStore((s) => s.loadDocuments);
  const selectDocument = useDocumentStore((s) => s.selectDocument);
  const deleteDocument = useDocumentStore((s) => s.deleteDocument);
  const selectedDocument = useDocumentStore((s) => s.selectedDocument);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  if (documents.length === 0 && !loading) return null;

  return (
    <div className="mt-1">
      <button
        onClick={onToggle}
        className="flex items-center gap-1 w-full px-3 py-1 text-[11px] font-semibold text-[#6b6b8a] uppercase tracking-wider hover:text-[#e0e0e0] transition-colors"
      >
        {expanded ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        Lab Results ({documents.length})
      </button>

      {expanded && (
        <div className="space-y-0.5">
          {documents.map((doc) => (
            <DocumentItem
              key={doc.id}
              doc={doc}
              isSelected={selectedDocument?.id === doc.id}
              onSelect={() => selectDocument(doc.id)}
              onDelete={() => deleteDocument(doc.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DocumentItem({
  doc,
  isSelected,
  onSelect,
  onDelete,
}: {
  doc: Document;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className={`
        group flex items-center gap-2 rounded-lg px-3 py-1.5 cursor-pointer transition-colors
        ${isSelected ? "bg-[#2d2d5e] text-white" : "text-[#b0b0c8] hover:bg-[#2d2d5e]/40"}
      `}
    >
      <StatusIcon status={doc.processing_status} />
      <div className="flex-1 min-w-0">
        <div className="text-xs truncate">{doc.original_filename}</div>
        <div className="text-[10px] text-[#6b6b8a]">
          {formatSize(doc.file_size_bytes)} &middot; {statusLabel(doc.processing_status)}
        </div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 p-1 text-[#6b6b8a] hover:text-red-400 transition-all"
        title="Delete"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}
