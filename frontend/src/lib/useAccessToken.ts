"use client";

import { useSession } from "next-auth/react";
import * as React from "react";

/**
 * Liefert das Access Token und den Auth-Status (Client-seitig gecacht).
 */
export function useAccessToken() {
  const { data, status } = useSession();
  const [token, setToken] = React.useState<string | undefined>(undefined);

  React.useEffect(() => {
    if (status === "authenticated") {
      const t =
        (data as any)?.accessToken ??
        (data as any)?.user?.accessToken ??
        (data as any)?.user?.token ??
        (data as any)?.access_token;
      setToken(typeof t === "string" ? t : undefined);
    } else if (status === "unauthenticated") {
      setToken(undefined);
    }
  }, [status, data]);

  return {
    token,
    loading: status === "loading",
    authenticated: status === "authenticated",
  };
}

/**
 * Holt *immer* die frischeste Session-Ansicht vom Server und extrahiert das Access-Token.
 * Nutzt NextAuth `/api/auth/session`. Keine Exceptions nach außen – bei Fehler `undefined`.
 */
export async function fetchFreshAccessToken(): Promise<string | undefined> {
  try {
    const res = await fetch("/api/auth/session", { cache: "no-store" });
    if (!res.ok) return undefined;
    const json = await res.json();
    const t =
      json?.accessToken ??
      json?.user?.accessToken ??
      json?.user?.token ??
      json?.access_token;
    return typeof t === "string" ? t : undefined;
  } catch {
    return undefined;
  }
}
