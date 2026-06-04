from app.services.multimodal_input_service import InputType, MultimodalInputService


def test_article_number_decoder_extracts_dimension_triple_as_proposals() -> None:
    extraction = MultimodalInputService().process_article_number("NOK BAUSL 28x45x7")
    assert extraction.input_type is InputType.ARTICLE_NUMBER
    assert extraction.extracted_parameters["shaft.diameter_mm"] == 28.0
    assert extraction.user_verification_required is True
