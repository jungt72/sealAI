'use client';

import { useRef, useEffect, useState } from 'react';
import { useSession } from 'next-auth/react';
import clsx from 'clsx';
import { ArrowUpIcon } from '@heroicons/react/24/solid';

import MarkdownMessage from './MarkdownMessage';
import { useChatWs }    from '@/lib/useChatWs';

export default function Chat() {
  const { data: session } = useSession();
  const accessToken       = session?.accessToken as string | undefined;
  const { connected, messages, send } = useChatWs(accessToken);
  const [input, setInput]  = useState('');
  const endRef             = useRef<HTMLDivElement>(null);

  // Auto-Scroll
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col h-full w-full">
      {/* Chat history */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.map((m, i) => (
          <div
            key={i}
            className={clsx(
              'mb-3 max-w-[80%] whitespace-pre-wrap',
              m.role === 'user' ? 'self-end text-right' : 'self-start text-left'
            )}
          >
            <MarkdownMessage>{m.content}</MarkdownMessage>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={e => {
          e.preventDefault();
          send(input);
          setInput('');
        }}
        className="border-t p-4 flex items-center gap-2"
      >
        <textarea
          rows={1}
          className="flex-1 resize-none outline-none"
          placeholder="Nachricht schreiben …"
          value={input}
          onChange={e => setInput(e.target.value)}
        />
        <button
          type="submit"
          disabled={!input.trim() || !connected}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40
                     text-white rounded-full h-10 w-10 flex items-center justify-center"
        >
          <ArrowUpIcon className="h-5 w-5" />
        </button>
      </form>
    </div>
  );
}
