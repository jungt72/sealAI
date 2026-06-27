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
  rolesFromToken,
  rpInitiatedLogout,
  type OidcConfig,
} from "./auth/oidc";
import { AdminPane } from "./components/AdminPane";
import { ChatPane } from "./components/ChatPane";
import { Shell } from "./components/Shell";
import type { Briefing, ComputeResponse, ConversationMemory, ParamItem } from "./contracts";
import { FALLBACK_FRAMING, type Framing } from "./framing";
import { FramingContext } from "./framing-context";

const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env ?? {};
// Realm role that unlocks the owner/admin dashboard (matches the backend's auth_admin_role default).
const ADMIN_ROLE = env.VITE_ADMIN_ROLE ?? "admin";
const CONFIG: OidcConfig = {
  issuer: env.VITE_OIDC_ISSUER ?? "https://sealingai.com/realms/sealAI",
  clientId: env.VITE_OIDC_CLIENT_ID ?? "sealai-v2",
  redirectUri: env.VITE_OIDC_REDIRECT_URI ?? `${location.origin}/dashboard/callback`,
  scope: "openid email profile",
  postLogoutRedirectUri: env.VITE_OIDC_POST_LOGOUT_REDIRECT_URI ?? `${location.origin}/dashboard/`,
};

export function App() {
  const [authed, setAuthed] = useState<boolean>(() => getAccessToken() !== null);
  // true while we attempt a one-shot silent SSO re-auth on load (avoids flashing the login view)
  const [bootstrapping, setBootstrapping] = useState<boolean>(() => getAccessToken() === null);
  const [error, setError] = useState<string | null>(null);
  const [framing, setFraming] = useState<Framing>(FALLBACK_FRAMING);
  const [memory, setMemory] = useState<ConversationMemory>({ case_state: [], history: [] });
  // M8 kernel channel: the deterministic compute for the current session (drives the Berechnungen panel)
  const [compute, setCompute] = useState<ComputeResponse | null>(null);
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
  // owner/admin gate — display-only (the backend re-checks the role on every /admin call). When false
  // the dashboard is never rendered AND never offered in the nav.
  const isAdmin = useMemo(
    () => (authed ? rolesFromToken(getAccessToken()).includes(ADMIN_ROLE) : false),
    [authed],
  );
  const [adminView, setAdminView] = useState(false);

  const refreshMemory = useCallback(() => {
    api.memory().then(setMemory).catch(() => undefined);
  }, [api]);

  // M8: the kernel channel is recomputed server-side on every input change; the panel re-reads it
  // here (flush-then-recompute happens on the backend). Fail-quiet — a failed read never blanks the UI.
  const refreshCompute = useCallback(() => {
    api.compute().then(setCompute).catch(() => undefined);
  }, [api]);

  // refresh BOTH projections (chips + kernel panel) after any state change — one call site.
  const refreshState = useCallback(() => {
    refreshMemory();
    refreshCompute();
  }, [refreshMemory, refreshCompute]);

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
    const isCallback = url.pathname.endsWith("/callback");

    // OIDC return — both the explicit login AND the silent prompt=none land on /callback.
    if (isCallback) {
      const code = url.searchParams.get("code");
      if (code) {
        const verifier = sessionStorage.getItem("v2_pkce_verifier") ?? "";
        exchangeCode(CONFIG, code, verifier)
          .then(() => {
            sessionStorage.removeItem("v2_pkce_verifier"); // one-time; token stays in memory
            sessionStorage.removeItem("v2_auth_redirect_at"); // clear the redirect-loop window
            window.history.replaceState({}, "", "/dashboard/");
            setAuthed(true);
          })
          .catch(() => setError("Anmeldung fehlgeschlagen — bitte erneut anmelden."))
          .finally(() => setBootstrapping(false));
        return;
      }
      // No code → the silent attempt found NO live SSO session (error=login_required) or was
      // denied. Do NOT retry (would loop) — fall through to the explicit login view.
      sessionStorage.removeItem("v2_pkce_verifier");
      window.history.replaceState({}, "", "/dashboard/");
      setBootstrapping(false);
      return;
    }

    // Normalize V1-style /dashboard/* paths (nginx try_files serves index.html for all of them).
    if (url.pathname.startsWith("/dashboard") && url.pathname !== "/dashboard/") {
      window.history.replaceState({}, "", "/dashboard/");
    }

    // Already have an in-memory token (e.g. SPA-internal nav) → nothing to do.
    if (getAccessToken()) {
      setBootstrapping(false);
      return;
    }

    // No token and not returning from Keycloak → go straight to the Keycloak authorize endpoint
    // (full flow, not prompt=none). A live SSO session returns a code with NO form → the dashboard
    // appears directly; no session → Keycloak shows its login form directly. This removes the
    // intermediate "Mit Keycloak anmelden" page. Loop guard = a short, SELF-EXPIRING time window
    // (not a sticky flag, which previously got stuck and wrongly showed the button): if we return
    // here tokenless within a few seconds of redirecting (e.g. a failed token exchange), show the
    // manual button instead of re-redirecting. The window clears itself, so the button is only ever
    // a transient failure fallback — never permanently stuck.
    const lastRedirectAt = Number(sessionStorage.getItem("v2_auth_redirect_at") ?? "0");
    if (Date.now() - lastRedirectAt < 8000) {
      setBootstrapping(false);
      return;
    }
    sessionStorage.setItem("v2_auth_redirect_at", String(Date.now()));
    const verifier = randomVerifier();
    const state = randomVerifier();
    sessionStorage.setItem("v2_pkce_verifier", verifier);
    void authorizeUrl(CONFIG, { verifier, state }).then((u) => {
      window.location.href = u;
    });
  }, []);

  useEffect(() => {
    if (authed) refreshState();
  }, [authed, refreshState]);

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
        refreshState();
      }
    },
    [api, refreshState],
  );

  const makeBriefing = useCallback(() => {
    if (!lastMessage) return;
    api.briefing(lastMessage).then(setBriefing).catch(() => setError("Briefing fehlgeschlagen."));
  }, [api, lastMessage]);

  // R2 live preview: the read-only backend kern over the form DRAFT (no settle, no persist). Returns
  // null on failure (the form keeps its values; never a stale number); a working preview clears a
  // prior transient error. The kern owns every number — the client never computes.
  const onPreview = useCallback(
    async (items: ParamItem[]): Promise<ComputeResponse | null> => {
      try {
        const res = await api.previewParams(items);
        setError(null);
        return res;
      } catch {
        setError("Vorschau konnte nicht berechnet werden — bitte erneut versuchen.");
        return null;
      }
    },
    [api],
  );

  const newQuestion = useCallback(() => {
    setError(null);
    setBriefing(null);
    setLastMessage("");
    setConvKey((k) => k + 1);
  }, []);

  if (!authed) {
    if (bootstrapping) {
      return (
        <FramingContext.Provider value={framing}>
          <div className="login" data-testid="auth-bootstrap" aria-busy="true">
            <div className="stage-glow" aria-hidden="true" />
            <h1>
              sealing<span className="brand-sep"> | </span>Intelligence
            </h1>
            <p>Anmeldung wird geprüft …</p>
          </div>
        </FramingContext.Provider>
      );
    }
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
      <Shell
        onLogout={logout}
        onNewQuestion={newQuestion}
        onAdmin={isAdmin ? () => setAdminView(true) : undefined}
      >
        {adminView && isAdmin ? (
          <AdminPane api={api} onClose={() => setAdminView(false)} />
        ) : (
        <ChatPane
          key={convKey}
          onSend={send}
          error={error}
          memory={memory}
          greetingName={greetingName}
          liveStage={liveStage}
          onEditFact={(feld, wert) => {
            const next = window.prompt(`${feld}:`, wert);
            if (next != null) api.editFact(feld, next).then(refreshState).catch(() => undefined);
          }}
          onForgetFact={(feld) => api.forgetFact(feld).then(refreshState).catch(() => undefined)}
          onForgetAll={() => api.forgetAll().then(refreshState).catch(() => undefined)}
          onSubmitParams={async (items, deletes = []) => {
            // R2 „Übernehmen": forget the reconciled (cleared) felder, then batch-settle + recompute
            // server-side; refresh chips + kern panel; return the deterministic confirmation. On
            // failure set the error + rethrow — the form keeps its values, ChatPane appends nothing.
            try {
              await Promise.all(deletes.map((feld) => api.forgetFact(feld)));
              const conf = await api.submitParams(items);
              refreshState();
              return conf;
            } catch (e) {
              setError("Übernehmen fehlgeschlagen — bitte erneut versuchen.");
              throw e;
            }
          }}
          onPreview={onPreview}
          onConfirmUnit={(feld, value) =>
            // confirm the suggested unit → re-settle through the EXISTING edit/settle channel
            // (no new binding path); the backend M8 recompute fires and the kern then computes.
            api.editFact(feld, value).then(refreshState).catch(() => undefined)
          }
          onMakeBriefing={makeBriefing}
          canBriefing={Boolean(lastMessage)}
          briefing={briefing}
          compute={compute}
          onAnfrage={(partnerId, message) => api.anfrage(partnerId, message)}
        />
        )}
      </Shell>
    </FramingContext.Provider>
  );
}
