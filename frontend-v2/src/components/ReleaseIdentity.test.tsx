import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReleaseIdentity } from "./ReleaseIdentity";

const SOURCE = "a".repeat(40);
const DIGEST = "b".repeat(64);

afterEach(() => vi.unstubAllGlobals());

describe("ReleaseIdentity", () => {
  it("shows the bound commit/digest and links safely to the full evidence", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            release_id: `${SOURCE}-${DIGEST}`,
            source_git_sha: SOURCE,
            artifact_sha256: DIGEST,
            node_version: "v24.15.0",
            npm_version: "11.12.1",
          }),
          { status: 200 },
        ),
      ),
    );

    render(<ReleaseIdentity />);
    const identity = await screen.findByTestId("release-identity");
    expect(identity).toHaveTextContent(SOURCE.slice(0, 12));
    expect(identity).toHaveTextContent(DIGEST.slice(0, 12));
    expect(identity).toHaveAttribute("href", "/dashboard/release.json");
    expect(identity).toHaveAttribute("target", "_blank");
    expect(identity).toHaveAttribute("rel", "noopener noreferrer");
    expect(identity).toHaveAccessibleName(new RegExp(`${SOURCE}.*${DIGEST}`));
  });

  it("renders no unverified identity when the manifest is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 404 })),
    );
    const { container } = render(<ReleaseIdentity />);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    expect(container).toBeEmptyDOMElement();
  });
});
