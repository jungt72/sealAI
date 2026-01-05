"use client";

import * as React from "react";
import { useRef, useEffect, useCallback, useState } from "react";
import { useContextState } from "../context/ContextStateProvider";
import { ParameterFormModal } from "./ParameterFormModal";
import { Paperclip, Settings, ArrowUp, StopCircle } from "lucide-react";

interface UploadedTechnicalFile {
    name: string;
    size: number;
    type: string;
}

interface AdvancedInputBarProps {
    value: string;
    setValue: (v: string) => void;
    onSend: (v: string) => void;
    onStop?: () => void;
    disabled?: boolean;
    streaming?: boolean;
    placeholder?: string;
    onUploadFiles?: (files: File[]) => Promise<void>;
}

export default function AdvancedInputBar({
    value,
    setValue,
    onSend,
    onStop,
    disabled,
    streaming,
    placeholder = "Frag SealAI...",
    onUploadFiles,
}: AdvancedInputBarProps) {
    const { contextState, updateContext, addAttachments } = useContextState();
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [isParamModalOpen, setIsParamModalOpen] = useState(false);

    const autosize = useCallback(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }, []);

    useEffect(() => {
        autosize();
    }, [value, autosize]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            doSend();
        }
    };

    const doSend = () => {
        if (disabled || !value.trim()) return;
        onSend(value.trim());
        setValue("");
        if (textareaRef.current) textareaRef.current.style.height = "auto";
    };

    const handleUploadClick = () => fileInputRef.current?.click();

    const handleFilesSelected = async (files: FileList | null) => {
        if (!files || !files.length) return;
        const fileArray = Array.from(files);
        const mapped: UploadedTechnicalFile[] = fileArray.map((file) => ({
            name: file.name,
            size: file.size,
            type: file.type,
        }));
        addAttachments(mapped);
        await onUploadFiles?.(fileArray);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    };

    return (
        <div className="w-full max-w-[800px] mx-auto">
            <div className="relative flex flex-col gap-2 rounded-[26px] border border-gray-200 bg-white shadow-sm transition-shadow focus-within:shadow-md focus-within:border-gray-300 p-2">

                {/* Textarea Area */}
                <div className="px-3 pt-1">
                    <textarea
                        ref={textareaRef}
                        className="w-full resize-none bg-transparent text-[16px] leading-relaxed text-gray-900 outline-none placeholder:text-gray-400 max-h-[200px]"
                        placeholder={disabled ? "Offline" : placeholder}
                        rows={1}
                        disabled={streaming}
                        value={value}
                        onChange={(e) => {
                            setValue(e.target.value);
                            autosize();
                        }}
                        onKeyDown={handleKeyDown}
                    />
                </div>

                {/* Attachments Preview */}
                {contextState.attachments.length > 0 && (
                    <div className="px-3 flex flex-wrap gap-2">
                        {contextState.attachments.map((file) => (
                            <span
                                key={file.name}
                                className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-600"
                            >
                                📄 {file.name}
                            </span>
                        ))}
                    </div>
                )}

                {/* Toolbar */}
                <div className="flex items-center justify-between px-2 pb-1">
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            onClick={handleUploadClick}
                            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition"
                            title="Datei anhängen"
                        >
                            <Paperclip size={20} />
                        </button>
                        <button
                            type="button"
                            onClick={() => setIsParamModalOpen(true)}
                            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition"
                            title="Parameter"
                        >
                            <Settings size={20} />
                        </button>
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            accept=".pdf,.dxf,.dwg,image/*"
                            className="hidden"
                            onChange={(e) => handleFilesSelected(e.target.files)}
                        />
                    </div>

                    <div>
                        {streaming ? (
                            <button
                                type="button"
                                onClick={onStop}
                                className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-700 transition"
                            >
                                <StopCircle size={16} fill="currentColor" />
                            </button>
                        ) : (
                            <button
                                type="button"
                                onClick={doSend}
                                disabled={disabled || !value.trim()}
                                className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-gray-900 transition"
                            >
                                <ArrowUp size={18} strokeWidth={3} />
                            </button>
                        )}
                    </div>
                </div>
            </div>

            <div className="mt-2 text-center text-[11px] text-gray-400">
                SealAI kann Fehler machen. Überprüfe wichtige Informationen.
            </div>

            <ParameterFormModal
                open={isParamModalOpen}
                onClose={() => setIsParamModalOpen(false)}
                contextState={contextState}
                onSave={(next) => updateContext(next)}
            />
        </div>
    );
}
