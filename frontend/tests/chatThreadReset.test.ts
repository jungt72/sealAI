import { beforeEach, describe, expect, it } from "vitest";
import { clearAllThreadStorage } from "../src/app/dashboard/components/Chat/ChatContainer";

describe("chat thread hard reset", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("clears sessionStorage keys with the sealai:thread: prefix", () => {
    sessionStorage.setItem("sealai:thread:current", "sealai:thread:user-1");
    sessionStorage.setItem("sealai:thread:user-1", "thread-123");
    sessionStorage.setItem("other:key", "keep");

    const removed = clearAllThreadStorage();

    expect(removed).toBe(2);
    expect(sessionStorage.getItem("sealai:thread:current")).toBeNull();
    expect(sessionStorage.getItem("sealai:thread:user-1")).toBeNull();
    expect(sessionStorage.getItem("other:key")).toBe("keep");
  });
});
