from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agent.services import medium_research
from app.agent.services.medium_research import MediumResearchService


@pytest.mark.asyncio
async def test_medium_research_builds_source_marked_saltwater_deep_dive(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_retrieve_with_tenant(*_args, **_kwargs):
        return [], {"tier": "tier3_empty", "k_returned": 0}

    monkeypatch.setattr(medium_research, "_retrieve_web_evidence", _disabled_web)
    monkeypatch.setattr("app.agent.services.real_rag.retrieve_with_tenant", fake_retrieve_with_tenant)

    result = await MediumResearchService().build("Salzwasser", tenant_id="tenant-1", user_id="user-1")
    dumped = result.model_dump_json().lower()

    assert result.not_for_release_decisions is True
    assert any(section.id == "saltwater_deep_dive" for section in result.sections)
    assert "chlorid" in dumped
    assert "korrosion" in dumped
    assert "feder" in dumped or "welle" in dumped
    assert "kristallisation" in dumped
    assert any(item.source_type == "deterministic" for item in result.evidence)
    assert result.answer_markdown
    assert result.answer_markdown_source == "deterministic_sections"
    assert result.research_status.rag.attempted is True
    assert result.research_status.web.attempted is False


@pytest.mark.asyncio
async def test_medium_research_injects_rag_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_retrieve_with_tenant(*_args, **_kwargs):
        return [
            {
                "topic": "Hydraulikoel HLP 46",
                "source_ref": "/private/path/hydraulic-oil.pdf",
                "content": "HLP 46 ist ein Hydraulikoel. Additive, Temperatur und Dichtungswerkstoff muessen geprueft werden.",
            }
        ], {"tier": "tier2_bm25", "k_returned": 1}

    monkeypatch.setattr(medium_research, "_retrieve_web_evidence", _disabled_web)
    monkeypatch.setattr("app.agent.services.real_rag.retrieve_with_tenant", fake_retrieve_with_tenant)

    result = await MediumResearchService().build("Hydraulikoel", tenant_id="tenant-1", user_id="user-1")

    assert result.research_status.rag.status == "ok"
    assert result.research_status.rag.hit_count == 1
    assert result.evidence[-1].source_type == "rag"
    assert result.evidence[-1].source_name == "hydraulic-oil.pdf"
    assert "/private/path" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_medium_research_uses_default_tenant_for_rag_when_auth_tenant_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    async def fake_retrieve_with_tenant(_query, tenant_id, **_kwargs):
        seen["tenant_id"] = tenant_id
        return [], {"tier": "tier3_empty", "k_returned": 0}

    monkeypatch.delenv("SEALAI_DEFAULT_TENANT_ID", raising=False)
    monkeypatch.setattr(medium_research, "_retrieve_web_evidence", _disabled_web)
    monkeypatch.setattr("app.agent.services.real_rag.retrieve_with_tenant", fake_retrieve_with_tenant)

    result = await MediumResearchService().build("Salzwasser", tenant_id=None, user_id="user-1")

    assert seen["tenant_id"] == "default"
    assert result.research_status.rag.attempted is True
    assert result.research_status.rag.status == "no_hits"


@pytest.mark.asyncio
async def test_medium_research_does_not_fake_web_sources_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_retrieve_with_tenant(*_args, **_kwargs):
        return [], {"tier": "tier3_empty", "k_returned": 0}

    monkeypatch.delenv("SEALAI_ENABLE_MEDIUM_WEB_RESEARCH", raising=False)
    monkeypatch.setattr("app.agent.services.real_rag.retrieve_with_tenant", fake_retrieve_with_tenant)

    result = await MediumResearchService().build("PFAS-haltiges Medium", tenant_id="tenant-1", user_id="user-1")

    assert result.research_status.web.attempted is False
    assert result.research_status.web.status == "disabled"
    assert not any(item.source_type == "web" for item in result.evidence)
    assert any("keine Live-Webaussagen" in limitation for limitation in result.limitations)


@pytest.mark.asyncio
async def test_medium_answer_composer_disabled_does_not_call_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(_role: str):
        raise AssertionError("composer provider must not be called when feature flag is disabled")

    monkeypatch.delenv("SEALAI_ENABLE_MEDIUM_ANSWER_COMPOSER", raising=False)
    monkeypatch.setattr(medium_research, "get_async_llm", fail_if_called)
    monkeypatch.setattr(medium_research, "_retrieve_rag_evidence", _empty_rag)
    monkeypatch.setattr(medium_research, "_retrieve_web_evidence", _disabled_web)

    result = await MediumResearchService().build("Salzwasser", tenant_id="tenant-1", user_id="user-1")

    assert result.answer_markdown_source == "deterministic_sections"
    assert result.composer.enabled is False
    assert result.composer.attempted is False
    assert result.answer_markdown


@pytest.mark.asyncio
async def test_medium_research_can_accept_mocked_web_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponses:
        async def create(self, **_kwargs):
            return SimpleNamespace(output_text="Webhinweis: Herstellerdaten und Sicherheitsdatenblatt muessen geprueft werden.")

    fake_client = SimpleNamespace(responses=FakeResponses())
    monkeypatch.setenv("SEALAI_ENABLE_MEDIUM_WEB_RESEARCH", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(medium_research, "get_async_llm", lambda _role: (fake_client, "test-model"))
    monkeypatch.setattr(medium_research, "_retrieve_rag_evidence", _empty_rag)

    evidence, attempt = await medium_research._retrieve_web_evidence("Salzwasser")

    assert attempt.status == "ok"
    assert evidence[0].source_type == "web"
    assert "Webhinweis" in evidence[0].excerpt


@pytest.mark.asyncio
async def test_medium_answer_composer_can_produce_visible_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCompletions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "answer_markdown": "### Salzwasser\n\nChloride, Welle und Feder sind zentrale Pruefpunkte. Das bleibt Orientierung, keine Freigabe.",
                                    "confidence_note": None,
                                }
                            )
                        )
                    )
                ]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setenv("SEALAI_ENABLE_MEDIUM_ANSWER_COMPOSER", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(medium_research, "get_async_llm", lambda _role: (fake_client, "test-model"))
    monkeypatch.setattr(medium_research, "_retrieve_rag_evidence", _empty_rag)
    monkeypatch.setattr(medium_research, "_retrieve_web_evidence", _disabled_web)

    result = await MediumResearchService().build("Salzwasser", tenant_id="tenant-1", user_id="user-1")

    assert result.answer_markdown_source == "medium_composer"
    assert result.composer.enabled is True
    assert result.composer.attempted is True
    assert result.composer.succeeded is True
    assert "Chloride" in (result.answer_markdown or "")
    assert "Freigabe" in (result.answer_markdown or "")


@pytest.mark.asyncio
async def test_medium_answer_composer_falls_back_on_unsafe_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCompletions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "answer_markdown": "Das Material ist geeignet.",
                                    "confidence_note": None,
                                }
                            )
                        )
                    )
                ]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setenv("SEALAI_ENABLE_MEDIUM_ANSWER_COMPOSER", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(medium_research, "get_async_llm", lambda _role: (fake_client, "test-model"))
    monkeypatch.setattr(medium_research, "_retrieve_rag_evidence", _empty_rag)
    monkeypatch.setattr(medium_research, "_retrieve_web_evidence", _disabled_web)

    result = await MediumResearchService().build("Salzwasser", tenant_id="tenant-1", user_id="user-1")

    assert result.answer_markdown_source == "composer_fallback"
    assert result.composer.succeeded is False
    assert result.composer.fallback_reason
    assert "Das Material ist geeignet" not in (result.answer_markdown or "")


@pytest.mark.asyncio
async def test_medium_research_sanitizes_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_retrieve_with_tenant(*_args, **_kwargs):
        return [
            {
                "topic": "Secret test",
                "source_ref": "/tmp/source.pdf",
                "content": "token sk-secretvalue should never leak as a raw secret",
            }
        ], {"tier": "tier2_bm25", "k_returned": 1}

    monkeypatch.setattr(medium_research, "_retrieve_web_evidence", _disabled_web)
    monkeypatch.setattr("app.agent.services.real_rag.retrieve_with_tenant", fake_retrieve_with_tenant)

    result = await MediumResearchService().build("Wasser", tenant_id="tenant-1", user_id="user-1")
    dumped = result.model_dump_json()

    assert "sk-secretvalue" not in dumped
    assert "/tmp/source.pdf" not in dumped


async def _disabled_web(_medium: str):
    return [], medium_research.MediumResearchAttempt(
        attempted=False,
        status="disabled",
        note="disabled in test",
    )


async def _empty_rag(*_args, **_kwargs):
    return [], medium_research.MediumResearchAttempt(
        attempted=True,
        status="no_hits",
        note="no hits",
    )
