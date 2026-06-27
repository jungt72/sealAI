import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BriefingPane } from "./BriefingPane";

const downloadBriefingPdf = vi.fn();
vi.mock("../lib/pdf", () => ({
  downloadBriefingPdf: (...args: unknown[]) => downloadBriefingPdf(...args),
}));

afterEach(cleanup);

const BRIEFING = {
  kind: "briefing",
  title: "Technische Orientierung",
  body: "Inhalt",
  provenance: ["FK-1"],
};

describe("BriefingPane", () => {
  it("renders nothing without a briefing", () => {
    const { container } = render(<BriefingPane briefing={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the briefing + downloads it as PDF (without sending)", () => {
    render(<BriefingPane briefing={BRIEFING} />);
    expect(screen.getByTestId("briefing-body")).toHaveTextContent("Inhalt");
    fireEvent.click(screen.getByTestId("briefing-pdf"));
    expect(downloadBriefingPdf).toHaveBeenCalledWith(BRIEFING);
  });
});
