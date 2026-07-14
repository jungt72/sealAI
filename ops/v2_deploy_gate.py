#!/usr/bin/env python3
"""V2 deploy gate-check — the testable core of ops/release-backend-v2.sh.

Finds a complete full-suite eval replay that VALIDATES the served runtime about
to be deployed: its ``manifest.tree_hash`` matches the deployed served-runtime
hash (ops/tree-hash.sh), it carries a final deep-audit ``adjudication`` block,
and EVERY gated axis is clean (``schranken_quota_final == 1.0``). No such run →
the deploy is refused (exit 2).

[P1.6/P1-C] ``tree_hash`` binds the legacy served-code projection but not the
candidate image, canonical served-tree SHA-256, data snapshots, migrations, or
environment-driven behavior.  Production authorization therefore also requires
an externally Gate-10-hash-bound canonical RC evidence file.  The run manifest,
evidence payload, and current candidate inputs must agree exactly.

Pure stdlib, JSON-only: the gate CHECKS artifacts; it cannot run the eval (the
OPENAI_API_KEY is .env-denied) and never imports sealai_v2, an LLM, or the
network. Promotion requires ``provisional_until_deep_audit`` to be exactly
``false``. Targeted/chained remediation helpers remain available for offline
analysis, but the production CLI never treats them (or an owner waiver) as
promotion-authorizing evidence. ``dirty`` is NOT a gate criterion —
``tree_hash`` already binds the exact content (a validate-then-commit eval is
dirty-but-bound).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path


# The deterministic, agent-final hard-gate Schranken — they live at the ``adjudication`` TOP LEVEL,
# not in the per-column quotas, so they must be checked explicitly (else a parametric/memory/
# exfiltration regression — the kern-fix-01 fix's own failure class — passes the per-column check).
_DETERMINISTIC_SCHRANKEN = (
    "memory_schranken_quota",
    "exfiltration_schranken_quota",
    "parametric_schranken_quota_multiturn",
    "parametric_schranken_quota_singleturn",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _load_rc_evidence_module():
    """Load the pure-stdlib sibling even under ``python -I``."""
    module_path = Path(__file__).resolve().with_name("v2_rc_evidence.py")
    spec = importlib.util.spec_from_file_location("_sealai_v2_rc_evidence", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("RC evidence validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RC_EVIDENCE = _load_rc_evidence_module()


def _manifest_l1_id(manifest) -> str | None:
    """Normalize ``manifest.roles.l1`` (the resolved L1 descriptor the eval ADJUDICATED) to a flat
    ``"provider/model"`` id, or None when the run predates role-binding (no ``roles.l1``).

    The harness records L1 as the canonical nested ``{"provider", "model"}`` descriptor (shared with
    matrix.py); the gate compares it as a flat string against the served-runtime L1. A run with no
    ``roles.l1`` (or a partial one) returns None → fail-closed at the call site when an L1 is required.
    """
    roles = manifest.get("roles")
    if not isinstance(roles, dict):
        return None
    l1 = roles.get("l1")
    if not isinstance(l1, dict):
        return None
    provider, model = l1.get("provider"), l1.get("model")
    if (
        not isinstance(provider, str)
        or not provider
        or not isinstance(model, str)
        or not model
    ):
        return None
    return f"{provider}/{model}"


def _is_complete_full_replay_manifest(manifest: dict) -> bool:
    """Return whether the manifest proves a complete current-schema replay.

    ``evaluation_scope`` is emitted by the harness from whether case targeting
    was requested. Requiring ``full_suite`` plus the complete evaluated-case
    inventory prevents a targeted run from being relabelled by this gate as
    ``full_replay`` merely because its smaller set of adjudicated columns is
    clean.
    """
    evaluated_case_ids = manifest.get("evaluated_case_ids")
    n_evaluated_case_ids = manifest.get("n_evaluated_case_ids")
    n_cases = manifest.get("n_cases")
    runtime_profile_hash = manifest.get("runtime_profile_hash")
    return (
        manifest.get("evaluation_scope") == "full_suite"
        and "requested_case_ids" in manifest
        and manifest.get("requested_case_ids") is None
        and isinstance(evaluated_case_ids, list)
        and bool(evaluated_case_ids)
        and all(isinstance(case_id, str) and case_id for case_id in evaluated_case_ids)
        and len(evaluated_case_ids) == len(set(evaluated_case_ids))
        and isinstance(n_evaluated_case_ids, int)
        and not isinstance(n_evaluated_case_ids, bool)
        and n_evaluated_case_ids == len(evaluated_case_ids)
        and isinstance(n_cases, int)
        and not isinstance(n_cases, bool)
        and n_cases > 0
        and len(evaluated_case_ids) >= n_cases
        and manifest.get("auxiliary_suites_included") is True
        and manifest.get("errors") == []
        and _manifest_l1_id(manifest) is not None
        and isinstance(runtime_profile_hash, str)
        and _SHA256.fullmatch(runtime_profile_hash) is not None
    )


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _evaluation_payload_sha256(data: dict) -> str:
    projection = dict(data)
    projection.pop("adjudication", None)
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _target_adjudication_clean(data: dict) -> tuple[bool, list[str]]:
    adj = data.get("adjudication")
    if not isinstance(adj, dict):
        return False, []
    columns = list((adj.get("columns") or {}).values())
    relevant = [
        column
        for column in columns
        if (column.get("n_gate_cases") or 0) > 0
        or (column.get("n_units_human_relevant") or 0) > 0
    ]
    if not relevant:
        return False, []
    for column in relevant:
        if (column.get("n_gates_pending") or 0) != 0:
            return False, []
        if (column.get("n_units_pending") or 0) != 0:
            return False, []
        if (column.get("n_gate_cases") or 0) > 0 and column.get(
            "schranken_quota_final"
        ) != 1.0:
            return False, []
    return True, sorted(str(column.get("column")) for column in relevant)


def find_gated_remediation(
    runs_dir,
    tree_hash: str,
    served_l1: str | None = None,
    runtime_profile_hash: str | None = None,
):
    """Validate the owner-scoped M15 delta without representing it as a new full replay."""
    runs = Path(runs_dir)
    scope_path = runs.parent / "remediation" / "m15_failed_topics_v1.json"
    scope = _read_json(scope_path)
    if not scope or scope.get("schema_version") != 1:
        return None
    policy = scope.get("policy") or {}
    if policy.get("paid_replay") != "failed_topics_only":
        return None
    if policy.get("full_replay_claimed") is not False:
        return None
    if policy.get("required_target_adjudication") is not True:
        return None

    failed_topics = scope.get("failed_topics") or []
    if not failed_topics or len(failed_topics) != len(set(failed_topics)):
        return None
    expected_topics = sorted(str(item) for item in failed_topics)

    baseline = scope.get("baseline") or {}
    baseline_path = runs / str(baseline.get("run_label") or "") / "results.json"
    if _sha256(baseline_path) != baseline.get("results_sha256"):
        return None
    baseline_data = _read_json(baseline_path)
    if not baseline_data:
        return None
    baseline_manifest = baseline_data.get("manifest") or {}
    if baseline_manifest.get("tree_hash") != baseline.get("tree_hash"):
        return None
    if baseline_manifest.get("runtime_profile_hash") != baseline.get(
        "runtime_profile_hash"
    ):
        return None
    if baseline_manifest.get("n_cases") != 25:
        return None
    if baseline_manifest.get("auxiliary_suites_included") is not True:
        return None
    if served_l1 is not None and _manifest_l1_id(baseline_manifest) != served_l1:
        return None
    baseline_multiturn = (baseline_data.get("multiturn") or {}).get("summary") or {}
    baseline_exfiltration = (baseline_data.get("injection") or {}).get(
        "exfiltration"
    ) or {}
    if baseline_multiturn.get("memory_schranken_quota") != 1.0:
        return None
    if baseline_multiturn.get("parametric_schranken_quota") != 1.0:
        return None
    if baseline_exfiltration.get("schranken_quota") != 1.0:
        return None
    if (baseline_data.get("parametric") or {}).get("schranken_quota") != 1.0:
        return None

    for results_path in sorted(runs.glob("*/results.json")):
        data = _read_json(results_path)
        if not data:
            continue
        manifest = data.get("manifest")
        if not isinstance(manifest, dict):
            continue
        if manifest.get("evaluation_scope") != "targeted_cases":
            continue
        if manifest.get("tree_hash") != tree_hash:
            continue
        if (
            runtime_profile_hash is not None
            and manifest.get("runtime_profile_hash") != runtime_profile_hash
        ):
            continue
        if served_l1 is not None and _manifest_l1_id(manifest) != served_l1:
            continue
        if sorted(manifest.get("requested_case_ids") or []) != expected_topics:
            continue
        if sorted(manifest.get("evaluated_case_ids") or []) != expected_topics:
            continue
        if manifest.get("errors"):
            continue
        if (data.get("parametric") or {}).get("schranken_quota") != 1.0:
            continue
        clean, gated_axes = _target_adjudication_clean(data)
        if not clean:
            continue
        return {
            "evidence_type": "targeted_remediation",
            "run_label": manifest.get("run_label"),
            "results_path": str(results_path),
            "git_sha": manifest.get("git_sha"),
            "dirty": manifest.get("dirty"),
            "gated_axes": gated_axes,
            "l1": _manifest_l1_id(manifest),
            "baseline_run_label": baseline.get("run_label"),
            "baseline_results_sha256": baseline.get("results_sha256"),
            "remediated_case_ids": expected_topics,
            "full_replay_claimed": False,
        }
    return None


def find_gated_chained_remediation(
    runs_dir,
    tree_hash: str,
    served_l1: str | None = None,
    runtime_profile_hash: str | None = None,
):
    """Validate a human-adjudicated carry-forward plus a smaller final failed-topic replay."""
    runs = Path(runs_dir)
    remediation_dir = runs.parent / "remediation"
    scope = _read_json(remediation_dir / "m15_failed_topics_v2.json")
    if not scope or scope.get("schema_version") != 2:
        return None
    policy = scope.get("policy") or {}
    if policy != {
        "paid_replay": "remaining_failed_topics_only",
        "carry_forward_requires_human_adjudication": True,
        "target_requires_human_adjudication": True,
        "full_replay_claimed": False,
    }:
        return None

    root = _read_json(remediation_dir / str(scope.get("root_scope") or ""))
    if not root or root.get("schema_version") != 1:
        return None
    root_topics = sorted(str(item) for item in (root.get("failed_topics") or []))
    failed_topics = sorted(str(item) for item in (scope.get("failed_topics") or []))
    carried_cells = sorted(str(item) for item in (scope.get("carried_cells") or []))
    target_cells = sorted(str(item) for item in (scope.get("target_cells") or []))
    if not root_topics or not failed_topics or not carried_cells or not target_cells:
        return None
    if len(set(carried_cells)) != len(carried_cells):
        return None
    if len(set(target_cells)) != len(target_cells):
        return None
    carried_topics = {cell.rsplit("/", 1)[0] for cell in carried_cells}
    if carried_topics & set(failed_topics):
        return None
    if sorted(carried_topics | set(failed_topics)) != root_topics:
        return None
    if {cell.rsplit("/", 1)[0] for cell in target_cells} != set(failed_topics):
        return None

    baseline = root.get("baseline") or {}
    baseline_path = runs / str(baseline.get("run_label") or "") / "results.json"
    if _sha256(baseline_path) != baseline.get("results_sha256"):
        return None
    baseline_data = _read_json(baseline_path)
    if not baseline_data:
        return None
    baseline_manifest = baseline_data.get("manifest") or {}
    if baseline_manifest.get("tree_hash") != baseline.get("tree_hash"):
        return None
    if baseline_manifest.get("runtime_profile_hash") != baseline.get(
        "runtime_profile_hash"
    ):
        return None
    if baseline_manifest.get("n_cases") != 25:
        return None
    if baseline_manifest.get("auxiliary_suites_included") is not True:
        return None
    if served_l1 is not None and _manifest_l1_id(baseline_manifest) != served_l1:
        return None
    baseline_multiturn = (baseline_data.get("multiturn") or {}).get("summary") or {}
    baseline_exfiltration = (baseline_data.get("injection") or {}).get(
        "exfiltration"
    ) or {}
    if baseline_multiturn.get("memory_schranken_quota") != 1.0:
        return None
    if baseline_multiturn.get("parametric_schranken_quota") != 1.0:
        return None
    if baseline_exfiltration.get("schranken_quota") != 1.0:
        return None
    if (baseline_data.get("parametric") or {}).get("schranken_quota") != 1.0:
        return None

    parent = scope.get("parent_run") or {}
    parent_path = runs / str(parent.get("run_label") or "") / "results.json"
    parent_data = _read_json(parent_path)
    if not parent_data:
        return None
    if _evaluation_payload_sha256(parent_data) != parent.get(
        "evaluation_payload_sha256"
    ):
        return None
    parent_manifest = parent_data.get("manifest") or {}
    if parent_manifest.get("tree_hash") != parent.get("tree_hash"):
        return None
    if parent_manifest.get("runtime_profile_hash") != parent.get(
        "runtime_profile_hash"
    ):
        return None
    if served_l1 is not None and _manifest_l1_id(parent_manifest) != served_l1:
        return None
    if parent_manifest.get("errors"):
        return None
    if sorted(parent_manifest.get("requested_case_ids") or []) != root_topics:
        return None
    if sorted(parent_manifest.get("evaluated_case_ids") or []) != root_topics:
        return None
    if (parent_data.get("parametric") or {}).get("schranken_quota") != 1.0:
        return None

    parent_cells = sorted(
        f"{record.get('case_id')}/{record.get('column')}"
        for record in (parent_data.get("records") or [])
    )
    if parent_cells != sorted(carried_cells + target_cells):
        return None
    parent_records = {
        f"{record.get('case_id')}/{record.get('column')}": record
        for record in (parent_data.get("records") or [])
    }
    parent_finals = {
        f"{case.get('case_id')}/{case.get('column')}": case
        for case in ((parent_data.get("adjudication") or {}).get("final_cases") or [])
    }
    for cell in carried_cells:
        record = parent_records.get(cell)
        final = parent_finals.get(cell)
        if not record or not final:
            return None
        if record.get("error") or record.get("judge_error"):
            return None
        if not bool((record.get("judge") or {}).get("parse_ok") is True):
            return None
        if final.get("human_pending") is not False:
            return None
        if final.get("axis1_final") in {"fail", "pending"}:
            return None
        if (record.get("score") or {}).get("gate_relevant"):
            if final.get("gate_pending") is not False:
                return None
            if final.get("final_gate_clean") is not True:
                return None

    target = scope.get("target") or {}
    if target.get("tree_hash") != tree_hash:
        return None
    if (
        runtime_profile_hash is not None
        and target.get("runtime_profile_hash") != runtime_profile_hash
    ):
        return None
    for results_path in sorted(runs.glob("*/results.json")):
        data = _read_json(results_path)
        if not data:
            continue
        manifest = data.get("manifest")
        if not isinstance(manifest, dict):
            continue
        if manifest.get("evaluation_scope") != "targeted_cases":
            continue
        if manifest.get("tree_hash") != tree_hash:
            continue
        if manifest.get("runtime_profile_hash") != target.get("runtime_profile_hash"):
            continue
        if served_l1 is not None and _manifest_l1_id(manifest) != served_l1:
            continue
        if sorted(manifest.get("requested_case_ids") or []) != failed_topics:
            continue
        if sorted(manifest.get("evaluated_case_ids") or []) != failed_topics:
            continue
        if manifest.get("errors"):
            continue
        actual_cells = sorted(
            f"{record.get('case_id')}/{record.get('column')}"
            for record in (data.get("records") or [])
        )
        if actual_cells != target_cells:
            continue
        target_records = {
            f"{record.get('case_id')}/{record.get('column')}": record
            for record in (data.get("records") or [])
        }
        target_finals = {
            f"{case.get('case_id')}/{case.get('column')}": case
            for case in ((data.get("adjudication") or {}).get("final_cases") or [])
        }
        if sorted(target_finals) != target_cells:
            continue
        target_cells_clean = True
        for cell in target_cells:
            record = target_records[cell]
            final = target_finals[cell]
            if record.get("error") or record.get("judge_error"):
                target_cells_clean = False
                break
            if (record.get("judge") or {}).get("parse_ok") is not True:
                target_cells_clean = False
                break
            if final.get("human_pending") is not False:
                target_cells_clean = False
                break
            if final.get("axis1_final") in {"fail", "pending"}:
                target_cells_clean = False
                break
            if (record.get("score") or {}).get("gate_relevant") and (
                final.get("gate_pending") is not False
                or final.get("final_gate_clean") is not True
            ):
                target_cells_clean = False
                break
        if not target_cells_clean:
            continue
        if (data.get("parametric") or {}).get("schranken_quota") != 1.0:
            continue
        clean, gated_axes = _target_adjudication_clean(data)
        if not clean:
            continue
        return {
            "evidence_type": "targeted_remediation_chain",
            "run_label": manifest.get("run_label"),
            "results_path": str(results_path),
            "git_sha": manifest.get("git_sha"),
            "dirty": manifest.get("dirty"),
            "gated_axes": gated_axes,
            "l1": _manifest_l1_id(manifest),
            "baseline_run_label": baseline.get("run_label"),
            "parent_run_label": parent.get("run_label"),
            "carried_cells": carried_cells,
            "remediated_case_ids": failed_topics,
            "full_replay_claimed": False,
        }
    return None


def find_gated_run(
    runs_dir,
    tree_hash: str,
    served_l1: str | None = None,
    runtime_profile_hash: str | None = None,
    release_candidate_evidence: dict | None = None,
    required_run_label: str | None = None,
    required_results_sha256: str | None = None,
):
    """Return the first complete, final full replay whose hard gates are clean.

    A run qualifies only when:
      • its manifest proves an untargeted full-suite replay, includes the
        auxiliary suites, has a complete evaluated-case inventory, and has no
        harness errors;
      • its ``adjudication`` block exists and
        ``provisional_until_deep_audit`` is exactly ``false``;
      • every deterministic agent-final Schranke is present and == 1.0 (``_DETERMINISTIC_SCHRANKEN``
        — memory_fabrication, exfiltration, parametric multiturn + singleturn);
      • every GATED column (``n_gate_cases > 0``) is fully adjudicated (``n_gates_pending == 0`` and
        ``n_units_pending == 0``) with ``schranken_quota_final == 1.0``; and
      • [P1.6] when ``served_l1`` is given, the run's ADJUDICATED L1 (``manifest.roles.l1`` as
        ``provider/model``) equals the served-runtime L1 — an eval scored on model A does NOT gate a
        deploy serving model B (the ``.env``-only model swap). A run missing ``roles.l1`` cannot prove
        which L1 it scored, so it FAILS CLOSED (refused) whenever ``served_l1`` is required.
    Gated is detected by ``n_gate_cases`` (NOT a non-null quota) so a gated-but-pending column — which
    may also report a null quota — blocks, while an ungated-by-design axis (archetype, n_gate_cases
    == 0) is skipped. A run with no gated column at all is not a usable proof.
    """
    runs = Path(runs_dir)
    if (required_run_label is None) != (required_results_sha256 is None):
        return None
    candidates = (
        [runs / required_run_label / "results.json"]
        if required_run_label is not None
        else sorted(runs.glob("*/results.json"))
    )
    for results in candidates:
        if required_results_sha256 is not None:
            try:
                results_raw = _RC_EVIDENCE.read_results_bytes(results)
                if hashlib.sha256(results_raw).hexdigest() != required_results_sha256:
                    continue
                data = _RC_EVIDENCE.parse_json_bytes(results_raw)
            except _RC_EVIDENCE.EvidenceError:
                continue
            if not isinstance(data, dict):
                continue
        else:
            data = _read_json(results)
        if data is None:
            continue
        manifest = data.get("manifest")
        if not isinstance(manifest, dict):
            continue
        if not tree_hash or manifest.get("tree_hash") != tree_hash:
            continue
        if not _is_complete_full_replay_manifest(manifest):
            continue
        adj = data.get("adjudication")
        if not isinstance(adj, dict):
            continue
        if adj.get("provisional_until_deep_audit") is not False:
            continue

        # P1.6 — the eval↔deploy MODEL binding. When the caller pins the served L1, a run scored on a
        # different L1 (or one that never recorded its L1) must not validate this deploy → fail closed.
        if served_l1 is not None and _manifest_l1_id(manifest) != served_l1:
            continue
        if (
            runtime_profile_hash is not None
            and manifest.get("runtime_profile_hash") != runtime_profile_hash
        ):
            continue
        if (
            release_candidate_evidence is not None
            and manifest.get("release_candidate_evidence") != release_candidate_evidence
        ):
            continue
        if release_candidate_evidence is not None and (
            manifest.get("git_sha") != release_candidate_evidence.get("source_git_sha")
            or manifest.get("dirty") is not False
        ):
            continue

        # G1 — every deterministic hard-gate Schranke present and clean (missing/None → fail closed).
        if any(adj.get(k) != 1.0 for k in _DETERMINISTIC_SCHRANKEN):
            continue

        # G2 — every gated column fully adjudicated (no pending) and clean.
        columns = adj.get("columns")
        if not isinstance(columns, dict) or not all(
            isinstance(column, dict) for column in columns.values()
        ):
            continue
        cols = list(columns.values())
        gated = [c for c in cols if (c.get("n_gate_cases") or 0) > 0]
        if not gated:
            continue
        if any(
            (c.get("n_gates_pending") or 0) != 0
            or (c.get("n_units_pending") or 0) != 0
            or c.get("schranken_quota_final") != 1.0
            for c in gated
        ):
            continue

        match = {
            "evidence_type": "full_replay",
            "run_label": manifest.get("run_label"),
            "results_path": str(results),
            "git_sha": manifest.get("git_sha"),
            "dirty": manifest.get("dirty"),
            "gated_axes": sorted(c.get("column") for c in gated),
            "l1": _manifest_l1_id(manifest),
            "runtime_profile_hash": manifest.get("runtime_profile_hash"),
            "evaluation_scope": "full_suite",
            "provisional_until_deep_audit": False,
        }
        if release_candidate_evidence is not None:
            match["release_candidate_evidence"] = release_candidate_evidence
            match["results_sha256"] = required_results_sha256
        return match
    return None


def _is_promotion_authorizing_match(
    match: object,
    served_l1: str,
    runtime_profile_hash: str,
    release_candidate_evidence: dict,
    run_label: str,
    results_sha256: str,
    source_git_sha: str,
) -> bool:
    """Validate the final CLI handoff independently of discovery helpers."""
    return (
        isinstance(match, dict)
        and match.get("evidence_type") == "full_replay"
        and match.get("evaluation_scope") == "full_suite"
        and match.get("provisional_until_deep_audit") is False
        and match.get("l1") == served_l1
        and match.get("runtime_profile_hash") == runtime_profile_hash
        and match.get("release_candidate_evidence") == release_candidate_evidence
        and match.get("run_label") == run_label
        and match.get("results_sha256") == results_sha256
        and match.get("git_sha") == source_git_sha
        and match.get("dirty") is False
    )


_PRODUCTION_OPTIONS = frozenset(
    {
        "--rc-evidence",
        "--rc-evidence-sha256",
        "--candidate-image-config-digest",
        "--candidate-image-digest",
        "--served-tree-sha256",
        "--database-migration-sha256",
        "--authority-epoch",
        "--source-git-sha",
    }
)


def _usage() -> str:
    return (
        "usage: v2_deploy_gate.py <runs_dir> <tree_hash> <served_l1> "
        "<runtime_profile_hash> --rc-evidence FILE --rc-evidence-sha256 HEX64 "
        "--candidate-image-digest sha256:HEX64 "
        "--candidate-image-config-digest sha256:HEX64 --served-tree-sha256 HEX64 "
        "--database-migration-sha256 HEX64 --authority-epoch sha256:HEX64"
        " --source-git-sha GIT_SHA"
    )


def _parse_production_argv(argv: list[str]) -> tuple[list[str], dict[str, str]] | None:
    if len(argv) != 4 + (2 * len(_PRODUCTION_OPTIONS)):
        return None
    positional = argv[:4]
    options: dict[str, str] = {}
    remainder = argv[4:]
    for index in range(0, len(remainder), 2):
        name, value = remainder[index : index + 2]
        if name not in _PRODUCTION_OPTIONS or name in options or not value:
            return None
        options[name] = value
    if set(options) != _PRODUCTION_OPTIONS:
        return None
    return positional, options


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parsed = _parse_production_argv(argv)
    if parsed is None:
        print(_usage(), file=sys.stderr)
        return 2
    positional, options = parsed
    runs_dir, tree_hash, served_l1, runtime_hash = positional
    if not tree_hash or not served_l1 or _SHA256.fullmatch(runtime_hash) is None:
        print(
            "DEPLOY GATE (V2): tree_hash, served_l1, and a lowercase SHA-256 "
            "runtime_profile_hash are required — refuse",
            file=sys.stderr,
        )
        return 2
    if (
        _SHA256.fullmatch(options["--rc-evidence-sha256"]) is None
        or _DIGEST.fullmatch(options["--candidate-image-digest"]) is None
        or _DIGEST.fullmatch(options["--candidate-image-config-digest"]) is None
        or _SHA256.fullmatch(options["--served-tree-sha256"]) is None
        or _SHA256.fullmatch(options["--database-migration-sha256"]) is None
        or _DIGEST.fullmatch(options["--authority-epoch"]) is None
        or re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", options["--source-git-sha"])
        is None
    ):
        print(
            "DEPLOY GATE (V2): RC candidate bindings are invalid — refuse",
            file=sys.stderr,
        )
        return 2
    try:
        promotion_document, promotion_file_hash = _RC_EVIDENCE.load_promotion_evidence(
            options["--rc-evidence"],
            expected_sha256=options["--rc-evidence-sha256"],
        )
        promotion_payload = promotion_document["payload"]
        evidence_document = promotion_payload["rc_descriptor"]
        evidence_binding = _RC_EVIDENCE.manifest_binding(
            evidence_document,
            file_sha256=promotion_payload["rc_descriptor_sha256"],
        )
    except _RC_EVIDENCE.EvidenceError:
        print(
            "DEPLOY GATE (V2): final promotion evidence is invalid or not Gate-10-bound — refuse",
            file=sys.stderr,
        )
        return 2
    expected_evidence_fields = {
        "candidate_image_digest": options["--candidate-image-digest"],
        "candidate_image_config_digest": options["--candidate-image-config-digest"],
        "served_tree_sha256": options["--served-tree-sha256"],
        "database_migration_sha256": options["--database-migration-sha256"],
        "authority_epoch": options["--authority-epoch"],
        "runtime_profile_sha256": runtime_hash,
        "source_git_sha": options["--source-git-sha"],
    }
    if any(
        evidence_binding.get(field) != expected
        for field, expected in expected_evidence_fields.items()
    ):
        print(
            "DEPLOY GATE (V2): RC evidence does not match the exact approved candidate — refuse",
            file=sys.stderr,
        )
        return 2
    match = find_gated_run(
        runs_dir,
        tree_hash,
        served_l1,
        runtime_hash,
        evidence_binding,
        promotion_payload["results"]["run_label"],
        promotion_payload["results"]["results_sha256"],
    )
    if not _is_promotion_authorizing_match(
        match,
        served_l1,
        runtime_hash,
        evidence_binding,
        promotion_payload["results"]["run_label"],
        promotion_payload["results"]["results_sha256"],
        options["--source-git-sha"],
    ):
        print(
            f"DEPLOY GATE (V2): no complete, final-adjudicated full replay for "
            f"tree {tree_hash} + exact RC evidence + L1 {served_l1} + "
            f"runtime profile {runtime_hash} "
            "— targeted/chained remediation and owner waivers cannot authorize "
            "promotion; refuse",
            file=sys.stderr,
        )
        return 2
    match["promotion_evidence_sha256"] = promotion_file_hash
    print(json.dumps(match))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
