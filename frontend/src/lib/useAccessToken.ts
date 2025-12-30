"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

export type AccessTokenState = {
  token?: string;
  error?: "expired" | "missing";
  status?: number;
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
    if (
      session.error === "RefreshAccessTokenError" ||
      session.error === "RefreshTokenExpired" ||
      session.error === "RefreshTokenMissing"
    ) {
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
    if (res.status === 401) return { error: "expired", status: 401 };
    if (!res.ok) return { error: "missing", status: res.status };
    const json = (await res.json()) as SessionShape;
    if (
      json.error === "RefreshAccessTokenError" ||
      json.error === "RefreshTokenExpired" ||
      json.error === "RefreshTokenMissing"
    ) {
      return { error: "expired", status: res.status };
    }
    if (!json.accessToken) return { error: "missing", status: res.status };
    return { token: json.accessToken, status: res.status };
  } catch {
    return { error: "missing" };
  }
}
