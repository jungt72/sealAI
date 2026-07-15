import { useEffect, useState } from "react";

import {
  fetchDashboardReleaseIdentity,
  type DashboardReleaseIdentity,
} from "../api/release";

export function ReleaseIdentity() {
  const [identity, setIdentity] = useState<DashboardReleaseIdentity | null>(null);

  useEffect(() => {
    let mounted = true;
    void fetchDashboardReleaseIdentity().then((value) => {
      if (mounted) setIdentity(value);
    });
    return () => {
      mounted = false;
    };
  }, []);

  if (!identity) return null;
  return (
    <a
      className="release-identity"
      href="/dashboard/release.json"
      role="menuitem"
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Build-Nachweis, Commit ${identity.sourceGitSha}, Artefakt SHA-256 ${identity.artifactSha256}`}
      data-testid="release-identity"
    >
      <span>Build-Nachweis</span>
      <code title={`Commit ${identity.sourceGitSha}`}>{identity.sourceGitSha.slice(0, 12)}</code>
      <code title={`Artefakt SHA-256 ${identity.artifactSha256}`}>
        {identity.artifactSha256.slice(0, 12)}
      </code>
    </a>
  );
}
