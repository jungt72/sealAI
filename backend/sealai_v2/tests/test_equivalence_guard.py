from __future__ import annotations

from sealai_v2.core.equivalence_guard import (
    detect_equivalence_claim,
    equivalence_hedge_text,
)


def test_flags_affirmative_interchangeability():
    for s in [
        "Die sind 1:1 austauschbar.",
        "Das ist baugleich, kannst du nehmen.",
        "Du kannst die problemlos tauschen.",
        "Der Ring ist direkt ersetzbar.",
        "Ohne weiteres austauschbar.",
        "Das ist exakt dasselbe Teil.",
        "Die Teile sind 100% identisch.",
        "Der ist eins zu eins austauschbar.",
    ]:
        assert detect_equivalence_claim(s), f"should flag: {s!r}"


def test_does_not_flag_the_negated_doctrine_correct_form():
    for s in [
        "Nein, die sind nicht 1:1 austauschbar.",
        "Das ist nicht baugleich.",
        "Die kannst du nicht problemlos tauschen.",
        "Kein direkter Ersatz ohne Freigabe.",
        "Formal gleich heißt nicht automatisch 1:1 austauschbar.",
        # the real gpt-5.1 DEC-AEQUIVALENZ answer pattern (must NOT false-trigger):
        'Nein, "formal gleich" heißt nicht automatisch "1:1 austauschbar". Ob er funktional '
        "gleichwertig ist, haengt vom Compound ab; die finale Freigabe liegt beim Hersteller.",
    ]:
        assert detect_equivalence_claim(s) == (), f"should NOT flag: {s!r}"


def test_hedge_text_is_owner_grounded_and_does_not_self_trigger():
    h = equivalence_hedge_text()
    assert "Freigabe liegt beim Hersteller" in h
    assert (
        detect_equivalence_claim(h) == ()
    )  # the hedge must not re-trigger the detector
