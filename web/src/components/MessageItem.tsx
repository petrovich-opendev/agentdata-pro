import { Bot, User, Copy, Check } from "lucide-react";
import { useState, useCallback, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types";

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

export default function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === "user";

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
              {message.content}
            </div>
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
