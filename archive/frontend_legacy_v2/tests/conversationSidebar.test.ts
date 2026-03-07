import { describe, expect, it } from "vitest";

import { normalizeConversationEntry } from "@/components/ConversationSidebar";

describe("normalizeConversationEntry", () => {
  it("admits thread_id and preserves last_preview", () => {
    const raw = {
      thread_id: "thread-1",
      title: "Greetings",
      updated_at: "2025-08-01T12:00:00.000Z",
      last_preview: "Hello preview",
    };

    expect(normalizeConversationEntry(raw)).toEqual({
      id: "thread-1",
      title: "Greetings",
      updated_at: "2025-08-01T12:00:00.000Z",
      last_preview: "Hello preview",
    });
  });

  it("falls back to id when thread_id is missing and rejects invalid payloads", () => {
    const raw = {
      id: "legacy",
      title: "Legacy title",
      updatedAt: "2025-09-01T00:00:00.000Z",
    };

    const normalized = normalizeConversationEntry(raw);
    expect(normalized).not.toBeNull();
    expect(normalized?.id).toBe("legacy");
    expect(normalized?.title).toBe("Legacy title");

    expect(normalizeConversationEntry({})).toBeNull();
    expect(
      normalizeConversationEntry({
        thread_id: "",
        updated_at: "",
      }),
    ).toBeNull();
  });
});
