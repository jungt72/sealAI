'use client';

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'sealai:consent.optin';
const EVENT_KEY = 'sealai:consent:event';

export function useConsentPreference(defaultValue = false): [boolean, (next: boolean) => void] {
  const [consent, setConsent] = useState<boolean>(() => defaultValue);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored != null) {
      setConsent(stored === '1');
    }
    const storageHandler = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY && event.newValue != null) {
        setConsent(event.newValue === '1');
      }
    };
    const customHandler = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail;
      if (typeof detail === 'boolean') setConsent(detail);
    };
    window.addEventListener('storage', storageHandler);
    window.addEventListener(EVENT_KEY, customHandler as EventListener);
    return () => {
      window.removeEventListener('storage', storageHandler);
      window.removeEventListener(EVENT_KEY, customHandler as EventListener);
    };
  }, []);

  const updateConsent = useCallback(
    (next: boolean) => {
      setConsent(next);
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
        window.dispatchEvent(new CustomEvent(EVENT_KEY, { detail: next }));
      }
    },
    [],
  );

  return [consent, updateConsent];
}

