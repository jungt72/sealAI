from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    planned_cost_usd: float
    max_run_cost_usd: float
    balance_usd: float
    reason: str


def check_budget(*, planned_cost_usd: float, max_run_cost_usd: float, balance_usd: float) -> BudgetDecision:
    if planned_cost_usd < 0:
        return BudgetDecision(False, planned_cost_usd, max_run_cost_usd, balance_usd, "planned cost must be >= 0")
    if max_run_cost_usd < 0:
        return BudgetDecision(False, planned_cost_usd, max_run_cost_usd, balance_usd, "max run cost must be >= 0")
    if planned_cost_usd > max_run_cost_usd:
        return BudgetDecision(False, planned_cost_usd, max_run_cost_usd, balance_usd, "planned cost exceeds run limit")
    if planned_cost_usd > balance_usd:
        return BudgetDecision(False, planned_cost_usd, max_run_cost_usd, balance_usd, "planned cost exceeds balance")
    return BudgetDecision(True, planned_cost_usd, max_run_cost_usd, balance_usd, "ok")
