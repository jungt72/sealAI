'use client';

import React, { ReactNode, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import '@/styles/chat-markdown.css';

function CodeBlock({
  inline,
  className,
  children,
  ...rest
}: {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const [copied, setCopied] = useState(false);

  if (inline) {
    return (
      <code className="cm-inline" {...rest}>
        {children}
      </code>
    );
  }

  const text =
    typeof children === 'string'
      ? children
      : Array.isArray(children)
      ? children.join('')
      : String(children ?? '');

  const match = /language-([\w-]+)/.exec(className || '');
  const lang = (match?.[1] || 'text').toLowerCase();

  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1100);
    } catch {}
  };

  return (
    <div className="cm-codeblock">
      <div className="cm-codeblock__toolbar">
        <span className="cm-lang">{lang}</span>
        <button className="cm-copy" onClick={doCopy} type="button">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="cm-pre">
        <code className={`language-${lang}`} {...rest}>
          {text}
        </code>
      </pre>
    </div>
  );
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
  // 1) Rohtext ermitteln
  const raw =
    typeof children === 'string'
      ? children
      : Array.isArray(children)
      ? children.filter(Boolean).join('')
      : String(children ?? '');

  // 2) Nur OPTISCH vornweg „…denke nach…“ entfernen (u2026 = Ellipse …)
  const content = raw.replace(
    /^\s*(?:\u2026|\.)*\s*denke\s*nach(?:\s*(?:\u2026|\.))*\s*[:\-–]?\s*/i,
    ''
  );

  const toneClass = isTool ? 'cm-tool' : isUser ? 'cm-user' : 'cm-assistant';

  return (
    <div className={`chat-markdown ${toneClass}`} aria-live="polite">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[]}
        components={{
          h1: (p) => <h1 className="cm-h1" {...p} />,
          h2: (p) => <h2 className="cm-h2" {...p} />,
          h3: (p) => <h3 className="cm-h3" {...p} />,
          h4: (p) => <h4 className="cm-h4" {...p} />,
          p: ({ node, ...props }) => <p className="cm-p" {...props} />,
          a: ({ node, ...props }) => <a className="cm-a" target="_blank" rel="noreferrer" {...props} />,
          ul: (p) => <ul className="cm-ul" {...p} />,
          ol: (p) => <ol className="cm-ol" {...p} />,
          li: (p) => <li className="cm-li" {...p} />,
          blockquote: (p) => <blockquote className="cm-quote" {...p} />,
          hr: () => <hr className="cm-hr" />,
          table: (p) => (
            <div className="cm-tablewrap">
              <table className="cm-table" {...p} />
            </div>
          ),
          thead: (p) => <thead className="cm-thead" {...p} />,
          th: (p) => <th className="cm-th" {...p} />,
          td: (p) => <td className="cm-td" {...p} />,
          img: (p) => <img className="cm-img" {...p} />,
          code: CodeBlock,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
