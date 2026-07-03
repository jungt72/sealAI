import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const themeCss = readFileSync(resolve(process.cwd(), "src/styles/theme.css"), "utf8");
const appCss = readFileSync(resolve(process.cwd(), "src/styles/app.css"), "utf8");

describe("chat markdown typography contract", () => {
  it("keeps the active chat reading width and composer tokens at 48rem", () => {
    expect(themeCss).toContain('--font-sans: "IBM Plex Sans", Roboto, "Open Sans", Arial, system-ui, sans-serif;');
    expect(themeCss).toContain("--sai-chat-shell-max-width: 48rem;");
    expect(themeCss).toContain("--sai-content-max-width: 48rem;");
    expect(themeCss).toContain("--sai-composer-max-width: 48rem;");
    expect(themeCss).toContain("--sai-chat-padding-x: clamp(16px, 2.5vw, 24px);");
    expect(themeCss).toContain("--sai-chat-frame-max-width:");
  });

  it("exposes the full available IBM Plex Sans weight range for visible emphasis", () => {
    const fontCss = readFileSync(resolve(process.cwd(), "src/styles/fonts.css"), "utf8");

    expect(fontCss).toContain("font-weight: 100 700;");
    expect(fontCss).not.toContain("font-weight: 300 600;");
  });

  it("keeps chat markdown readable instead of falling back to the old narrow 40rem layout", () => {
    expect(themeCss).not.toContain("--sai-content-max-width: 40rem;");
    expect(appCss).toContain("width: min(100%, var(--sai-chat-frame-max-width));");
    expect(appCss).toContain("max-width: var(--sai-chat-frame-max-width);");
    expect(appCss).toContain("width: min(100%, var(--sai-composer-max-width));");
    expect(appCss).toContain("line-height: 26px; background: transparent; border: 0; box-shadow: none;");
  });

  it("keeps wheel scrolling immediate while explicit jump-to-bottom may stay smooth", () => {
    expect(appCss).toContain("height: 100%; scroll-behavior: auto;");
    expect(appCss).not.toContain("height: 100%; scroll-behavior: smooth;");
  });

  it("keeps paragraph, heading, and list rhythm aligned with the researched Markdown style", () => {
    expect(appCss).toContain(".markdown {\n  width: 100%;");
    expect(themeCss).toContain("--sai-text: #0d0d0d;");
    expect(appCss).toContain("color: var(--md-ink); font-size: 16px;");
    expect(appCss).toContain("font-weight: 400; line-height: 26px; letter-spacing: 0;");
    expect(appCss).toContain(".markdown p { margin: 0 0 4px; font-size: 16px; line-height: 26px; color: var(--md-ink); }");
    expect(appCss).toContain(".markdown p + p { margin-top: 16px; }");
    expect(appCss).toContain(".markdown h2 { font-size: 20px; line-height: 28px; font-weight: 600;");
    expect(appCss).toContain(".markdown h3 { font-size: 18px; line-height: 26px; font-weight: 600;");
    expect(appCss).toContain(".markdown strong, .markdown b { font-weight: 600; color: var(--md-heading); }");
    expect(appCss).toContain(".markdown .md-standalone-strong {");
    expect(appCss).toContain("margin: 16px 0 4px;");
    expect(appCss).toContain("font-size: 20px;");
    expect(appCss).toContain("line-height: 28px;");
    expect(appCss).toContain(".markdown ul, .markdown ol { margin: 0; padding-left: 26px; }");
    expect(appCss).toContain(".markdown li { margin: 0; padding-left: 6px; font-size: 16px; line-height: 26px; color: var(--md-ink);");
    expect(appCss).toContain(".markdown li::marker { color: #4d4d4d; font-size: 16px; }");
  });

  it("keeps technical Markdown surfaces calm and scannable", () => {
    expect(appCss).toContain(".markdown table { width: 100%; border-collapse: collapse;");
    expect(appCss).toContain(".markdown th { font-weight: 600; line-height: 16px;");
    expect(appCss).toContain(".markdown blockquote { margin: 20px 0; padding: 0 0 0 16px;");
    expect(appCss).toContain(".md-code { margin: 1em 0; border: 1px solid var(--hairline);");
    expect(appCss).toContain(".md-code-head { display: flex; align-items: center; justify-content: space-between;");
  });

  it("preserves existing trust and Gegencheck disclosure styling", () => {
    expect(appCss).toContain("color: #7d7d7d;");
    expect(appCss).toContain("font-size: 11.5px;");
    expect(appCss).toContain(".badge-verified { background: transparent; border: 0; color: var(--sai-text-subtle); }");
    expect(appCss).toContain(".badge-hedged { background: transparent; border: 0; color: var(--color-warning-fg); }");
    expect(appCss).toContain(".badge-unverified { background: transparent; border: 0; color: var(--sai-text-subtle); }");
    expect(appCss).toContain(".gegencheck-note {");
    expect(appCss).toContain("max-width: var(--sai-content-max-width);");
  });
});
