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
import { AdminPane } from "./AdminPane";

afterEach(cleanup);

function fakeApi(over: Partial<ApiClient> = {}): ApiClient {
  return {
    adminListHersteller: vi.fn().mockResolvedValue({ hersteller: [] }),
    adminUpsertHersteller: vi.fn().mockResolvedValue({}),
    adminDeleteHersteller: vi.fn().mockResolvedValue({ deleted: "x" }),
    adminListLeads: vi.fn().mockResolvedValue({ leads: [] }),
    ...over,
  } as unknown as ApiClient;
}

const ACME: AdminPartner = {
  hersteller: "acme",
  firmenname: "ACME GmbH",
  aktiv: true,
  lead_email: "leads@acme",
  website: "",
  beschreibung: "",
  standort: "DE",
  kontakt_oeffentlich: "",
  partner_seit: "",
  plan: "basic",
  werkstoffe: ["FKM"],
  bauformen: ["RWDR"],
  groessen: "",
  zertifikate: [],
};

describe("AdminPane", () => {
  it("lists partners on open", async () => {
    const api = fakeApi({
      adminListHersteller: vi.fn().mockResolvedValue({ hersteller: [ACME] }),
    });
    render(<AdminPane api={api} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("ACME GmbH")).toBeInTheDocument());
    expect(screen.getByTestId("row-acme")).toBeInTheDocument();
  });

  it("creates a partner — upsert called with id + body (id NOT in body, CSV parsed)", async () => {
    const upsert = vi.fn().mockResolvedValue({});
    const api = fakeApi({ adminUpsertHersteller: upsert });
    render(<AdminPane api={api} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("admin-new"));
    fireEvent.change(screen.getByTestId("f-id"), { target: { value: "neu" } });
    fireEvent.change(screen.getByTestId("f-name"), { target: { value: "Neu GmbH" } });
    fireEvent.change(screen.getByTestId("f-werkstoffe"), {
      target: { value: "FKM, EPDM" },
    });
    fireEvent.click(screen.getByTestId("admin-save"));
    await waitFor(() => expect(upsert).toHaveBeenCalled());
    const [id, body] = upsert.mock.calls[0];
    expect(id).toBe("neu");
    expect(body.firmenname).toBe("Neu GmbH");
    expect(body.werkstoffe).toEqual(["FKM", "EPDM"]);
    expect("hersteller" in body).toBe(false);
  });

  it("blocks save with an empty id (no upsert call)", async () => {
    const upsert = vi.fn();
    const api = fakeApi({ adminUpsertHersteller: upsert });
    render(<AdminPane api={api} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("admin-new"));
    fireEvent.click(screen.getByTestId("admin-save"));
    await waitFor(() =>
      expect(screen.getByTestId("admin-error")).toBeInTheDocument(),
    );
    expect(upsert).not.toHaveBeenCalled();
  });

  it("deletes a partner", async () => {
    const del = vi.fn().mockResolvedValue({ deleted: "acme" });
    const api = fakeApi({
      adminListHersteller: vi.fn().mockResolvedValue({ hersteller: [ACME] }),
      adminDeleteHersteller: del,
    });
    render(<AdminPane api={api} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("row-acme")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("del-acme"));
    await waitFor(() => expect(del).toHaveBeenCalledWith("acme"));
  });

  it("shows leads (with the briefing) on the Leads tab", async () => {
    const api = fakeApi({
      adminListLeads: vi.fn().mockResolvedValue({
        leads: [
          {
            id: 1,
            partner_id: "acme",
            firmenname: "ACME GmbH",
            lead_email: "leads@acme",
            tenant_id: "t",
            session_id: "s",
            briefing_title: "Briefing",
            briefing_body: "INHALT",
            created_at: "2026-06-27",
            status: "neu",
          },
        ],
      }),
    });
    render(<AdminPane api={api} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("tab-leads"));
    await waitFor(() => expect(screen.getByTestId("lead-1")).toBeInTheDocument());
    expect(screen.getByText("INHALT")).toBeInTheDocument();
  });

  it("calls onClose", () => {
    const onClose = vi.fn();
    render(<AdminPane api={fakeApi()} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("admin-close"));
    expect(onClose).toHaveBeenCalled();
  });
});
