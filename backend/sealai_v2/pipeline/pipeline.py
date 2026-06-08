"""The thin V2 answer pipeline (build-spec §5 / Prinzipien §3).

M1 wires only understand→answer; ground/verify/cite are inert stubs. Tenant scope (P0) is
mandatory and validated at the entry point. No deterministic gate, no routing — the soft
intent annotates but never alters the answer path.
"""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import (
    Flags,
    LlmClient,
    ModelConfig,
    PipelineResult,
    VerifierVerdict,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier
from sealai_v2.knowledge.traps import TrapCatalog, load_traps
from sealai_v2.pipeline import stages
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.security.tenant import TenantContext, require_tenant


@dataclass
class Pipeline:
    generator: L1Generator
    client: LlmClient
    helper_model: ModelConfig
    understand_enabled: bool = True
    verifier: L3Verifier | None = None  # None → L3 disabled (incident kill-switch only)
    catalog: TrapCatalog | None = None

    async def run(
        self,
        question: str,
        *,
        tenant: TenantContext,
        flags: Flags | None = None,
    ) -> PipelineResult:
        scope = require_tenant(tenant)  # P0 — fail-closed if tenant missing/empty
        flags = flags or Flags()

        understanding = None
        if self.understand_enabled:
            understanding = await stages.understand(
                self.client, self.helper_model, question
            )

        grounding_facts = await stages.ground(question)  # stub → ()
        answer = await self.generator.generate(
            question, flags=flags, grounding_facts=grounding_facts
        )

        verdict: VerifierVerdict | None = None
        if self.verifier is not None and self.catalog is not None:
            answer, verdict = await stages.verify(
                self.verifier,
                self.generator,
                self.catalog,
                question,
                answer,
                flags=flags,
            )

        answer = await stages.cite(answer)  # stub → unchanged

        return PipelineResult(
            question=question,
            tenant_id=scope.tenant_id,
            flags=flags,
            understanding=understanding,
            answer=answer,
            grounded=False,
            verified=verdict is not None,
            cited=False,
            verifier=verdict,
        )


def build_pipeline(
    settings: Settings, client: LlmClient, *, l1_model: str | None = None
) -> Pipeline:
    """Wire the pipeline from settings + an injected client. The template file reads happen once
    here (assembler construction), keeping the pure generator/verifier I/O-free. L3 is ALWAYS-ON
    (core trust layer, not flag-gated) unless ``verify_enabled`` is turned off (incident only)."""
    assembler = PromptAssembler()
    l1_cfg = ModelConfig(
        model=l1_model or settings.l1_model, temperature=settings.l1_temperature
    )
    helper_cfg = ModelConfig(
        model=settings.helper_model, temperature=settings.helper_temperature
    )
    generator = L1Generator(client, assembler, l1_cfg)

    verifier: L3Verifier | None = None
    catalog: TrapCatalog | None = None
    if settings.verify_enabled:
        catalog = load_traps()
        verifier_cfg = ModelConfig(
            model=settings.verifier_model, temperature=settings.verifier_temperature
        )
        verifier = L3Verifier(client, VerifierPromptAssembler(), verifier_cfg, catalog)

    return Pipeline(
        generator=generator,
        client=client,
        helper_model=helper_cfg,
        understand_enabled=settings.understand_enabled,
        verifier=verifier,
        catalog=catalog,
    )
