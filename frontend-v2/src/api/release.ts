export type DashboardReleaseIdentity = {
  releaseId: string;
  sourceGitSha: string;
  artifactSha256: string;
  nodeVersion: string;
  npmVersion: string;
};

const SOURCE_SHA = /^[0-9a-f]{40}([0-9a-f]{24})?$/;
const SHA256 = /^[0-9a-f]{64}$/;

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** Read-only display metadata; deployment eligibility is enforced server-side by GATE-08. */
export async function fetchDashboardReleaseIdentity(
  fetcher: typeof fetch = fetch,
): Promise<DashboardReleaseIdentity | null> {
  try {
    const response = await fetcher("/dashboard/release.json", {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    const value = record(await response.json());
    if (!value) return null;
    const sourceGitSha = value.source_git_sha;
    const artifactSha256 = value.artifact_sha256;
    const releaseId = value.release_id;
    const nodeVersion = value.node_version;
    const npmVersion = value.npm_version;
    if (
      typeof sourceGitSha !== "string" ||
      !SOURCE_SHA.test(sourceGitSha) ||
      typeof artifactSha256 !== "string" ||
      !SHA256.test(artifactSha256) ||
      typeof releaseId !== "string" ||
      releaseId !== `${sourceGitSha}-${artifactSha256}` ||
      typeof nodeVersion !== "string" ||
      nodeVersion.length === 0 ||
      typeof npmVersion !== "string" ||
      npmVersion.length === 0
    ) {
      return null;
    }
    return { releaseId, sourceGitSha, artifactSha256, nodeVersion, npmVersion };
  } catch {
    return null;
  }
}
