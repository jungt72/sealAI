import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Alternativen, AnfrageResponse } from "../contracts";
import { AlternativenPanel } from "./AlternativenPanel";

afterEach(cleanup);

const PARTNERS: Alternativen = {
  grounded_data: true,
  partner: true,
  ordered_by: "capability",
  hersteller: [
    {
      id: "acme",
      firmenname: "ACME Dichtungen GmbH",
      standort: "DE",
      beschreibung: "RWDR-Spezialist",
      werkstoffe: ["FKM"],
      zertifikate: ["ISO 9001"],
      website: "https://acme.example",
    },
    { id: "beta", firmenname: "Beta Seals" },
  ],
  neutralitaet: "nach Fähigkeit, nie nach Bezahlung",
};

describe("AlternativenPanel", () => {
  it("renders the partner pool (objects) + the transparent Partner·Anzeige label", () => {
    render(<AlternativenPanel data={PARTNERS} />);
    expect(screen.getByTestId("alternativen-panel")).toBeInTheDocument();
    expect(screen.getByText("ACME Dichtungen GmbH")).toBeInTheDocument();
    expect(screen.getByText("Beta Seals")).toBeInTheDocument();
    // paid listing is TRANSPARENTLY labelled — never disguised as neutral merit
    expect(screen.getByText(/Partner · Anzeige/)).toBeInTheDocument();
    expect(screen.getByText(/nach Fähigkeit/)).toBeInTheDocument();
  });

  it("shows the honest no-data hinweis when the pool is empty", () => {
    const data: Alternativen = {
      grounded_data: false,
      hinweis: "Aktuell liegen keine geerdeten Hersteller-Fähigkeitsdaten vor.",
    };
    render(<AlternativenPanel data={data} />);
    expect(
      screen.getByText(/keine geerdeten Hersteller-Fähigkeitsdaten/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("renders no Anfrage button when no handler is provided", () => {
    render(<AlternativenPanel data={PARTNERS} />);
    expect(screen.queryByTestId("anfrage-acme")).not.toBeInTheDocument();
  });

  it("fires the Anfrage and shows the returned briefing + hinweis (transparency)", async () => {
    const res: AnfrageResponse = {
      status: "captured",
      lead_id: 1,
      case_id: "case-a",
      case_revision: 7,
      read_only: true,
      partner: { hersteller: "acme", firmenname: "ACME Dichtungen GmbH" },
      briefing: {
        title: "Technische Orientierung (Screening)",
        body: "BRIEFING-INHALT",
        provenance: [],
      },
      hinweis: "Ihre Anfrage wurde an den Hersteller übermittelt.",
    };
    const onAnfrage = vi.fn().mockResolvedValue(res);
    render(<AlternativenPanel data={PARTNERS} onAnfrage={onAnfrage} />);
    fireEvent.click(screen.getByTestId("anfrage-acme"));
    await waitFor(() =>
      expect(screen.getByTestId("anfrage-done")).toBeInTheDocument(),
    );
    expect(onAnfrage).toHaveBeenCalledWith("acme");
    expect(screen.getByText(/an den Hersteller übermittelt/)).toBeInTheDocument();
    // the user transparently sees what was sent to the manufacturer
    expect(screen.getByText("BRIEFING-INHALT")).toBeInTheDocument();
  });

  it("surfaces an error state when the Anfrage fails", async () => {
    const onAnfrage = vi.fn().mockRejectedValue(new Error("boom"));
    render(<AlternativenPanel data={PARTNERS} onAnfrage={onAnfrage} />);
    fireEvent.click(screen.getByTestId("anfrage-acme"));
    await waitFor(() =>
      expect(screen.getByText(/Anfrage fehlgeschlagen/)).toBeInTheDocument(),
    );
  });

  it("offers the PDF download (without sending) and fires it", async () => {
    const onDownloadPdf = vi.fn().mockResolvedValue(undefined);
    render(<AlternativenPanel data={PARTNERS} onDownloadPdf={onDownloadPdf} />);
    fireEvent.click(screen.getByTestId("alt-download-pdf"));
    await waitFor(() => expect(onDownloadPdf).toHaveBeenCalled());
  });

  it("hides the PDF button when no handler is provided", () => {
    render(<AlternativenPanel data={PARTNERS} />);
    expect(screen.queryByTestId("alt-download-pdf")).not.toBeInTheDocument();
  });
});
