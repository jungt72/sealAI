import { afterEach, describe, expect, it } from "vitest";

import { getCaseIdFromUrl, newCaseId, setCaseIdInUrl } from "./caseId";

afterEach(() => {
  window.history.replaceState({}, "", "/dashboard/");
});

describe("caseId URL persistence ('Fälle'-Sidebar)", () => {
  it("getCaseIdFromUrl returns null when the URL has no ?case= param", () => {
    window.history.replaceState({}, "", "/dashboard/");
    expect(getCaseIdFromUrl()).toBeNull();
  });

  it("getCaseIdFromUrl returns null for a blank ?case= param", () => {
    window.history.replaceState({}, "", "/dashboard/?case=");
    expect(getCaseIdFromUrl()).toBeNull();
  });

  it("getCaseIdFromUrl reads a present case id", () => {
    window.history.replaceState({}, "", "/dashboard/?case=abc-123");
    expect(getCaseIdFromUrl()).toBe("abc-123");
  });

  it("setCaseIdInUrl writes the param and getCaseIdFromUrl reads it back", () => {
    window.history.replaceState({}, "", "/dashboard/");
    setCaseIdInUrl("new-case-1");
    expect(getCaseIdFromUrl()).toBe("new-case-1");
    expect(window.location.pathname).toBe("/dashboard/"); // path preserved
  });

  it("setCaseIdInUrl with replace:true (default) does not grow browser history", () => {
    window.history.replaceState({}, "", "/dashboard/");
    const before = window.history.length;
    setCaseIdInUrl("case-a");
    setCaseIdInUrl("case-b");
    expect(window.history.length).toBe(before); // both replaced, no new entries
    expect(getCaseIdFromUrl()).toBe("case-b");
  });

  it("setCaseIdInUrl with replace:false adds a browser-history entry", () => {
    window.history.replaceState({}, "", "/dashboard/");
    const before = window.history.length;
    setCaseIdInUrl("case-pushed", { replace: false });
    expect(window.history.length).toBe(before + 1);
    expect(getCaseIdFromUrl()).toBe("case-pushed");
  });

  it("newCaseId returns a non-empty string and two calls never collide", () => {
    const a = newCaseId();
    const b = newCaseId();
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });
});
