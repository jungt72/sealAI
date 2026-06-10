import type { ReactNode } from "react";
import { SafetyBanner } from "./SafetyBanner";

/** The reused DESIGN.md shell — top header · main chat column · right cockpit column — wearing the
 * brand tokens. The SafetyBanner is mounted persistently (independent of content/error state). */
export function Shell({
  children,
  cockpit,
  onLogout,
}: {
  children: ReactNode;
  cockpit: ReactNode;
  onLogout: () => void;
}) {
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">
          sealing<span className="brand-sep"> | </span>Intelligence
        </span>
        <button className="logout" onClick={onLogout} data-testid="logout">
          Abmelden
        </button>
      </header>
      <SafetyBanner />
      <div className="workspace">
        <main className="chat-col">{children}</main>
        <aside className="cockpit-col">{cockpit}</aside>
      </div>
    </div>
  );
}
