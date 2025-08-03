'use client';

import React, { useRef, useEffect } from 'react';

interface ChatInputProps {
  value: string;
  setValue: (v: string) => void;
  onSend?: (value: string) => void;
  disabled?: boolean;
}

export default function ChatInput({
  value,
  setValue,
  onSend,
  disabled,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Autosize Textarea, max 4 Zeilen
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 104)}px`;
    }
  }, [value]);

  const handleSend = () => {
    if (onSend && value.trim()) {
      onSend(value.trim());
      setValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className="flex flex-col w-full items-center"
      style={{
        maxWidth: '768px',
        minWidth: '320px',
        width: '100%',
      }}
    >
      <div
        className={`
          bg-white rounded-[32px]
          border border-gray-200
          shadow-[0_8px_32px_0_rgba(60,80,120,0.10)]
          flex flex-col justify-between
          transition-all
          px-6 pt-5 pb-4
        `}
        style={{
          minHeight: '104px',
          maxWidth: '768px',
          width: '100%',
        }}
      >
        {/* Eingabe (Textarea) */}
        <textarea
          ref={textareaRef}
          className="
            w-full resize-none border-none outline-none
            bg-transparent text-base text-gray-900 placeholder-gray-400
            min-h-[28px] max-h-[104px]
            leading-[1.4]
            pr-3 pl-2
            transition
            scrollbar-thin
            overflow-y-auto
          "
          rows={1}
          maxLength={3000}
          autoFocus
          value={value}
          disabled={disabled}
          placeholder="Was möchtest du wissen?"
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          style={{
            borderRadius: 0, // keine Rundung mehr am Textarea selbst
            fontSize: '16px',
            background: 'transparent',
            minHeight: '28px',
            maxHeight: '104px',
            boxSizing: 'border-box',
            paddingTop: 2,
            paddingBottom: 2,
            paddingLeft: 2,
            paddingRight: 12,
          }}
        />
        {/* Button Row unten */}
        <div className="flex flex-row justify-between items-center mt-3">
          {/* Kompetenzbutton unten links */}
          <button
            type="button"
            tabIndex={-1}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full text-xs bg-gray-100 text-gray-700 font-normal select-none shadow-sm hover:bg-gray-200 transition"
            disabled
          >
            🧑‍💼 Kompetenz wählen [Demo]
          </button>
          {/* Senden-Button unten rechts */}
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || !value.trim()}
            className={`
              flex items-center justify-center
              h-9 w-9 ml-2
              rounded-full
              shadow
              transition
              ${
                disabled || !value.trim()
                  ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  : 'bg-[#343541] hover:bg-[#202123] text-white'
              }
            `}
            style={{
              zIndex: 20,
            }}
            aria-label="Senden"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none"
              viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
