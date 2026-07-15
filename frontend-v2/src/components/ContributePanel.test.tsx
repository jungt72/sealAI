import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { AdminPane } from "./AdminPane";
import { ContributePanel } from "./ContributePanel";

afterEach(cleanup);

describe("ContributePanel (Wissens-Beitrag)", () => {
  it("opens the form, submits anonym + outcome, shows the confirmation", async () => {
    const onContribute = vi.fn().mockResolvedValue({
      status: "captured",
      id: 1,
      anonym: true,
      lifecycle_state: "quarantined",
      prompt_trust: "untrusted",
      idempotent_replay: false,
      hinweis: "Der Beitrag liegt in Review-Quarantäne.",
    });
    render(<ContributePanel onContribute={onContribute} />);
    fireEvent.click(screen.getByTestId("contrib-open"));
    fireEvent.change(screen.getByTestId("contrib-outcome"), {
      target: { value: "FKM-AS hat bei 150°C gehalten" },
    });
    fireEvent.change(screen.getByTestId("contrib-provenance"), {
      target: { value: "eigene Felderfahrung" },
    });
    fireEvent.click(screen.getByTestId("contrib-rights-confirmed"));
    fireEvent.click(screen.getByTestId("contrib-submit"));
    await waitFor(() => expect(screen.getByTestId("contrib-done")).toBeInTheDocument());
    expect(onContribute).toHaveBeenCalledWith(true, "FKM-AS hat bei 150°C gehalten", {
      rights_confirmed: true,
      rights_basis: "review_required",
      license_id: "review_required",
      provenance: "eigene Felderfahrung",
      document_type: "other_review_required",
      pii_classification: "unknown",
      prompt_trust: "untrusted",
    });
    expect(screen.getByText(/Review-Quarantäne/)).toBeInTheDocument();
  });

  it("can opt out of anonymity", async () => {
    const onContribute = vi.fn().mockResolvedValue({
      status: "captured",
      id: 2,
      anonym: false,
      lifecycle_state: "quarantined",
      prompt_trust: "untrusted",
      idempotent_replay: false,
      hinweis: "ok",
    });
    render(<ContributePanel onContribute={onContribute} />);
    fireEvent.click(screen.getByTestId("contrib-open"));
    fireEvent.click(screen.getByTestId("contrib-anonym")); // toggle off
    fireEvent.change(screen.getByTestId("contrib-provenance"), {
      target: { value: "documented source" },
    });
    fireEvent.click(screen.getByTestId("contrib-rights-confirmed"));
    fireEvent.click(screen.getByTestId("contrib-submit"));
    await waitFor(() => expect(onContribute).toHaveBeenCalled());
    expect(onContribute.mock.calls[0][0]).toBe(false);
    expect(onContribute.mock.calls[0][1]).toBe("");
  });
});

function fakeApi(over: Partial<ApiClient> = {}): ApiClient {
  return {
    adminListHersteller: vi.fn().mockResolvedValue({ hersteller: [] }),
    adminListLeads: vi.fn().mockResolvedValue({ leads: [] }),
    adminListContributions: vi.fn().mockResolvedValue({
      contributions: [
        {
          id: 1, anonym: true, tenant_ref: "anon", subject_ref: "", situation: "RWDR 150C",
          case_state: [{ feld: "medium", wert: "Öl" }], recommendation: "FKM-AS", outcome: "hielt",
          created_at: "2026-06-27", status: "neu", review_note: "",
        },
      ],
    }),
    adminSetContributionStatus: vi.fn().mockResolvedValue({}),
    ...over,
  } as unknown as ApiClient;
}

describe("AdminPane — Beiträge-Tab (Review-Queue)", () => {
  it("lists contributions and lets the owner set a status", async () => {
    const setStatus = vi.fn().mockResolvedValue({});
    render(<AdminPane api={fakeApi({ adminSetContributionStatus: setStatus })} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("tab-beitraege"));
    await waitFor(() => expect(screen.getByTestId("contrib-1")).toBeInTheDocument());
    expect(screen.getByText(/hielt/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("contrib-reviewed-1"));
    await waitFor(() => expect(setStatus).toHaveBeenCalledWith(1, "reviewed", ""));
  });
});
