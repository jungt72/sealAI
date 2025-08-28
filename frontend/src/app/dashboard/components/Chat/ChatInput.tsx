'use client';

import React, { useRef, useEffect, useCallback } from 'react';

interface ChatInputProps {
  value: string;
  setValue: (v: string) => void;
  onSend?: (value: string) => void;
  onStop?: () => void;
  /** Bedeutet: Senden-Button sperren – NICHT das Tippen */
  disabled?: boolean;
  streaming?: boolean;
  placeholder?: string;
}

/**
 * ChatInput – tippen immer möglich, auch offline.
 * Nur Senden/Stop werden je nach Status deaktiviert.
 */
export default function ChatInput({
  value,
  setValue,
  onSend,
  onStop,
  disabled = false,   // -> sperrt NUR Buttons
  streaming = false,  // -> sperrt Textarea (während Stream)
  placeholder = 'Was möchtest du wissen?',
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // --- Autosize Textarea, max 4 Zeilen (~104px) ---
  const autosize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const next = Math.min(el.scrollHeight, 104);
    el.style.height = `${next}px`;
  }, []);

  useEffect(() => {
    autosize();
  }, [value, autosize]);

  const focusTextarea = useCallback(() => {
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, []);

  const doSend = useCallback(() => {
    const text = value.trim();
    if (!onSend || !text) return;
    onSend(text);
    setValue('');
    focusTextarea();
  }, [onSend, setValue, value, focusTextarea]);

  const doStop = useCallback(() => {
    if (onStop) onStop();
    focusTextarea();
  }, [onStop, focusTextarea]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Während Streaming nicht senden
    if (streaming) return;

    // Shift+Enter = Zeilenumbruch
    if (e.key === 'Enter' && e.shiftKey) return;

    // Enter / Ctrl+Enter senden – aber nur, wenn Buttons nicht gesperrt
    if ((e.key === 'Enter' && !e.shiftKey) || (e.key === 'Enter' && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      if (!disabled) doSend();
    }
  };

  const canSend = !disabled && !streaming && value.trim().length > 0;
  const canStop = !disabled && streaming;

  return (
    <div
      className="flex flex-col w-full items-center"
      style={{ maxWidth: '768px', minWidth: '320px', width: '100%' }}
    >
      <div
        className={[
          'bg-white rounded-3xl',
          'border border-gray-200',
          'shadow-[0_8px_28px_rgba(60,80,120,0.10)]',
          'flex flex-col justify-between',
          'transition-all',
          // kompaktere Innenabstände
          'px-5 pt-4 pb-3',
          streaming ? 'opacity-90' : '',
        ].join(' ')}
        style={{ minHeight: '92px', maxWidth: '768px', width: '100%' }}
      >
        {/* Eingabe (Textarea): nur während Streaming gesperrt */}
        <textarea
          ref={textareaRef}
          className={[
            'w-full resize-none border-none outline-none bg-transparent',
            'text-[0.97rem] leading-[1.5]',
            'text-gray-900 placeholder-gray-400',
            'min-h-[26px] max-h-[104px]',
            'pr-2 pl-2',
            'transition',
            'scrollbar-thin',
            'overflow-y-auto',
            streaming ? 'cursor-not-allowed' : '',
          ].join(' ')}
          rows={1}
          maxLength={3000}
          autoFocus
          value={value}
          disabled={streaming}             // <-- wichtig: NICHT mehr „disabled || streaming“
          placeholder={
            disabled ? 'Offline – du kannst tippen, Senden ist deaktiviert' : placeholder
          }
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Chat-Eingabe"
          aria-disabled={streaming}
          style={{
            borderRadius: 0,
            fontSize: '0.97rem',
            background: 'transparent',
            minHeight: '26px',
            maxHeight: '104px',
            boxSizing: 'border-box',
            paddingTop: 2,
            paddingBottom: 2,
            paddingLeft: 6,
            paddingRight: 10,
          }}
        />

        {/* Bottom Row */}
        <div className="flex flex-row justify-between items-center mt-2">
          {/* Platzhalter-Button links */}
          <button
            type="button"
            tabIndex={-1}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full text-[11.5px] bg-gray-100 text-gray-700 font-normal select-none shadow-sm hover:bg-gray-200 transition"
            disabled
            aria-disabled="true"
            title="Kompetenz wählen (Demo)"
          >
            🧑‍💼 Kompetenz wählen [Demo]
          </button>

          {/* Rechts: Stop- oder Send-Button */}
          {streaming ? (
            <button
              type="button"
              onClick={doStop}
              disabled={!canStop}
              className={[
                'flex items-center justify-center',
                'h-8 px-3 ml-2',
                'rounded-full',
                'shadow',
                'transition',
                canStop
                  ? 'bg-red-500 hover:bg-red-600 text-white'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed',
              ].join(' ')}
              style={{ zIndex: 20 }}
              aria-label="Stopp"
              title="Stopp"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              type="button"
              onClick={doSend}
              disabled={!canSend}
              className={[
                'flex items-center justify-center',
                'h-8 w-8 ml-2',
                'rounded-full',
                'shadow',
                'transition',
                canSend
                  ? 'bg-[#343541] hover:bg-[#202123] text-white'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed',
              ].join(' ')}
              style={{ zIndex: 20 }}
              aria-label="Senden"
              title={disabled ? 'Offline – Senden deaktiviert' : 'Senden (Enter)'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* kleine Shortcut-Hilfe */}
      <div className="mt-1.5 text-[11px] text-gray-500">
        {disabled ? 'Offline – du kannst schon tippen; Senden ist aus.' : 'Enter: senden · Shift+Enter: neue Zeile · Strg/⌘+Enter: senden'}
      </div>
    </div>
  );
}
