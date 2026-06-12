import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiClient } from "./api/client";
import { fetchFraming } from "./api/framing";
import {
  authorizeUrl,
  clearAccessToken,
  exchangeCode,
  getAccessToken,
  givenNameFromToken,
  randomVerifier,
  rpInitiatedLogout,
  type OidcConfig,
} from "./auth/oidc";
import { ChatPane } from "./components/ChatPane";
import { Shell } from "./components/Shell";
import type { Briefing, ConversationMemory } from "./contracts";
import { FALLBACK_FRAMING, type Framing } from "./framing";
import { FramingContext } from "./framing-context";

const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env ?? {};
const CONFIG: OidcConfig = {
  issuer: env.VITE_OIDC_ISSUER ?? "https://sealingai.com/realms/sealAI",
  clientId: env.VITE_OIDC_CLIENT_ID ?? "sealai-v2",
  redirectUri: env.VITE_OIDC_REDIRECT_URI ?? `${location.origin}/dashboard/callback`,
  scope: "openid email profile",
  postLogoutRedirectUri: env.VITE_OIDC_POST_LOGOUT_REDIRECT_URI ?? `${location.origin}/dashboard/`,
};

export function App() {
  const [authed, setAuthed] = useState<boolean>(() => getAccessToken() !== null);
  const [error, setError] = useState<string | null>(null);
  const [framing, setFraming] = useState<Framing>(FALLBACK_FRAMING);
  const [memory, setMemory] = useState<ConversationMemory>({ case_state: [], history: [] });
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [lastMessage, setLastMessage] = useState<string>("");
  // bumping the key remounts ChatPane → fresh conversation view; server-side memory is untouched
  const [convKey, setConvKey] = useState(0);
  // P4b: latest stage-start from the /chat/stream progress frames (keys only; labels in ChatPane)
  const [liveStage, setLiveStage] = useState<string | null>(null);

  // 401/expiry path: LOCAL clear + re-login only — must NOT end the Keycloak SSO session
  const onUnauthenticated = useCallback(() => {
    clearAccessToken();
    setAuthed(false);
  }, []);

  // explicit Abmelden: RP-initiated logout — clear local tokens, then end the SSO session at Keycloak
  const logout = useCallback(() => {
    setAuthed(false);
    rpInitiatedLogout(CONFIG);
  }, []);
  const api = useMemo(() => new ApiClient(getAccessToken, onUnauthenticated), [onUnauthenticated]);
  // greeting name from the session token's given_name claim — display-only, never logged (PII)
  const greetingName = useMemo(() => (authed ? givenNameFromToken(getAccessToken()) : null), [authed]);

  const refreshMemory = useCallback(() => {
    api.memory().then(setMemory).catch(() => undefined);
  }, [api]);

  useEffect(() => {
    // Single backend-owned framing source; on any failure the fallback stays (never blank).
    let cancelled = false;
    fetchFraming().then((f) => {
      if (f && !cancelled) setFraming(f);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    // The SPA has no sub-routes: nginx serves index.html for every /dashboard/* path (try_files),
    // e.g. V1's post-login /dashboard/new. Normalize everything except the OIDC callback so the
    // address bar matches what the app actually renders.
    if (
      url.pathname.startsWith("/dashboard") &&
      url.pathname !== "/dashboard/" &&
      !url.pathname.endsWith("/callback")
    ) {
      window.history.replaceState({}, "", "/dashboard/");
    }
    if (url.pathname.endsWith("/callback") && url.searchParams.get("code")) {
      const code = url.searchParams.get("code") as string;
      const verifier = sessionStorage.getItem("v2_pkce_verifier") ?? "";
      exchangeCode(CONFIG, code, verifier)
        .then(() => {
          sessionStorage.removeItem("v2_pkce_verifier"); // PKCE verifier is one-time; token stays in memory
          window.history.replaceState({}, "", "/dashboard");
          setAuthed(true);
        })
        .catch(() => setError("Anmeldung fehlgeschlagen — bitte erneut anmelden."));
    }
  }, []);

  useEffect(() => {
    if (authed) refreshMemory();
  }, [authed, refreshMemory]);

  const login = useCallback(async () => {
    const verifier = randomVerifier();
    const state = randomVerifier();
    sessionStorage.setItem("v2_pkce_verifier", verifier);
    window.location.href = await authorizeUrl(CONFIG, { verifier, state });
  }, []);

  const send = useCallback(
    async (message: string) => {
      setError(null);
      setLastMessage(message);
      try {
        return await api.chatStream(message, setLiveStage);
      } catch (e) {
        setError("Es ist ein Fehler aufgetreten — bitte erneut versuchen.");
        throw e;
      } finally {
        setLiveStage(null);
        refreshMemory();
      }
    },
    [api, refreshMemory],
  );

  const makeBriefing = useCallback(() => {
    if (!lastMessage) return;
    api.briefing(lastMessage).then(setBriefing).catch(() => setError("Briefing fehlgeschlagen."));
  }, [api, lastMessage]);

  const newQuestion = useCallback(() => {
    setError(null);
    setBriefing(null);
    setLastMessage("");
    setConvKey((k) => k + 1);
  }, []);

  if (!authed) {
    return (
      <FramingContext.Provider value={framing}>
        <div className="login" data-testid="login-view">
          <div className="stage-glow" aria-hidden="true" />
          <h1>
            sealing<span className="brand-sep"> | </span>Intelligence
          </h1>
          <button onClick={() => void login()} data-testid="login">
            Mit Keycloak anmelden
          </button>
          {error && <p role="alert">{error}</p>}
        </div>
      </FramingContext.Provider>
    );
  }

  return (
    <FramingContext.Provider value={framing}>
      <Shell onLogout={logout} onNewQuestion={newQuestion}>
        <ChatPane
          key={convKey}
          onSend={send}
          error={error}
          memory={memory}
          greetingName={greetingName}
          liveStage={liveStage}
          onEditFact={(feld, wert) => {
            const next = window.prompt(`${feld}:`, wert);
            if (next != null) api.editFact(feld, next).then(refreshMemory).catch(() => undefined);
          }}
          onForgetFact={(feld) => api.forgetFact(feld).then(refreshMemory).catch(() => undefined)}
          onForgetAll={() => api.forgetAll().then(refreshMemory).catch(() => undefined)}
          onSubmitParam={(feld, wert) =>
            api.editFact(feld, wert, "user-form").then(refreshMemory).catch(() => undefined)
          }
          onMakeBriefing={makeBriefing}
          canBriefing={Boolean(lastMessage)}
          briefing={briefing}
        />
      </Shell>
    </FramingContext.Provider>
  );
}
