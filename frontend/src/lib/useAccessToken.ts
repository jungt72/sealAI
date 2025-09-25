"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

/**
 * Liefert direkt den Token-String (oder undefined).
 * Zieht bevorzugt accessToken, fällt ansonsten auf idToken & Varianten zurück.
 */
export function useAccessToken(): string | undefined {
  const { data, status } = useSession();
  const [token, setToken] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (status !== "authenticated") {
      setToken(undefined);
      return;
    }
    const s: any = data || {};
    const t =
      s.accessToken ??
      s.idToken ??
      s.user?.accessToken ??
      s.user?.token ??
      s.access_token;
    setToken(typeof t === "string" && t.length > 0 ? t : undefined);
  }, [status, data]);

  return token;
}

/**
 * Holt immer die frischeste Session-Ansicht vom Server
 * und extrahiert den Token-String (accessToken/idToken/Fallbacks).
 */
export async function fetchFreshAccessToken(): Promise<string | undefined> {
  try {
    const res = await fetch("/api/auth/session", { cache: "no-store" });
    if (!res.ok) return undefined;
    const json: any = await res.json();
    const t =
      json?.accessToken ??
      json?.idToken ??
      json?.user?.accessToken ??
      json?.user?.token ??
      json?.access_token;
    return typeof t === "string" && t.length > 0 ? t : undefined;
  } catch {
    return undefined;
  }
}
