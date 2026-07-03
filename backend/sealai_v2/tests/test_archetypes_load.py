"""G2 (V2.1 Inc 1) — Archetyp-Store loader + owner-grounding circularity guard.

Mirrors ``test_fachkarten_load.py``: the same two review states (reviewed/draft), the same
"no LLM erdet LLM" guard (a reviewed profile must be owner-grounded (path i) OR carry a primary
source (path ii); a draft profile is flag-only and unconstrained), plus the archetype-specific
schema rules (mandatory ``key``/``provenance``/``interview_fragen``; ``anwendbare_regime`` is
STRUCTURAL and may be empty at Inc 1 — content lands with the norms catalogue). RED before the
``knowledge/archetypes.py`` module exists.
"""

from __future__ import annotations

import json

import pytest

from sealai_v2.knowledge.archetypes import load_archetypes

_MINIMAL = {
    "typische_konstellation": {"wellenlage": "horizontal"},
    "dichtungsrelevante_besonderheiten": ["x"],
    "typische_versagensmodi": [],
    "typische_eignungen": {"werkstoffe": ["FKM"], "bauformen": ["RWDR"]},
    "anwendbare_regime": [],
    "interview_fragen": ["Welches Öl?"],
    "blinde_flecken": ["y"],
}


def _write(tmp_path, profiles):
    p = tmp_path / "arch.json"
    p.write_text(json.dumps({"version": "t", "profiles": profiles}), encoding="utf-8")
    return p


def test_draft_profile_loads(tmp_path):
    prof = {
        "key": "getriebe",
        "review_state": "draft",
        "provenance": ["owner:draft"],
        **_MINIMAL,
    }
    cat = load_archetypes(_write(tmp_path, [prof]))
    p = cat.by_archetype("getriebe")
    assert p is not None and p.review_state == "draft"
    assert p.interview_fragen == ("Welches Öl?",)
    assert p.anwendbare_regime == ()  # structural, empty at Inc 1


def test_reviewed_without_owner_or_source_is_load_error(tmp_path):
    prof = {
        "key": "getriebe",
        "review_state": "reviewed",
        "provenance": ["model_knowledge:UNREVIEWED"],
        **_MINIMAL,
    }
    with pytest.raises(ValueError, match="LLM erdet LLM"):
        load_archetypes(_write(tmp_path, [prof]))


def test_reviewed_owner_grounded_ok(tmp_path):
    prof = {
        "key": "getriebe",
        "review_state": "reviewed",
        "provenance": ["owner:thorsten"],
        **_MINIMAL,
    }
    cat = load_archetypes(_write(tmp_path, [prof]))
    assert cat.by_archetype("getriebe").review_state == "reviewed"


def test_reviewed_with_primary_source_ok(tmp_path):
    prof = {
        "key": "getriebe",
        "review_state": "reviewed",
        "provenance": ["deep-research"],
        "sources": ["DIN 3760"],
        **_MINIMAL,
    }
    cat = load_archetypes(_write(tmp_path, [prof]))
    assert cat.by_archetype("getriebe").review_state == "reviewed"


def test_missing_provenance_is_error(tmp_path):
    prof = {"key": "getriebe", "review_state": "draft", **_MINIMAL}
    with pytest.raises(ValueError, match="provenance"):
        load_archetypes(_write(tmp_path, [prof]))


def test_missing_interview_fragen_is_error(tmp_path):
    bad = dict(_MINIMAL, interview_fragen=[])
    prof = {
        "key": "getriebe",
        "review_state": "draft",
        "provenance": ["owner:draft"],
        **bad,
    }
    with pytest.raises(ValueError, match="interview_fragen"):
        load_archetypes(_write(tmp_path, [prof]))


def test_duplicate_key_is_error(tmp_path):
    prof = {
        "key": "getriebe",
        "review_state": "draft",
        "provenance": ["owner:draft"],
        **_MINIMAL,
    }
    with pytest.raises(ValueError, match="duplicate"):
        load_archetypes(_write(tmp_path, [prof, dict(prof)]))


def test_missing_key_is_error(tmp_path):
    prof = {"review_state": "draft", "provenance": ["owner:draft"], **_MINIMAL}
    with pytest.raises((ValueError, KeyError)):
        load_archetypes(_write(tmp_path, [prof]))


def test_seed_loads_starter_profiles_owner_reviewed():
    """G3 (post-HALT-#3): the real seed ships Getriebe + Rührwerk as OWNER-REVIEWED + grounded
    (content freigegeben 2026-06-19). The circularity guard held (owner-grounded provenance).
    ``anwendbare_regime`` stays structural/empty (Inc 1 — content via the norms catalogue)."""
    cat = load_archetypes()  # default seed file
    assert {"getriebe", "ruehrwerk"} <= cat.keys
    assert len(cat.reviewed()) == 2  # both owner-grounded after HALT #3
    for key in ("getriebe", "ruehrwerk"):
        p = cat.by_archetype(key)
        assert p.review_state == "reviewed", f"{key} owner-reviewed at HALT #3"
        assert p.owner_grounded, f"{key} must carry owner-grounded provenance"
        assert p.interview_fragen, f"{key} must carry interview questions"
        assert p.blinde_flecken, f"{key} must carry blind spots"
        assert p.anwendbare_regime == (), (
            f"{key}: anwendbare_regime structural/empty at Inc 1"
        )
