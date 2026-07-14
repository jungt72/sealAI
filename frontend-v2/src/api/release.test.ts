import { describe, expect, it, vi } from "vitest";

import { fetchDashboardReleaseIdentity } from "./release";

const SOURCE = "a".repeat(40);
const DIGEST = "b".repeat(64);

describe("dashboard release identity", () => {
  it("accepts a commit/digest-bound canonical identity and bypasses caches", async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({
          release_id: `${SOURCE}-${DIGEST}`,
          source_git_sha: SOURCE,
          artifact_sha256: DIGEST,
          node_version: "v24.15.0",
          npm_version: "11.12.1",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(fetchDashboardReleaseIdentity(fetcher)).resolves.toEqual({
      releaseId: `${SOURCE}-${DIGEST}`,
      sourceGitSha: SOURCE,
      artifactSha256: DIGEST,
      nodeVersion: "v24.15.0",
      npmVersion: "11.12.1",
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/dashboard/release.json",
      expect.objectContaining({ cache: "no-store", credentials: "same-origin" }),
    );
  });

  it("fails quiet for a mismatched release id or an unavailable manifest", async () => {
    const mismatched = vi.fn(async () =>
      new Response(
        JSON.stringify({
          release_id: `${SOURCE}-${"c".repeat(64)}`,
          source_git_sha: SOURCE,
          artifact_sha256: DIGEST,
          node_version: "v24.15.0",
          npm_version: "11.12.1",
        }),
        { status: 200 },
      ),
    );
    await expect(fetchDashboardReleaseIdentity(mismatched)).resolves.toBeNull();
    await expect(
      fetchDashboardReleaseIdentity(vi.fn(async () => new Response(null, { status: 404 }))),
    ).resolves.toBeNull();
  });
});
