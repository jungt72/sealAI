import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeJwt } from "../tests/jwt";
import { App } from "./App";
import { clearAccessToken, setAccessToken } from "./auth/oidc";
import type { ConversationMemory } from "./contracts";

afterEach(() => {
  cleanup();
  clearAccessToken();
  vi.unstubAllGlobals();
});

/** Route-aware fetch stub for the authed App: framing (public), memory, chat. `memoryRef.current`
 * is read FRESH on every memory call, so a test can change what the server "knows" mid-flight. */
function stubApi(memoryRef: { current: ConversationMemory }) {
  const calls: string[] = [];
  const json = (body: unknown) =>
    Promise.resolve(
      new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
  const result = { answer: "ok", model: "m", grounded: true, intent: null, citations: [] };
  const sse = () => {
    const enc = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(enc.encode('event: stage\ndata: {"stage":"generate","status":"start"}\n\n'));
        c.enqueue(enc.encode(`event: result\ndata: ${JSON.stringify(result)}\n\n`));
        c.close();
      },
    });
    return Promise.resolve(
      new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
  };
  const fn = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    if (url.endsWith("/framing")) return json({});
    if (url.endsWith("/conversations/current/memory")) return json(memoryRef.current);
    if (url.endsWith("/chat/stream")) return sse();
    if (url.endsWith("/chat")) return json(result);
    return json({});
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

describe("App auth gate (check 5: unauthenticated → re-login)", () => {
  it("with no in-memory token, renders the login view (not the dashboard)", () => {
    clearAccessToken();
    render(<App />);
    expect(screen.getByTestId("login-view")).toBeInTheDocument();
    expect(screen.getByTestId("login")).toHaveTextContent(/anmelden/i);
    // no dashboard content leaks before auth
    expect(screen.queryByTestId("chat-pane")).toBeNull();
  });
});

describe("Part 2: greeting name from the session token's given_name claim", () => {
  it("greets with the given name when the claim is present", async () => {
    stubApi({ current: { case_state: [], history: [] } });
    setAccessToken(fakeJwt({ given_name: "Thorsten", sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() =>
      expect(screen.getByTestId("greeting")).toHaveTextContent("Welche Dichtungsfrage steht an, Thorsten?"),
    );
  });

  it("falls back to the nameless greeting when the claim is absent", async () => {
    stubApi({ current: { case_state: [], history: [] } });
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() =>
      expect(screen.getByTestId("greeting")).toHaveTextContent("Welche Dichtungsfrage steht an?"),
    );
  });
});

describe("Fix A: fact chips refresh after each chat turn (no reload)", () => {
  it("re-fetches conversation memory after a chat turn and renders the new chips", async () => {
    const memoryRef = { current: { case_state: [], history: [] } as ConversationMemory };
    const { calls } = stubApi(memoryRef);
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-pane")).toBeInTheDocument());
    expect(screen.queryByTestId("memory-panel")).toBeNull(); // fresh: no chips

    // the server distills a fact during the turn; the next memory fetch sees it
    memoryRef.current = {
      case_state: [{ feld: "medium", wert: "Hydrauliköl", provenance: "distilled-from-conversation" }],
      history: [],
    };
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "HLP 46, 80 °C" } });
    fireEvent.click(screen.getByTestId("composer-send"));

    // chips appear without any reload/remount — memory was re-fetched after the turn resolved
    await waitFor(() => expect(screen.getByTestId("remembered-fact")).toHaveTextContent("Hydrauliköl"));
    const chatIdx = calls.findIndex((u) => u.endsWith("/chat/stream") || u.endsWith("/chat"));
    const refreshIdx = calls.findIndex((u, i) => i > chatIdx && u.endsWith("/conversations/current/memory"));
    expect(chatIdx).toBeGreaterThan(-1);
    expect(refreshIdx).toBeGreaterThan(chatIdx); // the re-fetch happens AFTER the turn completed
  });
});

describe("URL normalization (cutover 1b: nginx try_files serves the SPA for every /dashboard/*)", () => {
  it("normalizes a hard navigation to /dashboard/new (V1's post-login target) to /dashboard/", () => {
    window.history.pushState({}, "", "/dashboard/new");
    render(<App />);
    expect(window.location.pathname).toBe("/dashboard/");
    expect(screen.getByTestId("login-view")).toBeInTheDocument();
  });

  it("leaves the OIDC callback path untouched", () => {
    window.history.pushState({}, "", "/dashboard/callback");
    render(<App />);
    expect(window.location.pathname).toBe("/dashboard/callback");
    window.history.pushState({}, "", "/");
  });
});
