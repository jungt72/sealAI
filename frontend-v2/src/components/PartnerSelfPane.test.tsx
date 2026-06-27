import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import type { AdminPartner } from "../contracts";
import { PartnerSelfPane } from "./PartnerSelfPane";

afterEach(cleanup);

const ME: AdminPartner = {
  hersteller: "acme",
  firmenname: "ACME GmbH",
  aktiv: true,
  lead_email: "leads@acme",
  website: "",
  beschreibung: "",
  standort: "DE",
  kontakt_oeffentlich: "",
  partner_seit: "2026",
  plan: "enterprise",
  werkstoffe: ["FKM"],
  bauformen: ["RWDR"],
  groessen: "",
  zertifikate: [],
};

function fakeApi(over: Partial<ApiClient> = {}): ApiClient {
  return {
    partnerSelfGet: vi.fn().mockResolvedValue(ME),
    partnerSelfUpdate: vi.fn().mockResolvedValue(ME),
    partnerSelfLeads: vi.fn().mockResolvedValue({ leads: [] }),
    ...over,
  } as unknown as ApiClient;
}

describe("PartnerSelfPane", () => {
  it("loads the own profile with READ-ONLY membership (aktiv/plan, no input)", async () => {
    render(<PartnerSelfPane api={fakeApi()} onClose={() => {}} />);
    await waitFor(() =>
      expect(screen.getByTestId("self-form")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("self-membership")).toHaveTextContent("aktiv gelistet");
    expect(screen.getByTestId("self-membership")).toHaveTextContent("enterprise");
    expect(screen.queryByTestId("sf-aktiv")).not.toBeInTheDocument(); // not editable
  });

  it("saves editable fields — the PUT body carries NO owner-controlled fields", async () => {
    const update = vi.fn().mockResolvedValue(ME);
    render(
      <PartnerSelfPane
        api={fakeApi({ partnerSelfUpdate: update })}
        onClose={() => {}}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("self-form")).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByTestId("sf-name"), {
      target: { value: "ACME neu" },
    });
    fireEvent.change(screen.getByTestId("sf-werkstoffe"), {
      target: { value: "FKM, EPDM" },
    });
    fireEvent.click(screen.getByTestId("self-save"));
    await waitFor(() => expect(update).toHaveBeenCalled());
    const body = update.mock.calls[0][0];
    expect(body.firmenname).toBe("ACME neu");
    expect(body.werkstoffe).toEqual(["FKM", "EPDM"]);
    expect("aktiv" in body).toBe(false); // owner-controlled — never in the self PUT
    expect("plan" in body).toBe(false);
    await waitFor(() =>
      expect(screen.getByTestId("self-saved")).toBeInTheDocument(),
    );
  });

  it("shows the no-profile message on 404", async () => {
    const api = fakeApi({
      partnerSelfGet: vi.fn().mockRejectedValue({ status: 404 }),
    });
    render(<PartnerSelfPane api={api} onClose={() => {}} />);
    await waitFor(() =>
      expect(screen.getByTestId("self-no-profile")).toBeInTheDocument(),
    );
  });

  it("shows the own leads (RFQ briefings) on the Leads tab", async () => {
    const api = fakeApi({
      partnerSelfLeads: vi.fn().mockResolvedValue({
        leads: [
          {
            id: 7,
            firmenname: "x",
            briefing_title: "Briefing",
            briefing_body: "RFQ-INHALT",
            created_at: "2026",
            status: "neu",
          },
        ],
      }),
    });
    render(<PartnerSelfPane api={api} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("self-tab-leads"));
    await waitFor(() =>
      expect(screen.getByTestId("self-lead-7")).toBeInTheDocument(),
    );
    expect(screen.getByText("RFQ-INHALT")).toBeInTheDocument();
  });

  it("calls onClose", async () => {
    const onClose = vi.fn();
    render(<PartnerSelfPane api={fakeApi()} onClose={onClose} />);
    await waitFor(() =>
      expect(screen.getByTestId("self-form")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("self-close"));
    expect(onClose).toHaveBeenCalled();
  });
});
