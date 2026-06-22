/* Phase 1a — components render the RESOLVED framing: the server value when provided, the
 * build-time fallback otherwise (a component outside the provider, or before the fetch resolves,
 * still shows the full framing — the banner can never go blank). */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CLAIM_BOUNDARY, FALLBACK_FRAMING } from "../framing";
import { FramingContext } from "../framing-context";
import { SafetyBanner } from "./SafetyBanner";

afterEach(cleanup);

describe("framing resolution (server-first, fallback-safe)", () => {
  it("renders the server framing when provided", () => {
    const server = { ...FALLBACK_FRAMING, claim_boundary: "Server-Text — Orientierung, keine Freigabe." };
    render(
      <FramingContext.Provider value={server}>
        <SafetyBanner />
      </FramingContext.Provider>,
    );
    expect(screen.getByTestId("claim-boundary")).toHaveTextContent("Server-Text — Orientierung, keine Freigabe.");
  });

  it("renders the fallback outside any provider", () => {
    render(<SafetyBanner />);
    expect(screen.getByTestId("claim-boundary")).toHaveTextContent(CLAIM_BOUNDARY);
  });
});
