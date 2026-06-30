import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type {
  AnfrageResponse,
  Briefing,
  ChatResponse,
  ComputeResponse,
  ConfirmationResponse,
  ContributePayload,
  ConversationMemory,
  ParamItem,
} from "../contracts";
import { clampCockpitPx, clearCockpitPx, loadCockpitPx, saveCockpitPx } from "../lib/cockpitWidth";
import { useStickToBottom } from "../lib/stickToBottom";
import { Answer } from "./Answer";
import {BerechnungenPanel, isNotApplicable } from "./BerechnungenPanel";
import { BriefingPane } from "./BriefingPane";
import { AlternativenPanel } from "./AlternativenPanel";
import { ContributePanel } from "./ContributePanel";
import { KandidatenSpecPanel } from "./KandidatenSpecPanel";
import { MediumPanel } from "./MediumPanel";
import { MemoryPanel } from "./MemoryPanel";
import { ParamConfirmation } from "./ParamConfirmation";
import { ParameterForm } from "./ParameterForm";
import { PaperclipIcon, SendIcon } from "./icons";

type Msg =
  | { role: "user"; text: string }
  | { role: "assistant"; res: ChatResponse }
  | { role: "confirmation"; conf: ConfirmationResponse };

/* P4b — the frontend owns the German stage labels; the backend streams keys only. Unmapped keys
 * (recall, cite, future stages) keep the last mapped label — forward-compatible by ignoring. */
const STAGE_LABELS: Record<string, string> = {
  understand: "Verstehen",
  ground: "Fakten suchen",
  compute: "Berechnen",
  generate: "Antwort formulieren",
  verify: "Prüfen",
};

/** The pilot-ui main surface: a persistent two-column workspace — the conversation on the left, a
 *  persistent cockpit (parameter fast-path form + Fallkontext chips + Berechnungen) on the right,
 *  present from the landing. Two states of ONE conversation:
 *  - stage (no messages yet): a calm, centered greeting + composer over the radial glow;
 *  - chat view (conversation started): the message log with the same composer docked at the bottom.
 *  The cockpit is IDENTICAL in both states. On a failed send the assistant message is NOT appended
 *  (no stale/wrong content); the error is surfaced and the persistent doctrine line (Shell) stays. */
export function ChatPane({
  onSend,
  error,
  memory,
  onEditFact,
  onForgetFact,
  onForgetAll,
  onSubmitParams,
  onPreview,
  onMakeBriefing,
  canBriefing,
  briefing,
  greetingName,
  liveStage,
  compute,
  onConfirmUnit,
  onAnfrage,
  onDownloadPdf,
  onContribute,
}: {
  onSend: (message: string) => Promise<ChatResponse>;
  error: string | null;
  memory: ConversationMemory;
  onEditFact: (feld: string, wert: string) => void;
  onForgetFact: (feld: string) => void;
  onForgetAll: () => void;
  /** R2 adopt: the non-empty form items + the reconcile `deletes` (managed felder cleared since the
   * last commit) → the host forgets the deletes, then settles the batch (POST /facts). */
  onSubmitParams: (items: ParamItem[], deletes?: string[]) => Promise<ConfirmationResponse>;
  /** R2 live preview: the read-only backend kern over the form DRAFT (null on error/empty). */
  onPreview?: (items: ParamItem[]) => Promise<ComputeResponse | null>;
  onMakeBriefing: () => void;
  canBriefing: boolean;
  briefing: Briefing | null;
  greetingName?: string | null;
  liveStage?: string | null;
  compute?: ComputeResponse | null;
  onConfirmUnit?: (feld: string, value: string) => void;
  /** Modus F lead-gen: route a structured RFQ briefing to the chosen partner. The host supplies the
   * session message; the panel passes only the partner id. */
  onAnfrage?: (partnerId: string, message: string) => Promise<AnfrageResponse>;
  /** Download the Anfrage briefing as a PDF (no send). The host fetches the briefing for the session
   * message + builds the PDF; the panel passes nothing. */
  onDownloadPdf?: (message: string) => Promise<void>;
  /** Wissens-Beitrag: the user shares their solution + outcome to improve sealingAI (untrusted DRAFT). */
  onContribute?: (payload: ContributePayload) => Promise<{ hinweis: string }>;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  // claude.ai chat↔artifact: the cockpit opens on the right (a case becomes active, or the user opens
  // the form) and closes back to centered chat-only. `userOpened`/`userClosed` capture explicit intent
  // over the auto-open; `everOpened` keeps the panel MOUNTED once shown (open/close is CSS-visibility
  // only — the form keeps its values, no remount).
  const [userOpened, setUserOpened] = useState(false);
  const [userClosed, setUserClosed] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { ref: logRef, onScroll } = useStickToBottom<HTMLDivElement>(msgs.length);
  // resizable chat|cockpit divider (split, ≥1024px): the chosen width drives the `--cockpit-w` track;
  // null = CSS default (~50/50). Persisted in localStorage, restored on mount, reset on double-click.
  const workspaceRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const dragPxRef = useRef<number | null>(null);
  const [cockpitW, setCockpitW] = useState<string | null>(() => {
    const px = loadCockpitPx();
    return px != null ? `${px}px` : null;
  });
  // latest mapped label survives unmapped keys (recall/cite) and clears when the turn ends
  const [stageLabel, setStageLabel] = useState<string | null>(null);
  useEffect(() => {
    if (!busy) setStageLabel(null);
    else if (liveStage && STAGE_LABELS[liveStage]) setStageLabel(STAGE_LABELS[liveStage]);
  }, [busy, liveStage]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await onSend(text);
      setMsgs((m) => [...m, { role: "assistant", res }]);
    } catch {
      // error rendered via the `error` prop; deliberately append nothing (no stale content)
    } finally {
      setBusy(false);
    }
  }

  // R2 „Übernehmen": forget the reconciled (cleared) felder + settle the batch server-side, then
  // append the DETERMINISTIC confirmation (post-bind echo + kern result + Rückfragen) as a chat
  // message. No LLM, no client compute. On failure nothing is appended and the form keeps its values.
  async function submitParams(items: ParamItem[], deletes: string[] = []) {
    if (items.length === 0 && deletes.length === 0) return;
    try {
      const conf = await onSubmitParams(items, deletes);
      if (items.length > 0) setMsgs((m) => [...m, { role: "confirmation", conf }]);
    } catch {
      // error surfaced via the `error` prop (the host sets it); append nothing (no stale content)
    }
  }

  // The committed case-state as feld → settled value: hydrates the form fields (the single editable
  // surface) and is the baseline for the empty-field reconcile on „Übernehmen".
  const committed = Object.fromEntries(memory.case_state.map((f) => [f.feld, f.wert]));

  const composer = (
    <div className="pill-wrap">
      <div className="pill">
        <textarea
          ref={inputRef}
          className="pill-input"
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="sealingAI fragen"
          data-testid="composer-input"
        />
        <button
          className="pill-icon"
          disabled
          title="Anhang hinzufügen — in Vorbereitung"
          aria-label="Anhang hinzufügen (in Vorbereitung)"
        >
          <PaperclipIcon />
        </button>
        <button
          className="pill-send"
          onClick={() => void send()}
          disabled={busy || !input.trim()}
          title="Senden"
          aria-label="Senden"
          data-testid="composer-send"
        >
          <SendIcon />
        </button>
      </div>
    </div>
  );

  const chips = (
    <MemoryPanel memory={memory} onEdit={onEditFact} onForget={onForgetFact} onForgetAll={onForgetAll} />
  );

  const briefingButton = (
    <button
      className="make-briefing"
      onClick={onMakeBriefing}
      disabled={!canBriefing}
      data-testid="make-briefing"
    >
      Briefing erstellen
    </button>
  );

  // The cockpit's chips+kern area is empty when there are no remembered facts AND the kern has nothing
  // to show — an honest placeholder instead of a blank box (the parameter form above it is always shown).
  // Mirrors the calm Berechnungen visibility: a not_computed-only kern is "empty" here (it surfaces no
  // panel), so the placeholder shows rather than an empty box.
  const caseStateEmpty =
    memory.case_state.length === 0 &&
    (compute?.computed?.length ?? 0) === 0 &&
    (compute?.clarifications?.length ?? 0) === 0 &&
    (compute?.notes?.length ?? 0) === 0;

  // Medium Intelligence (Phase 2): the MEDIUM panel shows the most recent turn's researched medium
  // (vorläufig). Null until the backend ships the field + the feature flag is enabled.
  const latestMedium = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant" && m.res.medium_intelligence)
        return m.res.medium_intelligence;
    }
    return null;
  }, [msgs]);

  // Produktspec v3.1: the PRODUKT-KANDIDAT panel shows the most recent turn's Kandidaten-Spezifikation
  // (always vorläufig). Null until the backend ships the field + the feature flag is enabled by the owner.
  const latestSpec = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant" && m.res.kandidaten_spec) return m.res.kandidaten_spec;
    }
    return null;
  }, [msgs]);

  // Modus F (Hersteller-Auswahl): the most recent turn's manufacturer suggestion, or null (it fires
  // only on an explicit alternatives/manufacturer request).
  const latestAlternativen = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant" && m.res.alternativen) return m.res.alternativen;
    }
    return null;
  }, [msgs]);

  // The Anfrage briefing is rendered server-side from the SESSION case-state; the message it runs is
  // the user's last substantive question (recalls the worked-out situation). The panel passes only the
  // partner id — the host injects this message + talks to /api/v2/anfrage.
  const lastUserMessage = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "user") return m.text;
    }
    return "";
  }, [msgs]);
  const panelOnAnfrage = useMemo(
    () =>
      onAnfrage
        ? (partnerId: string) =>
            onAnfrage(
              partnerId,
              lastUserMessage || "Anfrage zur besprochenen Dichtungslösung",
            )
        : undefined,
    [onAnfrage, lastUserMessage],
  );
  const panelOnDownloadPdf = useMemo(
    () =>
      onDownloadPdf
        ? () =>
            onDownloadPdf(
              lastUserMessage || "Anfrage zur besprochenen Dichtungslösung",
            )
        : undefined,
    [onDownloadPdf, lastUserMessage],
  );
  const lastAnswer = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant") return m.res.answer;
    }
    return "";
  }, [msgs]);
  // Wissens-Beitrag: the host builds the full payload (situation + case-state + recommendation) from the
  // session; the panel supplies only anonym + outcome.
  const panelOnContribute = useMemo(
    () =>
      onContribute
        ? (anonym: boolean, outcome: string) =>
            onContribute({
              anonym,
              situation: lastUserMessage,
              recommendation: lastAnswer,
              outcome,
              case_state: memory.case_state.map((f) => ({ feld: f.feld, wert: f.wert })),
            })
        : undefined,
    [onContribute, lastUserMessage, lastAnswer, memory.case_state],
  );

  // claude.ai chat↔artifact: the cockpit is OPEN when the case is active OR the user opened it,
  // and NOT explicitly closed. Default / pure Q&A → chat-only (centered, no right panel). Opening
  // moves the chat left and splits ~50/50; closing returns to centered chat-only.
  const caseActive = !caseStateEmpty;
  const cockpitVisible = (caseActive || userOpened) && !userClosed;
  const openCockpit = () => {
    setUserOpened(true);
    setUserClosed(false);
  };
  const closeCockpit = () => {
    setUserClosed(true);
    setUserOpened(false);
  };
  // mount the cockpit once it has been shown, then keep it mounted (open/close = CSS only → the form
  // keeps its values; no remount).
  useEffect(() => {
    if (cockpitVisible) setEverOpened(true);
  }, [cockpitVisible]);

  // A subtle, low-key affordance near the composer — present only while the cockpit is closed.
  const openFormLink = cockpitVisible ? null : (
    <button type="button" className="open-cockpit-link" data-testid="open-cockpit" onClick={openCockpit}>
      Parameter direkt eingeben
    </button>
  );

  // ── chat|cockpit divider drag (split, ≥1024px) — pointer-capture, self-contained ─────────────
  // The cockpit sits on the right; new width = workspace right edge − pointer x, clamped. Committed
  // to localStorage on release (not per move). Double-click / Home → reset to the ~50/50 default.
  function onSplitterDown(e: ReactPointerEvent<HTMLDivElement>) {
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    draggingRef.current = true;
  }
  function onSplitterMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    const ws = workspaceRef.current;
    if (!ws) return;
    const rect = ws.getBoundingClientRect();
    const px = clampCockpitPx(rect.right - e.clientX, rect.width);
    dragPxRef.current = px;
    setCockpitW(`${px}px`);
  }
  function onSplitterUp(e: ReactPointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    if (dragPxRef.current != null) saveCockpitPx(dragPxRef.current);
  }
  function onSplitterReset() {
    dragPxRef.current = null;
    setCockpitW(null);
    clearCockpitPx();
  }
  // keyboard support for the separator: ←/→ nudge (left widens the cockpit), Home resets
  function onSplitterKey(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "Home") {
      e.preventDefault();
      onSplitterReset();
      return;
    }
    const dir = e.key === "ArrowLeft" ? 1 : e.key === "ArrowRight" ? -1 : 0;
    if (dir === 0) return;
    const ws = workspaceRef.current;
    if (!ws) return;
    e.preventDefault();
    const rect = ws.getBoundingClientRect();
    const current = dragPxRef.current ?? Math.round(rect.width * 0.5);
    const px = clampCockpitPx(current + dir * 24, rect.width);
    dragPxRef.current = px;
    setCockpitW(`${px}px`);
    saveCockpitPx(px);
  }

  // null → no inline override → the CSS default (~50/50) applies; a px string → the dragged width
  const workspaceStyle = cockpitW ? ({ "--cockpit-w": cockpitW } as unknown as CSSProperties) : undefined;

  // The right cockpit panel (the artifact-equivalent): a clean header (closeable → centered chat-only)
  // + the Parameter | Readout 2-pane (side-by-side when the panel is wide, stacked when narrow — a CSS
  // container query). The fast-path form is the SINGLE form entry point; its batch submit reuses the
  // SAME settle → confirmation path. Pure placement: no data-flow / settle / recompute change.
  const computeHasCritical =
    (compute?.notes?.length ?? 0) +
      (compute?.clarifications?.length ?? 0) +
      ((compute?.not_computed ?? []).filter((n) => !isNotApplicable(n)).length) >
    0;
  const mediumReadoutRows = [
    { key: "medium", label: "Medium" },
    { key: "medium_kategorie", label: "Kategorie" },
    { key: "druck", label: "Druck normal" },
    { key: "druck_max", label: "Druck max." },
    { key: "betriebstemperatur", label: "Betriebstemperatur" },
    { key: "spitzentemperatur", label: "Spitzentemperatur" },
    { key: "additive", label: "Additive" },
  ].flatMap(({ key, label }) => {
    const value = committed[key];
    return value ? [{ key, label, value }] : [];
  });

  const cockpit = (
    <aside className="cockpit-panel" data-testid="case-state" aria-label="Fallkontext und Berechnungen">
      <header className="cockpit-header">
        <span className="cockpit-title">Cockpit</span>
        <button
          type="button"
          className="cockpit-close"
          data-testid="cockpit-close"
          onClick={closeCockpit}
          title="Cockpit schließen"
          aria-label="Cockpit schließen"
        >
          ×
        </button>
      </header>
      <div className="cockpit-body cockpit-body--matrix scroll-area">
        <section className="cockpit-param-column" data-testid="cockpit-param-column" aria-label="Parameter">
          <span className="cockpit-section-title">Parameter</span>
          <div className="cockpit-form" data-testid="cockpit-form">
            <ParameterForm
              variant="stage"
              onSubmit={submitParams}
              onPreview={onPreview}
              committed={committed}
            />
          </div>
          {chips}
        </section>

        <section className="cockpit-readout-column" data-testid="cockpit-readout-column" aria-label="Auswertung">
          <section className="cockpit-readout-block" data-testid="cockpit-calculation-readout" aria-label="Berechnungen">
            <span className="cockpit-section-title">Berechnungen</span>
            <BerechnungenPanel compute={compute ?? null} view="results" />
            {(compute?.computed?.length ?? 0) === 0 ? (
              <p className="cockpit-readout-empty" data-testid="case-state-empty">
                Noch keine Werte vom Rechenkern.
              </p>
            ) : null}
            <div className="cockpit-critical-readout" data-testid="cockpit-critical-readout">
              <span className="cockpit-subsection-title">Kritische Punkte</span>
              <BerechnungenPanel compute={compute ?? null} onConfirmUnit={onConfirmUnit} view="critical" />
              {computeHasCritical ? null : (
                <p className="cockpit-readout-empty">Keine kritischen Punkte zu den aktuellen Eingaben.</p>
              )}
            </div>
          </section>

          <section className="cockpit-readout-block" data-testid="cockpit-medium-readout" aria-label="Medium">
            <span className="cockpit-section-title">Medium</span>
            {latestMedium ? (
              <MediumPanel data={latestMedium} />
            ) : mediumReadoutRows.length > 0 ? (
              <dl className="cockpit-medium-facts">
                {mediumReadoutRows.map((row) => (
                  <div key={row.key} className="cockpit-medium-fact">
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="cockpit-readout-empty">Noch keine Mediumdaten im Fallkontext.</p>
            )}
          </section>

          {latestSpec ? <KandidatenSpecPanel data={latestSpec} /> : null}
          {latestAlternativen ? (
            <AlternativenPanel
              data={latestAlternativen}
              onAnfrage={panelOnAnfrage}
              onDownloadPdf={panelOnDownloadPdf}
            />
          ) : null}

          <div className="readout-briefing">
            <p className="readout-briefing-soon">Briefing · RFQ-Reife — kommt bald</p>
            {briefingButton}
            {panelOnContribute ? (
              <ContributePanel onContribute={panelOnContribute} />
            ) : null}
          </div>
        </section>
      </div>
    </aside>
  );

  // chat-only (centered, no right panel) ⟷ split (chat | divider | cockpit ~50/50). The cockpit panel
  // stays mounted once shown (everOpened); chat-only just hides it (CSS) — no remount, no state loss.
  return (
    <div
      ref={workspaceRef}
      className={`workspace workspace--${cockpitVisible ? "split" : "chat-only"}`}
      style={workspaceStyle}
      data-testid="chat-pane"
    >
      <div className="chat-col">
        {msgs.length === 0 ? (
          // stage center: ONLY the greeting + composer over the glow — calm and centered.
          <div className="stage" data-testid="stage-center">
            <div className="stage-glow" aria-hidden="true" />
            <h1 className="greeting" data-testid="greeting">
              Welche Dichtungsfrage steht an{greetingName ? `, ${greetingName}` : ""}?
            </h1>
            {composer}
            {openFormLink}
            {error && (
              <div className="error-banner" role="alert" data-testid="chat-error">
                {error}
              </div>
            )}
          </div>
        ) : (
          <div className="chat-main">
            {/* the scroll region (fade cues on the wrapper); the composer below stays docked/sticky */}
            <div className="scroll-wrap chat-scroll-wrap">
              <div className="chat-log scroll-area" data-testid="chat-log" ref={logRef} onScroll={onScroll}>
                {msgs.map((m, i) =>
                  m.role === "user" ? (
                    <div key={i} className="msg-user">
                      {m.text}
                    </div>
                  ) : m.role === "confirmation" ? (
                    <ParamConfirmation key={i} conf={m.conf} />
                  ) : (
                    <Answer key={i} res={m.res} />
                  ),
                )}
                {busy && (
                  <div className="msg-pending" data-testid="stage-indicator" aria-live="polite">
                    <span className="pending-dots" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    {stageLabel && (
                      <span className="pending-label" data-testid="stage-label">
                        {stageLabel}
                      </span>
                    )}
                  </div>
                )}
                {error && (
                  <div className="error-banner" role="alert" data-testid="chat-error">
                    {error}
                  </div>
                )}
                <BriefingPane briefing={briefing} />
              </div>
            </div>
            <div className="chat-foot">
              {composer}
              {openFormLink}
            </div>
          </div>
        )}
      </div>
      {cockpitVisible && (
        <div
          className="cockpit-splitter"
          data-testid="cockpit-splitter"
          role="separator"
          aria-orientation="vertical"
          aria-label="Breite des Cockpits anpassen"
          tabIndex={0}
          onPointerDown={onSplitterDown}
          onPointerMove={onSplitterMove}
          onPointerUp={onSplitterUp}
          onDoubleClick={onSplitterReset}
          onKeyDown={onSplitterKey}
        />
      )}
      {everOpened && cockpit}
    </div>
  );
}
