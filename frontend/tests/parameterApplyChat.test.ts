import { describe, expect, it, vi } from "vitest";

import { applyParametersWithChatMessage } from "../src/lib/parameterApplyChat";

describe("applyParametersWithChatMessage", () => {
  it("patches and sends a summary message", async () => {
    const patch = { pressure_bar: 5, temperature_C: 80 };
    const patchParameters = vi.fn().mockResolvedValue(undefined);
    const sendChatMessage = vi.fn();
    const metadata = {
      source: "param_apply",
      kind: "parameter_summary",
      keys: ["pressure_bar", "temperature_C"],
    };

    const result = await applyParametersWithChatMessage({
      patch,
      patchParameters,
      sendChatMessage,
      metadata,
    });

    expect(patchParameters).toHaveBeenCalledTimes(1);
    expect(patchParameters).toHaveBeenCalledWith(patch);
    expect(sendChatMessage).toHaveBeenCalledTimes(1);
    expect(sendChatMessage).toHaveBeenCalledWith(
      "Parameter übernommen: Druck=5 bar, Temperatur=80 °C",
      metadata,
    );
    expect(result.summary).toBe("Parameter übernommen: Druck=5 bar, Temperatur=80 °C");
  });

  it("skips patching when no parameters are provided", async () => {
    const patchParameters = vi.fn().mockResolvedValue(undefined);
    const sendChatMessage = vi.fn();

    const result = await applyParametersWithChatMessage({
      patch: {},
      patchParameters,
      sendChatMessage,
    });

    expect(patchParameters).not.toHaveBeenCalled();
    expect(sendChatMessage).not.toHaveBeenCalled();
    expect(result.summary).toBe("");
  });
});
