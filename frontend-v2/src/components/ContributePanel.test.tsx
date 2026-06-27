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
    const onContribute = vi.fn().mockResolvedValue({ hinweis: "Danke — geht in die Review-Queue." });
    render(<ContributePanel onContribute={onContribute} />);
    fireEvent.click(screen.getByTestId("contrib-open"));
    fireEvent.change(screen.getByTestId("contrib-outcome"), {
      target: { value: "FKM-AS hat bei 150°C gehalten" },
    });
    fireEvent.click(screen.getByTestId("contrib-submit"));
    await waitFor(() => expect(screen.getByTestId("contrib-done")).toBeInTheDocument());
    expect(onContribute).toHaveBeenCalledWith(true, "FKM-AS hat bei 150°C gehalten"); // anonym default
    expect(screen.getByText(/Review-Queue/)).toBeInTheDocument();
  });

  it("can opt out of anonymity", async () => {
    const onContribute = vi.fn().mockResolvedValue({ hinweis: "ok" });
    render(<ContributePanel onContribute={onContribute} />);
    fireEvent.click(screen.getByTestId("contrib-open"));
    fireEvent.click(screen.getByTestId("contrib-anonym")); // toggle off
    fireEvent.click(screen.getByTestId("contrib-submit"));
    await waitFor(() => expect(onContribute).toHaveBeenCalledWith(false, ""));
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
