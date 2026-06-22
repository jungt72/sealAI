import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ChatResponse } from "../contracts";
import { Answer } from "./Answer";
import { Markdown, normalizeMath } from "./Markdown";

afterEach(cleanup);

describe("Markdown rendering (presentation port)", () => {
  it("typesets inline LaTeX written as \\(…\\) (the model's delimiter), not raw", () => {
    const { container } = render(<Markdown source={"Umfangsgeschwindigkeit \\(v = \\pi d n / 60000\\)."} />);
    expect(container.querySelector(".katex")).not.toBeNull(); // KaTeX-typeset
    expect(container.textContent ?? "").not.toContain("\\("); // no raw delimiter left
  });

  it("typesets display LaTeX written as \\[…\\]", () => {
    const { container } = render(<Markdown source={"\\[ v = \\pi d n / 60000 \\]"} />);
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.textContent ?? "").not.toContain("\\[");
  });

  it("renders markdown structure (bold, lists)", () => {
    const { container } = render(<Markdown source={"**fett**\n\n- eins\n- zwei"} />);
    expect(container.querySelector("strong")?.textContent).toBe("fett");
    expect(container.querySelectorAll("li").length).toBe(2);
  });

  it("XSS: raw HTML from the untrusted model is inert (no live node)", () => {
    const { container } = render(
      <Markdown source={'<img src=x onerror="alert(1)"> <script>alert(2)</script>\n\n**safe**'} />,
    );
    expect(container.querySelector("img")).toBeNull(); // raw HTML not rendered as a node
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("strong")?.textContent).toBe("safe"); // surrounding markdown still renders
  });

  it("normalizeMath converts both delimiters (display before inline)", () => {
    expect(normalizeMath("a \\(x\\) b")).toBe("a $x$ b");
    expect(normalizeMath("a \\[y\\] b")).toBe("a $$y$$ b");
  });

  it("an answer keeps its trust badges around a markdown/math body", () => {
    const res: ChatResponse = {
      answer: "Die Geschwindigkeit \\(v = \\pi d n\\) ist relevant.",
      model: "m",
      grounded: false,
      intent: null,
      citations: [],
    };
    const { container } = render(<Answer res={res} />);
    expect(screen.getByTestId("candidate-label")).toBeInTheDocument(); // candidate badge intact
    expect(screen.getByTestId("vorlaeufig-label")).toBeInTheDocument(); // ungrounded → vorläufig intact
    expect(container.querySelector(".katex")).not.toBeNull(); // math typeset inside the answer body
  });
});
