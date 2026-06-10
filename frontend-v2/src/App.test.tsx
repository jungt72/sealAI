import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { clearAccessToken } from "./auth/oidc";

afterEach(() => {
  cleanup();
  clearAccessToken();
});

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
