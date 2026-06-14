import { useState, type ReactNode } from "react";
import { SafetyBanner } from "./SafetyBanner";
import { ComposeIcon, HistoryIcon, PersonIcon, RingIcon, SearchIcon, SettingsIcon } from "./icons";

/** Pilot-ui shell (owner-approved Gemini-style mockup): a borderless floating icon rail on the
 * left — brandmark, new-question, then placeholders — and the main stage. The doctrine line
 * (SafetyBanner) stays persistently mounted, fixed at the bottom, independent of content/error
 * state. Search/history/settings are visually present but disabled until they have real backing —
 * no invented functionality. */
export function Shell({
  children,
  onLogout,
  onNewQuestion,
}: {
  children: ReactNode;
  onLogout: () => void;
  onNewQuestion: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="shell">
      <nav className="rail" aria-label="Navigation">
        <div className="rail-brand" title="sealing | Intelligence">
          <RingIcon />
        </div>
        <button
          className="rail-btn"
          onClick={onNewQuestion}
          title="Neue Frage"
          aria-label="Neue Frage"
          data-testid="rail-new-question"
        >
          <ComposeIcon />
        </button>
        <button className="rail-btn" disabled title="Suche — in Vorbereitung" aria-label="Suche (in Vorbereitung)">
          <SearchIcon />
        </button>
        <button className="rail-btn" disabled title="Verlauf — in Vorbereitung" aria-label="Verlauf (in Vorbereitung)">
          <HistoryIcon />
        </button>
        <div className="rail-spacer" />
        <button
          className="rail-btn"
          disabled
          title="Einstellungen — in Vorbereitung"
          aria-label="Einstellungen (in Vorbereitung)"
        >
          <SettingsIcon />
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
        </button>
        {menuOpen && (
          <div className="rail-menu" role="menu">
            <button className="rail-menu-item" role="menuitem" onClick={onLogout} data-testid="logout">
              Abmelden
            </button>
          </div>
        )}
      </nav>
      <main className="main-area">{children}</main>
      <SafetyBanner />
    </div>
  );
}
