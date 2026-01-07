import { describe, expect, it } from "vitest";

import { reduceParamStore } from "../src/lib/stores/paramStore";

describe("Param store applyServerParams", () => {
  it("overwrites provided keys and honors the pressure alias", () => {
    const initialState = {
      byChatId: {
        test: {
          parameters: { pressure_bar: 2, medium: "oil" },
          versions: {},
          updatedAt: {},
          dirty: new Set(),
          pending: new Set(),
          applied: {},
          lastServerEventId: null,
        },
      },
    } as any;
    const action = {
      type: "apply_server_params",
      payload: {
        chatId: "test",
        parameters: {
          pressure: 7,
          medium: "water",
        },
      },
    } as any;
    const next = reduceParamStore(initialState, action);
    expect(next.byChatId.test.parameters.medium).toBe("water");
    expect(next.byChatId.test.parameters.pressure_bar).toBe(7);
  });
});
