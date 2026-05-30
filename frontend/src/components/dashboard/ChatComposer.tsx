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
        "flex h-10 w-10 shrink-0 items-center justify-center text-muted-foreground transition-colors hover:bg-muted hover:text-seal-blue disabled:cursor-not-allowed disabled:opacity-50",
        isHero ? "rounded-full" : "rounded-md",
      )}
    >
      <Paperclip size={18} />
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
        "flex h-10 w-10 shrink-0 items-center justify-center transition-colors",
        isHero ? "rounded-full" : "rounded-md",
        canSend
          ? "bg-seal-blue text-white hover:opacity-90"
          : "cursor-not-allowed bg-slate-100 text-slate-400",
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
        "w-full border border-[#C9D1DC] bg-white shadow-[0_4px_18px_rgba(15,23,42,0.06)]",
        isHero ? "rounded-[28px] p-4" : "rounded-[16px] p-2",
      )}
    >
      <div className={cn(isHero ? "flex flex-col" : "flex items-end gap-2")}>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.txt,.md,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={handleFileChange}
          disabled={!canUpload}
        />
        {!isHero ? uploadButton : null}
        <textarea
          ref={textareaRef}
          rows={1}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={cn(
            "max-h-[220px] flex-1 resize-none bg-transparent text-foreground placeholder:text-[#6B7280] focus:outline-none",
            isHero
              ? "min-h-[58px] px-1 py-1 text-[16px] leading-7"
              : "min-h-10 px-1 py-2.5 text-[15px] leading-6",
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
  );
}
