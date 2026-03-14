"""
LLM write protection.

Two mechanisms:

1. ``claim_whitelist_check()`` — validates that claims only target allowed
   state fields before they reach :func:`process_cycle_update`.
2. ``assert_deterministic_unchanged()`` — post-LLM invariant check that
   the governance / cycle / selection layers were not mutated during LLM
   node execution.

Field names in the whitelist and forbidden sets are aligned with the actual
field names used in ``agent/logic.py``, ``agent/state.py``, and
``agent/calc.py``.  Do **not** change them without also updating the
reducer in ``logic.py``.
"""
import hashlib
import json
import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelist: field keys that validated_params / working_profile may contain
# ---------------------------------------------------------------------------
# These are the exact keys used in logic.py::apply_engineering_firewall_transition
# and extract_parameters.  Any key not listed here is stripped with a warning.
#
# Actual keys produced by evaluate_claim_conflicts (logic.py):
#   "temperature"  – Celsius float, from PhysicalParameter.to_base_unit()
#   "pressure"     – bar float,     from PhysicalParameter.to_base_unit()
#
# Keys used in extract_parameters / working_profile:
#   "speed"        – RPM float
#   "diameter"     – shaft diameter mm float
#   "medium"       – medium name string ("Wasser", "Öl", …)
#   "material"     – material family string ("PTFE", "NBR", …)

ALLOWED_CLAIM_TARGETS: Set[str] = {
    # Physical parameters extracted from claim statements (regex-parsed in logic.py)
    "temperature",      # operating temperature in °C
    "pressure",         # operating pressure in bar
    # Working-profile parameters (extract_parameters in logic.py)
    "speed",            # shaft speed in rpm
    "diameter",         # shaft diameter in mm
    "medium",           # sealing medium name
    "material",         # material family hint
}

# ---------------------------------------------------------------------------
# Forbidden: top-level SealingAIState layer keys + computed / derived fields
# that must NEVER be written by LLM-submitted claims.
# ---------------------------------------------------------------------------
# Top-level layers from SealingAIState (state.py):
#   governance, cycle, selection, result_contract, rwdr
# Computed physics values (calc.py):
#   v_m_s, pv_value
# Governance sub-fields (GovernanceLayer in state.py):
#   release_status, rfq_admissibility, specificity_level,
#   gate_failures, unknowns_release_blocking, unknowns_manufacturer_validation,
#   conflicts, scope_of_validity, assumptions_active
# Material qualification fields (referenced in CLAUDE.md hardening spec):
#   material_shortlist, hard_stops, qualification_level,
#   rfq_admissible, promoted_candidates

FORBIDDEN_STATE_PATHS: Set[str] = {
    # Top-level SealingAIState layers
    "governance",
    "cycle",
    "selection",
    "result_contract",
    "rwdr",
    # Computed physics (calc.py) — must not be LLM-written
    "v_m_s",
    "pv_value",
    # Governance sub-fields (GovernanceLayer)
    "release_status",
    "rfq_admissibility",
    "specificity_level",
    "gate_failures",
    "unknowns_release_blocking",
    "unknowns_manufacturer_validation",
    "conflicts",
    "scope_of_validity",
    "assumptions_active",
    # Material qualification / candidate fields
    "material_shortlist",
    "hard_stops",
    "qualification_level",
    "rfq_admissible",
    "promoted_candidates",
}


def claim_whitelist_check(validated_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter ``validated_params`` returned by :func:`evaluate_claim_conflicts`.

    Only keys present in :data:`ALLOWED_CLAIM_TARGETS` pass through.

    - Keys in :data:`FORBIDDEN_STATE_PATHS` trigger a ``CRITICAL`` log and are
      stripped.
    - Unknown keys (not in either set) trigger a ``WARNING`` log and are
      stripped.

    Args:
        validated_params: Raw dict from ``evaluate_claim_conflicts``.

    Returns:
        Cleaned dict containing only allowed keys.
    """
    clean: Dict[str, Any] = {}
    for key, value in validated_params.items():
        normalized_key = key.lower().strip()
        if normalized_key in FORBIDDEN_STATE_PATHS:
            logger.critical(
                "GUARD VIOLATION: LLM attempted to write forbidden state key %r "
                "with value %r. Stripped from state update.",
                key,
                value,
            )
            continue
        if normalized_key in ALLOWED_CLAIM_TARGETS:
            clean[key] = value
        else:
            logger.warning(
                "GUARD: Unknown claim target %r not in whitelist. Stripped.",
                key,
            )
    return clean


def snapshot_deterministic_layers(sealing_state: Dict[str, Any]) -> str:
    """
    Create a stable SHA-256 hash of the deterministic layers in sealing state.

    The deterministic layers are ``governance``, ``cycle``, and ``selection``.
    Call this function **before** any LLM node execution and compare with the
    result of :func:`assert_deterministic_unchanged` after execution.

    Args:
        sealing_state: The current ``SealingAIState`` dict.

    Returns:
        Hex-encoded SHA-256 digest of the serialised deterministic layers.
    """
    deterministic_keys = ["governance", "cycle", "selection"]
    snapshot = {key: sealing_state[key] for key in deterministic_keys if key in sealing_state}
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, default=str).encode()
    ).hexdigest()


def assert_deterministic_unchanged(
    before_hash: str,
    sealing_state: Dict[str, Any],
    node_name: str = "unknown",
) -> None:
    """
    Assert that deterministic state layers were not modified during LLM execution.

    Call this function **after** every LLM node execution, passing the hash
    obtained from :func:`snapshot_deterministic_layers` before the node ran.

    In production: logs a ``CRITICAL`` alert and raises :class:`RuntimeError`.
    In tests: the :class:`RuntimeError` causes hard assertion failure.

    Args:
        before_hash: Hash captured before LLM node execution.
        sealing_state: The state dict after LLM node execution.
        node_name: Name of the LLM node (for diagnostic messages).

    Raises:
        RuntimeError: If the deterministic layers changed during LLM execution.
    """
    after_hash = snapshot_deterministic_layers(sealing_state)
    if before_hash != after_hash:
        msg = (
            f"CRITICAL INVARIANT VIOLATION in node '{node_name}': "
            "Deterministic state layers (governance/cycle/selection) were modified "
            "during LLM execution. "
            f"Before: {before_hash}, After: {after_hash}"
        )
        logger.critical(msg)
        raise RuntimeError(msg)
