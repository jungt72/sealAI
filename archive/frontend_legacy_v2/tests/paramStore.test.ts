import { describe, expect, it } from "vitest";
import { getParamSnapshot, reduceParamStore } from "../src/lib/stores/paramStore";

const emptyState = { byChatId: {} };

describe("paramStore reducer", () => {
  it("initializes chat state once", () => {
    const next = reduceParamStore(emptyState, {
      type: "init",
      payload: { chatId: "chat-1", parameters: { medium: "oil" } },
    });
    expect(next.byChatId["chat-1"].parameters.medium).toBe("oil");

    const ignored = reduceParamStore(next, {
      type: "init",
      payload: { chatId: "chat-1", parameters: { medium: "water" } },
    });
    expect(ignored.byChatId["chat-1"].parameters.medium).toBe("oil");
  });

  it("replaces from server", () => {
    const next = reduceParamStore(emptyState, {
      type: "replace",
      payload: {
        chatId: "chat-1",
        parameters: { pressure_bar: 7 },
        versions: { pressure_bar: 2 },
        updatedAt: { pressure_bar: 123 },
      },
    });
    expect(next.byChatId["chat-1"].parameters.pressure_bar).toBe(7);
    expect(next.byChatId["chat-1"].versions.pressure_bar).toBe(2);
    expect(next.byChatId["chat-1"].updatedAt.pressure_bar).toBe(123);
  });

  it("normalizes pressure alias to pressure_bar", () => {
    const next = reduceParamStore(emptyState, {
      type: "replace",
      payload: {
        chatId: "chat-1",
        parameters: { pressure: 4 } as any,
        versions: {},
        updatedAt: {},
      },
    });
    expect(next.byChatId["chat-1"].parameters.pressure_bar).toBe(4);
    expect((next.byChatId["chat-1"].parameters as any).pressure).toBeUndefined();
  });

  it("applies patch ack with versions", () => {
    const seeded = reduceParamStore(emptyState, {
      type: "replace",
      payload: {
        chatId: "chat-1",
        parameters: { pressure_bar: 5 },
        versions: { pressure_bar: 1 },
        updatedAt: { pressure_bar: 100 },
      },
    });
    const next = reduceParamStore(seeded, {
      type: "apply_patch",
      payload: {
        chatId: "chat-1",
        ack: {
          patch: { pressure_bar: 8 },
          versions: { pressure_bar: 2 },
          updated_at: { pressure_bar: 200 },
          rejected_fields: [],
        },
      },
    });
    expect(next.byChatId["chat-1"].parameters.pressure_bar).toBe(8);
    expect(next.byChatId["chat-1"].versions.pressure_bar).toBe(2);
    expect(next.byChatId["chat-1"].updatedAt.pressure_bar).toBe(200);
  });

  it("marks local edits as dirty", () => {
    const seeded = reduceParamStore(emptyState, {
      type: "init",
      payload: { chatId: "chat-1" },
    });
    const next = reduceParamStore(seeded, {
      type: "apply_local",
      payload: { chatId: "chat-1", patch: { pressure_bar: 5 }, markDirty: true },
    });
    expect(next.byChatId["chat-1"].dirty.has("pressure_bar")).toBe(true);
  });

  it("applies SSE deltas and clears dirty when forced", () => {
    const seeded = reduceParamStore(emptyState, {
      type: "apply_local",
      payload: { chatId: "chat-1", patch: { pressure_bar: 5 }, markDirty: true },
    });
    const next = reduceParamStore(seeded, {
      type: "apply_delta",
      payload: {
        chatId: "chat-1",
        incoming: { pressure_bar: 7 },
        meta: { pressure_bar: { force_overwrite: true, source: "user" } },
        eventId: "evt-1",
      },
    });
    expect(next.byChatId["chat-1"].parameters.pressure_bar).toBe(7);
    expect(next.byChatId["chat-1"].dirty.has("pressure_bar")).toBe(false);
    expect(next.byChatId["chat-1"].lastServerEventId).toBe("evt-1");
  });

  it("clears pending keys on patch ack", () => {
    const seeded = reduceParamStore(emptyState, {
      type: "apply_local",
      payload: { chatId: "chat-1", patch: { pressure_bar: 5 }, markDirty: true },
    });
    const pending = reduceParamStore(seeded, {
      type: "set_pending",
      payload: { chatId: "chat-1", keys: new Set(["pressure_bar"]) },
    });
    const next = reduceParamStore(pending, {
      type: "apply_patch",
      payload: {
        chatId: "chat-1",
        ack: {
          patch: { pressure_bar: 8 },
          versions: { pressure_bar: 2 },
          updated_at: { pressure_bar: 200 },
          rejected_fields: [],
        },
      },
    });
    expect(next.byChatId["chat-1"].pending.has("pressure_bar")).toBe(false);
  });

  it("builds a snapshot from state", () => {
    const seeded = reduceParamStore(emptyState, {
      type: "replace",
      payload: {
        chatId: "chat-1",
        parameters: { pressure_bar: 5 },
        versions: { pressure_bar: 2 },
        updatedAt: { pressure_bar: 100 },
      },
    });
    const snapshot = getParamSnapshot(seeded, "chat-1");
    expect(snapshot).toEqual({
      parameters: { pressure_bar: 5 },
      versions: { pressure_bar: 2 },
      updated_at: { pressure_bar: 100 },
    });
  });
});
