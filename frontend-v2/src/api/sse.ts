/* P4b — incremental SSE frame parser for the /chat/stream reader. fetch+ReadableStream delivers
 * arbitrary chunk boundaries, so frames are buffered until their blank-line terminator. Comment
 * blocks (": keepalive") are dropped here — callers only ever see real frames. */

export interface SseFrame {
  event: string;
  data: string;
}

export class SseParser {
  private buffer = "";

  /** Feed one decoded chunk; returns every frame completed by it (possibly none). */
  push(chunk: string): SseFrame[] {
    this.buffer += chunk;
    const frames: SseFrame[] = [];
    let idx: number;
    while ((idx = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);
      const frame = parseBlock(block);
      if (frame) frames.push(frame);
    }
    return frames;
  }
}

function parseBlock(block: string): SseFrame | null {
  let event = "message"; // SSE default event name
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue; // comment / keepalive
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data.push(line.slice("data:".length).replace(/^ /, ""));
  }
  if (data.length === 0) return null; // comment-only or empty block
  return { event, data: data.join("\n") };
}
