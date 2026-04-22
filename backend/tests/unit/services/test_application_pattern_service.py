from app.services.application_pattern_service import ApplicationPatternLibrary


def test_seed_library_contains_required_14_patterns() -> None:
    assert len(ApplicationPatternLibrary().list_patterns()) >= 14


def test_pattern_matching_is_explicit_and_returns_candidates() -> None:
    candidates = ApplicationPatternLibrary().match("Wir haben Schokolade und CIP Reinigung")
    assert candidates
    assert candidates[0].pattern.canonical_name == "food_processing_chocolate_melter"
    selection = ApplicationPatternLibrary().select(candidates[0].pattern.canonical_name)
    assert selection.user_confirmation_required is True
