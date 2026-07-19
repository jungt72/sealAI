"""One-shot isolated execution of the deterministic RP-001 AI review pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from sealai_v2.core.material_evidence_ai_review import (
    AIReviewEnvironment,
    AdjudicatorAgentRunV1,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence_ai_review import (
    MaterialEvidenceAIReviewRepositoryV1,
    NonProductionAIReviewContextV1,
)
from sealai_v2.db.material_evidence_v2 import MaterialEvidenceRepositoryV2
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _upgrade_engine, migration_status
from sealai_v2.material_evidence_ai_review.audit import (
    AIFindingCategory,
    ClaudeClaimVerdict,
    FindingAdjudicationV1,
    FindingDisposition,
    create_adjudication,
)
from sealai_v2.material_evidence_ai_review.rp001_pack import (
    RP001PackArtifactsV1,
    build_rp001_pack,
)
from sealai_v2.material_evidence_ai_review.runner import run_claude_challenge


ADJUDICATOR_PROMPT_VERSION = "rp001-ai-adjudicator.v1"
CREATED_BY = "ai-agent:codex-rp001-creator-20260718-01"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require_isolated_database(database_url: str) -> None:
    parsed = make_url(database_url)
    if parsed.drivername.startswith("sqlite"):
        if not parsed.database or parsed.database == ":memory:":
            raise ValueError("RP-001 execution requires a durable isolated database")
        return
    if not parsed.drivername.startswith("postgresql"):
        raise ValueError("RP-001 execution accepts only SQLite or PostgreSQL")
    if parsed.host not in {"127.0.0.1", "localhost", "host.docker.internal"}:
        raise ValueError("RP-001 PostgreSQL host must be local")
    if not (parsed.database or "").startswith("sealai_rp001_ai_pack_"):
        raise ValueError("RP-001 PostgreSQL database name must use the isolated prefix")


def _persist_draft(
    artifacts: RP001PackArtifactsV1, *, database_url: str
) -> tuple[MaterialEvidenceAIReviewRepositoryV1, NonProductionAIReviewContextV1]:
    _require_isolated_database(database_url)
    engine = make_engine(database_url)
    if inspect(engine).get_table_names():
        raise ValueError("RP-001 execution database must be empty")
    _upgrade_engine(engine, "20260718_0019")
    if migration_status(engine) != ("20260718_0019", "20260718_0019"):
        raise RuntimeError("RP-001 migration fingerprint drift")
    factory = make_sessionmaker(engine)
    created_at = artifacts.package_input["created_at"]

    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=artifacts.ruleset.ruleset_id,
        domain_pack_id=artifacts.ruleset.payload.domain_pack_id,
        created_by_subject=CREATED_BY,
        created_at=created_at,
    )
    if (
        rulesets.store_snapshot(
            ruleset_id=artifacts.ruleset.ruleset_id,
            raw_payload=artifacts.ruleset.canonical_bytes,
            created_by_subject=CREATED_BY,
            created_at=created_at,
        )
        != artifacts.ruleset
    ):
        raise RuntimeError("persisted ruleset snapshot drift")

    evidence = MaterialEvidenceRepositoryV2(factory)
    for snapshot in (artifacts.evidence, *artifacts.media_identity_evidence):
        evidence.create_manifest(
            manifest_id=snapshot.manifest_id,
            target=snapshot.payload.target,
            domain_pack_id=snapshot.payload.domain_pack_id,
            created_by_subject=CREATED_BY,
            created_at=created_at,
        )
        if (
            evidence.store_snapshot(
                manifest_id=snapshot.manifest_id,
                raw_payload=snapshot.canonical_bytes,
                created_by_subject=CREATED_BY,
                created_at=created_at,
            )
            != snapshot
        ):
            raise RuntimeError("persisted Evidence snapshot drift")

    context = NonProductionAIReviewContextV1(
        tenant_id=artifacts.package_input["tenant_id"],
        environment=AIReviewEnvironment.TEST,
        authorization_ref=artifacts.package_input["authorization_ref"],
    )
    reviews = MaterialEvidenceAIReviewRepositoryV1(factory)
    reviews.create_batch(
        payload=artifacts.review.payload,
        context=context,
        created_at=created_at,
        batch_id=artifacts.review.batch_id,
    )
    if (
        reviews.store_snapshot(
            batch_id=artifacts.review.batch_id,
            raw_payload=artifacts.review.canonical_bytes,
            context=context,
            created_at=created_at,
        )
        != artifacts.review
    ):
        raise RuntimeError("persisted AI review snapshot drift")
    return reviews, context


def _adjudicate_findings(challenge) -> tuple[FindingAdjudicationV1, ...]:
    adjudications = []
    for result in challenge.report.claim_results:
        for finding in result.findings:
            disposition = FindingDisposition.QUARANTINED
            if (
                challenge.report.overall_verdict is ClaudeClaimVerdict.PASS
                and finding.category is AIFindingCategory.NON_FACTUAL_DOCUMENTATION
            ):
                disposition = FindingDisposition.ACCEPTED_NONBLOCKING
            adjudications.append(
                FindingAdjudicationV1(
                    finding_ref=finding.finding_ref,
                    disposition=disposition,
                )
            )
    return tuple(sorted(adjudications, key=lambda item: item.finding_ref))


def execute_rp001_pack(
    *,
    creator_input_raw: bytes,
    creator_prompt_raw: bytes,
    adjudicator_prompt_raw: bytes,
    candidate_register_raw: bytes,
    source_directory: Path,
    database_url: str,
    output_directory: Path,
) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[4]
    output = output_directory.expanduser().resolve()
    if output == repository or repository in output.parents:
        raise ValueError("RP-001 execution output must be outside the repository")
    if output.exists():
        raise ValueError("RP-001 execution output already exists")
    output.mkdir(mode=0o700, parents=True)

    artifacts = build_rp001_pack(
        creator_input_raw=creator_input_raw,
        creator_prompt_raw=creator_prompt_raw,
        candidate_register_raw=candidate_register_raw,
        source_directory=source_directory,
    )
    reviews, context = _persist_draft(artifacts, database_url=database_url)
    receipt = run_claude_challenge(
        artifacts.review,
        ruleset=artifacts.ruleset,
        evidence=artifacts.evidence,
        media_identity_evidence=artifacts.media_identity_evidence,
        output_directory=output / "claude-run",
        max_turns=20,
        max_budget_usd="10.00",
    )
    challenged = reviews.record_challenge(
        receipt=receipt,
        context=context,
        created_at=artifacts.package_input["created_at"],
    )
    if challenged.state.value != "ai_challenged":
        raise RuntimeError("challenge lifecycle drift")

    challenge = receipt.challenge
    finding_adjudications = _adjudicate_findings(challenge)
    adjudicator_input = _canonical_json(
        {
            "challenge_id": challenge.challenge_id,
            "finding_refs": [item.finding_ref for item in finding_adjudications],
            "report_sha256": challenge.report_sha256,
            "review_snapshot_id": artifacts.review.review_snapshot_id,
        }
    )
    adjudicator_output = _canonical_json(
        {
            "dispositions": [item.to_dict() for item in finding_adjudications],
            "factual_change_performed": False,
            "policy": (
                "clean PASS or non-factual LOW only; every other finding quarantined"
            ),
        }
    )
    adjudicator = AdjudicatorAgentRunV1(
        agent_model="gpt-5.6-sol",
        agent_version="codex-desktop-2026-07-18",
        prompt_version=ADJUDICATOR_PROMPT_VERSION,
        prompt_sha256=hashlib.sha256(adjudicator_prompt_raw).hexdigest(),
        run_id=(
            "codex-rp001-adjudicator-sha256:"
            + hashlib.sha256(adjudicator_input).hexdigest()
        ),
        input_sha256=hashlib.sha256(adjudicator_input).hexdigest(),
        output_sha256=hashlib.sha256(adjudicator_output).hexdigest(),
    )
    adjudication = create_adjudication(
        snapshot=artifacts.review,
        challenge=challenge,
        adjudicator=adjudicator,
        finding_adjudications=finding_adjudications,
    )
    projection = reviews.record_adjudication(
        adjudication=adjudication,
        context=context,
        created_at=artifacts.package_input["created_at"],
    )
    if (
        reviews.load_projection(artifacts.review.review_snapshot_id, context=context)
        != projection
    ):
        raise RuntimeError("persisted lifecycle replay drift")

    final_receipt = {
        **artifacts.snapshot_index(),
        "activation_authority": False,
        "adjudication": adjudication.to_dict(),
        "challenge": challenge.to_dict(),
        "final_state": projection.state.value,
        "human_review_or_approval": False,
        "production_migration": False,
        "public_projection": False,
        "runner_receipt_sha256": receipt.runner_receipt_sha256,
        "sampling": 0,
    }
    (output / "adjudicator-input.json").write_bytes(adjudicator_input)
    (output / "adjudicator-output.json").write_bytes(adjudicator_output)
    (output / "challenge.json").write_bytes(_canonical_json(challenge.to_dict()))
    (output / "adjudication.json").write_bytes(_canonical_json(adjudication.to_dict()))
    (output / "final-receipt.json").write_bytes(_canonical_json(final_receipt))
    return final_receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--creator-input", type=Path, required=True)
    parser.add_argument("--creator-prompt", type=Path, required=True)
    parser.add_argument("--adjudicator-prompt", type=Path, required=True)
    parser.add_argument("--candidate-register", type=Path, required=True)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--database-url-env", default="SEALAI_V2_RP001_DATABASE_URL")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    database_url = os.environ.get(args.database_url_env, "").strip()
    if not database_url:
        raise ValueError("isolated database URL environment variable is absent")
    receipt = execute_rp001_pack(
        creator_input_raw=args.creator_input.read_bytes(),
        creator_prompt_raw=args.creator_prompt.read_bytes(),
        adjudicator_prompt_raw=args.adjudicator_prompt.read_bytes(),
        candidate_register_raw=args.candidate_register.read_bytes(),
        source_directory=args.source_directory,
        database_url=database_url,
        output_directory=args.output,
    )
    print(
        json.dumps(
            {
                "final_state": receipt["final_state"],
                "review_snapshot_id": receipt["review"]["snapshot_id"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
