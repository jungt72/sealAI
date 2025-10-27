"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

type MaybeSession = Record<string, unknown> | null | undefined;

function pickToken(source: MaybeSession): string | undefined {
  if (!source || typeof source !== "object") return undefined;
  const candidates = [
    (source as Record<string, unknown>).accessToken,
    (source as Record<string, unknown>).idToken,
    (source as Record<string, unknown>).access_token,
    (source as Record<string, unknown>).token,
    (source as Record<string, unknown>).user && (source as Record<string, unknown>).user as Record<string, unknown>,
  ];
  for (const candidate of candidates) {
    if (candidate && typeof candidate === "string" && candidate.length > 0) {
      return candidate;
    }
    if (candidate && typeof candidate === "object") {
      const nested = pickToken(candidate as MaybeSession);
      if (nested) return nested;
    }
  }
  return undefined;
}

export function useAccessToken(): string | undefined {
  const { data, status } = useSession();
  const [token, setToken] = useState<string | undefined>();

  useEffect(() => {
    if (status !== "authenticated") {
      setToken(undefined);
      return;
    }
    setToken(pickToken(data));
  }, [status, data]);

  return token;
}

export async function fetchFreshAccessToken(): Promise<string | undefined> {
  try {
    const res = await fetch("/api/auth/session", { cache: "no-store" });
    if (!res.ok) return undefined;
    const json = (await res.json()) as MaybeSession;
    return pickToken(json);
  } catch {
    return undefined;
  }
}
