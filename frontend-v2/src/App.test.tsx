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
