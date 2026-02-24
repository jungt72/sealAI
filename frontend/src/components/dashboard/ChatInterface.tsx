"use client";

import { Bot, User, RotateCcw } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useSession } from "next-auth/react";
import ChatComposer from "./ChatComposer";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';

type Message = { role: "user" | "assistant"; content: string };

export default function ChatInterface() {
    const { data: session } = useSession();
    // Empty start = zero state hero
    const [messages, setMessages] = useState<Message[]>([]);
    const [chatId, setChatId] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const isZeroState = messages.length === 0;
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!isZeroState) {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, isZeroState]);

    const startNewChat = () => {
        setMessages([]);
        setChatId(null);
    };

    const onSendMessage = async (message: string) => {
        if (!message.trim() || isLoading) return;

        if (!(session as any)?.accessToken) {
            setMessages(prev => [...prev, {
                role: "assistant",
                content: "Error: Keine aktive Sitzung. Bitte melden Sie sich erneut an."
            }]);
            return;
        }

        const userText = message;
        setMessages(prev => [
            ...prev,
            { role: "user", content: userText },
            { role: "assistant", content: "" }
        ]);

        setIsLoading(true);

        const clientMsgId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
            ? crypto.randomUUID()
            : `msg-${Date.now()}`;

        let currentChatId = chatId;
        if (!currentChatId) {
            currentChatId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
                ? crypto.randomUUID()
                : `chat-${Date.now()}`;
            setChatId(currentChatId);
        }

        const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
        const targetUrl = apiBase.startsWith("http://backend") || !apiBase
            ? "/api/v1/langgraph/chat/v2"
            : `${apiBase}/api/v1/langgraph/chat/v2`;

        try {
            const response = await fetch(targetUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${(session as any).accessToken}`
                },
                body: JSON.stringify({
                    input: userText,
                    chat_id: currentChatId,
                    client_msg_id: clientMsgId,
                    metadata: {},
                    client_context: {},
                }),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error ${response.status}: ${errorText || "request failed"}`);
            }

            const reader = response.body?.getReader();
            if (!reader) throw new Error("No reader available");

            const decoder = new TextDecoder();
            let sseBuffer = "";
            let streamDone = false;

            while (true) {
                const { done, value } = await reader.read();
                const chunk = decoder.decode(value || new Uint8Array(), { stream: !done });
                sseBuffer += chunk;

                let boundary = sseBuffer.indexOf("\n\n");
                while (boundary !== -1) {
                    const rawEvent = sseBuffer.slice(0, boundary);
                    sseBuffer = sseBuffer.slice(boundary + 2);

                    const dataLines = rawEvent
                        .split(/\r?\n/)
                        .filter(line => line.startsWith("data:"))
                        .map(line => line.slice(5).trimStart());

                    if (dataLines.length > 0) {
                        const rawPayload = dataLines.join("\n");
                        if (rawPayload === "[DONE]") { streamDone = true; break; }

                        let data: any = null;
                        try {
                            data = JSON.parse(rawPayload);
                        } catch (e) {
                            if (rawPayload.includes("token")) console.error("Error parsing SSE:", e, rawPayload);
                            boundary = sseBuffer.indexOf("\n\n");
                            continue;
                        }

                        if (data?.type === "token" && typeof data.text === "string") {
                            const tokenText = data.text;
                            setMessages(prev => {
                                const newMessages = [...prev];
                                const lastIndex = newMessages.length - 1;
                                if (lastIndex >= 0 && newMessages[lastIndex].role === "assistant") {
                                    newMessages[lastIndex] = {
                                        ...newMessages[lastIndex],
                                        content: newMessages[lastIndex].content + tokenText
                                    };
                                }
                                return newMessages;
                            });
                        } else if (data?.type === "error") {
                            throw new Error(data.message || "Streaming error");
                        } else if (data?.type === "done") {
                            streamDone = true;
                        }
                    }
                    if (streamDone) break;
                    boundary = sseBuffer.indexOf("\n\n");
                }
                if (done || streamDone) break;
            }
        } catch (error) {
            console.error("Failed to stream message:", error);
            setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                const errorMessage = "⚠️ Verbindung unterbrochen. Bitte versuchen Sie es erneut.";
                if (last?.role === "assistant") {
                    return [...next.slice(0, -1), { ...last, content: last.content ? `${last.content}\n\n${errorMessage}` : errorMessage }];
                }
                return [...prev, { role: "assistant", content: errorMessage }];
            });
        } finally {
            setIsLoading(false);
        }
    };

    const markdownComponents = {
        p: ({ node, ...props }: any) => <p className="mb-4 last:mb-0" {...props} />,
        a: ({ node, ...props }: any) => <a className="text-[#007AFF] hover:underline" {...props} />,
        ul: ({ node, ...props }: any) => <ul className="list-disc pl-5 mb-4 space-y-2" {...props} />,
        ol: ({ node, ...props }: any) => <ol className="list-decimal pl-5 mb-4 space-y-2" {...props} />,
        li: ({ node, ...props }: any) => <li className="pl-1" {...props} />,
        h1: ({ node, ...props }: any) => <h1 className="text-xl font-semibold mb-3 mt-6 text-[#0D1B2A]" {...props} />,
        h2: ({ node, ...props }: any) => <h2 className="text-lg font-semibold mb-2 mt-5 text-[#0D1B2A]" {...props} />,
        h3: ({ node, ...props }: any) => <h3 className="text-base font-semibold mb-2 mt-4 text-[#0D1B2A]" {...props} />,
        table: ({ node, ...props }: any) => (
            <div className="overflow-x-auto mb-6 border border-gray-200 rounded-xl shadow-sm">
                <table className="w-full text-left text-sm" {...props} />
            </div>
        ),
        thead: ({ node, ...props }: any) => <thead className="bg-[#F0F4F8] font-semibold border-b border-gray-200" {...props} />,
        th: ({ node, ...props }: any) => <th className="px-4 py-3" {...props} />,
        td: ({ node, ...props }: any) => <td className="px-4 py-3 border-b border-gray-100 last:border-0" {...props} />,
        code: ({ node, inline, ...props }: any) =>
            inline
                ? <code className="bg-[#F0F4F8]/80 text-[#E01E5A] px-1.5 py-0.5 rounded-md text-[13px] font-mono" {...props} />
                : <code className="block bg-[#F8F9FA] text-[#1D1D1F] p-4 rounded-xl text-[13px] font-mono overflow-x-auto mb-6 border border-gray-100 shadow-inner" {...props} />,
        blockquote: ({ node, ...props }: any) => <blockquote className="border-l-4 border-[#007AFF]/20 pl-4 italic text-gray-500 my-6 bg-blue-50/20 py-1" {...props} />
    };

    return (
        // Hier passiert die Magie für die absolute Mitte im Zero-State (items-center justify-center)
        <div className={`relative flex flex-col w-full h-full overflow-hidden bg-white ${isZeroState ? 'items-center justify-center' : ''}`}>

            {/* New Chat Button (Top Right) */}
            {!isZeroState && (
                <button
                    onClick={startNewChat}
                    className="absolute top-6 right-6 z-[60] p-2 bg-white/80 hover:bg-white border border-gray-200 rounded-full shadow-sm text-gray-500 hover:text-[#007AFF] transition-all active:scale-95 flex items-center gap-2 px-3 pr-4"
                    title="Neuer Chat"
                >
                    <RotateCcw size={18} />
                    <span className="text-sm font-medium">Neuer Chat</span>
                </button>
            )}

            {/* SCROLL AREA — only visible when messages exist */}
            {!isZeroState && (
                <div className="flex-1 overflow-y-auto w-full">
                    <div className="max-w-3xl mx-auto w-full flex flex-col gap-8 pb-40 pt-16 px-4">
                        {messages.map((m, i) => (
                            <div key={i} className={`w-full ${m.role === "user" ? "flex justify-end" : "flex justify-start"}`}>
                                {m.role === "assistant" ? (
                                    <div className="flex items-start gap-4 w-full">
                                        <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0 bg-white border border-gray-100 shadow-sm mt-1">
                                            <Bot size={20} className="text-[#007AFF]" />
                                        </div>
                                        <div className="flex-1 text-[16px] leading-relaxed text-[#1D1D1F] py-2">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]} className="break-words" components={markdownComponents}>
                                                {m.content}
                                            </ReactMarkdown>
                                            {isLoading && i === messages.length - 1 && !m.content && (
                                                <span className="inline-block w-2 h-4 bg-[#007AFF]/20 animate-pulse ml-1 align-middle" />
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="bg-[#007AFF] text-white px-5 py-3.5 rounded-3xl rounded-tr-sm max-w-[80%] shadow-sm text-[16px] leading-relaxed">
                                        {m.content}
                                    </div>
                                )}
                            </div>
                        ))}
                        <div ref={messagesEndRef} />
                    </div>
                </div>
            )}

            {/* GROK-STYLE: LOGO & INPUT WRAPPER */}
            <motion.div
                layout
                transition={{ type: "spring", stiffness: 200, damping: 25 }}
                className={`w-full px-4 z-50 flex flex-col items-center ${
                    isZeroState
                        ? "max-w-3xl" // Im Zero-State wird dieser Block durch den Parent perfekt zentriert
                        : "absolute bottom-8 left-0 right-0 mx-auto max-w-3xl" // Bei aktiven Nachrichten rutscht er an den Boden
                }`}
            >
                {/* Das Logo & Claim (Nur im Zero-State sichtbar) */}
                <AnimatePresence>
                    {isZeroState && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95, filter: "blur(4px)", transitionEnd: { display: "none" } }}
                            transition={{ duration: 0.3 }}
                            className="mb-12 flex flex-col items-center"
                        >
                            {/* Logo */}
                            <img
                                src="/images/logo/Logo_sealai_schwebend-removebg-preview.png"
                                alt="SealAI Logo"
                                className="h-20 w-auto object-contain drop-shadow-sm mb-6"
                            />
                            {/* Claim im "Mercedes"-Style: Serifenschrift, groß, elegant */}
                            <h1 className="text-4xl md:text-5xl font-serif text-[#1D1D1F] tracking-tight text-center">
                                Sealing Intelligence
                            </h1>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Eingabefeld */}
                <div className="w-full max-w-2xl">
                    <ChatComposer onSend={onSendMessage} isLoading={isLoading} autoFocus={true} />
                </div>
            </motion.div>
        </div>
    );
}
