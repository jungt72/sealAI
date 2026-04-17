"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Plus, SendHorizontal, Mic } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatComposerProps {
    onSend: (message: string) => void;
    isLoading?: boolean;
    autoFocus?: boolean;
    externalValue?: string | null;
}

export default function ChatComposer({ onSend, isLoading, autoFocus, externalValue }: ChatComposerProps) {
    const [message, setMessage] = useState('');
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        if (externalValue !== undefined && externalValue !== null) {
            setMessage(externalValue);
            textareaRef.current?.focus();
        }
    }, [externalValue]);

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
        }
    }, [message]);

    const handleSubmit = (e?: React.FormEvent) => {
        e?.preventDefault();
        if (message.trim() && !isLoading) {
            onSend(message);
            setMessage('');
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    const canSend = Boolean(message.trim()) && !isLoading;

    return (
        <form
            onSubmit={handleSubmit}
            className="flex flex-col w-full bg-muted rounded-[28px] p-2 transition-all focus-within:bg-[#EAECEF] border border-transparent focus-within:border-border"
        >
            <div className="flex items-end gap-1">
                <button
                    type="button"
                    className="flex h-12 w-12 items-center justify-center rounded-full text-muted-foreground hover:bg-[#DDE3EA] transition-colors shrink-0"
                >
                    <Plus size={24} />
                </button>

                <textarea
                    ref={textareaRef}
                    rows={1}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Beschreiben Sie Ihr Dichtungsproblem..."
                    className="flex-1 bg-transparent px-2 py-3 text-base text-foreground placeholder-muted-foreground focus:outline-none resize-none max-h-60 leading-relaxed"
                    disabled={isLoading}
                    autoFocus={autoFocus}
                />

                <div className="flex items-center gap-1 shrink-0 p-1">
                    <button
                        type="button"
                        className="flex h-10 w-10 items-center justify-center rounded-full text-muted-foreground hover:bg-[#DDE3EA] transition-colors"
                    >
                        <Mic size={20} />
                    </button>
                    <button
                        type="submit"
                        disabled={!canSend}
                        className={cn(
                            "flex h-10 w-10 items-center justify-center rounded-full transition-all",
                            canSend 
                                ? "text-seal-blue hover:bg-[#DDE3EA]" 
                                : "text-muted-foreground opacity-40 cursor-not-allowed"
                        )}
                    >
                        <SendHorizontal size={20} />
                    </button>
                </div>
            </div>
        </form>
    );
}
