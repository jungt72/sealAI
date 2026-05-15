import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RagDocumentGrid from "./RagDocumentGrid";

vi.mock("@/lib/ragApi", () => ({
  listRagDocuments: vi.fn(async () => ({
    items: [
      {
        document_id: "doc-1",
        filename: "pump-drawing.pdf",
        content_type: "application/pdf",
        size_bytes: 2048,
        status: "indexed",
        updated_at: "2026-04-29T10:00:00Z",
        ingest_stats: { chunks: 3 },
        error: "Parser failed at /Users/thorstenjung/Documents/sealai/uploads/pump-drawing.pdf",
      },
    ],
  })),
  healthCheckRagDocument: vi.fn(async () => ({
    document_id: "doc-1",
    tenant_id: "tenant-1",
    status: "indexed",
    collection: "sealai",
    filesystem: {
      path: "/home/thorsten/sealai/uploads/pump-drawing.pdf",
      exists: false,
    },
    qdrant: {
      points: 3,
    },
    is_consistent: false,
    issues: ["missing file /tmp/rag/pump-drawing.pdf"],
  })),
  reingestRagDocument: vi.fn(),
  deleteRagDocument: vi.fn(),
  uploadRagDocument: vi.fn(),
}));

describe("RagDocumentGrid", () => {
  it("renders uploaded documents as evidence candidates, not confirmed truth", async () => {
    render(<RagDocumentGrid />);

    expect(await screen.findByText("pump-drawing.pdf")).toBeInTheDocument();
    expect(screen.getByText("Evidence-Kandidat")).toBeInTheDocument();
    expect(screen.getByText("SealingPedia Markdown & Evidence Upload")).toBeInTheDocument();
    expect(screen.getByText(/Uploads bestätigen keine technischen Werte automatisch\./i)).toBeInTheDocument();
    expect(screen.getByText("nicht automatisch bestaetigt")).toBeInTheDocument();
  });

  it("redacts internal paths from document errors and health issues", async () => {
    render(<RagDocumentGrid />);

    await screen.findByText("pump-drawing.pdf");

    await waitFor(() => {
      expect(screen.getAllByText(/interner Pfad redigiert/).length).toBeGreaterThan(0);
    });
    expect(screen.queryByText(/\/Users\/thorstenjung/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/home\/thorsten/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/tmp\/rag/)).not.toBeInTheDocument();
  });
});
