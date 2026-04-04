"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { normalizeAssistantMarkdown } from "@/lib/assistantText";

export default function MarkdownRenderer({ children }: { children: string }) {
  const content = normalizeAssistantMarkdown(children);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      className="sealai-markdown break-words"
      components={{
        p: ({ node, ...props }) => <p className="sealai-markdown-paragraph" {...props} />,
        a: ({ node, ...props }) => <a className="sealai-markdown-link" {...props} />,
        ul: ({ node, ...props }) => (
          <ul className="sealai-markdown-list sealai-markdown-list-disc" {...props} />
        ),
        ol: ({ node, ...props }) => (
          <ol className="sealai-markdown-list sealai-markdown-list-decimal" {...props} />
        ),
        li: ({ node, ...props }) => <li className="sealai-markdown-list-item" {...props} />,
        h1: ({ node, ...props }) => <h1 className="sealai-markdown-h1" {...props} />,
        h2: ({ node, ...props }) => <h2 className="sealai-markdown-h2" {...props} />,
        h3: ({ node, ...props }) => <h3 className="sealai-markdown-h3" {...props} />,
        strong: ({ node, ...props }) => (
          <strong className="font-semibold text-slate-900" {...props} />
        ),
        em: ({ node, ...props }) => <em className="italic text-slate-700" {...props} />,
        hr: ({ node, ...props }) => <hr className="my-6 border-slate-200" {...props} />,
        table: ({ node, ...props }) => (
          <div className="mb-6 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm" {...props} />
          </div>
        ),
        thead: ({ node, ...props }) => (
          <thead className="border-b border-slate-200 bg-slate-50 font-semibold" {...props} />
        ),
        th: ({ node, ...props }) => <th className="px-4 py-3" {...props} />,
        td: ({ node, ...props }) => (
          <td className="align-top border-b border-slate-100 px-4 py-3 last:border-0" {...props} />
        ),
        code: ({ node, inline, ...props }: any) =>
          inline ? (
            <code
              className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[13px] text-rose-600"
              {...props}
            />
          ) : (
            <code
              className="block overflow-x-auto rounded-2xl border border-slate-200 bg-slate-950 p-4 font-mono text-[13px] text-slate-100 shadow-inner"
              {...props}
            />
          ),
        blockquote: ({ node, ...props }) => (
          <blockquote
            className="my-6 border-l-4 border-sky-300 bg-sky-50 px-4 py-3 text-slate-700"
            {...props}
          />
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
