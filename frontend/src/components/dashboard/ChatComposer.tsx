'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Plus, ArrowUp, Paperclip, X } from 'lucide-react';

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
            setMessage(externalValue);
            // Focus and move cursor to end
            if (textareaRef.current) {
                textareaRef.current.focus();
            }
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

    return (
        <div className="w-full">

            <form
                onSubmit={handleSubmit}
                className="bg-white/90 backdrop-blur-md rounded-[32px] shadow-[0_20px_70px_-20px_rgba(0,0,0,0.1)] border border-gray-200/50 p-2 flex items-end gap-2 transition-all duration-300 focus-within:shadow-[0_20px_70px_-10px_rgba(0,122,255,0.1)]"
            >
                {/* Attachment Button */}
                <button
                    type="button"
                    className="w-10 h-10 rounded-full bg-[#F5F5F7] hover:bg-[#E5E5EA] flex items-center justify-center text-gray-500 transition-all duration-200 cursor-pointer active:scale-95 flex-shrink-0"
                >
                    <Plus size={20} />
                </button>

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

                {/* Send Button */}
                <button
                    type="submit"
                    disabled={!message.trim() || isLoading}
                    className={`w-10 h-10 rounded-full flex items-center justify-center text-white shadow-sm transition-all duration-300 active:scale-90 flex-shrink-0 ${message.trim()
                        ? 'bg-[#007AFF] hover:bg-[#0066CC] shadow-[#007AFF]/20'
                        : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                        }`}
                >
                    <ArrowUp size={20} strokeWidth={2.5} />
                </button>
            </form>
        </div>
    );
}
