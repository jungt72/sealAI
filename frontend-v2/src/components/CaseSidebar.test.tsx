import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CaseSummary } from "../contracts";
import { CaseSidebar } from "./CaseSidebar";

afterEach(cleanup);

const CASES: CaseSummary[] = [
  { case_id: "c1", title: "EPDM in Hydrauliköl", created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-03T00:00:00Z" },
  { case_id: "c2", title: null, created_at: null, updated_at: null },
];

describe("CaseSidebar", () => {
  it("shows the loading state", () => {
    render(
      <CaseSidebar cases={[]} activeCaseId={null} loading onSelect={vi.fn()} onClose={vi.fn()} />,
    );
    expect(screen.getByText("Lädt …")).toBeInTheDocument();
  });

  it("shows the empty state when there are no cases", () => {
    render(
      <CaseSidebar
        cases={[]}
        activeCaseId={null}
        loading={false}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("case-sidebar-empty")).toBeInTheDocument();
  });

  it("renders every case with its title, falling back to a placeholder when title is null", () => {
    render(
      <CaseSidebar
        cases={CASES}
        activeCaseId={null}
        loading={false}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const items = screen.getAllByTestId("case-sidebar-item");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("EPDM in Hydrauliköl");
    expect(items[1]).toHaveTextContent("Neuer Fall");
  });

  it("marks the active case and no other", () => {
    render(
      <CaseSidebar
        cases={CASES}
        activeCaseId="c2"
        loading={false}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const items = screen.getAllByTestId("case-sidebar-item");
    expect(items[0]).not.toHaveAttribute("aria-current");
    expect(items[1]).toHaveAttribute("aria-current", "true");
  });

  it("clicking a case calls onSelect with its case_id", () => {
    const onSelect = vi.fn();
    render(
      <CaseSidebar
        cases={CASES}
        activeCaseId={null}
        loading={false}
        onSelect={onSelect}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getAllByTestId("case-sidebar-item")[0]);
    expect(onSelect).toHaveBeenCalledWith("c1");
  });

  it("the close button calls onClose", () => {
    const onClose = vi.fn();
    render(
      <CaseSidebar cases={[]} activeCaseId={null} loading={false} onSelect={vi.fn()} onClose={onClose} />,
    );
    fireEvent.click(screen.getByTestId("case-sidebar-close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("a case with no updated_at shows no relative-time label (never a bogus date)", () => {
    render(
      <CaseSidebar cases={CASES} activeCaseId={null} loading={false} onSelect={vi.fn()} onClose={vi.fn()} />,
    );
    const items = screen.getAllByTestId("case-sidebar-item");
    expect(items[1].querySelector('[data-testid="case-sidebar-item-time"]')).toBeNull();
  });
});
