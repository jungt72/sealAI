/* Fetches the backend-owned safety-framing (single source: sealai_v2/core/framing.py). No token —
 * the route is public so the framing renders pre-login. Returns null on ANY failure or partial
 * payload, so the caller keeps FALLBACK_FRAMING and the framing is never blank or half-replaced. */

import type { Framing } from "../framing";

const FIELDS: ReadonlyArray<keyof Framing> = [
  "claim_boundary",
  "vorlaeufig",
  "remembered_hint",
  "candidate",
  "geltungsrahmen",
];

export async function fetchFraming(base = "/api/v2"): Promise<Framing | null> {
  try {
    const res = await fetch(`${base}/framing`);
    if (!res.ok) return null;
    const body = (await res.json()) as Record<string, unknown>;
    const framing = {} as Record<keyof Framing, string>;
    for (const field of FIELDS) {
      const value = body[field];
      if (typeof value !== "string" || value.length === 0) return null;
      framing[field] = value;
    }
    return framing;
  } catch {
    return null;
  }
}
