'use client';

import React, { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm      from 'remark-gfm';
import rehypeRaw      from 'rehype-raw';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';

interface CodeProps {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
}

export default function MarkdownMessage({
  children,
  isUser,
  isTool,
}: {
  children: ReactNode;
  isUser?: boolean;
  isTool?: boolean;
}) {
  const content =
    typeof children === 'string'
      ? children
      : Array.isArray(children)
      ? children.filter(Boolean).join('')
      : String(children);

  /* Tool‑Blöcke in Monospace, sonst normal */
  const baseClass = isTool
    ? 'font-mono text-[15px]'
    : isUser
    ? 'font-medium text-gray-900'
    : 'text-gray-800';

  return (
    <div
      className={`markdown-body break-words ${baseClass}`}
      style={{ minWidth: 0, overflowWrap: 'anywhere' }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeHighlight]}
        components={{
          p: ({ node, ...props }) => (
            <p className="my-0.5 leading-relaxed" {...props} />
          ),
          code: (props: CodeProps) => {
            const { inline, className, children, ...rest } = props;
            return inline ? (
              <code
                className="bg-gray-100 px-1 rounded text-[90%] font-mono"
                {...rest}
              >
                {children}
              </code>
            ) : (
              <pre className="rounded-lg bg-gray-900 text-gray-100 p-3 overflow-x-auto text-sm my-2">
                <code className={className} {...rest}>
                  {children}
                </code>
              </pre>
            );
          },
          /* … alle übrigen Überschreibungen bleiben unverändert … */
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
