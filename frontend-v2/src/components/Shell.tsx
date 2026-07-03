import { useState, type ReactNode } from "react";
import type { CaseSummary } from "../contracts";
import { loadNavExpanded, saveNavExpanded } from "../lib/navSidebar";
import { CaseSidebar } from "./CaseSidebar";
import { SafetyBanner } from "./SafetyBanner";
import {
  ComposeIcon,
  HistoryIcon,
  LogoIcon,
  PanelLeftIcon,
  PersonIcon,
  SearchIcon,
  SettingsIcon,
} from "./icons";

/** Pilot-ui shell — a claude.ai-style collapsible navigation sidebar on the left + the main stage.
 * Collapsed = a calm narrow icon rail; expanded = wider with labels (the state is persisted). The
 * width is driven by `--rail-w` on `.shell` (overridden when expanded). Search/history/settings are
 * visually present but disabled until they have real backing — no invented functionality. */
export function Shell({
  children,
  onLogout,
  onNewQuestion,
  onAdmin,
  onPartnerSelf,
  cases = [],
  casesLoading = false,
  activeCaseId = null,
  onSelectCase = () => undefined,
}: {
  children: ReactNode;
  onLogout: () => void;
  onNewQuestion: () => void;
  /** Owner-only: open the Hersteller-Partner dashboard. Provided only when the token carries the
   * admin role — otherwise the entry is never rendered. */
  onAdmin?: () => void;
  /** Manufacturer-only: open the self-service profile. Provided only when the token carries the
   * manufacturer role + a hersteller_id — otherwise never rendered. */
  onPartnerSelf?: () => void;
  /** "Fälle"-Sidebar: the tenant's case list + which one is active. The "Verlauf" button opens a
   * drawer listing them; clicking one hands the id back to the host (App owns the actual switch).
   * Optional (default empty/inert) so callers that don't care about cases — e.g. existing Shell
   * tests that only exercise nav collapse/expand — don't need to wire them. */
  cases?: CaseSummary[];
  casesLoading?: boolean;
  activeCaseId?: string | null;
  onSelectCase?: (caseId: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [navExpanded, setNavExpanded] = useState<boolean>(loadNavExpanded);
  const toggleNav = () =>
    setNavExpanded((v) => {
      const next = !v;
      saveNavExpanded(next);
      return next;
    });

  return (
    <div className={`shell${navExpanded ? " shell--nav-expanded" : ""}`}>
      <nav className="rail" aria-label="Navigation">
        <div className="rail-top">
          <div className="rail-brand" title="sealing | Intelligence">
            <LogoIcon />
            <span className="rail-label">
              sealing<span className="brand-sep"> | </span>Intelligence
            </span>
          </div>
          <button
            className="rail-toggle"
            onClick={toggleNav}
            title={navExpanded ? "Navigation einklappen" : "Navigation ausklappen"}
            aria-label={navExpanded ? "Navigation einklappen" : "Navigation ausklappen"}
            aria-expanded={navExpanded}
            data-testid="rail-toggle"
          >
            <PanelLeftIcon />
          </button>
        </div>
        <button
          className="rail-btn"
          onClick={onNewQuestion}
          title="Neue Frage"
          aria-label="Neue Frage"
          data-testid="rail-new-question"
        >
          <ComposeIcon />
          <span className="rail-label">Neue Frage</span>
        </button>
        <button className="rail-btn" disabled title="Suche — in Vorbereitung" aria-label="Suche (in Vorbereitung)">
          <SearchIcon />
          <span className="rail-label">Suche</span>
        </button>
        <button
          className="rail-btn"
          onClick={() => setHistoryOpen((o) => !o)}
          title="Fälle"
          aria-label="Fälle"
          aria-expanded={historyOpen}
          data-testid="rail-history"
        >
          <HistoryIcon />
          <span className="rail-label">Fälle</span>
        </button>
        <div className="rail-spacer" />
        <button
          className="rail-btn"
          disabled
          title="Einstellungen — in Vorbereitung"
          aria-label="Einstellungen (in Vorbereitung)"
        >
          <SettingsIcon />
          <span className="rail-label">Einstellungen</span>
        </button>
        <button
          className="rail-avatar"
          onClick={() => setMenuOpen((o) => !o)}
          title="Konto"
          aria-label="Konto"
          aria-expanded={menuOpen}
          data-testid="account-avatar"
        >
          <PersonIcon />
          <span className="rail-label">Konto</span>
        </button>
        {menuOpen && (
          <div className="rail-menu" role="menu">
            {onAdmin ? (
              <button
                className="rail-menu-item"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  onAdmin();
                }}
                data-testid="nav-admin"
              >
                Hersteller verwalten
              </button>
            ) : null}
            {onPartnerSelf ? (
              <button
                className="rail-menu-item"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  onPartnerSelf();
                }}
                data-testid="nav-partner-self"
              >
                Mein Hersteller-Profil
              </button>
            ) : null}
            <button className="rail-menu-item" role="menuitem" onClick={onLogout} data-testid="logout">
              Abmelden
            </button>
          </div>
        )}
      </nav>
      {historyOpen && (
        <CaseSidebar
          cases={cases}
          loading={casesLoading}
          activeCaseId={activeCaseId}
          onSelect={(caseId) => {
            onSelectCase(caseId);
            setHistoryOpen(false);
          }}
          onClose={() => setHistoryOpen(false)}
        />
      )}
      <main className="main-area">
        {children}
        <SafetyBanner />
      </main>
    </div>
  );
}
