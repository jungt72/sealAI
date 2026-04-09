from app.agent.agent import clarification, readiness, reply_builder, selection
from app.agent.domain import threshold
from app.agent.state import projections_extended


def test_selection_reexports_split_module_symbols() -> None:
    assert selection.build_clarification_projection is clarification.build_clarification_projection
    assert selection.evaluate_output_readiness is readiness.evaluate_output_readiness
    assert selection.project_threshold_status is threshold.project_threshold_status
    assert selection.build_output_contract_projection is projections_extended.build_output_contract_projection
    assert selection.build_final_reply is reply_builder.build_final_reply
