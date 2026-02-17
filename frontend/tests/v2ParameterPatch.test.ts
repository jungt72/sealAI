import { describe, expect, it, vi, afterEach } from "vitest";
import {
  fetchV2StateParameters,
  patchV2ParametersAndFetchState,
} from "../src/lib/v2ParameterPatch";

describe("v2 parameter patch helpers", () => {
  afterEach(() => {
    vi.useRealTimers();
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
      parameters: { medium: "oil", pressure_bar: 2 },
      baseVersions: { medium: 3, pressure_bar: 7, ignored: 9 },
    });

    expect(params).toEqual({ medium: "oil" });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const [patchUrl, patchInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(patchUrl).toBe("/api/v1/langgraph/parameters/patch");
    expect(patchInit.method).toBe("POST");
    expect(toHeaderObject(patchInit.headers)).toMatchObject({
      "content-type": "application/json",
      authorization: "Bearer token-abc",
    });
    expect(patchInit.body).toBe(
      JSON.stringify({
        chat_id: "chat-123",
        parameters: { medium: "oil", pressure_bar: 2 },
        base_versions: { medium: 3, pressure_bar: 7 },
      })
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

  it("does not retry when state endpoint returns 404 state_not_found", async () => {
    const stateMissingResponse = {
      ok: false,
      status: 404,
      headers: new Headers(),
      json: () => Promise.resolve({ detail: { code: "state_not_found", message: "missing checkpoint" } }),
      text: () => Promise.resolve(""),
    } as unknown as Response;

    const fetchMock = vi.fn().mockResolvedValueOnce(stateMissingResponse);
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchV2StateParameters({
      chatId: "chat-missing",
      token: "token-xyz",
    });

    await expect(promise).rejects.toMatchObject({
      status: 404,
      code: "state_not_found",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries 429 with Retry-After delay instead of tight-looping", async () => {
    vi.useFakeTimers();
    const rateLimitedResponse = {
      ok: false,
      status: 429,
      headers: new Headers({ "Retry-After": "2" }),
      json: () => Promise.resolve({ detail: { message: "rate limited" } }),
      text: () => Promise.resolve(""),
    } as unknown as Response;
    const okResponse = {
      ok: true,
      status: 200,
      headers: new Headers(),
      json: () => Promise.resolve({ parameters: { medium: "oil" } }),
      text: () => Promise.resolve(""),
    } as unknown as Response;

    const fetchMock = vi.fn().mockResolvedValueOnce(rateLimitedResponse).mockResolvedValueOnce(okResponse);
    vi.stubGlobal("fetch", fetchMock);

    const pending = fetchV2StateParameters({
      chatId: "chat-429",
      token: "token-xyz",
    });
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1999);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toEqual({ medium: "oil" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry on 401 session_expired and surfaces auth code", async () => {
    vi.useFakeTimers();
    const expiredResponse = {
      ok: false,
      status: 401,
      headers: new Headers(),
      json: () => Promise.resolve({ detail: "session_expired" }),
      text: () => Promise.resolve(""),
    } as unknown as Response;

    const fetchMock = vi.fn().mockResolvedValueOnce(expiredResponse);
    vi.stubGlobal("fetch", fetchMock);

    const pending = fetchV2StateParameters({
      chatId: "chat-expired",
      token: "token-expired",
    });

    await expect(pending).rejects.toMatchObject({
      status: 401,
      code: "session_expired",
    });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not call state endpoint when token is missing", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchV2StateParameters({
        chatId: "chat-no-token",
        token: "",
      }),
    ).rejects.toMatchObject({
      status: 401,
      code: "missing_token",
    });

    expect(fetchMock).toHaveBeenCalledTimes(0);
  });

  it("enforces a minimum polling interval between consecutive state fetches", async () => {
    vi.useFakeTimers();
    const responseA = {
      ok: true,
      status: 200,
      headers: new Headers(),
      json: () => Promise.resolve({ parameters: { medium: "oil" } }),
      text: () => Promise.resolve(""),
    } as unknown as Response;
    const responseB = {
      ok: true,
      status: 200,
      headers: new Headers(),
      json: () => Promise.resolve({ parameters: { medium: "water" } }),
      text: () => Promise.resolve(""),
    } as unknown as Response;

    const fetchMock = vi.fn().mockResolvedValueOnce(responseA).mockResolvedValueOnce(responseB);
    vi.stubGlobal("fetch", fetchMock);

    const first = fetchV2StateParameters({
      chatId: "chat-min-interval",
      token: "token-1",
    });
    await expect(first).resolves.toEqual({ medium: "oil" });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const second = fetchV2StateParameters({
      chatId: "chat-min-interval",
      token: "token-1",
    });
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1999);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1);
    await expect(second).resolves.toEqual({ medium: "water" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
