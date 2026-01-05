// frontend/src/app/dashboard/components/Chat/ChatHistory.tsx
'use client';

import React, { memo } from 'react';
import type { Message } from '@/types/chat';
import MarkdownMessage from './MarkdownMessage';

type Props = {
  messages: Message[];
  className?: string;
};

function ChatHistoryBase({ messages, className }: Props) {
  if (!messages || messages.length === 0) return null;

  return (
    <div className={className}>
      <div className="w-full max-w-[768px] mx-auto px-4 py-4 space-y-6">
        {messages.map((m, i) => {
          const isUser = m.role === 'user';
          // >>> stabile Keys: NICHT vom (sich ändernden) Inhalt ableiten!
          const key = `m-${i}-${m.role}`;

          return (
            <div key={key} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={[
                  'max-w-[680px]',
                  'rounded-2xl',
                  'px-4 py-3',
                  'shadow-sm',
                  isUser
                    ? 'bg-blue-600 text-white cm-user'
                    : 'bg-white text-gray-900 cm-assistant',
                ].join(' ')}
              >
                {isUser ? (
                  <div className="whitespace-pre-wrap break-words leading-relaxed">
                    {m.content}
                  </div>
                ) : (
                  <MarkdownMessage>{m.content || ''}</MarkdownMessage>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ChatHistory = memo(ChatHistoryBase);
export default ChatHistory;
