import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeJwt } from "../tests/jwt";
import { App } from "./App";
import { clearAccessToken, setAccessToken } from "./auth/oidc";
import type { ConversationMemory } from "./contracts";

afterEach(() => {
  cleanup();
  clearAccessToken();
  sessionStorage.clear();
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
    // "Fälle"-Sidebar: every conversations/chat call now carries ?case_id=... — match the PATH
    // only (everything before "?"), same as a real router would, not the full querystring.
    const path = url.split("?")[0];
    if (path.endsWith("/framing")) return json({});
    if (path.endsWith("/conversations/current/memory")) return json(memoryRef.current);
    if (path.endsWith("/conversations")) return json({ cases: [] });
    if (path.endsWith("/chat/stream")) return sse();
    if (path.endsWith("/chat")) return json(result);
    return json({});
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

describe("App auth gate (check 5: unauthenticated → re-login)", () => {
  it("with no token, redirects to Keycloak on load (no intermediate login button)", () => {
    clearAccessToken();
    render(<App />);
    expect(sessionStorage.getItem("v2_auth_redirect_at")).not.toBeNull();
    expect(screen.getByTestId("auth-bootstrap")).toBeInTheDocument();
    expect(screen.queryByTestId("login-view")).toBeNull();
    // no dashboard content leaks before auth
    expect(screen.queryByTestId("chat-pane")).toBeNull();
  });

  it("within the redirect window (e.g. a failed exchange), renders the manual login view", () => {
    clearAccessToken();
    sessionStorage.setItem("v2_auth_redirect_at", String(Date.now())); // just redirected → fallback to button
    render(<App />);
    expect(screen.getByTestId("login-view")).toBeInTheDocument();
    expect(screen.getByTestId("login")).toHaveTextContent(/anmelden/i);
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
    const refreshIdx = calls.findIndex(
      (u, i) => i > chatIdx && u.split("?")[0].endsWith("/conversations/current/memory"),
    );
    expect(chatIdx).toBeGreaterThan(-1);
    expect(refreshIdx).toBeGreaterThan(chatIdx); // the re-fetch happens AFTER the turn completed
  });
});

describe("M8: the kernel compute is read on load and refreshed after a chat turn", () => {
  it("fetches /compute on auth and again after a chat turn (panel stays in sync)", async () => {
    const memoryRef = { current: { case_state: [], history: [] } as ConversationMemory };
    const { calls } = stubApi(memoryRef);
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() => expect(calls.some((u) => u.endsWith("/compute"))).toBe(true));
    const before = calls.filter((u) => u.endsWith("/compute")).length;
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    await waitFor(() =>
      expect(calls.filter((u) => u.endsWith("/compute")).length).toBeGreaterThan(before),
    );
  });
});

describe("URL normalization (cutover 1b: nginx try_files serves the SPA for every /dashboard/*)", () => {
  it("normalizes a hard navigation to /dashboard/new (V1's post-login target) to /dashboard/", () => {
    sessionStorage.setItem("v2_auth_redirect_at", String(Date.now())); // skip the auto-redirect → assert resting view
    window.history.pushState({}, "", "/dashboard/new");
    render(<App />);
    expect(window.location.pathname).toBe("/dashboard/");
    expect(screen.getByTestId("login-view")).toBeInTheDocument();
  });

  it("a callback with no code (silent SSO miss) normalizes to /dashboard/ and shows the login view", () => {
    window.history.pushState({}, "", "/dashboard/callback");
    render(<App />);
    expect(window.location.pathname).toBe("/dashboard/");
    expect(screen.getByTestId("login-view")).toBeInTheDocument();
    window.history.pushState({}, "", "/");
  });
});

describe("\"Fälle\"-Sidebar: a hard reload must not lose the current case", () => {
  it("writes the auto-generated caseId into the URL once authed (so a reload finds it)", async () => {
    window.history.pushState({}, "", "/dashboard/"); // no ?case= yet — matches a first-ever visit
    const memoryRef = { current: { case_state: [], history: [] } as ConversationMemory };
    stubApi(memoryRef);
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() => expect(window.location.search).toMatch(/case=[^&]+/));
    window.history.pushState({}, "", "/");
  });

  it("does not overwrite an existing ?case= from the URL (reload keeps the SAME case)", async () => {
    window.history.pushState({}, "", "/dashboard/?case=existing-case-id");
    const memoryRef = { current: { case_state: [], history: [] } as ConversationMemory };
    const { calls } = stubApi(memoryRef);
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() => expect(calls.some((u) => u.includes("case_id=existing-case-id"))).toBe(true));
    expect(window.location.search).toBe("?case=existing-case-id");
    window.history.pushState({}, "", "/");
  });
});


describe('"Fälle"-Sidebar: switching cases never shows a stale case\'s messages (2026-07-04 audit fix)', () => {
  function stubCaseAwareMemory(byCase: Record<string, ConversationMemory>) {
    const fetchFn = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.split("?")[0];
      if (path.endsWith("/framing")) return Promise.resolve(new Response("{}", { status: 200 }));
      if (path.endsWith("/conversations/current/memory")) {
        const caseId = new URL(url, "http://x").searchParams.get("case_id") ?? "case-a";
        // Real network latency: the fetch resolves AFTER the synchronous remount + first paint,
        // which is exactly the window the stale-hydration race lived in.
        return new Promise((resolve) =>
          setTimeout(
            () =>
              resolve(
                new Response(JSON.stringify(byCase[caseId] ?? { case_state: [], history: [] }), {
                  status: 200,
                  headers: { "Content-Type": "application/json" },
                }),
              ),
            20,
          ),
        );
      }
      if (path.endsWith("/conversations")) {
        return Promise.resolve(new Response(JSON.stringify({ cases: [] }), { status: 200 }));
      }
      return Promise.resolve(
        new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } }),
      );
    });
    vi.stubGlobal("fetch", fetchFn);
    return fetchFn;
  }

  it("popstate to a different case shows ONLY that case's messages once its fetch lands — never stuck on the old one", async () => {
    stubCaseAwareMemory({
      "case-a": { case_state: [], history: [{ role: "user", text: "A-ONLY-MESSAGE" }] },
      "case-b": { case_state: [], history: [{ role: "user", text: "B-ONLY-MESSAGE" }] },
    });
    window.history.pushState({}, "", "/dashboard/?case=case-a");
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() => expect(screen.queryByText("A-ONLY-MESSAGE")).toBeInTheDocument());

    window.history.pushState({}, "", "/dashboard/?case=case-b");
    window.dispatchEvent(new PopStateEvent("popstate"));

    await waitFor(() => expect(screen.queryByText("B-ONLY-MESSAGE")).toBeInTheDocument());
    expect(screen.queryByText("A-ONLY-MESSAGE")).not.toBeInTheDocument();
    window.history.pushState({}, "", "/");
  });

  it("selectCase (an actual sidebar click) shows ONLY the newly selected case's messages, never a stale flash that sticks", async () => {
    const fetchFn = stubCaseAwareMemory({
      "case-a": { case_state: [], history: [{ role: "user", text: "A-ONLY-MESSAGE" }] },
      "case-c": { case_state: [], history: [{ role: "user", text: "C-ONLY-MESSAGE" }] },
    });
    // override just the /conversations route so the drawer has a real, clickable case-c entry
    fetchFn.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.split("?")[0];
      if (path.endsWith("/conversations") && !path.includes("/current")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              cases: [{ case_id: "case-c", title: "Fall C", created_at: null, updated_at: null }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (path.endsWith("/framing")) return Promise.resolve(new Response("{}", { status: 200 }));
      if (path.endsWith("/conversations/current/memory")) {
        const caseId = new URL(url, "http://x").searchParams.get("case_id") ?? "case-a";
        const byCase: Record<string, ConversationMemory> = {
          "case-a": { case_state: [], history: [{ role: "user", text: "A-ONLY-MESSAGE" }] },
          "case-c": { case_state: [], history: [{ role: "user", text: "C-ONLY-MESSAGE" }] },
        };
        return new Promise((resolve) =>
          setTimeout(
            () =>
              resolve(
                new Response(JSON.stringify(byCase[caseId] ?? { case_state: [], history: [] }), {
                  status: 200,
                  headers: { "Content-Type": "application/json" },
                }),
              ),
            20,
          ),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } }),
      );
    });
    window.history.pushState({}, "", "/dashboard/?case=case-a");
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() => expect(screen.queryByText("A-ONLY-MESSAGE")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("rail-history"));
    await waitFor(() => expect(screen.getAllByTestId("case-sidebar-item").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByTestId("case-sidebar-item"));

    await waitFor(() => expect(screen.queryByText("C-ONLY-MESSAGE")).toBeInTheDocument());
    expect(screen.queryByText("A-ONLY-MESSAGE")).not.toBeInTheDocument();
    window.history.pushState({}, "", "/");
  });

  it("switching to a genuinely NEW/empty case never inherits the previous case's messages", async () => {
    stubCaseAwareMemory({
      "case-a": { case_state: [], history: [{ role: "user", text: "A-ONLY-MESSAGE" }] },
      // "case-fresh" deliberately absent from byCase -> the stub's default empty history
    });
    window.history.pushState({}, "", "/dashboard/?case=case-a");
    setAccessToken(fakeJwt({ sid: "s1", sub: "u1" }), 3600);
    render(<App />);
    await waitFor(() => expect(screen.queryByText("A-ONLY-MESSAGE")).toBeInTheDocument());

    window.history.pushState({}, "", "/dashboard/?case=case-fresh");
    window.dispatchEvent(new PopStateEvent("popstate"));

    // give the (empty) fetch time to land, then confirm the OLD message never lingers
    await new Promise((r) => setTimeout(r, 60));
    expect(screen.queryByText("A-ONLY-MESSAGE")).not.toBeInTheDocument();
    window.history.pushState({}, "", "/");
  });
});
