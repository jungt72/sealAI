// frontend/src/types/chat.ts

/**
 * Einfache Chat-Nachricht fürs Messaging
 */
export type Message = {
  role: "user" | "assistant" | "system";
  content: string;
};
