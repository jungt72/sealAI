import { afterEach, describe, expect, it, vi } from "vitest";

import { FALLBACK_FRAMING } from "../framing";
import { fetchFraming } from "./framing";

const SERVER = { ...FALLBACK_FRAMING, claim_boundary: "Server-Text — Orientierung, keine Freigabe." };

function stubFetch(impl: () => Promise<unknown>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

afterEach(() => vi.unstubAllGlobals());

describe("fetchFraming (server wins, fallback never half-replaced)", () => {
  it("returns the server payload when complete", async () => {
    stubFetch(async () => ({ ok: true, json: async () => ({ ...SERVER, version: "abc" }) }));
    expect(await fetchFraming()).toEqual(SERVER);
  });

  it("returns null on a non-OK response", async () => {
    stubFetch(async () => ({ ok: false, status: 503, json: async () => ({}) }));
    expect(await fetchFraming()).toBeNull();
  });

  it("returns null when a field is missing or empty (no partial replacement)", async () => {
    stubFetch(async () => ({ ok: true, json: async () => ({ ...SERVER, candidate: "" }) }));
    expect(await fetchFraming()).toBeNull();
    stubFetch(async () => {
      const { vorlaeufig: _drop, ...partial } = SERVER;
      return { ok: true, json: async () => partial };
    });
    expect(await fetchFraming()).toBeNull();
  });

  it("returns null when the fetch itself fails", async () => {
    stubFetch(async () => {
      throw new Error("network down");
    });
    expect(await fetchFraming()).toBeNull();
  });
});
