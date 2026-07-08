import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, type ApiClient } from "../api/client";
import { LegalGate } from "./LegalGate";

const DOCTRINE = {
  terms_version: "2026-07-07-v1",
  privacy_version: "2026-07-07-v1",
  dpa_version: "2026-07-07-v1",
  product_purpose_doctrine: "sealingAI ist eine KI-gestützte Wissens-, Strukturierungs- ...",
};

function stubDoctrineFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => DOCTRINE })),
  );
}

function fakeApi(over: Partial<ApiClient> = {}): ApiClient {
  return { submitLegalAcceptance: vi.fn().mockResolvedValue({ status: "accepted" }), ...over } as unknown as ApiClient;
}

async function fillRequiredFields() {
  fireEvent.change(screen.getByTestId("legal-gate-company"), { target: { value: "ACME Dichtungen GmbH" } });
  fireEvent.change(screen.getByTestId("legal-gate-email"), { target: { value: "einkauf@acme.example" } });
  fireEvent.change(screen.getByTestId("legal-gate-role"), { target: { value: "Einkauf" } });
  fireEvent.click(screen.getByTestId("legal-gate-checkbox-terms"));
  fireEvent.click(screen.getByTestId("legal-gate-checkbox-dpa"));
  await waitFor(() => expect(screen.getByTestId("legal-gate-submit")).not.toBeDisabled());
}

afterEach(cleanup);

describe("LegalGate", () => {
  it("submit is disabled until doctrine loaded + required fields + both checkboxes", async () => {
    stubDoctrineFetch();
    render(<LegalGate api={fakeApi()} onAccepted={() => {}} />);
    expect(screen.getByTestId("legal-gate-submit")).toBeDisabled();
    await fillRequiredFields();
  });

  it("submit stays disabled without the DPA checkbox even with everything else filled", async () => {
    stubDoctrineFetch();
    render(<LegalGate api={fakeApi()} onAccepted={() => {}} />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId("legal-gate-company"), { target: { value: "ACME GmbH" } });
    fireEvent.change(screen.getByTestId("legal-gate-email"), { target: { value: "a@acme.example" } });
    fireEvent.change(screen.getByTestId("legal-gate-role"), { target: { value: "Einkauf" } });
    fireEvent.click(screen.getByTestId("legal-gate-checkbox-terms")); // terms only, not DPA
    expect(screen.getByTestId("legal-gate-submit")).toBeDisabled();
  });

  it("submits the doctrine-current versions + both confirmations, then calls onAccepted", async () => {
    stubDoctrineFetch();
    const submit = vi.fn().mockResolvedValue({ status: "accepted" });
    const onAccepted = vi.fn();
    render(<LegalGate api={fakeApi({ submitLegalAcceptance: submit })} onAccepted={onAccepted} />);
    await fillRequiredFields();
    fireEvent.click(screen.getByTestId("legal-gate-submit"));
    await waitFor(() => expect(onAccepted).toHaveBeenCalled());
    expect(submit).toHaveBeenCalledWith({
      company_name: "ACME Dichtungen GmbH",
      business_email: "einkauf@acme.example",
      role: "Einkauf",
      vat_id: "",
      legal_basis_accepted: true,
      dpa_accepted: true,
      business_user_confirmed: true,
      terms_version: "2026-07-07-v1",
      privacy_version: "2026-07-07-v1",
      dpa_version: "2026-07-07-v1",
    });
  });

  it("shows a freemail-specific error on 422 and does not call onAccepted", async () => {
    stubDoctrineFetch();
    const submit = vi.fn().mockRejectedValue(new ApiError(422, "invalid"));
    const onAccepted = vi.fn();
    render(<LegalGate api={fakeApi({ submitLegalAcceptance: submit })} onAccepted={onAccepted} />);
    await fillRequiredFields();
    fireEvent.click(screen.getByTestId("legal-gate-submit"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/geschäftliche E-Mail/));
    expect(onAccepted).not.toHaveBeenCalled();
  });

  it("shows a stale-version error on 409", async () => {
    stubDoctrineFetch();
    const submit = vi.fn().mockRejectedValue(new ApiError(409, "conflict"));
    render(<LegalGate api={fakeApi({ submitLegalAcceptance: submit })} onAccepted={() => {}} />);
    await fillRequiredFields();
    fireEvent.click(screen.getByTestId("legal-gate-submit"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/aktualisiert/));
  });

  it("links to the three legal pages", async () => {
    stubDoctrineFetch();
    render(<LegalGate api={fakeApi()} onAccepted={() => {}} />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByText("Nutzungsbedingungen").closest("a")).toHaveAttribute(
      "href",
      "/nutzungsbedingungen",
    );
    expect(screen.getByText("Datenschutzerklärung").closest("a")).toHaveAttribute(
      "href",
      "/datenschutz",
    );
    expect(screen.getByText("Auftragsverarbeitungsvereinbarung (AVV)").closest("a")).toHaveAttribute(
      "href",
      "/auftragsverarbeitung",
    );
  });
});
