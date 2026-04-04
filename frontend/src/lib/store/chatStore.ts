/**
 * chatStore — Chat-Nachrichten, Streaming-State und registrierte Aktionen.
 *
 * Pattern: CaseScreen ruft useAgentStream auf und synchronisiert dessen
 * State per useEffect in diesen Store. ChatPane liest ausschließlich aus
 * dem Store — kein Props-Drilling mehr.
 *
 * sendMessage / startNewChat werden von CaseScreen per registerCallbacks
 * eingehängt, sobald die Hook-Implementierungen verfügbar sind.
 */
import { create } from "zustand";

import type { ChatMessage } from "@/hooks/useAgentStream";

interface ChatStore {
  /** Abgeschlossene Nachrichten (User + Assistant) */
  messages: ChatMessage[];
  /** Laufender Streaming-Text des aktuellen Assistant-Turns */
  streamingText: string;
  /** True während der Agent antwortet */
  isStreaming: boolean;
  /** Fehlermeldung des letzten fehlgeschlagenen Requests */
  error: string | null;

  // ── Registrierte Aktionen (werden von CaseScreen eingehängt) ──────────────
  /** Sendet eine neue Nutzernachricht an den Agent */
  sendMessage: (msg: string) => Promise<void>;
  /** Startet einen neuen leeren Chat und navigiert zu /dashboard/new */
  startNewChat: () => void;

  // ── State-Sync-Setter (nur für CaseScreen-useEffect) ─────────────────────
  setMessages: (msgs: ChatMessage[]) => void;
  setStreamingText: (text: string) => void;
  setIsStreaming: (v: boolean) => void;
  setError: (e: string | null) => void;

  // ── Registrierung ─────────────────────────────────────────────────────────
  registerCallbacks: (callbacks: {
    sendMessage: (msg: string) => Promise<void>;
    startNewChat: () => void;
  }) => void;
}

// Leere No-Op-Defaults, damit die Komponenten immer aufrufbare Funktionen
// vorfinden — auch bevor CaseScreen die echten Implementierungen registriert.
const noopSend = async (_msg: string): Promise<void> => {};
const noopStart = (): void => {};

export const useChatStore = create<ChatStore>()((set) => ({
  messages: [],
  streamingText: "",
  isStreaming: false,
  error: null,

  sendMessage: noopSend,
  startNewChat: noopStart,

  setMessages: (msgs) => set({ messages: msgs }),
  setStreamingText: (text) => set({ streamingText: text }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  setError: (e) => set({ error: e }),

  registerCallbacks: ({ sendMessage, startNewChat }) =>
    set({ sendMessage, startNewChat }),
}));
