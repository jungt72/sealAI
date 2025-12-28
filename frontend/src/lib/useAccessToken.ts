"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

export type AccessTokenState = {
  token?: string;
  error?: "expired" | "missing";
};

type SessionShape = {
  accessToken?: string | null;
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
    if (session.error === "RefreshAccessTokenError") {
      setState({ error: "expired" });
      return;
    }
    const token = session.accessToken ?? undefined;
    if (!token) {
      setState({ error: "missing" });
      return;
    }
    setState({ token });
  }, [status, data]);

  return state;
}

export async function fetchFreshAccessToken(): Promise<AccessTokenState> {
  try {
    const res = await fetch("/api/auth/session", { cache: "no-store" });
    if (!res.ok) return { error: "missing" };
    const json = (await res.json()) as SessionShape;
    if (json.error === "RefreshAccessTokenError") return { error: "expired" };
    if (!json.accessToken) return { error: "missing" };
    return { token: json.accessToken };
  } catch {
    return { error: "missing" };
  }
}
