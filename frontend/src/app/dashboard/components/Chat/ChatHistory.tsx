'use client';

import MarkdownMessage from './MarkdownMessage';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

/* -------------------------------------------------
   ChatHistory – optimiertes Spacing & max‑Breite
--------------------------------------------------*/
export default function ChatHistory({ messages }: { messages: Message[] }) {
  return (
    <div className="flex flex-col gap-7 w-full max-w-3xl mx-auto pb-4 scroll-mt-[72px]">
      {messages.map((m, i) => {
        const isUser = m.role === 'user';
        return (
          <div
            key={i}
            className={isUser ? 'flex justify-end' : 'flex justify-start'}
          >
            <div
              className={[
                'px-4 py-2 whitespace-pre-line leading-relaxed transition-all duration-200',
                isUser
                  ? 'max-w-[70%] bg-[#f0f4f9] rounded-2xl border border-gray-200'
                  : 'w-full'
              ].join(' ')}
            >
              <MarkdownMessage isUser={isUser}>{m.content}</MarkdownMessage>
            </div>
          </div>
        );
      })}
      <div id="chat-end" />
    </div>
  );
}
