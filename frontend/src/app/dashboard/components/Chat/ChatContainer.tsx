'use client';

import { useSession } from 'next-auth/react';
import { useChatWs } from '@/lib/useChatWs';
import ChatHistory from './ChatHistory';
import ChatInput from './ChatInput';
import { useEffect, useRef, useState } from 'react';

export default function ChatContainer() {
  const { data: session } = useSession();
  const accessToken = session?.accessToken as string | undefined;
  const { connected, messages, send } = useChatWs(accessToken);

  const [inputValue, setInputValue] = useState('');
  const [hasStarted, setHasStarted] = useState(false);

  // Debug-Info für Development-Umgebung
  if (process.env.NODE_ENV === 'development') {
    // eslint-disable-next-line no-console
    console.log('[ChatContainer] accessToken:', accessToken, 'session:', session);
  }

  // Der Ref gehört an das ENDE des Scrollbereichs!
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length > 0 && scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [messages]);

  const firstName = session?.user?.name?.split(' ')[0] || undefined;
  const isInitial = messages.length === 0 && !hasStarted;

  if (isInitial) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full">
        <div className="flex flex-col items-center justify-center w-full max-w-[768px]">
          <div className="text-2xl md:text-3xl font-bold text-gray-800 text-center leading-tight select-none">
            Willkommen zurück, {firstName}!
          </div>
          <div className="text-base md:text-lg text-gray-500 mb-10 text-center leading-snug font-medium select-none">
            Schön, dass du hier bist.
          </div>
          <div className="w-full">
            <ChatInput
              value={inputValue}
              setValue={setInputValue}
              onSend={msg => {
                if (!msg.trim()) return;
                send(msg.trim());
                setHasStarted(true);
                setInputValue('');
              }}
              disabled={!connected}
            />
          </div>
        </div>
      </div>
    );
  }

  // *** Die zentrale Scroll-Box ***
  return (
    <div className="flex flex-col h-full w-full bg-transparent relative">
      {/* 1. Chatverlauf, Scrollbox, Breite, Padding */}
      <div className="flex-1 flex justify-center overflow-hidden">
        <div
          className="w-full max-w-[768px] mx-auto flex flex-col h-full"
        >
          <div className="flex-1 overflow-y-auto w-full pb-36" /* 144px Abstand! */
               style={{ minHeight: 0 }}>
            {messages.length > 0 && <ChatHistory messages={messages} />}
            <div ref={scrollRef} />
          </div>
          {/* 2. Eingabefeld sticky/unten */}
          <div className="sticky bottom-0 left-0 right-0 z-20 flex justify-center bg-transparent pb-7 w-full">
            <div className="w-full max-w-[768px] pointer-events-auto">
              <ChatInput
                value={inputValue}
                setValue={setInputValue}
                onSend={msg => {
                  if (!msg.trim()) return;
                  send(msg.trim());
                  setHasStarted(true);
                  setInputValue('');
                }}
                disabled={!connected}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
