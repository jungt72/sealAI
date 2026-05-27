import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ChatComposer from "./ChatComposer";

describe("ChatComposer", () => {
  it("renders the ChatGPT-style composer controls", () => {
    render(<ChatComposer onSend={vi.fn()} onUpload={vi.fn()} placeholder="SealingAI fragen" />);

    expect(screen.getByPlaceholderText(/SealingAI fragen/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anhang hinzufügen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Antwortlänge" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Spracheingabe" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sprachmodus" })).toBeDisabled();
  });

  it("syncs external draft values without clearing local edits on null", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const { rerender } = render(<ChatComposer onSend={onSend} externalValue="RFQ-Preview vorbereiten" />);

    const composer = screen.getByPlaceholderText(/Beschreibe deine Dichtungssituation/i);
    expect(composer).toHaveValue("RFQ-Preview vorbereiten");

    await user.clear(composer);
    await user.type(composer, "Offene Punkte klaeren");
    expect(composer).toHaveValue("Offene Punkte klaeren");

    rerender(<ChatComposer onSend={onSend} externalValue={null} />);
    expect(composer).toHaveValue("Offene Punkte klaeren");

    rerender(<ChatComposer onSend={onSend} externalValue="RFQ-Preview vorbereiten" />);
    expect(composer).toHaveValue("RFQ-Preview vorbereiten");
  });
});
