from app._legacy_v2.utils.output_sanitizer import strip_meta_preamble


def test_frontdoor_smalltalk_reply_is_not_a_greeting() -> None:
    # Avoid importing nodes_frontdoor directly to prevent import-time circularities.
    import pathlib
    path = pathlib.Path(__file__).parent.parent / "nodes" / "nodes_frontdoor.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Hallo! Schön, von dir zu hören" not in content


def test_strip_meta_preamble_removes_greetings_and_meta_starters() -> None:
    samples = [
        "Hallo! Schön, von dir zu hören. Test.",
        "Gern. Test.",
        "Verstanden, Test.",
        "Natürlich: Test.",
        "Guten Tag! Test.",
        "Hallo! Gern. Verstanden. Test.",
    ]
    banned_prefixes = ("hallo", "gern", "verstanden", "übernommen", "natürlich", "guten ")

    for sample in samples:
        stripped = strip_meta_preamble(sample)
        assert stripped, sample
        assert not stripped.strip().lower().startswith(banned_prefixes), stripped
