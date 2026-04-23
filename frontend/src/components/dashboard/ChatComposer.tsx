"use client";

import React, { useEffect, useRef, useState } from "react";
import { Paperclip, SendHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  onSend: (message: string) => void;
  isLoading?: boolean;
  autoFocus?: boolean;
  externalValue?: string | null;
}

export default function ChatComposer({ onSend, isLoading, autoFocus, externalValue }: ChatComposerProps) {
  const [message, setMessage] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (externalValue !== undefined && externalValue !== null) {
      setMessage(externalValue);
      textareaRef.current?.focus();
    }
  }, [externalValue]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 220)}px`;
    }
  }, [message]);

  const handleSubmit = (event?: React.FormEvent) => {
    event?.preventDefault();
    const trimmed = message.trim();
    if (trimmed && !isLoading) {
      onSend(trimmed);
      setMessage("");
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const canSend = Boolean(message.trim()) && !isLoading;

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full rounded-lg border border-slate-200 bg-white p-2 shadow-sm transition-colors focus-within:border-seal-blue/40 focus-within:shadow-md"
    >
      <div className="flex items-end gap-2">
        <button
          type="button"
          title="Anhang hinzufügen"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-950"
        >
          <Paperclip size={18} />
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="PTFE-RWDR Fall, Medium, Druck, Temperatur oder Ausfallbild beschreiben..."
          className="max-h-[220px] min-h-10 flex-1 resize-none bg-transparent px-1 py-2.5 text-[15px] leading-6 text-slate-950 placeholder:text-slate-400 focus:outline-none"
          disabled={isLoading}
          autoFocus={autoFocus}
        />

        <button
          type="submit"
          title="Senden"
          disabled={!canSend}
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-md transition-colors",
            canSend
              ? "bg-seal-blue text-white hover:bg-[#0a2e68]"
              : "cursor-not-allowed bg-slate-100 text-slate-400",
          )}
        >
          <SendHorizontal size={18} />
        </button>
      </div>
    </form>
  );
}
