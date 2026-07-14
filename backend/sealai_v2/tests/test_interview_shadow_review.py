from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from sealai_v2.eval.interview_shadow_review import (
    ADJUDICATION_FILENAME,
    ATTESTATION_FILENAME,
    BLINDING_KEY_FILENAME,
    INSTRUCTIONS_FILENAME,
    MANIFEST_FILENAME,
    WORKSHEET_FILENAME,
    ReviewWorkflowError,
    adjudicate_review_set,
    export_review_set,
)
from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _complete_attestation(review_dir: Path) -> None:
    path = review_dir / ATTESTATION_FILENAME
    attestation = _read_json(path)
    attestation.update(
        {
            "reviewer": "Domain Owner",
            "reviewed_at": "2026-07-14T10:30:00+02:00",
            "reviewed_blinded": True,
            "attestation": attestation["required_attestation_text"],
        }
    )
    path.write_text(
        json.dumps(attestation, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _complete_worksheet(review_dir: Path, *, prefer: str = "controller") -> None:
    fieldnames, rows = _read_rows(review_dir / WORKSHEET_FILENAME)
    key = _read_json(review_dir / BLINDING_KEY_FILENAME)
    by_case = {item["case_id"]: item for item in key["entries"]}
    for row in rows:
        mapping = by_case[row["case_id"]]
        if prefer == "controller":
            row["preferred_next_action"] = (
                "A" if mapping["question_a_source"] == "controller" else "B"
            )
        else:
            row["preferred_next_action"] = "tie"
        row["relevant_to_case"] = "both"
        row["critical_gate_skipped"] = "none"
        row["asks_documented_information"] = "none"
        row["answerable_or_handles_unknown"] = "both"
        row["rationale"] = (
            "Beide Fragen sind anhand des dokumentierten Falls bewertbar."
        )
    _write_rows(review_dir / WORKSHEET_FILENAME, fieldnames, rows)


def test_export_produces_30_real_balanced_blinded_divergences(tmp_path: Path) -> None:
    manifest = export_review_set(tmp_path)
    fieldnames, rows = _read_rows(tmp_path / WORKSHEET_FILENAME)
    key = _read_json(tmp_path / BLINDING_KEY_FILENAME)
    attestation = _read_json(tmp_path / ATTESTATION_FILENAME)

    assert manifest["review_units"] == 30
    assert len(rows) == 30
    assert len({row["case_id"] for row in rows}) == 30
    assert manifest["controller_a_count"] == 15
    assert manifest["controller_b_count"] == 15
    assert manifest["additional_llm_calls"] == 0
    assert manifest["network_calls"] == 0
    assert manifest["automatic_activation_authorized"] is False
    assert manifest["reviewable_divergence_types"] == ["different_need"]
    assert all(item["divergence_type"] == "different_need" for item in key["entries"])
    assert all(
        not row[column]
        for row in rows
        for column in (
            "preferred_next_action",
            "relevant_to_case",
            "critical_gate_skipped",
            "asks_documented_information",
            "answerable_or_handles_unknown",
            "rationale",
        )
    )
    assert "question_a_source" not in fieldnames
    assert "controller_need_id" not in fieldnames
    assert "scenario_group" not in fieldnames
    assert all("Szenario:" not in row["case_context_de"] for row in rows)
    assert all("Nicht dokumentiert:" not in row["case_context_de"] for row in rows)
    assert attestation["reviewer"] == ""
    assert attestation["reviewed_blinded"] is None
    instructions = (tmp_path / INSTRUCTIONS_FILENAME).read_text(encoding="utf-8")
    assert "Boolean values such as `true` and `false` are invalid" in instructions


def test_application_goal_question_and_schema_cover_review_taxonomy() -> None:
    pack = load_rwdr_v1_pack()
    question = pack.question("rwdr.q.application_goal")

    assert pack.version == "1.0.1"
    assert pack.question_catalog_version == "rwdr.questions.1.0.1"
    assert question is not None
    assert "Retrofit" in question.canonical_text_de
    assert "Optimierung" in question.canonical_text_de
    assert set(question.answer_schema["enum"]) == {
        "new_design",
        "replacement",
        "retrofit",
        "optimization",
        "failure_analysis",
    }


def test_export_rejects_overwriting_review_evidence(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    with pytest.raises(ReviewWorkflowError, match="protected artifacts"):
        export_review_set(tmp_path)


def test_adjudication_recomputes_human_ratings_without_authorizing_cutover(
    tmp_path: Path,
) -> None:
    export_review_set(tmp_path)
    _complete_worksheet(tmp_path, prefer="controller")
    _complete_attestation(tmp_path)

    result = adjudicate_review_set(tmp_path)

    assert result["human_review_complete"] is True
    assert result["preferences"] == {"controller": 30, "legacy": 0, "tie": 0}
    assert result["controller_at_least_as_good_rate"] == 1.0
    assert result["zero_controller_critical_gate_skips"] is True
    assert result["zero_any_critical_gate_skips"] is True
    assert result["additional_llm_calls"] == 0
    assert result["network_calls"] == 0
    assert result["automatic_activation_authorized"] is False
    assert result["cutover_decision_required"] is True
    assert (tmp_path / ADJUDICATION_FILENAME).exists()


def test_adjudication_rejects_immutable_worksheet_tampering(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    _complete_worksheet(tmp_path)
    _complete_attestation(tmp_path)
    fieldnames, rows = _read_rows(tmp_path / WORKSHEET_FILENAME)
    rows[0]["case_context_de"] += " Nachtraeglich veraendert."
    _write_rows(tmp_path / WORKSHEET_FILENAME, fieldnames, rows)

    with pytest.raises(ReviewWorkflowError, match="immutable worksheet content"):
        adjudicate_review_set(tmp_path)


def test_adjudication_rejects_missing_human_verdict(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    _complete_worksheet(tmp_path)
    _complete_attestation(tmp_path)
    fieldnames, rows = _read_rows(tmp_path / WORKSHEET_FILENAME)
    rows[7]["preferred_next_action"] = ""
    _write_rows(tmp_path / WORKSHEET_FILENAME, fieldnames, rows)

    with pytest.raises(ReviewWorkflowError, match="invalid preferred_next_action"):
        adjudicate_review_set(tmp_path)


def test_adjudication_rejects_boolean_side_ratings(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    _complete_worksheet(tmp_path)
    _complete_attestation(tmp_path)
    fieldnames, rows = _read_rows(tmp_path / WORKSHEET_FILENAME)
    rows[0]["relevant_to_case"] = "true"
    _write_rows(tmp_path / WORKSHEET_FILENAME, fieldnames, rows)

    with pytest.raises(ReviewWorkflowError, match="invalid relevant_to_case"):
        adjudicate_review_set(tmp_path)


def test_adjudication_rejects_changed_row_order(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    _complete_worksheet(tmp_path)
    _complete_attestation(tmp_path)
    fieldnames, rows = _read_rows(tmp_path / WORKSHEET_FILENAME)
    rows[0], rows[1] = rows[1], rows[0]
    _write_rows(tmp_path / WORKSHEET_FILENAME, fieldnames, rows)

    with pytest.raises(ReviewWorkflowError, match="row order"):
        adjudicate_review_set(tmp_path)


def test_adjudication_requires_blinded_human_attestation(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    _complete_worksheet(tmp_path)

    with pytest.raises(ReviewWorkflowError, match="reviewer is required"):
        adjudicate_review_set(tmp_path)


def test_adjudication_rejects_changed_blinding_key(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    _complete_worksheet(tmp_path)
    _complete_attestation(tmp_path)
    key_path = tmp_path / BLINDING_KEY_FILENAME
    key = _read_json(key_path)
    current = key["entries"][0]["question_a_source"]
    key["entries"][0]["question_a_source"] = (
        "controller" if current == "legacy" else "legacy"
    )
    key_path.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ReviewWorkflowError, match="blinding key changed"):
        adjudicate_review_set(tmp_path)


def test_export_manifest_files_are_all_present(tmp_path: Path) -> None:
    export_review_set(tmp_path)
    assert {path.name for path in tmp_path.iterdir()} == {
        WORKSHEET_FILENAME,
        BLINDING_KEY_FILENAME,
        ATTESTATION_FILENAME,
        MANIFEST_FILENAME,
        INSTRUCTIONS_FILENAME,
    }
