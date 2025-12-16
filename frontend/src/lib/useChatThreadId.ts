'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSession } from 'next-auth/react';

const STORAGE_PREFIX = 'sealai:thread:';
const STORAGE_CURRENT = `${STORAGE_PREFIX}current`;

function makeIdentity(session: any): string {
  if (!session) return 'anon';
  const user = session.user || {};
  const sub = user.sub || user.id || user.userId || user.email || 'anon';
  const sid = session.sid || user.sid || session.session_state || user.session_state || '';
  return `${String(sub)}${sid ? `:${String(sid)}` : ''}`;
}

export function useChatThreadId(): string | null {
  const { data: session, status } = useSession();
  const [chatId, setChatId] = useState<string | null>(null);
  const identity = useMemo(() => {
    if (status !== 'authenticated') return null;
    return makeIdentity(session);
  }, [status, session]);
  const identityRef = useRef<string | null>(null);

  useEffect(() => {
    identityRef.current = identity;
  }, [identity]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    if (status !== 'authenticated' || !identity) {
      // clear previous session marker on logout / unauthenticated state
      const lastKey = sessionStorage.getItem(STORAGE_CURRENT);
      if (lastKey) sessionStorage.removeItem(lastKey);
      sessionStorage.removeItem(STORAGE_CURRENT);
      setChatId(null);
      return;
    }

    const storageKey = `${STORAGE_PREFIX}${identity}`;
    sessionStorage.setItem(STORAGE_CURRENT, storageKey);

    const existing = sessionStorage.getItem(storageKey);
    if (existing) {
      setChatId(existing);
      return;
    }

    const random = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    const newId = `thread-${random}`;
    sessionStorage.setItem(storageKey, newId);
    setChatId(newId);
  }, [status, identity]);

  return chatId;
}
