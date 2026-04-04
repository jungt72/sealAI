import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MediumStatusPanel from "@/components/dashboard/MediumStatusPanel";
import type { MediumStatusViewModel } from "@/lib/mediumStatusView";

function renderPanel(overrides: Partial<MediumStatusViewModel>) {
  const view: MediumStatusViewModel = {
    status: "recognized",
    statusLabel: "erkannt",
    tone: "success",
    label: "Salzwasser",
    family: "wässrig, salzhaltig",
    confidence: "hoch",
    rawMention: "salzwasser",
    summary: "Das Medium wurde erkannt und für die weitere Klärung eingeordnet.",
    nextStepHint: "Als Nächstes die Einsatzbedingungen wie Temperatur, Druck oder Konzentration präzisieren.",
    ...overrides,
  };

  render(<MediumStatusPanel view={view} />);
}

describe("MediumStatusPanel", () => {
  it("renders a recognized medium in a compact, user-facing form", () => {
    renderPanel({});

    expect(screen.getByText("Salzwasser")).toBeInTheDocument();
    expect(screen.getByText("erkannt")).toBeInTheDocument();
    expect(screen.getByText("wässrig, salzhaltig")).toBeInTheDocument();
    expect(screen.getByText("hoch")).toBeInTheDocument();
    expect(
      screen.getByText("Das Medium wurde erkannt und für die weitere Klärung eingeordnet."),
    ).toBeInTheDocument();
  });

  it("renders family_only with a precision hint instead of fake certainty", () => {
    renderPanel({
      status: "family_only",
      statusLabel: "Familienkontext erkannt",
      tone: "warning",
      label: "chemisch aggressiv",
      family: "chemisch aggressiv",
      confidence: "mittel",
      rawMention: "alkalische Reinigungslösung",
      summary: "Ein Medienkontext wurde erkannt, die genaue Einordnung ist aber noch zu präzisieren.",
      nextStepHint: "Als Nächstes die genaue Stoffart oder Konzentration präzisieren.",
    });

    expect(screen.getByText("Familienkontext erkannt")).toBeInTheDocument();
    expect(screen.getAllByText("chemisch aggressiv").length).toBeGreaterThan(0);
    expect(screen.getByText("alkalische Reinigungslösung")).toBeInTheDocument();
    expect(screen.queryByText("Als Nächstes die genaue Stoffart oder Konzentration präzisieren.")).not.toBeInTheDocument();
  });

  it("renders mentioned_unclassified with the raw mention and an honest status", () => {
    renderPanel({
      status: "mentioned_unclassified",
      statusLabel: "genannt, noch nicht eingeordnet",
      tone: "warning",
      label: "XY-Compound 4711",
      family: null,
      confidence: "niedrig",
      rawMention: "XY-Compound 4711",
      summary: "Ein Medium wurde genannt, konnte aber noch nicht belastbar klassifiziert werden.",
      nextStepHint: "Als Nächstes den Stoff, die Zusammensetzung oder den Produktnamen näher einordnen.",
    });

    expect(screen.getByText("genannt, noch nicht eingeordnet")).toBeInTheDocument();
    expect(screen.getAllByText("XY-Compound 4711").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Ein Medium wurde genannt, konnte aber noch nicht belastbar klassifiziert werden."),
    ).toBeInTheDocument();
  });

  it("renders unavailable as an open status without fake detail", () => {
    renderPanel({
      status: "unavailable",
      statusLabel: "noch offen",
      tone: "neutral",
      label: null,
      family: null,
      confidence: null,
      rawMention: null,
      summary: "Für die weitere Einordnung fehlt noch eine Angabe zum Medium.",
      nextStepHint: "Als Nächstes das Medium angeben.",
    });

    expect(screen.getAllByText("noch offen").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Für die weitere Einordnung fehlt noch eine Angabe zum Medium."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Als Nächstes das Medium angeben.")).not.toBeInTheDocument();
  });
});
