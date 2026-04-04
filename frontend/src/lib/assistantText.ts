export function appendAssistantText(current: string, nextChunk: string): string {
  if (!nextChunk) {
    return current;
  }

  return `${current}${nextChunk}`;
}

export function normalizeAssistantMarkdown(text: string): string {
  return text.replace(/\r\n?/g, "\n");
}
