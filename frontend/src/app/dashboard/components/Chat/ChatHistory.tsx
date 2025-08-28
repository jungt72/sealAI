'use client';

import MarkdownMessage from './MarkdownMessage';
import type { Message } from '@/types/chat';

/**
 * Kompaktere, grok/ChatGPT-nahe Bubble-Abstände.
 */
export default function ChatHistory({ messages }: { messages: Message[] }) {
  return (
    <div className="flex flex-col gap-5 w-full max-w-[720px] mx-auto pb-3 scroll-mt-[64px]">
      {messages.map((m, i) => {
        const isUser = m.role === 'user';
        const isSystem = m.role === 'system';

        return (
          <div
            key={i}
            className={isUser ? 'flex justify-end' : 'flex justify-start'}
          >
            <div
              className={[
                'px-3 py-2 leading-[1.45] transition-all duration-150',
                isUser
                  ? 'max-w-[66%] bg-[#f6f8fc] rounded-2xl border border-gray-200 shadow-sm'
                  : 'w-full',
                isSystem ? 'opacity-80 italic' : '',
              ].join(' ')}
            >
              <MarkdownMessage isUser={isUser} isTool={false}>
                {m.content}
              </MarkdownMessage>
            </div>
          </div>
        );
      })}
      <div id="chat-end" />
    </div>
  );
}
