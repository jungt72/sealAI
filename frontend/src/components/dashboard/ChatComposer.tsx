"use client";

import React, { useEffect, useRef, useState } from "react";
import { ArrowUp, Paperclip } from "lucide-react";
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
  placeholder = "Anschlussfrage stellen …",
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

  const uploadButton = (
    <button
      type="button"
      title="Anhang hinzufügen"
      aria-label="Anhang hinzufügen"
      onClick={() => fileInputRef.current?.click()}
      disabled={!canUpload}
      className={cn(
        "flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#6B7280] transition-colors",
        "hover:bg-[#F1F3F5] hover:text-[#1F2933] disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      <Paperclip size={20} strokeWidth={1.9} />
    </button>
  );

  const sendButton = (
    <button
      type="submit"
      title="Senden"
      aria-label="Senden"
      disabled={!canSend}
      className={cn(
        "flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#111418] text-white transition-opacity",
        "hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30",
      )}
    >
      <ArrowUp size={22} strokeWidth={2.1} />
    </button>
  );

  return (
    <form
      onSubmit={handleSubmit}
      data-private
      className={cn(
        "w-full rounded-[28px] border border-[#ECEEF1] bg-white px-3 py-2.5 pl-5",
        "shadow-[0_10px_30px_rgba(15,23,42,0.10),0_1px_0_rgba(255,255,255,0.9)_inset]",
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
        <textarea
          ref={textareaRef}
          rows={1}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={cn(
            "max-h-[220px] min-h-10 flex-1 resize-none overflow-hidden bg-transparent px-1 py-2",
            "text-[16px] leading-6 text-[#1F2933] placeholder:text-[#8B94A3] focus:outline-none",
          )}
          disabled={isLoading}
          autoFocus={autoFocus}
        />

        <div className="flex shrink-0 items-center gap-1">
          {uploadButton}
          {sendButton}
        </div>
      </div>
    </form>
  );
}
