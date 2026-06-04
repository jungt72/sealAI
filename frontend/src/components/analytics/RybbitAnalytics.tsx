import Script from "next/script";

const defaultScriptSrc = "https://analytics.sealingai.com/api/script.js";
const replayBlockSelector = ".sensitive-content, [data-private], [data-sensitive], [data-analytics-private]";
const replayIgnoreSelector = "textarea, input, [contenteditable=true], [data-no-replay]";

export function RybbitAnalytics() {
  const siteId = process.env.NEXT_PUBLIC_RYBBIT_SITE_ID?.trim();
  if (!siteId || process.env.NEXT_PUBLIC_RYBBIT_ENABLED === "false") {
    return null;
  }

  const scriptSrc = process.env.NEXT_PUBLIC_RYBBIT_SCRIPT_SRC?.trim() || defaultScriptSrc;

  return (
    <Script
      id="sealingai-rybbit"
      src={scriptSrc}
      data-site-id={siteId}
      strategy="afterInteractive"
      data-skip-patterns='["/admin/**"]'
      data-mask-patterns='["/dashboard/**","/account/**","/login/**","/api/auth/**"]'
      data-replay-mask-all-inputs="true"
      data-replay-block-selector={replayBlockSelector}
      data-replay-ignore-selector={replayIgnoreSelector}
    />
  );
}
