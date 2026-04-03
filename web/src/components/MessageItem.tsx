import { Bot, User, Copy, Check, FileText, Image, Loader2, AlertTriangle, ArrowDown, ArrowUp, Minus, ChevronRight } from "lucide-react";
import { useState, useCallback, type ReactNode } from "react";
import { useDocumentStore } from "../stores/documentStore";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message, Biomarker } from "../types";
import { useChatStore } from "../stores/chatStore";

interface MessageItemProps {
  message: Message;
}

function CodeBlock({ language, children }: { language: string; children: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [children]);

  return (
    <div className="relative group my-3 rounded-lg overflow-hidden border border-[#3a3a5c]">
      <div className="flex items-center justify-between px-4 py-1.5 bg-[#1a1a36] text-xs text-[#8888aa]">
        <span>{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-[#e0e0e0] transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 bg-[#0d0d1f] text-sm leading-relaxed">
        <code>{children}</code>
      </pre>
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        code(props: any) {
          const { className, children } = props;
          const match = /language-(\w+)/.exec(className || "");
          const text = String(children).replace(/\n$/, "");
          if (match) {
            return <CodeBlock language={match[1]} >{text}</CodeBlock>;
          }
          return (
            <code className="bg-[#2d2d5e] text-[#c4b5fd] px-1.5 py-0.5 rounded text-[13px]">
              {children}
            </code>
          );
        },
        pre({ children }: { children?: ReactNode }) {
          return <>{children}</>;
        },
        a({ href, children }: { href?: string; children?: ReactNode }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#818cf8] underline hover:text-[#a5b4fc]"
            >
              {children}
            </a>
          );
        },
        ul({ children }: { children?: ReactNode }) {
          return <ul className="list-disc pl-6 my-2 space-y-1">{children}</ul>;
        },
        ol({ children }: { children?: ReactNode }) {
          return <ol className="list-decimal pl-6 my-2 space-y-1">{children}</ol>;
        },
        li({ children }: { children?: ReactNode }) {
          return <li className="text-[#d0d0e0]">{children}</li>;
        },
        h1({ children }: { children?: ReactNode }) {
          return <h1 className="text-xl font-bold text-[#e0e0e0] mt-4 mb-2">{children}</h1>;
        },
        h2({ children }: { children?: ReactNode }) {
          return <h2 className="text-lg font-bold text-[#e0e0e0] mt-3 mb-2">{children}</h2>;
        },
        h3({ children }: { children?: ReactNode }) {
          return <h3 className="text-base font-semibold text-[#e0e0e0] mt-3 mb-1">{children}</h3>;
        },
        p({ children }: { children?: ReactNode }) {
          return <p className="my-2">{children}</p>;
        },
        blockquote({ children }: { children?: ReactNode }) {
          return (
            <blockquote className="border-l-3 border-[#6366f1] pl-4 my-2 text-[#b0b0c8] italic">
              {children}
            </blockquote>
          );
        },
        table({ children }: { children?: ReactNode }) {
          return (
            <div className="overflow-x-auto my-3">
              <table className="border-collapse border border-[#3a3a5c] text-sm">
                {children}
              </table>
            </div>
          );
        },
        th({ children }: { children?: ReactNode }) {
          return (
            <th className="border border-[#3a3a5c] px-3 py-1.5 bg-[#1e1e3a] text-left font-semibold text-[#e0e0e0]">
              {children}
            </th>
          );
        },
        td({ children }: { children?: ReactNode }) {
          return (
            <td className="border border-[#3a3a5c] px-3 py-1.5">
              {children}
            </td>
          );
        },
        hr() {
          return <hr className="border-[#3a3a5c] my-4" />;
        },
      }}
    >
      {content}
    </Markdown>
  );
}


function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileCard({ fileName, fileSize, fileType }: { fileName: string; fileSize?: number; fileType?: string }) {
  const isImage = fileType?.startsWith("image/");
  const Icon = isImage ? Image : FileText;

  return (
    <div className="inline-flex items-center gap-2.5 px-3 py-2 mb-2 rounded-lg bg-[#1a1a36] border border-[#3a3a5c] max-w-xs">
      <Icon className="w-5 h-5 text-[#818cf8] shrink-0" />
      <div className="min-w-0">
        <p className="text-sm text-[#e0e0e0] truncate" title={fileName}>{fileName}</p>
        {fileSize != null && (
          <p className="text-xs text-[#6b6b8a]">{formatFileSize(fileSize)}</p>
        )}
      </div>
    </div>
  );
}

const STEP_LABELS: { status: string; label: string }[] = [
  { status: "uploaded", label: "Загружаю документ..." },
  { status: "parsing", label: "Распознаю текст..." },
  { status: "extracting", label: "Извлекаю показатели..." },
];

function DocumentProcessingProgress({ documentId }: { documentId: string }) {
  const entry = useChatStore((s) => s.documentProcessing[documentId]);
  if (!entry) return null;

  const currentIdx = STEP_LABELS.findIndex((s) => s.status === entry.status);

  return (
    <div className="flex flex-col gap-2 py-1">
      {STEP_LABELS.map((step, idx) => {
        const isActive = idx === currentIdx;
        const isDone = idx < currentIdx;

        return (
          <div key={step.status} className="flex items-center gap-2.5">
            {isActive ? (
              <Loader2 className="w-4 h-4 text-[#818cf8] animate-spin shrink-0" />
            ) : isDone ? (
              <Check className="w-4 h-4 text-[#2d8a6e] shrink-0" />
            ) : (
              <div className="w-4 h-4 rounded-full border border-[#3a3a5c] shrink-0" />
            )}
            <span
              className={`text-sm ${
                isActive
                  ? "text-[#e0e0e0]"
                  : isDone
                  ? "text-[#6b6b8a]"
                  : "text-[#4a4a6a]"
              }`}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}


function StatusBadgeInline({ status }: { status: string | null }) {
  switch (status) {
    case "normal":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-900/30 text-emerald-400 border border-emerald-800/30">
          <Minus className="w-2.5 h-2.5" /> Норма
        </span>
      );
    case "low":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-amber-900/30 text-amber-400 border border-amber-800/30">
          <ArrowDown className="w-2.5 h-2.5" /> Ниже нормы
        </span>
      );
    case "high":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-amber-900/30 text-amber-400 border border-amber-800/30">
          <ArrowUp className="w-2.5 h-2.5" /> Выше нормы
        </span>
      );
    case "critical":
      return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-red-900/30 text-red-400 border border-red-800/30">
          <AlertTriangle className="w-2.5 h-2.5" /> Критично
        </span>
      );
    default:
      return null;
  }
}

function BiomarkerResults({ biomarkers, documentId }: { biomarkers: Biomarker[]; documentId?: string }) {
  const selectDocument = useDocumentStore((s) => s.selectDocument);
  const total = (biomarkers || []).length;
  const abnormal = (biomarkers || []).filter(
    (b) => b.status === "low" || b.status === "high" || b.status === "critical"
  );

  return (
    <div className="space-y-3">
      {/* Summary line */}
      <p className="text-sm text-[#d0d0e0]">
        {"✅"} Найдено <strong>{total}</strong> биомаркеров
        {abnormal.length > 0 && (
          <>, <span className="text-amber-400 font-medium">{abnormal.length} за пределами нормы</span></>
        )}
      </p>

      {/* Abnormal biomarker cards */}
      {abnormal.length > 0 && (
        <div className="flex flex-col gap-2">
          {abnormal.map((b) => (
            <div
              key={b.id}
              className={`flex items-center justify-between gap-3 px-3 py-2 rounded-lg border ${
                b.status === "critical"
                  ? "bg-red-900/10 border-red-900/30"
                  : "bg-amber-900/10 border-amber-900/30"
              }`}
            >
              <div className="min-w-0">
                <p className="text-sm text-[#e0e0e0] font-medium truncate">{b.name}</p>
                <p className="text-xs text-[#6b6b8a]">
                  <span className="font-mono text-[#e0e0e0]">{b.value}</span>
                  {b.unit && <span> {b.unit}</span>}
                  {b.ref_range_text && <span> (норма: {b.ref_range_text})</span>}
                </p>
              </div>
              <StatusBadgeInline status={b.status} />
            </div>
          ))}
        </div>
      )}

      {/* Show all results button */}
      {documentId && (
        <button
          onClick={() => selectDocument(documentId)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-[#818cf8] hover:text-[#a5b4fc] hover:bg-[#2d2d5e] rounded-lg transition-colors border border-[#3a3a5c]"
        >
          Показать все результаты
          <ChevronRight className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

export default function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === "user";
  const docProcessingId = message.metadata?.document_processing;
  // Subscribe to store directly: only show progress if entry still exists in documentProcessing map
  const isDocProcessing = useChatStore((s) =>
    docProcessingId ? !!s.documentProcessing[docProcessingId] : false
  );

  return (
    <div className="py-5 px-4 md:px-6">
      <div className="max-w-3xl mx-auto flex gap-4">
        <div
          className={`w-7 h-7 rounded-full shrink-0 flex items-center justify-center ${
            isUser ? "bg-[#6366f1]" : "bg-[#2d8a6e]"
          }`}
        >
          {isUser ? (
            <User className="w-3.5 h-3.5 text-white" />
          ) : (
            <Bot className="w-3.5 h-3.5 text-white" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[#e0e0e0] mb-1.5">
            {isUser ? "You" : "BioCoach"}
          </p>
          {isUser ? (
            <div className="text-[#d0d0e0] text-[15px] leading-relaxed whitespace-pre-wrap break-words">
              {message.metadata?.file_name && (
                <FileCard
                  fileName={message.metadata.file_name}
                  fileSize={message.metadata.file_size}
                  fileType={message.metadata.file_type}
                />
              )}
              {message.content}
            </div>
          ) : isDocProcessing && docProcessingId ? (
            <DocumentProcessingProgress documentId={docProcessingId} />
          ) : message.metadata?.biomarkers ? (
            <BiomarkerResults
              biomarkers={message.metadata.biomarkers}
              documentId={message.metadata.document_id}
            />
          ) : (
            <div className="text-[#d0d0e0] text-[15px] leading-relaxed break-words">
              <MarkdownContent content={message.content} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
