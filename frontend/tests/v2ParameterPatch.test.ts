import { describe, expect, it, vi, afterEach } from "vitest";
import { fetchV2StateParameters, patchV2ParametersAndFetchState } from "../src/lib/v2ParameterPatch";

describe("v2 parameter patch helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const toHeaderObject = (headers: RequestInit["headers"]) => {
    if (!headers) return {};
    const raw = headers instanceof Headers ? Object.fromEntries(headers.entries()) : headers;
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(raw || {})) {
      out[key.toLowerCase()] = String(value);
    }
    return out;
  };

  it("patches with chat_id and refreshes state", async () => {
    const patchResponse = {
      ok: true,
      status: 200,
      text: () => Promise.resolve(""),
    } as unknown as Response;

    const stateResponse = {
      ok: true,
      status: 200,
      json: () => Promise.resolve({ parameters: { medium: "oil" } }),
      text: () => Promise.resolve(""),
    } as unknown as Response;

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(patchResponse)
      .mockResolvedValueOnce(stateResponse);

    vi.stubGlobal("fetch", fetchMock);

    const params = await patchV2ParametersAndFetchState({
      chatId: "chat-123",
      token: "token-abc",
      parameters: { medium: "oil" },
    });

    expect(params).toEqual({ medium: "oil" });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const [patchUrl, patchInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(patchUrl).toBe("/api/langgraph/parameters/patch");
    expect(patchInit.method).toBe("POST");
    expect(toHeaderObject(patchInit.headers)).toMatchObject({
      "content-type": "application/json",
      authorization: "Bearer token-abc",
    });
    expect(patchInit.body).toBe(
      JSON.stringify({ chat_id: "chat-123", parameters: { medium: "oil" } })
    );

    const [stateUrl, stateInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(stateUrl).toBe("/api/langgraph/state?thread_id=chat-123");
    expect(stateInit.method).toBe("GET");
    expect(toHeaderObject(stateInit.headers)).toMatchObject({
      authorization: "Bearer token-abc",
    });
  });

  it("refreshes state parameters for the given chat_id", async () => {
    const stateResponse = {
      ok: true,
      status: 200,
      json: () => Promise.resolve({ parameters: { pressure_bar: 2, medium: "oil" } }),
      text: () => Promise.resolve(""),
    } as unknown as Response;

    const fetchMock = vi.fn().mockResolvedValueOnce(stateResponse);
    vi.stubGlobal("fetch", fetchMock);

    const params = await fetchV2StateParameters({
      chatId: "chat-456",
      token: "token-xyz",
    });

    expect(params).toEqual({ pressure_bar: 2, medium: "oil" });
    const [stateUrl, stateInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(stateUrl).toBe("/api/langgraph/state?thread_id=chat-456");
    expect(stateInit.method).toBe("GET");
    expect(toHeaderObject(stateInit.headers)).toMatchObject({
      authorization: "Bearer token-xyz",
    });
  });
});
