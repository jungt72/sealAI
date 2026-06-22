import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

/** LaTeX delimiter normalization: the model emits `\(…\)` / `\[…\]`, but remark-math only parses
 * `$…$` / `$$…$$`. Convert the former to the latter (display first, then inline) so the math actually
 * typesets instead of rendering raw. Targeted on the model's LaTeX braces — not a general `$` rewrite. */
export function normalizeMath(src: string): string {
  return src
    .replace(/\\\[([\s\S]+?)\\\]/g, (_m, body) => `$$${body}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_m, body) => `$${body}$`);
}

/** Renders an assistant answer as markdown + KaTeX. Raw HTML stays DISABLED (no rehype-raw) so the
 * untrusted model output can never inject a live node; KaTeX runs with throwOnError:false/trust:false
 * so a malformed formula degrades to visible source, never a crash or an escape. The trust framing
 * (candidate/vorläufig badges, citations, the persistent SafetyBanner) lives OUTSIDE this body in the
 * surrounding components — this renders only the answer text. */
export function Markdown({ source }: { source: string }) {
  return (
    <div className="markdown" data-testid="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, trust: false, strict: false }]]}
      >
        {normalizeMath(source)}
      </ReactMarkdown>
    </div>
  );
}
