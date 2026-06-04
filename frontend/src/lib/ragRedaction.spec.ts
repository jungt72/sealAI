import { describe, expect, it } from "vitest";

import { REDACTED_PATH_LABEL, redactInternalPaths, sanitizeRagPayload } from "./ragRedaction";

describe("ragRedaction", () => {
  it("redacts unix, file and windows paths from user-visible text", () => {
    const redacted = redactInternalPaths(
      "failed at /home/thorsten/sealai/uploads/doc.pdf and file:///app/data/uploads/a.pdf and C:\\Users\\thorsten\\doc.pdf",
    );

    expect(redacted).not.toContain("/home/thorsten");
    expect(redacted).not.toContain("file:///app");
    expect(redacted).not.toContain("C:\\Users");
    expect(redacted.match(new RegExp(REDACTED_PATH_LABEL, "g"))?.length).toBe(3);
  });

  it("normalizes backend redaction tokens into a user-safe label", () => {
    expect(redactInternalPaths("Parser failed at [REDACTED_PATH]")).toBe(
      `Parser failed at ${REDACTED_PATH_LABEL}`,
    );
  });

  it("sanitizes nested rag payload path fields and errors", () => {
    const payload = sanitizeRagPayload({
      filesystem: {
        path: "/var/lib/sealai/uploads/source.pdf",
        exists: false,
      },
      issues: ["missing file /tmp/rag/source.pdf"],
      error: "ParserError: /Users/thorstenjung/Documents/source.pdf",
    });

    expect(payload.filesystem.path).toBe(REDACTED_PATH_LABEL);
    expect(payload.issues[0]).toBe(`missing file ${REDACTED_PATH_LABEL}`);
    expect(payload.error).toBe(`ParserError: ${REDACTED_PATH_LABEL}`);
  });
});
