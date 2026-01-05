import type { StructuredAnswerPayload } from "./StructuredAnswerCard";
import type { Message } from "@/types/chat";

export function parseStructuredAnswer(raw: string | null | undefined): StructuredAnswerPayload | null {
  if (!raw) return null;
  const text = raw.trim();
  if (!text.startsWith("{") || !text.endsWith("}")) return null;
  try {
    const obj = JSON.parse(text);
    if (obj && obj.type === "structured_answer" && typeof obj.result === "string") {
      return obj as StructuredAnswerPayload;
    }
  } catch {
    return null;
  }
  return null;
}

export function extractStructuredFromMessage(message: Message): StructuredAnswerPayload | null {
  const fromContent = parseStructuredAnswer(message.content);
  if (fromContent) return fromContent;
  const metaStructured = (message.meta as any)?.structured_answer;
  if (metaStructured && metaStructured.type === "structured_answer" && typeof metaStructured.result === "string") {
    return metaStructured as StructuredAnswerPayload;
  }
  return null;
}
