import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiClient } from "./api/client";
import { fetchFraming } from "./api/framing";
import {
  authorizeUrl,
  clearAccessToken,
  exchangeCode,
  getAccessToken,
  givenNameFromToken,
  herstellerIdFromToken,
  msUntilExpiry,
  randomVerifier,
  refreshTokens,
  rolesFromToken,
  rpInitiatedLogout,
  type OidcConfig,
} from "./auth/oidc";
import { AdminPane } from "./components/AdminPane";
import { ChatPane } from "./components/ChatPane";
import { LegalGate } from "./components/LegalGate";
import { PartnerSelfPane } from "./components/PartnerSelfPane";
import { Shell } from "./components/Shell";
import type { Briefing, CaseSummary, ComputeResponse, ConversationMemory, ParamItem } from "./contracts";
import { FALLBACK_FRAMING, type Framing } from "./framing";
import { FramingContext } from "./framing-context";
import {
  getCaseIdFromUrl,
  newCaseId,
  setCaseIdInUrl,
  stashCaseIdForAuthRedirect,
  takeStashedCaseId,
} from "./lib/caseId";
import { downloadBriefingPdf } from "./lib/pdf";

const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env ?? {};
// Realm role that unlocks the owner/admin dashboard (matches the backend's auth_admin_role default).
const ADMIN_ROLE = env.VITE_ADMIN_ROLE ?? "admin";
// Realm role for the manufacturer self-service dashboard (matches auth_manufacturer_role default).
const MANUFACTURER_ROLE = env.VITE_MANUFACTURER_ROLE ?? "manufacturer";
// Legal-by-Design (Phase B): mirrors the backend's SEALAI_V2_LEGAL_GATE_ENABLED — both default OFF
// until the draft legal texts have had an attorney review pass (see docs/legal-onboarding.md). OFF
// here means this component is never mounted at all — byte-identical to before this patch.
const LEGAL_GATE_ENABLED = env.VITE_LEGAL_GATE_ENABLED === "true";
// A stable, reusable empty value for resetting `memory` the instant a case switch happens (see
// every setMemory(EMPTY_MEMORY) call below) — module-level so it's one constant reference, not a
// fresh object literal (and therefore a fresh render trigger) on every call site.
const EMPTY_MEMORY: ConversationMemory = { case_state: [], history: [] };
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
  // "Fälle"-Sidebar: the active case, persisted in the URL (?case=) so a hard reload keeps it —
  // generated client-side on first load if the URL has none yet. The backend row is created lazily
  // on the first real message; nothing here calls the API just to "start" a case. The URL itself is
  // NOT written here (see the effect below) — this initializer must stay a pure read, because it
  // also runs during the OIDC callback bootstrap, which needs to scrub ITS OWN query params
  // (code/state) via a hardcoded replaceState a moment later; writing `?case=` here first would
  // just get clobbered by that normalization.
  const [caseId, setCaseId] = useState<string>(() => getCaseIdFromUrl() ?? newCaseId());
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  // Legal-by-Design Phase B: null = not yet checked (renders nothing rather than flashing the
  // gate), true/false once GET /legal/acceptance-status has answered. Irrelevant (stays null,
  // never checked) when LEGAL_GATE_ENABLED is false — see the render branch below.
  const [legalAccepted, setLegalAccepted] = useState<boolean | null>(null);

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
  // manufacturer self-service gate — role AND a hersteller_id claim (mirrors the backend's
  // require_manufacturer). Display-only; the backend re-enforces both on every /partner/me call.
  const isManufacturer = useMemo(() => {
    if (!authed) return false;
    const tok = getAccessToken();
    return (
      rolesFromToken(tok).includes(MANUFACTURER_ROLE) && herstellerIdFromToken(tok) !== ""
    );
  }, [authed]);
  const [selfView, setSelfView] = useState(false);

  const refreshMemory = useCallback(() => {
    api.memory(caseId).then(setMemory).catch(() => undefined);
  }, [api, caseId]);

  // M8: the kernel channel is recomputed server-side on every input change; the panel re-reads it
  // here (flush-then-recompute happens on the backend). Fail-quiet — a failed read never blanks the UI.
  const refreshCompute = useCallback(() => {
    api.compute(caseId).then(setCompute).catch(() => undefined);
  }, [api, caseId]);

  // "Fälle"-Sidebar: the case list, re-fetched after every turn (a new case appears, the active
  // one's title/timestamp updates) — same fail-quiet discipline as the other refresh calls.
  // `casesLoading` only covers the FIRST fetch (the drawer's initial "Lädt …" state), never
  // subsequent refreshes — those replace the list in place without a loading flash.
  const refreshCases = useCallback(() => {
    api
      .listCases()
      .then((r) => setCases(r.cases))
      .catch(() => undefined)
      .finally(() => setCasesLoading(false));
  }, [api]);

  // refresh ALL projections (chips + kernel panel + case list) after any state change — one call site.
  const refreshState = useCallback(() => {
    refreshMemory();
    refreshCompute();
    refreshCases();
  }, [refreshMemory, refreshCompute, refreshCases]);

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
            // Restore the case that was active before this redirect (2026-07-04 audit finding):
            // neither Keycloak's fixed redirect_uri nor the OAuth `state` nonce carries app data
            // through the round trip, so the caseId must come back via sessionStorage instead —
            // stashed by every redirect-out call site below. Setting it here, before setAuthed,
            // means the existing "persist caseId to the URL once authed" effect further down
            // picks it up and writes it into the now-clean URL — no separate URL-write needed.
            const restoredCaseId = takeStashedCaseId();
            if (restoredCaseId) setCaseId(restoredCaseId);
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
    stashCaseIdForAuthRedirect(caseId); // survives the full-page round trip; restored above
    void authorizeUrl(CONFIG, { verifier, state }).then((u) => {
      window.location.href = u;
    });
  }, []);

  useEffect(() => {
    if (authed) refreshState();
  }, [authed, refreshState]);

  // Legal-by-Design Phase B: once authed (and only if the gate is switched on), ask the backend
  // whether THIS tenant already has a current acceptance. Deliberately fails CLOSED, unlike every
  // other fail-quiet refresh here: a network hiccup leaves legalAccepted at null, and the render
  // branch below treats null as "not yet cleared" (shows a neutral loading state, never Shell) —
  // a failed check must never silently unlock the app.
  useEffect(() => {
    if (!authed || !LEGAL_GATE_ENABLED) return;
    let cancelled = false;
    api
      .legalAcceptanceStatus()
      .then((s) => {
        if (!cancelled) setLegalAccepted(s.accepted);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [authed, api]);

  // "Fälle"-Sidebar: the browser back/forward buttons step between cases too, since switches use
  // pushState — sync React state when the URL changes from OUTSIDE our own setCaseId calls.
  useEffect(() => {
    const onPop = () => {
      const id = getCaseIdFromUrl();
      if (!id || id === caseId) return;
      setConvKey((k) => k + 1); // force a fresh ChatPane mount, same as selectCase/newQuestion
      setMemory(EMPTY_MEMORY); // same stale-memory race guard as selectCase/newQuestion
      setCaseId(id);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [caseId]);

  // Persist a freshly-generated caseId into the URL once auth bootstrap has settled — deferred
  // until `authed` so this never races the OIDC callback's own replaceState calls (which scrub
  // code/state/verifier right after login and would otherwise clobber an early write). Without
  // this, a caseId minted in-memory by the useState initializer above never reaches the URL, so a
  // hard reload finds no ?case= param, mints ANOTHER fresh id, and the chat looks lost.
  useEffect(() => {
    if (!authed) return;
    if (getCaseIdFromUrl() === caseId) return;
    setCaseIdInUrl(caseId, { replace: true });
  }, [authed, caseId]);

  // Proactive silent token refresh (the seamless-session pattern, like large platforms): while signed
  // in, refresh the access token WELL BEFORE it expires via the rotating refresh_token grant, so API
  // calls never hit a 401 mid-session. Transient failures retry within the remaining access-token
  // validity; a definitive failure (session ended / token revoked) hands off to re-auth. Memory-only
  // tokens → on reload this does nothing; the bootstrap effect's prompt=none re-auth covers that.
  useEffect(() => {
    if (!authed) return;
    let timer: number;
    let stopped = false;
    // refreshTokens is single-flight, so the timer + the visibility handler can both call it safely
    // (they coalesce onto one request — mandatory under refresh-token rotation).
    const refreshNow = () => refreshTokens(CONFIG).then(() => true).catch(() => false);
    const tick = async () => {
      if (stopped) return;
      if (msUntilExpiry() > 90_000) {
        timer = window.setTimeout(tick, 60_000); // plenty of runway → re-check in a minute
        return;
      }
      const ok = await refreshNow();
      if (stopped) return;
      if (ok) {
        timer = window.setTimeout(tick, 60_000);
      } else if (msUntilExpiry() > 15_000) {
        timer = window.setTimeout(tick, 10_000); // transient → retry inside the buffer
      } else {
        onUnauthenticated(); // out of runway → drop to re-auth
      }
    };
    // Background tabs throttle setTimeout, so the scheduled refresh can fire late → on return-to-focus
    // catch up immediately if the token is near/past expiry (coalesced with any in-flight refresh).
    const onVisible = () => {
      if (document.visibilityState === "visible" && msUntilExpiry() < 90_000) void refreshNow();
    };
    timer = window.setTimeout(tick, 1_000);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [authed, onUnauthenticated]);

  const login = useCallback(async () => {
    const verifier = randomVerifier();
    const state = randomVerifier();
    sessionStorage.setItem("v2_pkce_verifier", verifier);
    stashCaseIdForAuthRedirect(caseId); // survives the full-page round trip; restored above
    window.location.href = await authorizeUrl(CONFIG, { verifier, state });
  }, [caseId]);

  const send = useCallback(
    async (message: string) => {
      setError(null);
      setLastMessage(message);
      try {
        return await api.chatStream(message, setLiveStage, caseId);
      } catch (e) {
        setError("Es ist ein Fehler aufgetreten — bitte erneut versuchen.");
        throw e;
      } finally {
        setLiveStage(null);
        refreshState();
      }
    },
    [api, caseId, refreshState],
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
    // 2026-07-04 audit fix: same stale-memory race as selectCase — reset before the id/URL change.
    setMemory(EMPTY_MEMORY);
    // "Fälle"-Sidebar: "Neue Frage" starts an actual NEW case (not just a visual reset) — a fresh
    // id, pushed (not replaced) so the back button can step back to the previous case.
    const fresh = newCaseId();
    setCaseIdInUrl(fresh, { replace: false });
    setCaseId(fresh);
  }, []);

  // "Fälle"-Sidebar: switch to an existing case from the drawer. Same convKey bump as "Neue Frage"
  // so ChatPane remounts and re-hydrates from that case's memory.history.
  const selectCase = useCallback(
    (id: string) => {
      if (id === caseId) return;
      setError(null);
      setBriefing(null);
      setLastMessage("");
      setConvKey((k) => k + 1);
      // 2026-07-04 audit fix: without this, the freshly-remounted ChatPane's one-shot hydration
      // effect reads `memory` BEFORE this case's own memory fetch resolves (it's still the
      // PREVIOUS case's data at that instant) and locks it in permanently — resetting here, in
      // the same batch as setCaseId, means the new ChatPane sees an empty history on its very
      // first render instead of someone else's.
      setMemory(EMPTY_MEMORY);
      setCaseIdInUrl(id, { replace: false });
      setCaseId(id);
    },
    [caseId],
  );

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

  // Legal-by-Design Phase B: blocks Shell (chat/upload/case functions) until a current acceptance
  // is confirmed. `legalAccepted === null` covers BOTH "still checking" and "check failed" —
  // either way, fail closed: never render Shell, never render LegalGate on top of a stale check.
  if (LEGAL_GATE_ENABLED && legalAccepted !== true) {
    return (
      <FramingContext.Provider value={framing}>
        {legalAccepted === false ? (
          <LegalGate api={api} onAccepted={() => setLegalAccepted(true)} />
        ) : (
          <div className="login" data-testid="legal-gate-checking" aria-busy="true">
            <div className="stage-glow" aria-hidden="true" />
            <p>Wird geprüft …</p>
          </div>
        )}
      </FramingContext.Provider>
    );
  }

  return (
    <FramingContext.Provider value={framing}>
      <Shell
        onLogout={logout}
        onNewQuestion={newQuestion}
        onAdmin={isAdmin ? () => setAdminView(true) : undefined}
        onPartnerSelf={isManufacturer ? () => setSelfView(true) : undefined}
        cases={cases}
        casesLoading={casesLoading}
        activeCaseId={caseId}
        onSelectCase={selectCase}
      >
        {adminView && isAdmin ? (
          <AdminPane api={api} onClose={() => setAdminView(false)} />
        ) : selfView && isManufacturer ? (
          <PartnerSelfPane api={api} onClose={() => setSelfView(false)} />
        ) : (
        <ChatPane
          key={`${caseId}:${convKey}`}
          onSend={send}
          error={error}
          memory={memory}
          greetingName={greetingName}
          liveStage={liveStage}
          onEditFact={(feld, wert) => {
            const next = window.prompt(`${feld}:`, wert);
            if (next != null)
              api.editFact(feld, next, undefined, caseId).then(refreshState).catch(() => undefined);
          }}
          onForgetFact={(feld) =>
            api.forgetFact(feld, caseId).then(refreshState).catch(() => undefined)
          }
          onForgetAll={() => api.forgetAll(caseId).then(refreshState).catch(() => undefined)}
          onSubmitParams={async (items, deletes = []) => {
            // R2 „Übernehmen": forget the reconciled (cleared) felder, then batch-settle + recompute
            // server-side; refresh chips + kern panel; return the deterministic confirmation. On
            // failure set the error + rethrow — the form keeps its values, ChatPane appends nothing.
            try {
              await Promise.all(deletes.map((feld) => api.forgetFact(feld, caseId)));
              const conf = await api.submitParams(items, caseId);
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
            api.editFact(feld, value, undefined, caseId).then(refreshState).catch(() => undefined)
          }
          onMakeBriefing={makeBriefing}
          canBriefing={Boolean(lastMessage)}
          briefing={briefing}
          compute={compute}
          onAnfrage={(partnerId, message) => api.anfrage(partnerId, message)}
          onDownloadPdf={(message) =>
            api.briefing(message).then(downloadBriefingPdf)
          }
          onContribute={(payload) => api.contribute(payload)}
        />
        )}
      </Shell>
    </FramingContext.Provider>
  );
}
