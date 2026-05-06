"use client";

import React, { useEffect, useRef, useState } from "react";
import { Paperclip, SendHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  onSend: (message: string) => void;
  onUpload?: (file: File) => void;
  isLoading?: boolean;
  isUploading?: boolean;
  autoFocus?: boolean;
  externalValue?: string | null;
  placeholder?: string;
}

export default function ChatComposer({
  onSend,
  onUpload,
  isLoading,
  isUploading,
  autoFocus,
  externalValue,
  placeholder = "Beschreibe deine Dichtungssituation ...",
}: ChatComposerProps) {
  const [draft, setDraft] = useState(() => ({
    lastExternalValue: externalValue ?? null,
    message: externalValue ?? "",
  }));
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const message = draft.message;

  if (draft.lastExternalValue !== (externalValue ?? null)) {
    setDraft((current) => ({
      lastExternalValue: externalValue ?? null,
      message: externalValue ?? current.message,
    }));
  }

  useEffect(() => {
    if (externalValue !== undefined && externalValue !== null) {
      textareaRef.current?.focus();
    }
  }, [externalValue]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 220)}px`;
    }
  }, [message]);

  const setMessage = (nextMessage: string) => {
    setDraft((current) => ({
      ...current,
      message: nextMessage,
    }));
  };

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

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file && onUpload && !isLoading && !isUploading) {
      onUpload(file);
    }
  };

  const canSend = Boolean(message.trim()) && !isLoading;
  const canUpload = Boolean(onUpload) && !isLoading && !isUploading;

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full rounded-[16px] border border-[#D1D5DB] bg-white p-2 shadow-[0_4px_18px_rgba(15,23,42,0.06)] transition-colors focus-within:border-[#0B57D0] focus-within:shadow-[0_8px_24px_rgba(15,23,42,0.10)]"
    >
      <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.txt,.md,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={handleFileChange}
          disabled={!canUpload}
        />
        <button
          type="button"
          title="Anhang hinzufügen"
          onClick={() => fileInputRef.current?.click()}
          disabled={!canUpload}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Paperclip size={18} />
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
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
              ? "bg-[#0B57D0] text-white hover:bg-[#0847AD]"
              : "cursor-not-allowed bg-slate-100 text-slate-400",
          )}
        >
          <SendHorizontal size={18} />
        </button>
      </div>
    </form>
  );
}
