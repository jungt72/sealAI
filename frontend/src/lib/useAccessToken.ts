"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

export type AccessTokenState = {
  token?: string;
  error?: "expired" | "missing";
  status?: number;
};

type SessionShape = {
  error?: string | null;
};

export function useAccessToken(): AccessTokenState {
  const { data, status } = useSession();
  const [state, setState] = useState<AccessTokenState>({ error: "missing" });

  useEffect(() => {
    if (status !== "authenticated") {
      setState({ error: "missing" });
      return;
    }
    const session = (data || {}) as SessionShape;
    if (
      session.error === "RefreshAccessTokenError" ||
      session.error === "RefreshTokenExpired" ||
      session.error === "RefreshTokenMissing"
    ) {
      setState({ error: "expired" });
      return;
    }
    let active = true;
    void fetchFreshAccessToken().then((fresh) => {
      if (!active) return;
      if (fresh.token) {
        setState({ token: fresh.token });
        return;
      }
      setState({ error: fresh.error ?? "missing", status: fresh.status });
    });
    return () => {
      active = false;
    };
  }, [status, data]);

  return state;
}

export async function fetchFreshAccessToken(): Promise<AccessTokenState> {
  try {
    const res = await fetch("/api/auth/access-token", { cache: "no-store" });
    if (res.status === 401) return { error: "expired", status: 401 };
    if (!res.ok) return { error: "missing", status: res.status };
    const json = (await res.json()) as { accessToken?: string };
    if (!json.accessToken) return { error: "missing", status: res.status };
    return { token: json.accessToken, status: res.status };
  } catch {
    return { error: "missing" };
  }
}
