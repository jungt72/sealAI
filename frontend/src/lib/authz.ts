export type TokenRoles = {
  roles: string[];
  roleSet: Set<string>;
};

const decodeBase64Url = (value: string): string => {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
  if (typeof window === "undefined") {
    return Buffer.from(padded, "base64").toString("utf-8");
  }
  return atob(padded);
};

const extractRoles = (payload: any): string[] => {
  const roles: string[] = [];
  const realmRoles = payload?.realm_access?.roles;
  if (Array.isArray(realmRoles)) {
    roles.push(...realmRoles.map((r) => String(r)));
  }
  const resource = payload?.resource_access;
  if (resource && typeof resource === "object") {
    for (const entry of Object.values(resource)) {
      const entryRoles = (entry as any)?.roles;
      if (Array.isArray(entryRoles)) {
        roles.push(...entryRoles.map((r) => String(r)));
      }
    }
  }
  return roles;
};

export const getRolesFromAccessToken = (token?: string): TokenRoles => {
  if (!token) return { roles: [], roleSet: new Set() };
  const parts = token.split(".");
  if (parts.length < 2) return { roles: [], roleSet: new Set() };
  try {
    const payload = JSON.parse(decodeBase64Url(parts[1]));
    const roles = extractRoles(payload);
    return { roles, roleSet: new Set(roles) };
  } catch {
    return { roles: [], roleSet: new Set() };
  }
};

export const hasKnowledgeAccess = (token?: string): boolean => {
  const { roleSet } = getRolesFromAccessToken(token);
  return roleSet.has("admin");
};
