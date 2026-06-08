"""The thin V2 answer pipeline (build-spec §5 / Prinzipien §3).

M1 wires only understand→answer; ground/verify/cite are inert stubs. Tenant scope (P0) is
mandatory and validated at the entry point. No deterministic gate, no routing — the soft
intent annotates but never alters the answer path.
"""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Flags, LlmClient, ModelConfig, PipelineResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline import stages
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext, require_tenant


@dataclass
class Pipeline:
    generator: L1Generator
    client: LlmClient
    helper_model: ModelConfig
    understand_enabled: bool = True

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
        answer = await stages.verify(answer)  # stub → unchanged
        answer = await stages.cite(answer)  # stub → unchanged

        return PipelineResult(
            question=question,
            tenant_id=scope.tenant_id,
            flags=flags,
            understanding=understanding,
            answer=answer,
            grounded=False,
            verified=False,
            cited=False,
        )


def build_pipeline(
    settings: Settings, client: LlmClient, *, l1_model: str | None = None
) -> Pipeline:
    """Wire the pipeline from settings + an injected client. The template file read happens
    once here (assembler construction), keeping the pure generator I/O-free."""
    assembler = PromptAssembler()
    l1_cfg = ModelConfig(
        model=l1_model or settings.l1_model, temperature=settings.l1_temperature
    )
    helper_cfg = ModelConfig(
        model=settings.helper_model, temperature=settings.helper_temperature
    )
    generator = L1Generator(client, assembler, l1_cfg)
    return Pipeline(
        generator=generator,
        client=client,
        helper_model=helper_cfg,
        understand_enabled=settings.understand_enabled,
    )
