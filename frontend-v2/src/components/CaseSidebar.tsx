import type { CaseSummary } from "../contracts";

/** ChatGPT-style "Fälle" list — a drawer anchored to the right of the nav rail (opened via the
 * "Verlauf" rail button). Click a case to load its full transcript; the active case is highlighted.
 * `title`/`updated_at` are null for a case with no turn recorded yet (or one that predates this
 * feature) — rendered as a neutral placeholder rather than blank, so the row never looks broken. */
export function CaseSidebar({
  cases,
  activeCaseId,
  loading,
  onSelect,
  onClose,
}: {
  cases: CaseSummary[];
  activeCaseId: string | null;
  loading: boolean;
  onSelect: (caseId: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="case-sidebar" role="dialog" aria-label="Fälle">
      <div className="case-sidebar-head">
        <span className="case-sidebar-title">Fälle</span>
        <button
          className="case-sidebar-close"
          onClick={onClose}
          title="Schließen"
          aria-label="Schließen"
          data-testid="case-sidebar-close"
        >
          ×
        </button>
      </div>
      {loading ? (
        <p className="case-sidebar-empty">Lädt …</p>
      ) : cases.length === 0 ? (
        <p className="case-sidebar-empty" data-testid="case-sidebar-empty">
          Noch keine Fälle — die erste Nachricht legt den ersten Fall an.
        </p>
      ) : (
        <ul className="case-sidebar-list" data-testid="case-sidebar-list">
          {cases.map((c) => (
            <li key={c.case_id}>
              <button
                className={`case-sidebar-item${c.case_id === activeCaseId ? " case-sidebar-item--active" : ""}`}
                onClick={() => onSelect(c.case_id)}
                data-testid="case-sidebar-item"
                aria-current={c.case_id === activeCaseId ? "true" : undefined}
              >
                <span className="case-sidebar-item-title">{c.title ?? "Neuer Fall"}</span>
                {c.updated_at && <RelativeTime iso={c.updated_at} />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A small, dependency-free relative-time label ("gerade eben" / "vor 5 Min." / "vor 3 Std." /
 * "vor 2 Tagen" / a plain date beyond that) — no date library for one small label. */
function RelativeTime({ iso }: { iso: string }) {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  const diffMs = Date.now() - then;
  const label = formatRelative(diffMs, then);
  return (
    <span className="case-sidebar-item-time" data-testid="case-sidebar-item-time">
      {label}
    </span>
  );
}

function formatRelative(diffMs: number, then: number): string {
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "gerade eben";
  if (minutes < 60) return `vor ${minutes} Min.`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `vor ${hours} Std.`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `vor ${days} ${days === 1 ? "Tag" : "Tagen"}`;
  return new Date(then).toLocaleDateString("de-DE");
}
