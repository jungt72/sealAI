"""render — jinja2-Artefakt-Rendering: briefing/rfq, calc-report (build-spec §3/§4, M4b).

Terminal deterministic projection of a finished turn — never touches L1/L3. Public API:
``ArtifactRenderer`` (the ``Renderer`` Protocol impl), ``snapshot_from_result`` (PipelineResult →
RenderSnapshot adapter), ``CLAIM_BOUNDARY`` (owner-grounded scoped doctrine frame)."""

from sealai_v2.render.renderer import (
    CLAIM_BOUNDARY,
    ArtifactRenderer,
    snapshot_from_result,
)

__all__ = ["ArtifactRenderer", "CLAIM_BOUNDARY", "snapshot_from_result"]
