// frontend/src/lib/authz.ts
export type RoleParseResult = {
  roles: string[];
  roleSet: Set<string>;
};

/**
 * Extracts roles from a Keycloak access token.
 *
 * Supported claim shapes:
 * - realm_access.roles: string[]
 * - resource_access[clientId].roles: string[]
 * - roles: string[] (fallback)
 */
export function getRolesFromAccessToken(accessToken?: string | null): RoleParseResult {
  const empty: RoleParseResult = { roles: [], roleSet: new Set() };
  if (!accessToken) return empty;

  const parts = accessToken.split(".");
  if (parts.length < 2) return empty;

  try {
    // base64url decode
    const payloadB64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const pad = payloadB64.length % 4;
    const padded = pad ? payloadB64 + "=".repeat(4 - pad) : payloadB64;

    const json = Buffer.from(padded, "base64").toString("utf8");
    const payload = JSON.parse(json) as any;

    const roles: string[] = [];

    // realm roles
    const realmRoles = payload?.realm_access?.roles;
    if (Array.isArray(realmRoles)) roles.push(...realmRoles);

    // client roles (collect all clients)
    const ra = payload?.resource_access;
    if (ra && typeof ra === "object") {
      for (const v of Object.values(ra)) {
        const r = (v as any)?.roles;
        if (Array.isArray(r)) roles.push(...r);
      }
    }

    // fallback
    const topRoles = payload?.roles;
    if (Array.isArray(topRoles)) roles.push(...topRoles);

    const uniq = Array.from(new Set(roles.filter((x) => typeof x === "string" && x.length > 0)));
    return { roles: uniq, roleSet: new Set(uniq) };
  } catch {
    return empty;
  }
}
