/* Legal-by-Design Phase D (Goal 6) — frontend mirror of backend/sealai_v2/safety/risk_flags.py.
 * Detection itself is backend-only (deterministic, always-on, cannot be bypassed by the client);
 * this module only carries the SAME warning text so the chat badge and the PDF export show
 * identical wording — one string, two render sites, kept in sync by this comment + a shared test
 * fixture (see riskFlags.test.ts) rather than a runtime fetch (the text is static doctrine, not
 * request-dependent). */

export const RISK_WARNING_TEXT =
  "⚠️ Potenziell regulierter oder sicherheitskritischer Anwendungsbereich erkannt. sealingAI " +
  "liefert hierzu ausschließlich informative Strukturierung — keine Empfehlung, keine Eignungs-, " +
  "Freigabe- oder Konformitätsaussage. Eine Prüfung durch den Hersteller bzw. die zuständige " +
  "Fachstelle ist vor produktiver Nutzung zwingend erforderlich.";

export function hasRiskFlags(flags: readonly string[] | undefined | null): flags is string[] {
  return Array.isArray(flags) && flags.length > 0;
}
