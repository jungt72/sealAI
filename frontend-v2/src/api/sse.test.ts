import { describe, expect, it } from "vitest";

import { SseParser } from "./sse";

describe("SseParser (P4b: incremental SSE frame parsing for /chat/stream)", () => {
  it("parses a complete event/data frame", () => {
    const p = new SseParser();
    expect(p.push('event: stage\ndata: {"stage":"ground","status":"start"}\n\n')).toEqual([
      { event: "stage", data: '{"stage":"ground","status":"start"}' },
    ]);
  });

  it("buffers frames split across arbitrary chunk boundaries", () => {
    const p = new SseParser();
    expect(p.push("event: sta")).toEqual([]);
    expect(p.push('ge\ndata: {"stage":"verify","st')).toEqual([]);
    expect(p.push('atus":"start"}\n\nevent: re')).toEqual([
      { event: "stage", data: '{"stage":"verify","status":"start"}' },
    ]);
    expect(p.push('sult\ndata: {"answer":"ok"}\n\n')).toEqual([
      { event: "result", data: '{"answer":"ok"}' },
    ]);
  });

  it("returns multiple frames from one chunk, in order", () => {
    const p = new SseParser();
    const frames = p.push(
      "event: stage\ndata: {a}\n\nevent: stage\ndata: {b}\n\nevent: result\ndata: {c}\n\n",
    );
    expect(frames.map((f) => f.data)).toEqual(["{a}", "{b}", "{c}"]);
  });

  it("drops keepalive comment blocks (lines starting with ':')", () => {
    const p = new SseParser();
    expect(p.push(": keepalive\n\n")).toEqual([]);
    expect(p.push(': keepalive\n\nevent: result\ndata: {"x":1}\n\n')).toEqual([
      { event: "result", data: '{"x":1}' },
    ]);
  });

  it("joins multi-line data with newlines and defaults the event to 'message'", () => {
    const p = new SseParser();
    expect(p.push("data: line1\ndata: line2\n\n")).toEqual([
      { event: "message", data: "line1\nline2" },
    ]);
  });
});
