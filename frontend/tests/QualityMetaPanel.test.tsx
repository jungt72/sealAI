import React from "react";
import { create } from "react-test-renderer";
import { describe, expect, it } from "vitest";
import QualityMetaPanel from "../src/app/dashboard/components/QualityMetaPanel";
import type { ChatMeta } from "../src/types/chatMeta";

describe("QualityMetaPanel", () => {
  it("renders structured RAG sources", () => {
    const meta: ChatMeta = {
      ragSources: [
        {
          document_id: "doc-1",
          filename: "specs.pdf",
          page: 2,
          section: "Werkstoffe",
          score: 0.9,
          source: "upload",
        },
      ],
    };
    const tree = create(<QualityMetaPanel meta={meta} />).toJSON();
    const content = JSON.stringify(tree);
    expect(content).toContain("specs.pdf");
    expect(content).toContain("Seite 2");
    expect(content).toContain("Werkstoffe");
  });
});
