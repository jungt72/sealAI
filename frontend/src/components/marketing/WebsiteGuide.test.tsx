import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { WebsiteGuide } from "./WebsiteGuide";
import { guide } from "@/lib/marketing/homeContent";

describe("WebsiteGuide", () => {
  it("deflects a concrete technical question to the free analysis and gives no recommendation", () => {
    render(<WebsiteGuide />);

    fireEvent.change(screen.getByLabelText("Frage zu sealingAI"), {
      target: { value: "Welche Dichtung soll ich für Hydrauliköl 80 °C nehmen?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Fragen$/i }));

    // The guardrail answer is shown verbatim...
    expect(screen.getByText(guide.guardrail)).toBeInTheDocument();
    // ...and it redirects to the free analysis.
    expect(screen.getByRole("link", { name: /Kostenlos analysieren/i })).toBeInTheDocument();
    // ...and it recommends no material.
    expect(screen.queryByText(/NBR|FKM|PTFE|EPDM|Viton/)).not.toBeInTheDocument();
  });

  it("answers a platform question about neutrality without deflecting", () => {
    render(<WebsiteGuide />);
    fireEvent.click(screen.getByRole("button", { name: /Ist sealingAI neutral\?/i }));

    expect(screen.getByText(/technische Bewertung ist nicht käuflich/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Kostenlos analysieren/i })).not.toBeInTheDocument();
  });
});
