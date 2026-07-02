# UI Polish Memory - 2026-07-02

## Dashboard chat

- Source of truth: `frontend-v2`.
- Conversation width follows the Gemini-style reference: chat column `724px`, assistant markdown `707px`.
- Markdown body: IBM Plex Sans, `17px / 24px`, weight `400`, color `#1F1F1F`.
- User message bubble: `#F2F0F0`, `40px` radius, `20px 28px` padding, `17px / 24px`.
- Composer sits at the bottom with a white pill, soft border, subtle shadow, and `16-17px` input typography.
- `Parameter eingeben` is an orange CTA in the dashboard chrome, top right, not below the composer.
- Trust/status labels stay visible but quiet and secondary.
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
