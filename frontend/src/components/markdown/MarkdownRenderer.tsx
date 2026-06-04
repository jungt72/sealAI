"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Check, Copy } from "lucide-react";

import "katex/dist/katex.min.css";
import { normalizeAssistantMarkdown } from "@/lib/assistantText";
import { cn } from "@/lib/utils";

interface CodeBlockProps {
  language: string;
  value: string;
}

const CodeBlock = ({ language, value }: CodeBlockProps) => {
  const [copied, setCopied] = useState(false);

  const onCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="group relative my-6 overflow-hidden rounded-xl border border-border bg-[#1E1F20]">
      <div className="flex items-center justify-between bg-[#2D2E30] px-4 py-2 text-xs text-muted-foreground">
        <span className="font-mono uppercase tracking-wider">{language || "code"}</span>
        <button
          onClick={onCopy}
          className="flex items-center gap-1.5 transition-colors hover:text-foreground"
        >
          {copied ? (
            <>
              <Check size={14} className="text-emerald-500" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy size={14} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: "1.25rem",
          fontSize: "0.875rem",
          lineHeight: "1.6",
          background: "transparent",
        }}
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
};

interface MarkdownRendererProps {
  children: string;
  className?: string;
  variant?: "default" | "chat";
}

export default function MarkdownRenderer({ children, className, variant = "default" }: MarkdownRendererProps) {
  const content = normalizeAssistantMarkdown(children);
  const isChat = variant === "chat";

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      className={cn(
        "seal-markdown break-words text-[#1F1F1F]",
        isChat ? "text-[16px] leading-[1.625]" : "text-[16px] leading-relaxed",
        className,
      )}
      components={{
        p: ({ node, ...props }) => <p className={cn(isChat ? "mb-2 last:mb-0" : "mb-4 last:mb-0")} {...props} />,
        a: ({ node, ...props }) => (
          <a
            className="text-seal-blue no-underline hover:underline font-medium"
            target="_blank"
            rel="noopener noreferrer"
            {...props}
          />
        ),
        ul: ({ node, ...props }) => (
          <ul className={cn("list-disc", isChat ? "mb-2 ml-4 space-y-1" : "mb-4 ml-6 space-y-2")} {...props} />
        ),
        ol: ({ node, ...props }) => (
          <ol className={cn("list-decimal", isChat ? "mb-2 ml-4 space-y-1" : "mb-4 ml-6 space-y-2")} {...props} />
        ),
        li: ({ node, ...props }) => <li className={cn(isChat ? "pl-0.5" : "pl-1")} {...props} />,
        h1: ({ node, ...props }) => (
          <h1
            className={cn(
              "font-bold tracking-tight",
              isChat ? "mb-2 mt-1 text-[16px]" : "mb-6 mt-8 text-2xl",
            )}
            {...props}
          />
        ),
        h2: ({ node, ...props }) => (
          <h2
            className={cn(
              "font-bold tracking-tight",
              isChat ? "mb-2 mt-1 text-[16px]" : "mb-4 mt-6 text-xl",
            )}
            {...props}
          />
        ),
        h3: ({ node, ...props }) => (
          <h3
            className={cn(
              "font-bold tracking-tight",
              isChat ? "mb-1.5 mt-1 text-[16px]" : "mb-3 mt-5 text-lg",
            )}
            {...props}
          />
        ),
        strong: ({ node, ...props }) => <strong className="font-semibold text-[#1F1F1F]" {...props} />,
        hr: ({ node, ...props }) => <hr className="my-8 border-border" {...props} />,
        blockquote: ({ node, ...props }) => (
          <blockquote
            className={cn(
              "border-l-4 border-muted-foreground/20 italic text-muted-foreground",
              isChat ? "my-3 px-3 py-1" : "my-6 px-4 py-1",
            )}
            {...props}
          />
        ),
        table: ({ node, ...props }) => (
          <div className="my-6 overflow-x-auto rounded-xl border border-border">
            <table className="w-full border-collapse text-left text-sm" {...props} />
          </div>
        ),
        thead: ({ node, ...props }) => <thead className="bg-muted" {...props} />,
        th: ({ node, ...props }) => <th className="border-b border-border px-4 py-3 font-bold" {...props} />,
        td: ({ node, ...props }) => <td className="border-b border-border px-4 py-3 last:border-0" {...props} />,
        code: ({ node, inline, className, children, ...props }: any) => {
          const match = /language-(\w+)/.exec(className || "");
          const value = String(children).replace(/\n$/, "");

          if (!inline && match) {
            return <CodeBlock language={match[1]} value={value} />;
          }

          if (!inline && value.includes("\n")) {
            return <CodeBlock language="text" value={value} />;
          }

          return (
            <code
              className="rounded bg-muted px-1.5 py-0.5 font-mono text-[13px] font-medium text-[#D31B5E]"
              {...props}
            >
              {children}
            </code>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
