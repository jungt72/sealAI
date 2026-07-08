/* Fetches the backend-owned legal-doctrine versions (single source: sealai_v2/core/legal_doctrine.py).
 * No token — the route is public (mirrors api/framing.ts) so the Legal Gate can compare versions
 * before the user has accepted anything. Returns null on ANY failure so the caller can fail safe
 * (treat as "not yet known" rather than silently accepting stale/guessed versions). */

export interface LegalDoctrine {
  terms_version: string;
  privacy_version: string;
  dpa_version: string;
  product_purpose_doctrine: string;
}

const FIELDS: ReadonlyArray<keyof LegalDoctrine> = [
  "terms_version",
  "privacy_version",
  "dpa_version",
  "product_purpose_doctrine",
];

export async function fetchLegalDoctrine(base = "/api/v2"): Promise<LegalDoctrine | null> {
  try {
    const res = await fetch(`${base}/legal/doctrine`);
    if (!res.ok) return null;
    const body = (await res.json()) as Record<string, unknown>;
    const doctrine = {} as Record<keyof LegalDoctrine, string>;
    for (const field of FIELDS) {
      const value = body[field];
      if (typeof value !== "string" || value.length === 0) return null;
      doctrine[field] = value;
    }
    return doctrine;
  } catch {
    return null;
  }
}
