import { normalizeGermanVisibleText } from "./engineering/displayLabels.ts";

const QUOTE_WRAPPED_PARAGRAPH_RE = /(^|\n)([ \t]*)["“]([^"\n]{24,})["”]([ \t]*)(?=\n|$)/gm;

export function appendAssistantText(current: string, nextChunk: string): string {
  if (!nextChunk) {
    return current;
  }

  return `${current}${nextChunk}`;
}

export function normalizeAssistantMarkdown(text: string): string {
  return normalizeGermanVisibleText(text.replace(/\r\n?/g, "\n")).replace(
    QUOTE_WRAPPED_PARAGRAPH_RE,
    "$1$2$3$4",
  );
}
