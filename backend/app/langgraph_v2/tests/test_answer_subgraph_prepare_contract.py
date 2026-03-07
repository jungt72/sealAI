from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app.langgraph_v2.state import Intent, SealAIState


def test_prepare_contract_builds_friendly_greeting_for_smalltalk() -> None:
    state = SealAIState(
        intent=Intent(goal="smalltalk"),
        flags={
            "frontdoor_social_opening": True,
            "frontdoor_task_intents": [],
            "frontdoor_intent_category": "CHIT_CHAT",
        },
    )
    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.resolved_parameters.get("response_style") == "friendly_greeting"
    assert contract.calc_results.get("message_type") == "smalltalk"
    assert contract.selected_fact_ids == ["friendly_greeting"]
    assert contract.respond_with_uncertainty is False


def test_prepare_contract_forces_smalltalk_when_no_facts_and_no_parameters() -> None:
    state = SealAIState(intent=Intent(goal="design_recommendation"))
    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.resolved_parameters.get("response_style") == "friendly_greeting"
    assert contract.calc_results.get("message_type") == "smalltalk"
    assert contract.selected_fact_ids == ["friendly_greeting"]
    assert contract.respond_with_uncertainty is False
