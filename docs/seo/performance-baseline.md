# Performance Baseline

No Lighthouse/CrUX tooling is available from this working environment — the
numbers below are direct HTTP/asset measurements against production, not a
lab audit. **Field data (Search Console → Core Web Vitals report) is the
real source of truth after this ships; nothing here substitutes for it.**

## What was measured and fixed this session

| Metric | Before | After |
|---|---|---|
| Homepage TTFB | ~120ms (measured via `curl -w`) | unchanged, already good |
| Hero image delivery | CSS `background-image`, raw PNG, 1.3MB, not in the browser's preload scanner, not format-negotiated | `next/image` with `priority`; content-negotiated to WebP, ~25KB at `w=1920` (measured via `curl -H "Accept: image/webp"`) |
| Hero entrance animation | `opacity: 0 → 1` on the same element as the H1 (the likely LCP candidate) over 700ms | `transform`-only; element has non-zero opacity at first paint |
| Homepage `Cache-Control` | `s-maxage=31536000` (Next.js's static-page default) — a browser/proxy that cached the page once could sit on it for up to a year | `public, max-age=0, must-revalidate` |
| Article OG images | none (no `og:image` tag at all on any of the 25 articles) | 1200×630 `next/og`-generated PNG per article, ~85KB each |
| Homepage OG image | 1086×1448 portrait, 1.9MB (wrong aspect ratio for link previews) | 1200×630 JPEG, 46KB |

## Known open items (not measurable from here)

- Real-user LCP/INP/CLS per the Core Web Vitals thresholds (LCP <2.5s, INP
  <200ms, CLS <0.1) — needs Search Console field data after this deploy has
  had traffic.
- Total JS payload for the homepage was ~744KB (gzipped, summed from
  `_next/static/chunks/*`) as observed earlier in this audit — not
  re-optimized this session; worth a bundle-analyzer pass if INP field data
  comes back poor.
- No Lighthouse CI / performance budget gate exists in this repo's CI yet.
