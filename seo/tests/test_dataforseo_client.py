from sealai_seo.dataforseo_budget import check_budget
from sealai_seo.dataforseo_client import summarize_user_data


def test_summarize_user_data_redacts_credentials() -> None:
    payload = {
        "status_code": 20000,
        "status_message": "Ok.",
        "cost": 0,
        "tasks_error": 0,
        "tasks": [
            {
                "result": [
                    {
                        "login": "mail@example.com",
                        "money": {"balance": 1},
                    }
                ]
            }
        ],
    }

    assert summarize_user_data(payload) == {
        "status_code": 20000,
        "status_message": "Ok.",
        "cost": 0,
        "tasks_error": 0,
        "login": "mail@example.com",
        "balance": 1,
    }


def test_dataforseo_budget_allows_planned_cost_under_limit_and_balance() -> None:
    decision = check_budget(planned_cost_usd=0.2, max_run_cost_usd=0.25, balance_usd=1.0)

    assert decision.allowed is True
    assert decision.reason == "ok"


def test_dataforseo_budget_blocks_cost_above_run_limit() -> None:
    decision = check_budget(planned_cost_usd=0.3, max_run_cost_usd=0.25, balance_usd=1.0)

    assert decision.allowed is False
    assert decision.reason == "planned cost exceeds run limit"


def test_dataforseo_budget_blocks_cost_above_balance() -> None:
    decision = check_budget(planned_cost_usd=0.2, max_run_cost_usd=0.25, balance_usd=0.1)

    assert decision.allowed is False
    assert decision.reason == "planned cost exceeds balance"
