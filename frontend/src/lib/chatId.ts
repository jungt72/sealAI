/**
 * Utilities for strictly validating and generating UUIDv4 Chat IDs.
 * Pure logic only - no storage side effects.
 */

// Matches UUIDv4: xxxxxxxx-xxxx-4xxx-[89ab]xxx-xxxxxxxxxxxx
const UUID_V4_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function bytesToHex(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i++) out += bytes[i].toString(16).padStart(2, "0");
  return out;
}

function tryGetRandomBytes(n: number): Uint8Array | null {
  const c: any = (globalThis as any).crypto;
  if (c && typeof c.getRandomValues === "function") {
    const arr = new Uint8Array(n);
    c.getRandomValues(arr);
    return arr;
  }
  return null;
}

/**
 * Generates a RFC4122 UUIDv4.
 * - Uses crypto.randomUUID when available.
 * - Else uses crypto.getRandomValues (recommended fallback).
 * - Else uses Math.random (test/dev last resort).
 */
export function generateUuid(): string {
  const c: any = (globalThis as any).crypto;

  // 1) Best: native
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }

  // 2) Recommended fallback: 16 random bytes + set version/variant bits
  const rnd = tryGetRandomBytes(16);
  if (rnd) {
    rnd[6] = (rnd[6] & 0x0f) | 0x40; // version 4
    rnd[8] = (rnd[8] & 0x3f) | 0x80; // variant 10xx
    const hex = bytesToHex(rnd);
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(
      16,
      20
    )}-${hex.slice(20)}`;
  }

  // 3) Last resort: Math.random (non-crypto)
  // Still produces correct v4 format (version/variant set via template).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    const v = ch === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function isUuidV4(id: string): boolean {
  return UUID_V4_REGEX.test(id);
}

export function normalizeChatId(input?: string | null): string {
  return input && isUuidV4(input) ? input : generateUuid();
}
