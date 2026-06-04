from __future__ import annotations

from app.services.rag.contracts import RAGInput, RAGOutput, RenderedPrompt


def test_rag_contracts_are_instantiable() -> None:
    rag_input = RAGInput(
        query="PTFE fuer Dampf",
        parameters={"medium": "Dampf", "temperature_c": 180},
        language="de",
    )
    rag_output = RAGOutput(
        chunks=[{"id": "chunk-1", "text": "PTFE ist temperaturbestaendig."}],
        sources=["datasheet:ptfe"],
        confidence=0.82,
    )
    rendered_prompt = RenderedPrompt(
        template_name="engineering_report.j2",
        version="1.0.0",
        rendered_text="Beispiel",
        hash_sha256="a" * 64,
    )

    assert rag_input.query == "PTFE fuer Dampf"
    assert rag_input.parameters["medium"] == "Dampf"
    assert rag_output.sources == ["datasheet:ptfe"]
    assert rag_output.confidence == 0.82
    assert rendered_prompt.template_name == "engineering_report.j2"
    assert len(rendered_prompt.hash_sha256) == 64
