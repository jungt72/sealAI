"use client";

import { Bot, ChevronLeft, ChevronRight, RotateCcw, AlertCircle } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useSession } from "next-auth/react";
import ChatComposer from "./ChatComposer";
import LiveCalcTile, { type LiveCalcTileData } from "./LiveCalcTile";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";
import { useSealAIStream } from "@/hooks/useSealAIStream";

type Message = { role: "user" | "assistant"; content: string };

export default function ChatInterface() {
    const { data: session } = useSession();
    const [chatId, setChatId] = useState<string | null>(null);
    const [chatHistoryOffset, setChatHistoryOffset] = useState(0);
    const [suppressCurrentAiText, setSuppressCurrentAiText] = useState(false);
    const [authError, setAuthError] = useState<string | null>(null);
    const [liveCalcTile, setLiveCalcTile] = useState<LiveCalcTileData | null>(null);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [showTile, setShowTile] = useState(false);
    const [rfqReady, setRfqReady] = useState(false);
    const [rfqPdfBase64, setRfqPdfBase64] = useState<string | null>(null);
    const [rfqHtmlReport, setRfqHtmlReport] = useState<string | null>(null);

    const accessToken = (session as any)?.accessToken ?? "";
    const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
    const streamApiEndpoint = apiBase.startsWith("http://backend") || !apiBase
        ? "/api/v1/langgraph"
        : `${apiBase}/api/v1/langgraph`;

    const {
        chatHistory,
        currentAiText,
        isThinking,
        nodeStatus,
        workingProfile,
        error: streamError,
        sendMessage,
        cancelStream,
        clearError,
    } = useSealAIStream(streamApiEndpoint, accessToken);

    useEffect(() => {
        if (workingProfile && typeof workingProfile === 'object' && Object.keys(workingProfile).length > 0) {
            console.log("DEBUG WP:", workingProfile);
            const { temp_range, candidate_materials, ...rest } = workingProfile as any;
            setLiveCalcTile({
                status: (workingProfile as any).knowledge_coverage === 'FULL' ? 'ok' : 'warning',
                parameters: {
                    ...rest,
                    temperature_max_c: temp_range?.[1],
                    pressure_max_bar: (workingProfile as any).pressure_max_bar || (workingProfile as any).pressure_bar
                }
            });
            setShowTile(true);
        }
    }, [workingProfile]);

    const visibleHistory = chatHistory.slice(chatHistoryOffset);
    const completedMessages: Message[] = visibleHistory.map((message) => ({
        role: message.role === "ai" ? "assistant" : "user",
        content: message.text,
    }));

    let displayedMessages = authError
        ? [...completedMessages, { role: "assistant" as const, content: authError }]
        : completedMessages;
    
    if (streamError) {
        displayedMessages = [...displayedMessages, { role: "assistant" as const, content: `⚠️ **Fehler:** ${streamError}` }];
    }

    const hasTileData = Boolean(liveCalcTile && liveCalcTile.status !== "insufficient_data");
    const isSidebarVisible = (showTile || hasTileData) && isSidebarOpen;
    const shouldShowStreamingBubble = !suppressCurrentAiText && (isThinking || Boolean(currentAiText));
    const isZeroState = displayedMessages.length === 0 && !shouldShowStreamingBubble;

    const assistantMessageRefs = useRef<Record<number, HTMLDivElement | null>>({});
    const streamingAssistantRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (isZeroState) return;

        if (shouldShowStreamingBubble && streamingAssistantRef.current) {
            streamingAssistantRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
            return;
        }

        for (let i = displayedMessages.length - 1; i >= 0; i -= 1) {
            if (displayedMessages[i]?.role !== "assistant") continue;
            const node = assistantMessageRefs.current[i];
            if (!node) continue;
            node.scrollIntoView({ behavior: "smooth", block: "start" });
            break;
        }
    }, [displayedMessages, shouldShowStreamingBubble, currentAiText, isZeroState]);

    const startNewChat = () => {
        cancelStream();
        clearError();
        setChatHistoryOffset(chatHistory.length);
        setChatId(null);
        setSuppressCurrentAiText(true);
        setAuthError(null);
        setLiveCalcTile(null);
        setShowTile(false);
        setIsSidebarOpen(true);
        assistantMessageRefs.current = {};
        setRfqReady(false);
        setRfqPdfBase64(null);
        setRfqHtmlReport(null);
    };

    const onSendMessage = async (message: string) => {
        if (!message.trim() || isThinking) return;

        if (!accessToken) {
            setAuthError("Error: Keine aktive Sitzung. Bitte melden Sie sich erneut an.");
            return;
        }

        setAuthError(null);
        setSuppressCurrentAiText(false);

        let currentChatId = chatId;
        if (!currentChatId) {
            currentChatId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
                ? crypto.randomUUID()
                : `chat-${Date.now()}`;
            setChatId(currentChatId);
        }

        await sendMessage(message, currentChatId);
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
        blockquote: ({ node, ...props }: any) => <blockquote className="border-l-4 border-[#007AFF]/20 pl-4 italic text-gray-500 my-6 bg-blue-50/20 py-1" {...props} />,
    };

    return (
        <div className="h-full w-full overflow-hidden bg-[#f3f8ff]">
            <div className={`relative mx-auto grid h-full w-full max-w-[1700px] gap-4 p-4 ${isSidebarVisible ? "grid-cols-1 xl:grid-cols-3" : "grid-cols-1"}`}>
                
                <div className={`relative flex h-full w-full flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white transition-all duration-300 ${isSidebarVisible ? "xl:col-span-2" : "xl:col-span-3"} ${isZeroState ? "items-center justify-center" : ""}`}>

                    {!isZeroState && (
                        <div className="absolute top-6 right-6 z-[70] flex items-center gap-2">
                            <button
                                onClick={startNewChat}
                                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white/90 px-3 py-2 text-sm font-medium text-gray-600 shadow-sm transition-all hover:bg-white hover:text-[#007AFF] active:scale-95"
                                title="Neuer Chat"
                            >
                                <RotateCcw size={18} />
                                <span>Neuer Chat</span>
                            </button>
                        </div>
                    )}

                    {!isZeroState && (
                        <div className="flex-1 overflow-y-auto w-full [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
                            <div className="max-w-3xl mx-auto w-full flex flex-col gap-8 pb-40 pt-16 px-4">
                                {displayedMessages.map((m, i) => (
                                    <div key={i} className={`w-full ${m.role === "user" ? "flex justify-end" : "flex justify-start"}`}>
                                        {m.role === "assistant" ? (
                                            <div
                                                ref={(node) => {
                                                    assistantMessageRefs.current[i] = node;
                                                }}
                                                className="flex items-start gap-4 w-full"
                                            >
                                                <div className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 bg-white border shadow-sm mt-1 ${m.content.includes("⚠️ **Fehler:**") ? "border-red-100" : "border-gray-100"}`}>
                                                    {m.content.includes("⚠️ **Fehler:**") ? (
                                                        <AlertCircle size={20} className="text-red-500" />
                                                    ) : (
                                                        <Bot size={20} className="text-[#007AFF]" />
                                                    )}
                                                </div>
                                                <div className={`flex-1 text-[16px] leading-relaxed py-2 ${m.content.includes("⚠️ **Fehler:**") ? "text-red-600 font-medium" : "text-[#1D1D1F]"}`}>
                                                    <ReactMarkdown remarkPlugins={[remarkGfm]} className="break-words" components={markdownComponents}>
                                                        {m.content}
                                                    </ReactMarkdown>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="bg-[#007AFF] text-white px-5 py-3.5 rounded-3xl rounded-tr-sm max-w-[80%] shadow-sm text-[16px] leading-relaxed">
                                                {m.content}
                                            </div>
                                        )}
                                    </div>
                                ))}

                                {shouldShowStreamingBubble && (
                                    <div className="w-full flex justify-start">
                                        <div ref={streamingAssistantRef} className="flex items-start gap-4 w-full">
                                            <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0 bg-white border border-gray-100 shadow-sm mt-1">
                                                <Bot size={20} className="text-[#007AFF]" />
                                            </div>
                                            <div className="flex-1 text-[16px] leading-relaxed text-[#1D1D1F] py-2">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]} className="break-words" components={markdownComponents}>
                                                    {currentAiText}
                                                </ReactMarkdown>
                                                {isThinking && (
                                                    <div className="flex items-center gap-2 mt-2">
                                                        {!currentAiText && (
                                                            <span className="text-sm text-gray-400 italic">
                                                                {nodeStatus === 'research' ? 'Durchsuche Wissensdatenbank...' : 
                                                                 nodeStatus === 'answer' ? 'Formuliere Antwort...' :
                                                                 nodeStatus === 'audit' ? 'Prüfe technische Compliance...' :
                                                                 'SealAI denkt nach...'}
                                                            </span>
                                                        )}
                                                        <div className="flex gap-1">
                                                            <span className="w-1.5 h-1.5 bg-[#007AFF] rounded-full animate-bounce [animation-delay:-0.3s]" />
                                                            <span className="w-1.5 h-1.5 bg-[#007AFF] rounded-full animate-bounce [animation-delay:-0.15s]" />
                                                            <span className="w-1.5 h-1.5 bg-[#007AFF] rounded-full animate-bounce" />
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    <motion.div
                        layout
                        transition={{ type: "spring", stiffness: 200, damping: 25 }}
                        className={`w-full px-4 z-50 flex flex-col items-center ${
                            isZeroState
                                ? "max-w-3xl"
                                : "absolute bottom-8 left-0 right-0 mx-auto max-w-3xl"
                        }`}
                    >
                        <AnimatePresence>
                            {isZeroState && (
                                <motion.div
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    exit={{ opacity: 0, scale: 0.95, filter: "blur(4px)", transitionEnd: { display: "none" } }}
                                    transition={{ duration: 0.3 }}
                                    className="mb-12 flex flex-col items-center"
                                >
                                    <img
                                        src="/images/logo/Logo_sealai_schwebend-removebg-preview.png"
                                        alt="SealAI Logo"
                                        className="h-20 w-auto object-contain drop-shadow-sm mb-6"
                                    />
                                    <h1 className="text-4xl md:text-5xl font-serif text-[#1D1D1F] tracking-tight text-center">
                                        Sealing Intelligence
                                    </h1>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        <div className="w-full max-w-2xl">
                            <ChatComposer onSend={onSendMessage} isLoading={isThinking} autoFocus={true} />
                        </div>
                    </motion.div>
                </div>

                <AnimatePresence>
                    {isSidebarVisible && (
                        <motion.div
                            key="live-calc-tile"
                            initial={{ opacity: 0, x: 28 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 28 }}
                            transition={{ duration: 0.25, ease: "easeOut" }}
                            className="relative h-full xl:col-span-1"
                        >
                            <button
                                onClick={() => setIsSidebarOpen(false)}
                                className="absolute left-0 top-1/2 z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                                aria-label="Sidebar einklappen"
                            >
                                <ChevronRight className="h-4 w-4 text-slate-600" />
                            </button>
                            <LiveCalcTile
                                tile={liveCalcTile}
                                rfqReady={rfqReady}
                                rfqPdfBase64={rfqPdfBase64}
                                rfqHtmlReport={rfqHtmlReport}
                            />
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
