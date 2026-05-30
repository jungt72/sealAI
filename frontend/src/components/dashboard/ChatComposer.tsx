"use client";

import React, { useEffect, useRef, useState } from "react";
import { AudioLines, ChevronDown, Mic, Paperclip, SendHorizontal } from "lucide-react";
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
  placeholder = "Beschreibe deine Dichtungssituation ...",
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
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#1F1F1F] transition-colors hover:bg-[#F3F4F6] disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      <Plus size={21} strokeWidth={2} />
    </button>
  );
  const modeButton = (
    <button
      type="button"
      title="Antwortlänge"
      aria-label="Antwortlänge"
      className="hidden h-8 shrink-0 items-center gap-1 rounded-full px-3 text-[14px] font-medium text-[#5F6368] transition-colors hover:bg-[#F3F4F6] sm:inline-flex"
    >
      <span>Länger</span>
      <ChevronDown size={15} strokeWidth={2} />
    </button>
  );
  const micButton = (
    <button
      type="button"
      title="Spracheingabe"
      aria-label="Spracheingabe"
      className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#1F1F1F] transition-colors hover:bg-[#F3F4F6] sm:inline-flex"
    >
      <Mic size={19} strokeWidth={2} />
    </button>
  );
  const modeButton = (
    <button
      type="button"
      title="Antwortlänge"
      aria-label="Antwortlänge"
      className="hidden h-10 shrink-0 items-center gap-1 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-seal-blue sm:inline-flex"
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
      className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-seal-blue sm:inline-flex"
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
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors",
        "bg-[#0F0F0F] text-white shadow-[0_3px_10px_rgba(0,0,0,0.14)]",
        canSend ? "hover:bg-[#1F2937]" : "cursor-not-allowed opacity-95",
      )}
    >
      {canSend ? <SendHorizontal size={18} /> : <AudioLines size={18} />}
    </button>
  );

  return (
    <div className="w-full">
      <form
        onSubmit={handleSubmit}
        data-private
        className={cn(
          "w-full rounded-[999px] border border-[#DADDE3] bg-[#FFFFFF] shadow-[0_10px_30px_rgba(15,23,42,0.08)] transition-shadow focus-within:border-[#C9CED8] focus-within:shadow-[0_14px_38px_rgba(15,23,42,0.12)]",
          isHero ? "px-4 py-2 sm:px-5" : "px-3 py-1.5",
        )}
      >
        <div className="flex min-h-[40px] items-center gap-2">
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
              "max-h-[220px] min-w-0 flex-1 resize-none bg-transparent text-[#1F1F1F] placeholder:text-[#747775] focus:outline-none",
              isHero
                ? "min-h-[36px] px-1 py-[6px] text-[16px] leading-6"
                : "min-h-[36px] px-1 py-[6px] text-[16px] leading-6",
            )}
            disabled={isLoading}
            autoFocus={autoFocus}
          />

        {isHero ? (
          <div className="mt-3 flex items-center justify-between">
            {uploadButton}
            <div className="flex items-center gap-1">
              {modeButton}
              {micButton}
              {sendButton}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1">
            {modeButton}
            {micButton}
            {sendButton}
          </div>
        )}
      </div>
    </form>
    </div>
  );
}
