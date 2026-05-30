import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIsMobile } from "@/hooks/useIsMobile";

function Probe() {
  const isMobile = useIsMobile();
  return <div data-testid="value">{isMobile ? "mobile" : "desktop"}</div>;
}

function installMatchMedia(initialMatches: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  const mql = {
    matches: initialMatches,
    media: "(max-width: 1023px)",
    onchange: null,
    addEventListener: (_type: string, cb: (event: MediaQueryListEvent) => void) =>
      listeners.add(cb),
    removeEventListener: (_type: string, cb: (event: MediaQueryListEvent) => void) =>
      listeners.delete(cb),
    addListener: (cb: (event: MediaQueryListEvent) => void) => listeners.add(cb),
    removeListener: (cb: (event: MediaQueryListEvent) => void) => listeners.delete(cb),
    dispatchEvent: () => true,
  };
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia;
  return {
    fire(matches: boolean) {
      mql.matches = matches;
      listeners.forEach((cb) => cb({ matches } as MediaQueryListEvent));
    },
  };
}

afterEach(() => {
  // Restore jsdom default (no matchMedia).
  // @ts-expect-error - intentional cleanup
  delete window.matchMedia;
  vi.restoreAllMocks();
});

describe("useIsMobile", () => {
  it("stays desktop (false) when matchMedia is unavailable (SSR-safe default)", () => {
    render(<Probe />);
    expect(screen.getByTestId("value")).toHaveTextContent("desktop");
  });

  it("reflects a matching media query after mount", async () => {
    installMatchMedia(true);
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("mobile"));
  });

  it("updates when the media query changes", async () => {
    const mm = installMatchMedia(false);
    render(<Probe />);
    expect(screen.getByTestId("value")).toHaveTextContent("desktop");
    mm.fire(true);
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("mobile"));
  });
});
