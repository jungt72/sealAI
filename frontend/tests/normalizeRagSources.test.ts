import { describe, expect, it } from "vitest";
import { normalizeRagSources } from "@/lib/useChatSseV2";

describe("normalizeRagSources sanitization", () => {
  it("removes absolute paths and includes document ids", () => {
    const input = [
      {
        document_id: "doc-1",
        filename: "specs.pdf",
        source: "/app/rag_uploads/private/specs.pdf",
      },
    ];
    const normalized = normalizeRagSources(input);
    expect(normalized).toHaveLength(1);
    expect(normalized[0].source).toBe("specs.pdf");
  });

  it("falls back to filename or document id when source missing", () => {
    const normalized = normalizeRagSources([
      {
        document_id: "doc-2",
        filename: "summary.pdf",
      },
      {
        document_id: "doc-3",
      },
    ]);
    expect(normalized[0].source).toBe("summary.pdf");
    expect(normalized[1].source).toBe("doc-3");
  });

  it("keeps sources when filename is null and provides a display label", () => {
    const normalized = normalizeRagSources([
      {
        document_id: "doc-4",
        filename: null,
        source: "s3://bucket/reports/bericht.pdf",
      },
    ]);
    expect(normalized).toHaveLength(1);
    expect(normalized[0].source).toBe("bericht.pdf");
    expect(normalized[0].filename).toBe("bericht.pdf");
  });

  it("ensures filename null still yields a non-empty label", () => {
    const normalized = normalizeRagSources([
      {
        document_id: "",
        filename: null,
        source: null,
      },
    ]);
    expect(normalized).toHaveLength(1);
    expect(normalized[0].source).toBe("Unbekannte Quelle");
    expect(normalized[0].filename).toBe("Unbekannte Quelle");
  });

  it("reads document metadata when fields are nested", () => {
    const normalized = normalizeRagSources([
      {
        source: null,
        metadata: {
          document_id: "doc-9",
          filename: "PTFE.docx",
          page: 3,
          section: "Temperaturbereich",
          score: 0.77,
        },
      },
    ]);
    expect(normalized).toHaveLength(1);
    expect(normalized[0].document_id).toBe("doc-9");
    expect(normalized[0].filename).toBe("PTFE.docx");
    expect(normalized[0].page).toBe(3);
    expect(normalized[0].section).toBe("Temperaturbereich");
    expect(normalized[0].score).toBeCloseTo(0.77);
    expect(normalized[0].source).toBe("PTFE.docx");
  });
});
