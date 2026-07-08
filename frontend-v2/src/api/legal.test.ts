import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchLegalDoctrine, type LegalDoctrine } from "./legal";

const SERVER: LegalDoctrine = {
  terms_version: "2026-07-07-v1",
  privacy_version: "2026-07-07-v1",
  dpa_version: "2026-07-07-v1",
  product_purpose_doctrine: "sealingAI ist eine KI-gestützte Wissens-, Strukturierungs- ...",
};

function stubFetch(impl: () => Promise<unknown>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

afterEach(() => vi.unstubAllGlobals());

describe("fetchLegalDoctrine (fail-null, never partial)", () => {
  it("returns the server payload when complete", async () => {
    stubFetch(async () => ({ ok: true, json: async () => SERVER }));
    expect(await fetchLegalDoctrine()).toEqual(SERVER);
  });

  it("returns null on a non-OK response", async () => {
    stubFetch(async () => ({ ok: false, status: 503, json: async () => ({}) }));
    expect(await fetchLegalDoctrine()).toBeNull();
  });

  it("returns null when a field is missing or empty (no partial replacement)", async () => {
    stubFetch(async () => ({ ok: true, json: async () => ({ ...SERVER, dpa_version: "" }) }));
    expect(await fetchLegalDoctrine()).toBeNull();
    stubFetch(async () => {
      const { privacy_version: _drop, ...partial } = SERVER;
      return { ok: true, json: async () => partial };
    });
    expect(await fetchLegalDoctrine()).toBeNull();
  });

  it("returns null when the fetch itself fails", async () => {
    stubFetch(async () => {
      throw new Error("network down");
    });
    expect(await fetchLegalDoctrine()).toBeNull();
  });
});
