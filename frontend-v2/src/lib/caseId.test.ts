import { afterEach, describe, expect, it } from "vitest";

import {
  getCaseIdFromUrl,
  newCaseId,
  setCaseIdInUrl,
  stashCaseIdForAuthRedirect,
  takeStashedCaseId,
} from "./caseId";

afterEach(() => {
  sessionStorage.clear();
  window.history.replaceState({}, "", "/dashboard/");
});

describe("caseId non-URL persistence ('Fälle'-Sidebar)", () => {
  it("returns null when history and tab storage contain no case", () => {
    expect(getCaseIdFromUrl()).toBeNull();
  });

  it("imports and synchronously scrubs a valid legacy ?case= bookmark", () => {
    window.history.replaceState({}, "", "/dashboard/?case=abc-123&view=chat");
    expect(getCaseIdFromUrl()).toBe("abc-123");
    expect(window.location.search).toBe("?view=chat");
    expect(JSON.stringify(window.history.state)).toContain("abc-123");
  });

  it("scrubs and rejects an invalid legacy case value", () => {
    window.history.replaceState({}, "", "/dashboard/?case=bad%0Avalue");
    expect(getCaseIdFromUrl()).toBeNull();
    expect(window.location.search).toBe("");
  });

  it("writes history state + session fallback without changing the URL", () => {
    setCaseIdInUrl("new-case-1");
    expect(getCaseIdFromUrl()).toBe("new-case-1");
    expect(window.location.href).not.toContain("new-case-1");
    window.history.replaceState({}, "", "/dashboard/");
    expect(getCaseIdFromUrl()).toBe("new-case-1"); // reload-style fallback
  });

  it("replace does not grow history; push does", () => {
    const before = window.history.length;
    setCaseIdInUrl("case-a");
    setCaseIdInUrl("case-b");
    expect(window.history.length).toBe(before);
    setCaseIdInUrl("case-c", { replace: false });
    expect(window.history.length).toBe(before + 1);
    expect(getCaseIdFromUrl()).toBe("case-c");
  });

  it("rejects unsafe identifiers before they can become a header", () => {
    expect(() => setCaseIdInUrl("bad\r\nX-Evil: yes")).toThrow("invalid case id");
  });

  it("newCaseId returns unique non-empty IDs", () => {
    expect(newCaseId()).not.toBe(newCaseId());
  });
});

describe("auth redirect case stash", () => {
  it("round-trips once", () => {
    stashCaseIdForAuthRedirect("case-before-redirect");
    expect(takeStashedCaseId()).toBe("case-before-redirect");
    expect(takeStashedCaseId()).toBeNull();
  });

  it("keeps only the latest valid case", () => {
    stashCaseIdForAuthRedirect("case-1");
    stashCaseIdForAuthRedirect("case-2");
    expect(takeStashedCaseId()).toBe("case-2");
  });
});
