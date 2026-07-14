"""Deterministic, cost-free blinded review workflow for the RWDR shadow controller.

This module deliberately has no LLM, retrieval, network, production database, or
activation dependency. It exports controlled CaseState comparisons and only
recomputes human-entered verdicts after the reviewer signs an attestation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sealai_v2.core.case_state import (
    CaseField,
    CaseFieldSource,
    CaseFieldStatus,
    CaseStateV2,
)
from sealai_v2.db.interview import InProcessInterviewRepository
from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack
from sealai_v2.pipeline.adaptive_interview import AdaptiveInterviewService

_EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS_PATH = _EVAL_DIR / "seed_cases" / "rwdr_shadow_review_v1.json"
_PACK_PATH = _EVAL_DIR.parent / "knowledge" / "domain_packs" / "rwdr.v1.json"

WORKSHEET_FILENAME = "worksheet.csv"
BLINDING_KEY_FILENAME = "blinding_key.json"
ATTESTATION_FILENAME = "review_attestation.json"
MANIFEST_FILENAME = "manifest.json"
ADJUDICATION_FILENAME = "adjudication.json"

_REVIEWABLE_DIVERGENCES = {
    "different_need",
    "legacy_question_only",
    "controller_question_only",
    "controller_escalates",
}
_IMMUTABLE_COLUMNS = (
    "case_id",
    "scenario_group",
    "case_context_de",
    "question_a_de",
    "question_b_de",
)
_RATING_COLUMNS = (
    "preferred_next_action",
    "relevant_to_case",
    "critical_gate_skipped",
    "asks_documented_information",
    "answerable_or_handles_unknown",
    "rationale",
)
_WORKSHEET_COLUMNS = (*_IMMUTABLE_COLUMNS, "review_unit_hash", *_RATING_COLUMNS)
_ALLOWED_RATINGS = {
    "preferred_next_action": {"A", "B", "tie"},
    "relevant_to_case": {"A", "B", "both", "neither"},
    "critical_gate_skipped": {"A", "B", "both", "none"},
    "asks_documented_information": {"A", "B", "both", "none"},
    "answerable_or_handles_unknown": {"A", "B", "both", "neither"},
}
_ATTESTATION_TEXT = (
    "Ich bestaetige, alle Zeilen verblindet und vor dem Oeffnen von "
    "blinding_key.json bewertet zu haben."
)
_FIELD_LABELS = {
    "dichtungstyp": "Dichtungstyp",
    "anwendungsziel": "Anwendungsziel",
    "medium": "Medium",
    "betriebstemperatur": "Betriebstemperatur",
    "druck": "Druckregime",
    "wellendurchmesser": "Wellendurchmesser",
    "drehzahl": "Drehzahl",
}


class ReviewWorkflowError(ValueError):
    """Raised when review evidence is incomplete, inconsistent, or modified."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _load_corpus(path: Path) -> dict[str, Any]:
    try:
        corpus = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewWorkflowError(f"review corpus cannot be loaded: {exc}") from exc

    required = {
        "schema_version",
        "review_set_id",
        "pack_id",
        "pack_version",
        "policy_version",
        "profiles",
        "cases",
    }
    missing = required - set(corpus)
    if missing:
        raise ReviewWorkflowError(f"review corpus is missing {sorted(missing)}")
    if corpus["schema_version"] != "1.0":
        raise ReviewWorkflowError("unsupported review corpus schema")
    if len(corpus["cases"]) < 30:
        raise ReviewWorkflowError("at least 30 controlled review cases are required")

    profile_ids = [item.get("profile_id") for item in corpus["profiles"]]
    case_ids = [item.get("case_id") for item in corpus["cases"]]
    if len(profile_ids) != len(set(profile_ids)):
        raise ReviewWorkflowError("profile_id values must be unique")
    if len(case_ids) != len(set(case_ids)):
        raise ReviewWorkflowError("case_id values must be unique")
    if any(not value for value in (*profile_ids, *case_ids)):
        raise ReviewWorkflowError("profile_id and case_id values are required")
    return corpus


def _validate_versions(corpus: dict[str, Any]) -> None:
    pack = load_rwdr_v1_pack()
    expected = (pack.pack_id, pack.version, pack.policy_version)
    actual = (
        corpus["pack_id"],
        corpus["pack_version"],
        corpus["policy_version"],
    )
    if actual != expected:
        raise ReviewWorkflowError(
            "review corpus versions do not match the loaded domain pack: "
            f"corpus={actual!r}, pack={expected!r}"
        )


def _mapped_legacy_need(question_text: str) -> str | None:
    text = question_text.casefold()
    matched = {
        question.primary_need_id
        for question in load_rwdr_v1_pack().questions
        if any(alias.casefold() in text for alias in question.legacy_aliases)
    }
    return next(iter(matched)) if len(matched) == 1 else None


def _case_state(case: dict[str, Any], profile: dict[str, Any]) -> CaseStateV2:
    omitted = set(case.get("omit_fields", ()))
    fields = profile.get("fields")
    if not isinstance(fields, dict) or fields.get("dichtungstyp") is None:
        raise ReviewWorkflowError(
            f"profile {profile.get('profile_id')} has no RWDR CaseState fields"
        )
    unknown_omissions = omitted - set(fields)
    if unknown_omissions:
        raise ReviewWorkflowError(
            f"case {case['case_id']} omits unknown fields {sorted(unknown_omissions)}"
        )
    if not omitted:
        raise ReviewWorkflowError(
            f"case {case['case_id']} must omit at least one field"
        )
    return CaseStateV2(
        case_id=case["case_id"],
        revision=1,
        fields=tuple(
            CaseField(
                key=key,
                value=str(value),
                status=CaseFieldStatus.CONFIRMED,
                source=CaseFieldSource(kind="user_form"),
            )
            for key, value in fields.items()
            if key not in omitted
        ),
    )


def _case_context(
    case: dict[str, Any], profile: dict[str, Any], state: CaseStateV2
) -> str:
    documented = "; ".join(
        f"{_FIELD_LABELS.get(field.key, field.key)}={field.value}"
        for field in state.fields
    )
    missing = ", ".join(
        _FIELD_LABELS.get(key, key) for key in case.get("omit_fields", ())
    )
    return (
        f"Szenario: {profile['label_de']}. Dokumentiert: {documented}. "
        f"Nicht dokumentiert: {missing}."
    )


def _review_unit_hash(row: dict[str, str]) -> str:
    immutable = {key: row[key] for key in _IMMUTABLE_COLUMNS}
    payload = json.dumps(
        immutable,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _controller_side_by_case(corpus: dict[str, Any]) -> dict[str, str]:
    review_set_id = corpus["review_set_id"]
    ranked = sorted(
        (
            _sha256_bytes(f"{review_set_id}:{case['case_id']}".encode("utf-8")),
            case["case_id"],
        )
        for case in corpus["cases"]
    )
    split = len(ranked) // 2
    return {
        case_id: ("A" if index < split else "B")
        for index, (_, case_id) in enumerate(ranked)
    }


def _render_worksheet(rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=_WORKSHEET_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")


def export_review_set(
    output_dir: Path | str,
    *,
    corpus_path: Path | str = DEFAULT_CORPUS_PATH,
) -> dict[str, Any]:
    """Export a balanced blinded worksheet and separate unblinding key."""
    output_dir = Path(output_dir)
    corpus_path = Path(corpus_path)
    corpus = _load_corpus(corpus_path)
    _validate_versions(corpus)
    profiles = {item["profile_id"]: item for item in corpus["profiles"]}
    controller_sides = _controller_side_by_case(corpus)
    pack = load_rwdr_v1_pack()

    protected_outputs = (
        WORKSHEET_FILENAME,
        BLINDING_KEY_FILENAME,
        ATTESTATION_FILENAME,
        MANIFEST_FILENAME,
        ADJUDICATION_FILENAME,
    )
    existing = [name for name in protected_outputs if (output_dir / name).exists()]
    if existing:
        raise ReviewWorkflowError(
            f"review directory already contains protected artifacts: {existing}"
        )

    rows: list[dict[str, str]] = []
    key_entries: list[dict[str, Any]] = []
    for case in sorted(corpus["cases"], key=lambda item: item["case_id"]):
        profile = profiles.get(case.get("profile_id"))
        if profile is None:
            raise ReviewWorkflowError(
                f"case {case['case_id']} references an unknown profile"
            )
        state = _case_state(case, profile)
        legacy_need = _mapped_legacy_need(case["legacy_question_de"])
        if legacy_need != case["expected_legacy_need"]:
            raise ReviewWorkflowError(
                f"case {case['case_id']} legacy question maps to {legacy_need!r}, "
                f"not {case['expected_legacy_need']!r}"
            )

        service = AdaptiveInterviewService(
            pack=pack,
            repository=InProcessInterviewRepository(),
        )
        evaluation = service.evaluate(
            tenant_id="controlled-review",
            session_id=case["case_id"],
            case_state=state,
            legacy_answer_text=(
                "**Noch erforderlich**\n- " + case["legacy_question_de"]
            ),
            persist_shadow=False,
        )
        if evaluation is None or evaluation.next_question is None:
            raise ReviewWorkflowError(
                f"case {case['case_id']} produced no comparable controller question"
            )
        controller_need = evaluation.next_question.primary_need_id
        if controller_need != case["expected_controller_need"]:
            raise ReviewWorkflowError(
                f"case {case['case_id']} controller selected {controller_need!r}, "
                f"not {case['expected_controller_need']!r}"
            )
        if evaluation.divergence_type not in _REVIEWABLE_DIVERGENCES:
            raise ReviewWorkflowError(
                f"case {case['case_id']} is not reviewable: "
                f"{evaluation.divergence_type}"
            )

        controller_side = controller_sides[case["case_id"]]
        legacy_side = "B" if controller_side == "A" else "A"
        questions = {
            controller_side: evaluation.next_question.question_text,
            legacy_side: case["legacy_question_de"],
        }
        row = {
            "case_id": case["case_id"],
            "scenario_group": case["scenario_group"],
            "case_context_de": _case_context(case, profile, state),
            "question_a_de": questions["A"],
            "question_b_de": questions["B"],
            "review_unit_hash": "",
            **{column: "" for column in _RATING_COLUMNS},
        }
        row["review_unit_hash"] = _review_unit_hash(row)
        rows.append(row)
        key_entries.append(
            {
                "case_id": case["case_id"],
                "question_a_source": (
                    "controller" if controller_side == "A" else "legacy"
                ),
                "question_b_source": (
                    "controller" if controller_side == "B" else "legacy"
                ),
                "controller_need_id": controller_need,
                "legacy_need_id": legacy_need,
                "divergence_type": evaluation.divergence_type,
                "controller_rule_refs": list(evaluation.next_question.rule_refs),
            }
        )

    if len(rows) < 30:
        raise ReviewWorkflowError("fewer than 30 reviewable rows were produced")
    controller_a = sum(
        item["question_a_source"] == "controller" for item in key_entries
    )
    if abs(controller_a - (len(key_entries) - controller_a)) > 1:
        raise ReviewWorkflowError("blinding allocation is not balanced")

    worksheet_bytes = _render_worksheet(rows)
    key = {
        "schema_version": "1.0",
        "review_set_id": corpus["review_set_id"],
        "warning": "Do not open before the blinded worksheet is complete.",
        "entries": key_entries,
    }
    key_bytes = _json_bytes(key)
    attestation = {
        "schema_version": "1.0",
        "review_set_id": corpus["review_set_id"],
        "reviewer": "",
        "reviewed_at": "",
        "reviewed_blinded": None,
        "attestation": "",
        "required_attestation_text": _ATTESTATION_TEXT,
    }
    attestation_bytes = _json_bytes(attestation)
    manifest = {
        "schema_version": "1.0",
        "review_set_id": corpus["review_set_id"],
        "pack_id": pack.pack_id,
        "pack_version": pack.version,
        "policy_version": pack.policy_version,
        "question_catalog_version": pack.question_catalog_version,
        "review_units": len(rows),
        "reviewable_divergence_types": sorted(
            {item["divergence_type"] for item in key_entries}
        ),
        "controller_a_count": controller_a,
        "controller_b_count": len(key_entries) - controller_a,
        "corpus_sha256": _sha256_file(corpus_path),
        "domain_pack_sha256": _sha256_file(_PACK_PATH),
        "worksheet_template_sha256": _sha256_bytes(worksheet_bytes),
        "blinding_key_sha256": _sha256_bytes(key_bytes),
        "attestation_template_sha256": _sha256_bytes(attestation_bytes),
        "additional_llm_calls": 0,
        "network_calls": 0,
        "human_adjudication_required": True,
        "automatic_activation_authorized": False,
    }

    _atomic_write(output_dir / WORKSHEET_FILENAME, worksheet_bytes)
    _atomic_write(output_dir / BLINDING_KEY_FILENAME, key_bytes)
    _atomic_write(output_dir / ATTESTATION_FILENAME, attestation_bytes)
    _atomic_write(output_dir / MANIFEST_FILENAME, _json_bytes(manifest))
    return manifest


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewWorkflowError(f"{label} cannot be loaded: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewWorkflowError(f"{label} must be a JSON object")
    return value


def _read_worksheet(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _WORKSHEET_COLUMNS:
                raise ReviewWorkflowError("worksheet columns or order were modified")
            rows = list(reader)
    except OSError as exc:
        raise ReviewWorkflowError(f"worksheet cannot be loaded: {exc}") from exc
    return rows


def _validate_attestation(attestation: dict[str, Any], *, review_set_id: str) -> None:
    if attestation.get("review_set_id") != review_set_id:
        raise ReviewWorkflowError("attestation belongs to another review set")
    if not str(attestation.get("reviewer", "")).strip():
        raise ReviewWorkflowError("attestation reviewer is required")
    if attestation.get("reviewed_blinded") is not True:
        raise ReviewWorkflowError("reviewed_blinded must be true")
    if attestation.get("attestation") != _ATTESTATION_TEXT:
        raise ReviewWorkflowError("the required blinded-review attestation is missing")
    reviewed_at = str(attestation.get("reviewed_at", "")).strip()
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewWorkflowError("reviewed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ReviewWorkflowError("reviewed_at must include a timezone")


def _source_for_side(key: dict[str, Any], side: str) -> str:
    return key[f"question_{side.casefold()}_source"]


def _sources_for_rating(key: dict[str, Any], value: str) -> set[str]:
    if value in {"both"}:
        return {"controller", "legacy"}
    if value in {"none", "neither", "tie"}:
        return set()
    return {_source_for_side(key, value)}


def adjudicate_review_set(
    review_dir: Path | str,
    *,
    output_path: Path | str | None = None,
    corpus_path: Path | str = DEFAULT_CORPUS_PATH,
) -> dict[str, Any]:
    """Validate a completed worksheet and unblind only its aggregate results."""
    review_dir = Path(review_dir)
    corpus_path = Path(corpus_path)
    output_path = (
        Path(output_path)
        if output_path is not None
        else review_dir / ADJUDICATION_FILENAME
    )
    manifest = _load_json(review_dir / MANIFEST_FILENAME, label="manifest")
    key = _load_json(review_dir / BLINDING_KEY_FILENAME, label="blinding key")
    attestation = _load_json(
        review_dir / ATTESTATION_FILENAME,
        label="review attestation",
    )
    corpus = _load_corpus(corpus_path)
    _validate_versions(corpus)

    review_set_id = manifest.get("review_set_id")
    if not review_set_id or review_set_id != corpus["review_set_id"]:
        raise ReviewWorkflowError("manifest and corpus review_set_id differ")
    pack = load_rwdr_v1_pack()
    manifest_versions = (
        manifest.get("pack_id"),
        manifest.get("pack_version"),
        manifest.get("policy_version"),
        manifest.get("question_catalog_version"),
    )
    expected_versions = (
        pack.pack_id,
        pack.version,
        pack.policy_version,
        pack.question_catalog_version,
    )
    if manifest_versions != expected_versions:
        raise ReviewWorkflowError(
            "manifest versions differ from the loaded domain pack"
        )
    if manifest.get("additional_llm_calls") != 0 or manifest.get("network_calls") != 0:
        raise ReviewWorkflowError("manifest does not describe a zero-call review run")
    if key.get("review_set_id") != review_set_id:
        raise ReviewWorkflowError("blinding key belongs to another review set")
    if manifest.get("corpus_sha256") != _sha256_file(corpus_path):
        raise ReviewWorkflowError("review corpus changed after export")
    if manifest.get("domain_pack_sha256") != _sha256_file(_PACK_PATH):
        raise ReviewWorkflowError("domain pack changed after export")
    if manifest.get("blinding_key_sha256") != _sha256_file(
        review_dir / BLINDING_KEY_FILENAME
    ):
        raise ReviewWorkflowError("blinding key changed after export")
    if manifest.get("automatic_activation_authorized") is not False:
        raise ReviewWorkflowError("manifest must not authorize activation")

    _validate_attestation(attestation, review_set_id=review_set_id)
    rows = _read_worksheet(review_dir / WORKSHEET_FILENAME)
    key_by_case = {entry["case_id"]: entry for entry in key.get("entries", ())}
    if len(key_by_case) != len(key.get("entries", ())):
        raise ReviewWorkflowError("blinding key contains duplicate case IDs")
    if len(rows) != manifest.get("review_units") or len(rows) < 30:
        raise ReviewWorkflowError("worksheet does not contain the exported review set")
    row_ids = [row["case_id"] for row in rows]
    key_ids = [entry["case_id"] for entry in key.get("entries", ())]
    if len(row_ids) != len(set(row_ids)) or row_ids != key_ids:
        raise ReviewWorkflowError(
            "worksheet case IDs or row order differ from the blinding key"
        )

    preference_counts = {"controller": 0, "legacy": 0, "tie": 0}
    source_metrics = {
        "relevant_to_case": {"controller": 0, "legacy": 0},
        "critical_gate_skipped": {"controller": 0, "legacy": 0},
        "asks_documented_information": {"controller": 0, "legacy": 0},
        "answerable_or_handles_unknown": {"controller": 0, "legacy": 0},
    }
    outcomes: list[dict[str, Any]] = []
    for row in rows:
        case_id = row["case_id"]
        if row["review_unit_hash"] != _review_unit_hash(row):
            raise ReviewWorkflowError(
                f"immutable worksheet content changed for {case_id}"
            )
        for column, allowed in _ALLOWED_RATINGS.items():
            if row[column] not in allowed:
                raise ReviewWorkflowError(
                    f"{case_id} has invalid {column}: {row[column]!r}"
                )
        if not row["rationale"].strip():
            raise ReviewWorkflowError(f"{case_id} requires a concise rationale")

        entry = key_by_case[case_id]
        preference = row["preferred_next_action"]
        preferred_source = (
            "tie" if preference == "tie" else _source_for_side(entry, preference)
        )
        preference_counts[preferred_source] += 1
        outcome = {
            "case_id": case_id,
            "preferred_source": preferred_source,
            "controller_need_id": entry["controller_need_id"],
            "legacy_need_id": entry["legacy_need_id"],
            "divergence_type": entry["divergence_type"],
        }
        for metric in source_metrics:
            selected = _sources_for_rating(entry, row[metric])
            for source in selected:
                source_metrics[metric][source] += 1
            outcome[metric] = sorted(selected)
        outcomes.append(outcome)

    total = len(rows)
    controller_at_least_as_good = (
        preference_counts["controller"] + preference_counts["tie"]
    )
    result = {
        "schema_version": "1.0",
        "review_set_id": review_set_id,
        "reviewer": attestation["reviewer"],
        "reviewed_at": attestation["reviewed_at"],
        "human_review_complete": True,
        "review_units": total,
        "preferences": preference_counts,
        "controller_at_least_as_good_count": controller_at_least_as_good,
        "controller_at_least_as_good_rate": round(
            controller_at_least_as_good / total,
            4,
        ),
        "source_metrics": source_metrics,
        "zero_controller_critical_gate_skips": (
            source_metrics["critical_gate_skipped"]["controller"] == 0
        ),
        "zero_any_critical_gate_skips": (
            sum(source_metrics["critical_gate_skipped"].values()) == 0
        ),
        "worksheet_sha256": _sha256_file(review_dir / WORKSHEET_FILENAME),
        "attestation_sha256": _sha256_file(review_dir / ATTESTATION_FILENAME),
        "additional_llm_calls": 0,
        "network_calls": 0,
        "outcomes": outcomes,
        "automatic_activation_authorized": False,
        "cutover_decision_required": True,
        "decision_note": (
            "This artifact recomputes human ratings only. It is not a PASS/FAIL "
            "verdict and cannot authorize a visible cutover."
        ),
    }
    _atomic_write(output_path, _json_bytes(result))
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="cost-free RWDR shadow-controller human review workflow"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export", help="export a blinded review set")
    export.add_argument("--output-dir", type=Path, required=True)
    export.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    adjudicate = subparsers.add_parser(
        "adjudicate",
        help="validate and unblind a completed human worksheet",
    )
    adjudicate.add_argument("--review-dir", type=Path, required=True)
    adjudicate.add_argument("--output", type=Path)
    adjudicate.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "export":
        result = export_review_set(args.output_dir, corpus_path=args.corpus)
        print(
            f"Exported {result['review_units']} blinded review units to "
            f"{args.output_dir} (LLM calls: 0)."
        )
        return
    result = adjudicate_review_set(
        args.review_dir,
        output_path=args.output,
        corpus_path=args.corpus,
    )
    print(
        f"Adjudicated {result['review_units']} human-reviewed units; "
        "automatic activation remains disabled."
    )


if __name__ == "__main__":
    main()
