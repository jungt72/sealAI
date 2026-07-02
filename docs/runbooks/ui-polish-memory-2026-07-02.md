# UI Polish Memory - 2026-07-02

## Dashboard chat

- Source of truth: `frontend-v2`.
- Conversation width follows the Grok computed-style reference: chat column, assistant answer, markdown,
  and composer use `--sai-content-max-width: 40rem` (`640px`).
- Markdown body: Inter stack, `16px / 28px` root, paragraphs `16px / 26px`, weight `400`,
  letter-spacing `-0.1px`, color `#050505`, transparent surface with no answer card.
- Markdown rhythm: paragraphs `0 0 16px`, `p + p` top gap `8px`; h2 `22px / 30px / 560`;
  h3 `19px / 29px / 550`; lists `19px` left padding with `16px / 28px` list items.
- User message bubble: `#F3F3F3`, `28px` radius, `14px 18px` padding, `16px / 26px`,
  no hard border or heavy shadow.
- Composer sits at the bottom with a white pill, `rgba(5,5,5,0.08)` border, subtle shadow,
  and `16px / 28px` input typography.
- `Parameter eingeben` is an orange CTA in the dashboard chrome, top right, not below the composer.
- Trust/status labels stay in the DOM but outside the main reading flow inside the `Technische Vorbewertung`
  disclosure in `Answer.tsx`.
- Chat scrolling uses `frontend-v2/src/lib/chatScroll.ts`; new user turns pin near the upper third and a jump-to-latest button appears when needed.

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

- Dashboard SPA is built from `frontend-v2` and served by nginx from `/home/thorsten/sealai/frontend-v2/dist`.
- Public marketing frontend is the Next.js service `frontend` from the production compose file.
- Keycloak theme changes require the theme files on the VPS and a Keycloak restart/recreate if the theme cache does not refresh.
