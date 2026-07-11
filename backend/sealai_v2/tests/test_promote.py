"""Fachkarte promotion — merge_new_card's validate-before-write safety (2026-07-04 RAG audit fix
for the manual "hand-edit the seed JSON" friction)."""

from __future__ import annotations

import json

import pytest

from sealai_v2.knowledge.promote import PromotionError, merge_new_card

_EXISTING_CARD = {
    "id": "FK-EXISTING",
    "scope": {"material": ["FKM"]},
    "claims": [
        {
            "text": "Bestehende geprüfte Aussage.",
            "review_state": "reviewed",
            "sources": ["Testquelle Bestand"],
            "provenance": ["owner:bestand"],
            "reviewed_by": "test-domain-reviewer",
            "reviewed_at": "2026-07-11T00:00:00Z",
            "review_expires_at": "2099-07-11T00:00:00Z",
        }
    ],
    "review_state": "reviewed",
    "provenance": ["owner:bestand"],
}


def _seed(tmp_path, cards=(_EXISTING_CARD,)):
    p = tmp_path / "fk.json"
    p.write_text(json.dumps({"version": "t0", "cards": list(cards)}), encoding="utf-8")
    return p


def _new_reviewed_card(
    card_id="FK-NEW", provenance=("owner:neu",), sources=("Testquelle Neu",)
):
    return {
        "id": card_id,
        "scope": {"material": ["PTFE"]},
        "claims": [
            {
                "text": "Neue geprüfte Aussage.",
                "review_state": "reviewed",
                "sources": list(sources),
                "provenance": list(provenance),
                "reviewed_by": "test-domain-reviewer",
                "reviewed_at": "2026-07-11T00:00:00Z",
                "review_expires_at": "2099-07-11T00:00:00Z",
            }
        ],
        "review_state": "reviewed",
        "provenance": list(provenance),
    }


def test_merge_new_card_appends_a_valid_reviewed_card(tmp_path):
    seed_path = _seed(tmp_path)
    catalog = merge_new_card(_new_reviewed_card(), seed_path=seed_path)
    assert {c.id for c in catalog.cards} == {"FK-EXISTING", "FK-NEW"}
    assert catalog.by_id("FK-NEW").reviewed_claims()[0].sources == ("Testquelle Neu",)
    # re-read from disk independently — proves the write actually landed, not just an in-memory view
    on_disk = json.loads(seed_path.read_text(encoding="utf-8"))
    assert {c["id"] for c in on_disk["cards"]} == {"FK-EXISTING", "FK-NEW"}


def test_merge_new_card_accepts_a_draft_only_card_with_no_provenance_grounding(
    tmp_path,
):
    seed_path = _seed(tmp_path)
    draft = {
        "id": "FK-DRAFT-X",
        "scope": {"material": ["EPDM"]},
        "claims": [{"text": "Unbestätigte Vermutung.", "review_state": "draft"}],
        "review_state": "draft",
        "provenance": ["claude-research:draft"],
    }
    catalog = merge_new_card(draft, seed_path=seed_path)
    assert catalog.by_id("FK-DRAFT-X") is not None


def test_merge_new_card_rejects_id_collision_and_never_touches_the_file(tmp_path):
    seed_path = _seed(tmp_path)
    before = seed_path.read_text(encoding="utf-8")
    with pytest.raises(PromotionError, match="already exists"):
        merge_new_card(_new_reviewed_card(card_id="FK-EXISTING"), seed_path=seed_path)
    assert (
        seed_path.read_text(encoding="utf-8") == before
    )  # untouched — validated before any write
    assert not list(
        tmp_path.glob("*.bak-*")
    )  # no backup either — nothing was ever written


def test_merge_new_card_rejects_a_circularity_guard_violation(tmp_path):
    seed_path = _seed(tmp_path)
    before = seed_path.read_text(encoding="utf-8")
    ungrounded = _new_reviewed_card(provenance=(), sources=())
    with pytest.raises(PromotionError, match="no LLM erdet LLM|failed validation"):
        merge_new_card(ungrounded, seed_path=seed_path)
    assert seed_path.read_text(encoding="utf-8") == before


def test_merge_new_card_writes_a_timestamped_backup_by_default(tmp_path):
    seed_path = _seed(tmp_path)
    merge_new_card(_new_reviewed_card(), seed_path=seed_path)
    backups = list(tmp_path.glob("*.bak-pre-promote-*"))
    assert len(backups) == 1
    # the backup holds the PRE-promotion content (one card), not the merged result
    backed_up = json.loads(backups[0].read_text(encoding="utf-8"))
    assert [c["id"] for c in backed_up["cards"]] == ["FK-EXISTING"]


def test_merge_new_card_no_backup_flag_skips_the_backup_file(tmp_path):
    seed_path = _seed(tmp_path)
    merge_new_card(_new_reviewed_card(), seed_path=seed_path, backup=False)
    assert not list(tmp_path.glob("*.bak-*"))
