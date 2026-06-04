"use client";

import React, { useEffect, useRef, useState } from "react";
import { AudioLines, ChevronDown, Mic, Plus, SendHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  onSend: (message: string) => void;
  onUpload?: (file: File) => void;
  isLoading?: boolean;
  isUploading?: boolean;
  autoFocus?: boolean;
  externalValue?: string | null;
  placeholder?: string;
  variant?: "default" | "hero";
}

export default function ChatComposer({
  onSend,
  onUpload,
  isLoading,
  isUploading,
  autoFocus,
  externalValue,
  placeholder = "Was möchtest du wissen",
  variant = "default",
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
  const isHero = variant === "hero";
  const uploadButton = (
    <button
      type="button"
      title="Anhang hinzufügen"
      aria-label="Anhang hinzufügen"
      onClick={() => fileInputRef.current?.click()}
      disabled={!canUpload}
      className={cn(
        "flex h-10 w-10 shrink-0 items-center justify-center text-[#64748B] transition-colors hover:bg-white/55 hover:text-[#1F2933] disabled:cursor-not-allowed disabled:opacity-50",
        "rounded-full",
      )}
    >
      <Plus size={22} strokeWidth={1.9} />
    </button>
  );
  const modeButton = (
    <button
      type="button"
      title="Antwortlänge"
      aria-label="Antwortlänge"
      className={cn(
        "hidden h-10 shrink-0 items-center gap-1 px-3 text-sm font-medium text-[#1F2933] transition-colors hover:bg-white/55 sm:inline-flex",
        "rounded-full",
      )}
    >
      <span>Länger</span>
      <ChevronDown size={15} />
    </button>
  );
  const micButton = (
    <button
      type="button"
      title="Spracheingabe"
      aria-label="Spracheingabe"
      className={cn(
        "hidden h-10 w-10 shrink-0 items-center justify-center text-[#1F2933] transition-colors hover:bg-white/55 sm:inline-flex",
        "rounded-full",
      )}
    >
      <Mic size={18} />
    </button>
  );
  const sendButton = (
    <button
      type="submit"
      title={canSend ? "Senden" : "Sprachmodus"}
      aria-label={canSend ? "Senden" : "Sprachmodus"}
      disabled={!canSend}
      className={cn(
        "flex h-10 w-10 shrink-0 items-center justify-center transition-colors",
        "rounded-full",
        canSend
          ? "bg-seal-blue text-white hover:opacity-90"
          : "cursor-not-allowed bg-white/45 text-[#94A3B8]",
      )}
    >
      {canSend ? <SendHorizontal size={18} /> : <AudioLines size={18} />}
    </button>
  );

  return (
    <form
      onSubmit={handleSubmit}
      data-private
      className={cn(
        "w-full border border-white/70 bg-white/54 shadow-[0_18px_55px_rgba(15,23,42,0.10),inset_0_1px_0_rgba(255,255,255,0.86)] backdrop-blur-xl",
        "rounded-full px-4 py-2.5 ring-1 ring-[#CBD5E1]/45",
      )}
    >
      <div className="flex items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.txt,.md,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={handleFileChange}
          disabled={!canUpload}
        />
        {uploadButton}
        <textarea
          ref={textareaRef}
          rows={1}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={cn(
            "max-h-[220px] flex-1 resize-none bg-transparent text-[#1F2933] placeholder:text-[#667085] focus:outline-none",
            isHero
              ? "min-h-10 overflow-hidden px-1 py-2 text-[16px] leading-6"
              : "min-h-10 overflow-hidden px-1 py-2 text-[16px] leading-6",
          )}
          disabled={isLoading}
          autoFocus={autoFocus}
        />

        <div className="flex shrink-0 items-center gap-1">
          {modeButton}
          {micButton}
          {canSend ? sendButton : null}
        </div>
      </div>
    </form>
  );
}
