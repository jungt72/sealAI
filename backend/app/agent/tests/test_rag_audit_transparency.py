from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.api.utils import _knowledge_response_run_meta
from app.domain.pre_gate_classification import PreGateClassification


@dataclass(frozen=True)
class DummyCitation:
    source_id: str = "src-1"
    title: str = "RWDR Guide"
    source_type: Any = None
    validation_status: Any = None
    rank: int = 1
    excerpt: str = "RWDR evidence excerpt"
    confidence: float = 0.91

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_type": "rag_verified",
            "validation_status": "documented",
            "rank": self.rank,
            "excerpt": self.excerpt,
            "confidence": self.confidence,
        }


class DummyAnswerView:
    def as_dict(self) -> dict[str, Any]:
        return {
            "rag_lookup_attempted": True,
            "rag_answer_found": True,
            "rag_miss": False,
            "fallback_allowed": False,
            "fallback_used": False,
            "sources": [DummyCitation().as_dict()],
            "knowledge_evidence": [
                {
                    "source_type": "rag",
                    "title": "RWDR Guide",
                    "source_name": "sealai_knowledge_v3",
                    "content": "A radial shaft seal depends on shaft speed, medium, pressure and temperature.",
                    "confidence": 0.91,
                }
            ],
            "user_visible_label": "Kuratiertes/RAG-Wissen - dokumentiert",
        }


class DummyKnowledgeResponse:
    source_classification = PreGateClassification.KNOWLEDGE_QUERY
    output_class = "conversational_answer"
    no_case_created = True
    citations = (DummyCitation(),)
    knowledge_answer_view = DummyAnswerView()
    knowledge_debug = {"route": "knowledge_general"}
    answer_trace = {"reply_source": "knowledge_service"}


def test_knowledge_response_run_meta_contains_rag_audit_and_trace_flags() -> None:
    meta = _knowledge_response_run_meta(DummyKnowledgeResponse())

    audit = meta["rag_audit"]
    assert audit["contract_version"] == "sealai_rag_audit_v1"
    assert audit["lookup_attempted"] is True
    assert audit["answer_found"] is True
    assert audit["source_count"] == 1
    assert audit["evidence_count"] == 1
    assert audit["grounding_strategy"] == "rag_grounded"
    assert audit["miss_policy"] == "source_grounded"
    assert audit["sources"][0]["title"] == "RWDR Guide"

    trace = meta["answer_trace"]
    assert trace["rag_required"] is True
    assert trace["rag_lookup_attempted"] is True
    assert trace["rag_answer_found"] is True
    assert trace["rag_source_count"] == 1
    assert trace["rag_evidence_count"] == 1
    assert trace["rag_grounding_strategy"] == "rag_grounded"


class DummyDeterministicAnswerView:
    def as_dict(self) -> dict[str, Any]:
        return {
            "answer_available": True,
            "rag_lookup_attempted": True,
            "rag_answer_found": False,
            "rag_miss": True,
            "fallback_allowed": False,
            "fallback_used": False,
            "source_type": "system_derived",
            "validation_status": "unvalidated",
            "knowledge_evidence": [
                {
                    "source_type": "deterministic",
                    "title": "SeaLAI-Grundwissen",
                    "content": "Deterministische technische Orientierung ohne Freigabe.",
                }
            ],
            "missing_reason": "domain_glossary_answer_without_rag_hit",
            "user_visible_label": "SeaLAI-Grundwissen - allgemeine Orientierung",
        }


class DummyDeterministicKnowledgeResponse(DummyKnowledgeResponse):
    citations = ()
    knowledge_answer_view = DummyDeterministicAnswerView()


def test_knowledge_response_run_meta_marks_deterministic_orientation_separately() -> None:
    meta = _knowledge_response_run_meta(DummyDeterministicKnowledgeResponse())

    audit = meta["rag_audit"]
    assert audit["answer_found"] is False
    assert audit["rag_miss"] is True
    assert audit["source_count"] == 0
    assert audit["grounding_strategy"] == "deterministic_orientation_without_rag_hit"
    assert audit["miss_policy"] == "deterministic_orientation_limited_no_release"

    trace = meta["answer_trace"]
    assert trace["rag_miss"] is True
    assert trace["rag_grounding_strategy"] == "deterministic_orientation_without_rag_hit"
