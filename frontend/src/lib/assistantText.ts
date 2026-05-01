import { normalizeGermanVisibleText } from "@/lib/engineering/displayLabels";

export function appendAssistantText(current: string, nextChunk: string): string {
  if (!nextChunk) {
    return current;
  }

  return `${current}${nextChunk}`;
}

export function normalizeAssistantMarkdown(text: string): string {
  return normalizeGermanVisibleText(text.replace(/\r\n?/g, "\n"));
}
