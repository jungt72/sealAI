'use client'

import React, { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'

// Nimmt jetzt ReactNode entgegen, aber reicht nur den String an ReactMarkdown weiter
export default function MarkdownMessage({ children }: { children: ReactNode }) {
  // Kinder in String konvertieren, falls nicht schon string
  let content = ''
  if (typeof children === 'string') {
    content = children
  } else if (Array.isArray(children)) {
    content = children.filter(Boolean).join('')
  } else if (typeof children === 'number') {
    content = String(children)
  }

  return (
    <div className="prose prose-neutral prose-sm sm:prose-base max-w-none text-gray-800 break-words leading-normal">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeHighlight]}
        components={{
          h1: ({ node, ...props }) => (
            <h1 className="text-2xl font-semibold mt-4 mb-2 leading-tight" {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 className="text-xl font-semibold mt-4 mb-2 leading-tight" {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 className="text-lg font-semibold mt-4 mb-2 leading-tight" {...props} />
          ),
          ul: ({ node, ...props }) => <ul className="list-disc ml-6 mb-2" {...props} />,
          ol: ({ node, ...props }) => <ol className="list-decimal ml-6 mb-2" {...props} />,
          li: ({ node, ...props }) => <li className="mb-1" {...props} />,
          blockquote: ({ node, ...props }) => (
            <blockquote className="border-l-4 border-blue-300 pl-4 italic text-gray-500 my-2" {...props} />
          ),
          code(props) {
            const { inline, className, children, ...rest } = props as {
              inline?: boolean
              className?: string
              children?: ReactNode
            }
            if (inline) {
              return (
                <code className="bg-gray-100 px-1 rounded text-[90%] font-mono" {...rest}>
                  {children}
                </code>
              )
            }
            return (
              <pre className="rounded-lg bg-gray-900 text-gray-100 p-4 overflow-x-auto text-sm my-4">
                <code className={className} {...rest}>
                  {children}
                </code>
              </pre>
            )
          },
          strong: ({ node, ...props }) => (
            <strong className="font-semibold text-gray-900" {...props} />
          ),
          p: ({ node, ...props }) => <p className="my-2" {...props} />,
          a: ({ node, ...props }) => (
            <a className="text-blue-600 underline break-all" target="_blank" rel="noopener noreferrer" {...props} />
          ),
          hr: () => <hr className="my-4 border-gray-300" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
