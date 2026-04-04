'use client';

/**
 * ChatComposer — Texteingabe mit Attachment-Stub und Send-Button.
 * Hex-Literale durch Tailwind-Tokens ersetzt; Send-Button nutzt <Button>.
 */

import React, { useState, useRef, useEffect } from 'react';
import { Plus, ArrowUp } from 'lucide-react';

import Button from '@/components/ui/Button';
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

    // Patch C4: Handle external value setting
    useEffect(() => {
        if (externalValue !== undefined && externalValue !== null) {
            const frame = window.requestAnimationFrame(() => {
                setMessage(externalValue);
                textareaRef.current?.focus();
            });
            return () => window.cancelAnimationFrame(frame);
        }
    }, [externalValue]);

    // Auto-resize logic
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
        <div className="w-full">
            <form
                onSubmit={handleSubmit}
                className="bg-white/90 backdrop-blur-md rounded-[32px] shadow-[0_20px_70px_-20px_rgba(0,0,0,0.1)] border border-gray-200/50 p-2 flex items-end gap-2 transition-all duration-300 focus-within:shadow-[0_20px_70px_-10px_rgba(0,122,255,0.1)]"
            >
                {/* Attachment Button — Ghost-Variante mit rundem Override */}
                <Button
                    type="button"
                    variant="ghost"
                    size="md"
                    className="w-10 h-10 rounded-full p-0 flex-shrink-0 bg-seal-surface hover:bg-seal-surface-hover text-gray-500"
                    aria-label="Datei anhängen"
                >
                    <Plus size={20} />
                </Button>

                {/* Textarea Input */}
                <textarea
                    ref={textareaRef}
                    rows={1}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Frag mich, zieh PDFs hierher oder iteriere Parameter..."
                    className="w-full bg-transparent px-4 py-3 text-[17px] text-gray-900 placeholder-gray-400 focus:outline-none resize-none max-h-48 leading-relaxed"
                    disabled={isLoading}
                    autoFocus={autoFocus}
                />

                {/* Send Button — Primary-Variante mit rundem Override */}
                <Button
                    type="submit"
                    variant="primary"
                    size="md"
                    loading={isLoading}
                    disabled={!canSend}
                    className={cn(
                        'w-10 h-10 rounded-full p-0 flex-shrink-0',
                        !canSend && 'bg-gray-200 text-gray-400 hover:bg-gray-200',
                    )}
                    aria-label="Nachricht senden"
                >
                    {!isLoading && <ArrowUp size={20} strokeWidth={2.5} />}
                </Button>
            </form>
        </div>
    );
}
