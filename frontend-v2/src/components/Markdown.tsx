import {
  Children,
  isValidElement,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/** LaTeX delimiter normalization: the model emits `\(…\)` / `\[…\]`, but remark-math only parses
 * `$…$` / `$$…$$`. Convert the former to the latter (display first, then inline) so the math actually
 * typesets instead of rendering raw. Targeted on the model's LaTeX braces — not a general `$` rewrite. */
export function normalizeMath(src: string): string {
  return src
    .replace(/\\\[([\s\S]+?)\\\]/g, (_m, body) => `$$${body}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_m, body) => `$${body}$`);
}

/** Flatten a React children tree to its raw text (the code a copy-button must yield). */
function textOf(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="md-code-copy"
      aria-label="Code kopieren"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked (insecure context) — silent, never crash the render */
        }
      }}
    >
      {copied ? "Kopiert" : "Kopieren"}
    </button>
  );
}

/** Gemini-style code block: a framed widget with a header (language label + copy) over the <pre>.
 * `children` is the <code> element react-markdown produced — we keep it verbatim inside the <pre> so
 * the language class + content (and KaTeX-safe escaping) stay intact. */
function CodeBlock({ children }: { children?: ReactNode }) {
  const codeEl = Children.toArray(children).find(isValidElement) as ReactElement | undefined;
  const className = (codeEl?.props as { className?: string } | undefined)?.className ?? "";
  const lang = /language-([\w+-]+)/.exec(className)?.[1] ?? "";
  const code = textOf(codeEl?.props ? (codeEl.props as { children?: ReactNode }).children : children).replace(
    /\n$/,
    "",
  );
  return (
    <div className="md-code">
      <div className="md-code-head">
        <span className="md-code-lang">{lang || "Text"}</span>
        <CopyButton text={code} />
      </div>
      <pre>{children}</pre>
    </div>
  );
}

/** Renders an assistant answer as markdown + KaTeX. GFM is ON (tables, strikethrough, autolinks,
 * task-lists) so the briefing/answer formatting matches the Gemini-style reference. Raw HTML stays
 * DISABLED (no rehype-raw) so untrusted model output can never inject a live node; KaTeX runs with
 * throwOnError:false/trust:false so a malformed formula degrades to visible source, never a crash or
 * an escape. The trust framing (candidate/vorläufig badges, citations, the SafetyBanner) lives OUTSIDE
 * this body in the surrounding components — this renders only the answer text. */
export function Markdown({ source }: { source: string }) {
  return (
    <div className="markdown" data-testid="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, trust: false, strict: false }]]}
        components={{ pre: CodeBlock }}
      >
        {normalizeMath(source)}
      </ReactMarkdown>
    </div>
  );
}
