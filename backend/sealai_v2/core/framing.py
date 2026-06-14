"""Safety-framing single source (cutover Phase 1a). The claim-boundary wording that EVERY V2
surface renders — the SPA banner/badges (served via ``GET /api/v2/framing``) and the briefing's
Geltungsrahmen note (``render.renderer``) — lives HERE, so the liability text has exactly one
backend-owned source. Owner-grounded doctrine wording (AGENTS.md § Safety Boundaries); the
lawyer-reviewed revision before the first pilot lands in THIS module only.

Pure core: constants + a deterministic payload — no I/O, no Jinja, no LLM. The SPA's build-time
fallback is contract-pinned to ``contracts/framing.v2.json`` (both suites assert against it), so
the two ends cannot drift while tests are green.
"""

from __future__ import annotations

import hashlib

# UI banner (Shell/SafetyBanner + the briefing/recommendation notes in the SPA).
CLAIM_BOUNDARY = (
    "Orientierung, keine Freigabe — finale Auswahl, Validierung und Freigabe liegen beim "
    "Hersteller / verantwortlichen Ingenieur."
)

# Badge on any answer NOT backed by reviewed grounding (ChatResponse.grounded == false).
VORLAEUFIG = "vorläufig — gegen Datenblatt / Hersteller verifizieren"

# Frames a remembered (distilled) fact as unverified — the re-ask-keystone honesty hint.
REMEMBERED_HINT = "zuvor genannt — bei Bedarf bestätigen"

# Recommendations are candidates, never a final decision.
CANDIDATE = "Kandidat, nicht final"

# The briefing's Geltungsrahmen note (long form). Allowed scoped vocabulary only (screening,
# orientation, Hersteller-Prüfgrundlage); explicitly disclaims release / suitability / compliance.
GELTUNGSRAHMEN = (
    "**Hinweis (Geltungsrahmen):** Diese Zusammenstellung ist eine technische "
    "**Orientierung/Screening** auf Basis der aktuell vorliegenden Angaben und Richtwerte — "
    "**keine** verbindliche Auslegung, **keine** Freigabe und **keine** Eignungs-, Zulassungs- "
    "oder Konformitätszusage. Sie ist eine **Hersteller-Prüfgrundlage**: die finale Werkstoff- "
    "und Auslegungsentscheidung sowie die Freigabe trifft der Hersteller bzw. die verantwortliche "
    "Fachperson anhand des konkreten Datenblatts."
)

_TEXTS = (CLAIM_BOUNDARY, VORLAEUFIG, REMEMBERED_HINT, CANDIDATE, GELTUNGSRAHMEN)


def framing_version() -> str:
    """Deterministic content hash — clients/caches detect text changes (e.g. the lawyer revision)."""
    return hashlib.sha256("\n".join(_TEXTS).encode("utf-8")).hexdigest()[:12]


def framing_payload() -> dict[str, str]:
    """The ``GET /api/v2/framing`` body (version + the five texts)."""
    return {
        "version": framing_version(),
        "claim_boundary": CLAIM_BOUNDARY,
        "vorlaeufig": VORLAEUFIG,
        "remembered_hint": REMEMBERED_HINT,
        "candidate": CANDIDATE,
        "geltungsrahmen": GELTUNGSRAHMEN,
    }
