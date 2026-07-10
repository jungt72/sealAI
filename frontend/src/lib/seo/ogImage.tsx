import { ImageResponse } from "next/og";

/**
 * Shared per-article OG/Twitter card generator (docs/design §... social-share
 * gap). Rendered once per slug at request time via each route's
 * `opengraph-image.tsx` (Next's file convention — this is NOT a manual
 * <meta> tag, Next wires it up automatically). Kept to a solid brand
 * gradient (no external image fetch) so generation never depends on
 * network access during build/first-request.
 */
export const ogImageSize = { width: 1200, height: 630 } as const;
export const ogImageContentType = "image/png" as const;

export function renderArticleOgImage({ title, eyebrow }: { title: string; eyebrow: string }) {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          padding: "72px",
          backgroundColor: "#04070d",
          backgroundImage:
            "radial-gradient(120% 90% at 8% 100%, rgba(38,66,104,0.55) 0%, rgba(4,7,13,0) 55%), linear-gradient(165deg, rgba(0,42,91,0.5) 0%, rgba(6,12,22,0.4) 55%, #04070d 100%)",
          fontFamily: "Helvetica, Arial, sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            fontSize: 22,
            fontWeight: 600,
            letterSpacing: 4,
            color: "#ffffff",
            marginBottom: 16,
          }}
        >
          SEALINGAI · {eyebrow.toUpperCase()}
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 52,
            fontWeight: 500,
            lineHeight: 1.15,
            letterSpacing: -1,
            color: "#ffffff",
            maxWidth: 1000,
          }}
        >
          {title}
        </div>
      </div>
    ),
    { ...ogImageSize },
  );
}
