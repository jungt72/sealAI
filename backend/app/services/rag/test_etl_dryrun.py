from app.services.rag.rag_etl_pipeline import (
    LLMDocumentExtraction, LLMOperatingPoint, LLMCondition, LLMLimit,
    Operator, PipelineStatus, process_document_pipeline
)


def test_dryrun():
    """Ursprünglicher IV_2016-Dryrun — bleibt unverändert als Referenz."""
    llm_output = LLMDocumentExtraction(
        manufacturer="RBS Dichtungstechnik",
        product_name="IV_2016",
        operating_points=[
            LLMOperatingPoint(
                conditions=[
                    LLMCondition(parameter="medium", raw_value="Wasser", inferred_operator=Operator.EQ, evidence_ref="S. 1")
                ],
                limits=[
                    LLMLimit(limit_type="pressure_max_bar", raw_value="5 - 10 bar", evidence_ref="S. 2"),
                    LLMLimit(limit_type="temperature_max_c", raw_value="120,5", evidence_ref="S. 2")
                ]
            )
        ],
        safety_exclusions=["Nicht für nukleare Anwendungen."]
    )

    print("=== STARTING DRYRUN FOR IV_2016.pdf ===")
    result = process_document_pipeline(llm_output, "logical_iv_2016_key")

    print(f"\nPipeline Status: {result.status}")
    print("\nQuarantine Report:")
    for msg in result.quarantine_report:
        print(f"- {msg}")

    print("\nExtracted Qdrant Points:")
    for idx, p in enumerate(result.extracted_points):
        print(f"\n--- Point {idx} ---")
        print(f"Vector Text:\n{p['vector_text']}")
        print(f"Limits: {p['limits']}")


def test_bp30_safety_exclusion_does_not_block_validated():
    """
    Fix 3: Ein Dokument mit safety_exclusions darf NICHT QUARANTINED werden,
    solange die Operating Points valide sind.
    """
    llm_output = LLMDocumentExtraction(
        manufacturer="Trelleborg",
        product_name="BP30",
        operating_points=[
            LLMOperatingPoint(
                conditions=[
                    LLMCondition(parameter="medium", raw_value="Hydrauliköl HLP46", inferred_operator=Operator.EQ, evidence_ref="S. 1"),
                ],
                limits=[
                    LLMLimit(limit_type="pressure_max_bar", raw_value="350", evidence_ref="S. 2"),
                    LLMLimit(limit_type="temperature_max_c", raw_value="120", evidence_ref="S. 2"),
                    LLMLimit(limit_type="temperature_min_c", raw_value="-30", evidence_ref="S. 2"),
                ],
            )
        ],
        safety_exclusions=["Nicht für aggressive Säuren geeignet.", "Kein Einsatz bei Dampf > 150 °C."],
    )
    result = process_document_pipeline(llm_output, "logical_bp30_key")

    # Fix 3: VALIDATED, obwohl safety_exclusions vorhanden
    assert result.status == PipelineStatus.VALIDATED, (
        f"Erwartet VALIDATED, erhalten: {result.status}. Report: {result.quarantine_report}"
    )
    assert result.extracted_points, "BP30 muss mindestens einen validen Qdrant-Point liefern."

    # Safety-Warnings müssen im quarantine_report als Info erscheinen
    safety_msgs = [m for m in result.quarantine_report if "SAFETY_EXCLUSION_DETECTED" in m]
    assert safety_msgs, "Safety-Exclusion-Warnung muss im Report enthalten sein (informativ)."

    print("=== BP30: Fix 3 OK — SAFETY_EXCLUSION blockiert nicht mehr VALIDATED ===")


def test_bp30_material_family_in_vector_text():
    """
    Fix 1: material_family + polymer_name aus additional_metadata müssen im vector_text erscheinen.
    """
    llm_output = LLMDocumentExtraction(
        manufacturer="Trelleborg",
        product_name="BP30",
        operating_points=[
            LLMOperatingPoint(
                conditions=[
                    LLMCondition(parameter="medium", raw_value="Hydrauliköl", inferred_operator=Operator.EQ, evidence_ref="S. 1"),
                ],
                limits=[
                    LLMLimit(limit_type="pressure_max_bar", raw_value="250", evidence_ref="S. 2"),
                    LLMLimit(limit_type="temperature_max_c", raw_value="100", evidence_ref="S. 2"),
                ],
            )
        ],
        safety_exclusions=[],
    )
    additional_metadata = {
        "material_family": "FKM",
        "polymer_name": "Fluorocarbon",
    }
    result = process_document_pipeline(llm_output, "logical_bp30_key", additional_metadata)

    assert result.status == PipelineStatus.VALIDATED
    assert result.extracted_points

    vector_text = result.extracted_points[0]["vector_text"]
    # Fix 1: Beide Felder müssen im vector_text stehen
    assert "FKM" in vector_text, f"material_family 'FKM' fehlt im vector_text:\n{vector_text}"
    assert "Fluorocarbon" in vector_text, f"polymer_name 'Fluorocarbon' fehlt im vector_text:\n{vector_text}"

    print(f"=== BP30: Fix 1 OK — vector_text enthält material_family + polymer_name ===")
    print(f"Vector Text:\n{vector_text}")


def test_bp30_additional_metadata_absent_no_crash():
    """
    Fix 1 Robustheit: Kein additional_metadata → kein Crash, Felder fehlen einfach.
    """
    llm_output = LLMDocumentExtraction(
        manufacturer="Trelleborg",
        product_name="BP30",
        operating_points=[
            LLMOperatingPoint(
                conditions=[
                    LLMCondition(parameter="speed_max_m_s", raw_value="0.5", inferred_operator=Operator.LTE, evidence_ref="S. 3"),
                ],
                limits=[
                    LLMLimit(limit_type="pressure_max_bar", raw_value="400", evidence_ref="S. 3"),
                    LLMLimit(limit_type="temperature_max_c", raw_value="150", evidence_ref="S. 3"),
                ],
            )
        ],
        safety_exclusions=[],
    )
    result = process_document_pipeline(llm_output, "logical_bp30_key")

    assert result.status == PipelineStatus.VALIDATED
    vector_text = result.extracted_points[0]["vector_text"]
    assert "Material:" not in vector_text
    assert "Polymer:" not in vector_text
    print("=== BP30: Fix 1 Robustheit OK — kein additional_metadata → kein Crash ===")


if __name__ == "__main__":
    test_dryrun()
    print()
    test_bp30_safety_exclusion_does_not_block_validated()
    print()
    test_bp30_material_family_in_vector_text()
    print()
    test_bp30_additional_metadata_absent_no_crash()
    print("\n=== Alle BP30-Tests bestanden ===")

