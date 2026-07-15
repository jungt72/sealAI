# UI Polish Memory - 2026-07-02

## Dashboard chat

- Source of truth: `frontend-v2`.
- The SPA source is `frontend-v2`. This historical runbook's former direct deployment target is
  superseded by `docs/ops/IMMUTABLE_DASHBOARD_RELEASES.md`: builds stay under
  `.build/dashboard-candidate`, and production serves only the GATE-08-selected immutable release.
- Conversation width follows the ChatGPT computed-style reference: chat frame, assistant answer,
  markdown, and composer use `--sai-content-max-width: 48rem` (`768px`) plus responsive side padding.
- UI font is self-hosted IBM Plex Sans via `.woff2` assets under the same `/dashboard/` origin;
  `vite.config.ts` keeps `assetsInlineLimit: 0`, CSP remains `font-src 'self'`, and `data:font`
  must not be reintroduced.
- Markdown body: IBM Plex Sans stack, `16px / 26px`, weight `400`, letter-spacing `0`,
  color `#0d0d0d`, transparent surface with no answer card.
- Markdown rhythm: paragraphs `0 0 4px`, `p + p` top gap `16px`; h2 and standalone bold section
  headings `20px / 28px / 600`; h3 `18px / 26px / 600`; lists `26px` left padding with
  `16px / 26px` list items and `6px` item padding.
- Tables use compact technical rhythm (`14px / 24px`, `th` weight `600`, `th` line-height `16px`).
- User message bubble: `#F3F3F3`, `28px` radius, `14px 18px` padding, `16px / 26px`,
  no hard border or heavy shadow.
- Composer sits at the bottom with a white pill, `rgba(5,5,5,0.08)` border, subtle shadow,
  and `16px / 26px` input typography.
- `Parameter eingeben` is an orange CTA in the dashboard chrome, top right, not below the composer.
- Trust/status labels stay in the DOM but outside the main reading flow inside the `Technische Vorbewertung`
  disclosure in `Answer.tsx`.
- Chat scrolling uses `frontend-v2/src/lib/chatScroll.ts`; new user turns pin near the upper third,
  the viewport must not auto-follow when the assistant response lands, the temporary bottom spacer is
  trimmed via `settleNewTurnSpacer`, and a jump-to-latest button appears only when needed.
- Wheel scrolling is delegated from the full dashboard workspace into the chat log so pointer position
  inside or outside the chat column feels equally fast; line-mode wheels normalize at `40px` per line,
  nested scrollable answer/code surfaces keep their own scroll, and `.chat-log` uses
  `scroll-behavior: auto` so delegated wheel scrolling is not smoothed.

## Marketing homepage

- Source of truth: `frontend`.
- Page background target is `#FAFAF9` / near-off-white.
- Hero uses the sealing intelligence image asset and a transparent header over the hero.
- Header becomes readable after scroll via blur/background treatment.
- Hero claim text should stay responsive, clean, and Legora-inspired without copying proprietary assets.

## Keycloak login

- Theme source: `keycloak/themes/sealai-b2b`.
- Login CTA uses navy, not green.
- Login background surface is near-off-white.
- Right-side visual uses the engineer workspace image asset under `resources/img`.

## Deploy notes

- Dashboard SPA is built from `frontend-v2`; Nginx serves the immutable
  `frontend-v2/dashboard-releases/current` target after GATE-08 selection.
- Public marketing frontend is the Next.js service `frontend` from the production compose file.
- Keycloak theme changes require the theme files on the VPS and a Keycloak restart/recreate if the theme cache does not refresh.
