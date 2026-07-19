"""Deterministic, non-production builder for the first RP-001 AI rule pack.

The module turns an explicit, source-bound creator input into immutable
MAT-GOV-03A, MAT-EVID-01A.v2 and MAT-EVID-AI-REVIEW.v1 snapshots.  It does not
discover facts, normalize runtime media, review evidence, activate a ruleset,
or expose any public response surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, NoReturn

from sealai_v2.core.contracts import MaterialConstraintVerdict
from sealai_v2.core.material_evidence_ai_review import (
    AIEvidenceRisk,
    AIClaimContextV1,
    AIClaimPurpose,
    AIMaterialGranularity,
    AIMediumIdentityClaimContextV1,
    AIMediumIdentityContextV1,
    AIReviewEnvironment,
    AIReviewPayloadV1,
    AIReviewSnapshotV1,
    AISingleSourceTreatment,
    AISourceContextV1,
    CreatorAgentRunV1,
)
from sealai_v2.core.material_evidence_review import (
    EvidenceDocumentType,
    EvidenceRightsState,
    ExactLocatorV1,
    IncludedExcerptV1,
    ReviewedSourceMetadataV1,
)
from sealai_v2.core.material_evidence_v2 import (
    AtomicEvidenceClaimV2,
    EvidenceManifestPayloadV2,
    EvidenceManifestSnapshotV2,
    EvidenceSourceV2,
    MaterialRelationClaimScopeV2,
    MaterialRelationTargetV2,
    MediaIdentityClaimScopeV2,
    MediaIdentityTargetV2,
    RuleClaimBindingV2,
    derive_claim_ref_v2,
    derive_source_ref_v2,
)
from sealai_v2.core.material_rulesets import (
    MaterialRuleScopeV1,
    MaterialRuleV1,
    MaterialRulesetPayloadV1,
    MaterialRulesetSnapshotV1,
)
from sealai_v2.core.medium_catalog import (
    MediumIdentityKind,
    derive_media_id,
    derive_medium_identity_assertion_ref,
)
from sealai_v2.material_evidence_ai_review.audit import (
    ClaudeAuditInputV1,
    build_claude_audit_input,
)


PACKAGE_CONTRACT_VERSION = "RP-001-AI-PACK.v1"
EXPECTED_HUMAN_PACKAGE = "RP-001_ELASTOMER_MEDIA_EXCLUSIONS_V1"
EXPECTED_AI_PACKAGE = "RP-001_ELASTOMER_MEDIA_EXCLUSIONS_AI_V1"
EXPECTED_RULE_COUNT = 6
EXPECTED_SOURCE_COUNT = 2
EXPECTED_MEDIA_COUNT = 3

_TOP_LEVEL_FIELDS = frozenset(
    {
        "authorization_ref",
        "candidate_register_file_sha256",
        "created_at",
        "creator",
        "domain_pack_id",
        "environment",
        "media_identities",
        "package_contract_version",
        "package_id",
        "rules",
        "schema_version",
        "source_coverage_sha256",
        "sources",
        "tenant_id",
    }
)
_CREATOR_FIELDS = frozenset(
    {"agent_model", "agent_version", "prompt_version", "run_id"}
)
_SOURCE_FIELDS = frozenset(
    {
        "content_sha256",
        "document_id",
        "document_revision",
        "document_title",
        "document_type",
        "filename",
        "key",
        "locator",
        "publication_edition",
        "publisher",
        "retrieval_url",
        "rights_basis",
        "rights_state",
        "source_excerpt",
    }
)
_MEDIA_FIELDS = frozenset(
    {"canonical_name", "claim_text", "identity_kind", "key", "source_keys"}
)
_RULE_FIELDS = frozenset(
    {
        "application_scope",
        "claim_text",
        "condition",
        "conditions_and_exclusions",
        "material",
        "material_candidate_id",
        "media_key",
        "rule_ref",
        "seal_type_scope",
        "service_candidate_id",
        "source_keys",
        "temperature_scope",
    }
)
_CANDIDATE_REGISTER_FIELDS = frozenset(
    {
        "authority",
        "automatic_matrix_import_allowed",
        "automatic_pairing_allowed",
        "candidate_semantics",
        "material_axis_candidates",
        "package_id",
        "positive_statement_allowed",
        "proposed_rule_pairs",
        "register_schema_version",
        "register_state",
        "service_media_axis_candidates",
        "source_coverage_contract",
        "source_coverage_sha256",
    }
)


class RP001PackError(ValueError):
    """Stable fail-closed error for creator input and source preflight drift."""


def _fail(message: str) -> NoReturn:
    raise RP001PackError(message)


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON property: {key}")
        result[key] = value
    return result


def _load_json(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=lambda value: _fail(f"invalid JSON constant: {value}"),
            parse_float=lambda value: _fail(f"JSON float forbidden: {value}"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RP001PackError(f"{label} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        _fail(f"{label} root must be an object")
    return value


def _exact(value: dict[str, Any], expected: frozenset[str], *, path: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        _fail(
            f"{path} fields drift: unknown={sorted(actual - expected)} "
            f"missing={sorted(expected - actual)}"
        )


def _text(value: Any, *, path: str) -> str:
    if type(value) is not str or not any(not item.isspace() for item in value):
        _fail(f"{path} must be a non-whitespace string")
    return value


def _ordered_texts(value: Any, *, path: str) -> tuple[str, ...]:
    if type(value) is not list or not value:
        _fail(f"{path} must be a non-empty array")
    items = tuple(_text(item, path=f"{path}[]") for item in value)
    if items != tuple(sorted(set(items), key=lambda item: item.encode("utf-8"))):
        _fail(f"{path} must be unique and UTF-8-byte ordered")
    return items


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _family_id(prefix: str, package_id: str, purpose: str) -> str:
    digest = hashlib.sha256(
        b"sealai:rp001-ai-pack:family:v1\x00"
        + package_id.encode("ascii")
        + b"\x00"
        + purpose.encode("ascii")
    ).hexdigest()
    return f"{prefix}_{digest[:32]}"


@dataclass(frozen=True, slots=True)
class RP001PackArtifactsV1:
    package_input: dict[str, Any]
    creator_output_bytes: bytes
    ruleset: MaterialRulesetSnapshotV1
    evidence: EvidenceManifestSnapshotV2
    media_identity_evidence: tuple[EvidenceManifestSnapshotV2, ...]
    review: AIReviewSnapshotV1
    audit_input: ClaudeAuditInputV1
    source_file_sha256: tuple[tuple[str, str], ...]

    def snapshot_index(self) -> dict[str, Any]:
        return {
            "authority": self.review.payload.authority,
            "audit_input_sha256": self.audit_input.audit_input_sha256,
            "batch_id": self.review.batch_id,
            "evidence": {
                "content_sha256": self.evidence.content_sha256,
                "manifest_id": self.evidence.manifest_id,
                "snapshot_id": self.evidence.snapshot_id,
            },
            "media_identity_evidence": [
                {
                    "content_sha256": item.content_sha256,
                    "manifest_id": item.manifest_id,
                    "media_ref": item.payload.target.media_ref,
                    "snapshot_id": item.snapshot_id,
                }
                for item in self.media_identity_evidence
            ],
            "package_contract_version": PACKAGE_CONTRACT_VERSION,
            "package_id": self.package_input["package_id"],
            "positive_statement_allowed": False,
            "review": {
                "content_sha256": self.review.content_sha256,
                "snapshot_id": self.review.review_snapshot_id,
                "state": "ai_draft",
            },
            "ruleset": {
                "content_sha256": self.ruleset.content_sha256,
                "ruleset_id": self.ruleset.ruleset_id,
                "snapshot_id": self.ruleset.snapshot_id,
            },
            "source_file_sha256": dict(self.source_file_sha256),
        }


def _validate_candidate_register(
    *, creator_input: dict[str, Any], register_raw: bytes
) -> tuple[set[str], set[str]]:
    register = _load_json(register_raw, label="candidate register")
    _exact(register, _CANDIDATE_REGISTER_FIELDS, path="candidate register")
    if (
        register["package_id"] != EXPECTED_HUMAN_PACKAGE
        or register["register_schema_version"] != 1
        or register["positive_statement_allowed"] is not False
        or register["automatic_pairing_allowed"] is not False
        or register["automatic_matrix_import_allowed"] is not False
        or register["proposed_rule_pairs"] != []
    ):
        _fail("candidate register authority boundary drift")
    file_sha256 = hashlib.sha256(register_raw).hexdigest()
    if file_sha256 != creator_input["candidate_register_file_sha256"]:
        _fail("candidate register file digest drift")
    if register["source_coverage_sha256"] != creator_input["source_coverage_sha256"]:
        _fail("source coverage snapshot drift")
    material_ids = {
        _text(item.get("subject_id"), path="material candidate subject_id")
        for item in register["material_axis_candidates"]
        if type(item) is dict
        and item.get("coverage_status") == "evidence_gap"
        and item.get("triage_state") == "unassessed"
    }
    service_ids = {
        _text(item.get("subject_id"), path="service candidate subject_id")
        for item in register["service_media_axis_candidates"]
        if type(item) is dict
        and item.get("coverage_status") == "evidence_gap"
        and item.get("triage_state") == "unassessed"
    }
    if len(material_ids) + len(service_ids) != 53:
        _fail("candidate register no longer contains the exact 53 evidence gaps")
    return material_ids, service_ids


def _validate_input(
    creator_input: dict[str, Any], candidate_register_raw: bytes
) -> tuple[set[str], set[str]]:
    _exact(creator_input, _TOP_LEVEL_FIELDS, path="creator input")
    if (
        creator_input["schema_version"] != 1
        or creator_input["package_contract_version"] != PACKAGE_CONTRACT_VERSION
        or creator_input["package_id"] != EXPECTED_AI_PACKAGE
        or creator_input["environment"] != AIReviewEnvironment.TEST.value
    ):
        _fail("unsupported RP-001 creator input identity")
    _text(creator_input["authorization_ref"], path="authorization_ref")
    _text(creator_input["created_at"], path="created_at")
    _text(creator_input["domain_pack_id"], path="domain_pack_id")
    _text(creator_input["tenant_id"], path="tenant_id")
    creator = creator_input["creator"]
    if type(creator) is not dict:
        _fail("creator must be an object")
    _exact(creator, _CREATOR_FIELDS, path="creator")
    for field in _CREATOR_FIELDS:
        _text(creator[field], path=f"creator.{field}")
    sources = creator_input["sources"]
    media = creator_input["media_identities"]
    rules = creator_input["rules"]
    if (
        type(sources) is not list
        or len(sources) != EXPECTED_SOURCE_COUNT
        or type(media) is not list
        or len(media) != EXPECTED_MEDIA_COUNT
        or type(rules) is not list
        or len(rules) != EXPECTED_RULE_COUNT
    ):
        _fail("RP-001 package cardinality drift")
    for index, source in enumerate(sources):
        if type(source) is not dict:
            _fail(f"sources[{index}] must be an object")
        _exact(source, _SOURCE_FIELDS, path=f"sources[{index}]")
    for index, identity in enumerate(media):
        if type(identity) is not dict:
            _fail(f"media_identities[{index}] must be an object")
        _exact(identity, _MEDIA_FIELDS, path=f"media_identities[{index}]")
    for index, rule in enumerate(rules):
        if type(rule) is not dict:
            _fail(f"rules[{index}] must be an object")
        _exact(rule, _RULE_FIELDS, path=f"rules[{index}]")
    return _validate_candidate_register(
        creator_input=creator_input, register_raw=candidate_register_raw
    )


def _source_identity(source: dict[str, Any]) -> EvidenceSourceV2:
    values = {
        "document_id": _text(source["document_id"], path="source.document_id"),
        "document_revision": _text(
            source["document_revision"], path="source.document_revision"
        ),
        "publication_edition": _text(
            source["publication_edition"], path="source.publication_edition"
        ),
        "content_sha256": _text(source["content_sha256"], path="source.content_sha256"),
    }
    return EvidenceSourceV2(source_ref=derive_source_ref_v2(**values), **values)


def _source_context(
    source: dict[str, Any], identity: EvidenceSourceV2
) -> AISourceContextV1:
    return AISourceContextV1(
        metadata=ReviewedSourceMetadataV1(
            source_ref=identity.source_ref,
            document_id=identity.document_id,
            document_title=_text(
                source["document_title"], path="source.document_title"
            ),
            publisher=_text(source["publisher"], path="source.publisher"),
            document_type=EvidenceDocumentType(source["document_type"]),
            document_revision=identity.document_revision,
            publication_edition=identity.publication_edition,
            content_sha256=identity.content_sha256,
            locator=ExactLocatorV1(_text(source["locator"], path="source.locator")),
            rights_state=EvidenceRightsState(source["rights_state"]),
            rights_basis=_text(source["rights_basis"], path="source.rights_basis"),
            excerpt=IncludedExcerptV1(
                text=_text(source["source_excerpt"], path="source.source_excerpt"),
                rights_basis=_text(source["rights_basis"], path="source.rights_basis"),
            ),
        )
    )


def _verify_source_files(
    sources: list[dict[str, Any]], source_directory: Path | None
) -> tuple[tuple[str, str], ...]:
    if source_directory is None:
        return tuple(
            sorted(
                (
                    _text(source["filename"], path="source.filename"),
                    _text(source["content_sha256"], path="source.content_sha256"),
                )
                for source in sources
            )
        )
    results = []
    for source in sources:
        filename = _text(source["filename"], path="source.filename")
        path = source_directory / filename
        if path.is_symlink() or not path.is_file():
            _fail(f"source file is absent or not a regular file: {filename}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["content_sha256"]:
            _fail(f"source file digest drift: {filename}")
        results.append((filename, digest))
    return tuple(sorted(results))


def build_rp001_pack(
    *,
    creator_input_raw: bytes,
    creator_prompt_raw: bytes,
    candidate_register_raw: bytes,
    source_directory: Path | None = None,
) -> RP001PackArtifactsV1:
    creator_input = _load_json(creator_input_raw, label="creator input")
    material_candidates, service_candidates = _validate_input(
        creator_input, candidate_register_raw
    )
    source_file_sha256 = _verify_source_files(
        creator_input["sources"], source_directory
    )

    source_specs = {
        _text(item["key"], path="source.key"): item for item in creator_input["sources"]
    }
    if len(source_specs) != EXPECTED_SOURCE_COUNT:
        _fail("source keys must be unique")
    source_identities = {
        key: _source_identity(value) for key, value in source_specs.items()
    }
    source_contexts = tuple(
        sorted(
            (
                _source_context(source_specs[key], source_identities[key])
                for key in source_specs
            ),
            key=lambda item: item.source_ref,
        )
    )

    media_specs = {
        _text(item["key"], path="medium.key"): item
        for item in creator_input["media_identities"]
    }
    if len(media_specs) != EXPECTED_MEDIA_COUNT:
        _fail("media identity keys must be unique")
    media_values: dict[str, tuple[str, str, MediumIdentityKind, tuple[str, ...]]] = {}
    for key, spec in media_specs.items():
        canonical_name = _text(spec["canonical_name"], path="medium.canonical_name")
        identity_kind = MediumIdentityKind(spec["identity_kind"])
        aliases: tuple[str, ...] = ()
        media_ref = derive_media_id(canonical_name, identity_kind)
        assertion_ref = derive_medium_identity_assertion_ref(
            media_id=media_ref,
            canonical_name=canonical_name,
            identity_kind=identity_kind,
            aliases=aliases,
        )
        media_values[key] = (media_ref, assertion_ref, identity_kind, aliases)

    rule_specs = sorted(creator_input["rules"], key=lambda item: item["rule_ref"])
    seen_rule_refs: set[str] = set()
    material_rules: list[MaterialRuleV1] = []
    rule_parts: list[tuple[dict[str, Any], MaterialRelationClaimScopeV2]] = []
    for rule in rule_specs:
        rule_ref = _text(rule["rule_ref"], path="rule.rule_ref")
        if rule_ref in seen_rule_refs:
            _fail(f"duplicate rule_ref: {rule_ref}")
        seen_rule_refs.add(rule_ref)
        if rule["material_candidate_id"] not in material_candidates:
            _fail(f"rule references a foreign material gap: {rule_ref}")
        if rule["service_candidate_id"] not in service_candidates:
            _fail(f"rule references a foreign service gap: {rule_ref}")
        media_key = _text(rule["media_key"], path="rule.media_key")
        if media_key not in media_values:
            _fail(f"rule references an absent medium: {rule_ref}")
        material = _text(rule["material"], path="rule.material")
        condition = _text(rule["condition"], path="rule.condition")
        claim_text = _text(rule["claim_text"], path="rule.claim_text")
        media_ref = media_values[media_key][0]
        scope = MaterialRuleScopeV1(
            materials=(material,), media=(media_ref,), conditions=(condition,)
        )
        material_rules.append(
            MaterialRuleV1(
                rule_ref=rule_ref,
                material=material,
                medium=media_ref,
                condition=condition,
                verdict=MaterialConstraintVerdict.UNVERTRAEGLICH,
                statement=claim_text,
                scope=scope,
            )
        )
        rule_parts.append(
            (
                rule,
                MaterialRelationClaimScopeV2(
                    materials=(material,),
                    media=(media_ref,),
                    conditions=(condition,),
                ),
            )
        )

    package_id = creator_input["package_id"]
    ruleset = MaterialRulesetSnapshotV1.create(
        _family_id("mrs", package_id, "ruleset"),
        MaterialRulesetPayloadV1(
            domain_pack_id=creator_input["domain_pack_id"],
            rules=tuple(material_rules),
        ),
    )

    evidence_claims: list[AtomicEvidenceClaimV2] = []
    evidence_bindings: list[RuleClaimBindingV2] = []
    ai_claims: list[AIClaimContextV1] = []
    for rule, scope in rule_parts:
        source_keys = _ordered_texts(rule["source_keys"], path="rule.source_keys")
        if set(source_keys) != set(source_specs):
            _fail(f"family-wide rule lacks both primary sources: {rule['rule_ref']}")
        source_refs = tuple(
            sorted(source_identities[key].source_ref for key in source_keys)
        )
        claim_text = rule["claim_text"]
        claim_ref = derive_claim_ref_v2(claim_text=claim_text, scope=scope)
        evidence_claims.append(
            AtomicEvidenceClaimV2(
                claim_ref=claim_ref,
                claim_text=claim_text,
                scope=scope,
                source_refs=source_refs,
            )
        )
        evidence_bindings.append(
            RuleClaimBindingV2(rule_ref=rule["rule_ref"], claim_ref=claim_ref)
        )
        ai_claims.append(
            AIClaimContextV1(
                claim_ref=claim_ref,
                rule_ref=rule["rule_ref"],
                purpose=AIClaimPurpose.RULE_PRIMARY,
                claim_text=claim_text,
                scope=scope,
                source_refs=source_refs,
                primary_source_refs=source_refs,
                seal_type_scope=rule["seal_type_scope"],
                temperature_scope=rule["temperature_scope"],
                application_scope=rule["application_scope"],
                conditions_and_exclusions=rule["conditions_and_exclusions"],
                expected_verdict=MaterialConstraintVerdict.UNVERTRAEGLICH,
                evidence_risk=AIEvidenceRisk.FAMILY_WIDE,
                material_granularity=AIMaterialGranularity.MATERIAL_FAMILY,
                single_source_treatment=AISingleSourceTreatment.STANDARD,
                conflicting_claim_refs=(),
            )
        )

    evidence = EvidenceManifestSnapshotV2.create(
        _family_id("mef", package_id, "material-evidence"),
        EvidenceManifestPayloadV2(
            domain_pack_id=creator_input["domain_pack_id"],
            target=MaterialRelationTargetV2(ruleset.snapshot_id),
            sources=tuple(
                sorted(source_identities.values(), key=lambda item: item.source_ref)
            ),
            claims=tuple(sorted(evidence_claims, key=lambda item: item.claim_ref)),
            rule_claim_bindings=tuple(
                sorted(
                    evidence_bindings, key=lambda item: (item.rule_ref, item.claim_ref)
                )
            ),
        ),
    )

    identity_snapshots: list[EvidenceManifestSnapshotV2] = []
    identity_contexts: list[AIMediumIdentityContextV1] = []
    for media_key in sorted(media_specs):
        spec = media_specs[media_key]
        media_ref, assertion_ref, identity_kind, aliases = media_values[media_key]
        source_keys = _ordered_texts(spec["source_keys"], path="medium.source_keys")
        if set(source_keys) != set(source_specs):
            _fail(f"media identity lacks both sources: {media_key}")
        identities = tuple(
            sorted(
                (source_identities[key] for key in source_keys),
                key=lambda item: item.source_ref,
            )
        )
        identity_scope = MediaIdentityClaimScopeV2(
            media_ref=media_ref, identity_assertion_ref=assertion_ref
        )
        identity_claim_text = _text(spec["claim_text"], path="medium.claim_text")
        identity_claim = AtomicEvidenceClaimV2(
            claim_ref=derive_claim_ref_v2(
                claim_text=identity_claim_text, scope=identity_scope
            ),
            claim_text=identity_claim_text,
            scope=identity_scope,
            source_refs=tuple(item.source_ref for item in identities),
        )
        identity_snapshot = EvidenceManifestSnapshotV2.create(
            _family_id("mef", package_id, f"media-{media_key}"),
            EvidenceManifestPayloadV2(
                domain_pack_id=creator_input["domain_pack_id"],
                target=MediaIdentityTargetV2(media_ref),
                sources=identities,
                claims=(identity_claim,),
                rule_claim_bindings=(),
            ),
        )
        identity_snapshots.append(identity_snapshot)
        identity_contexts.append(
            AIMediumIdentityContextV1(
                media_ref=media_ref,
                canonical_name=spec["canonical_name"],
                identity_kind=identity_kind,
                aliases=aliases,
                identity_assertion_ref=assertion_ref,
                evidence_snapshot_id=identity_snapshot.snapshot_id,
                evidence_content_sha256=identity_snapshot.content_sha256,
                claims=(
                    AIMediumIdentityClaimContextV1(
                        claim_ref=identity_claim.claim_ref,
                        claim_text=identity_claim.claim_text,
                        scope=identity_claim.scope,
                        source_refs=identity_claim.source_refs,
                    ),
                ),
            )
        )

    creator_output = {
        "authority": "AI_CROSS_REVIEW_NON_AUTHORITATIVE",
        "candidate_register_file_sha256": creator_input[
            "candidate_register_file_sha256"
        ],
        "media_identities": [
            {
                "canonical_name": item["canonical_name"],
                "claim_text": item["claim_text"],
                "identity_kind": item["identity_kind"],
                "key": item["key"],
                "source_keys": item["source_keys"],
            }
            for item in creator_input["media_identities"]
        ],
        "package_contract_version": PACKAGE_CONTRACT_VERSION,
        "package_id": package_id,
        "positive_statement_allowed": False,
        "rules": rule_specs,
        "source_digests": {
            key: source_identities[key].content_sha256 for key in sorted(source_specs)
        },
    }
    creator_output_bytes = _canonical_json(creator_output)
    creator_spec = creator_input["creator"]
    creator = CreatorAgentRunV1(
        agent_model=creator_spec["agent_model"],
        agent_version=creator_spec["agent_version"],
        prompt_version=creator_spec["prompt_version"],
        prompt_sha256=hashlib.sha256(creator_prompt_raw).hexdigest(),
        run_id=creator_spec["run_id"],
        input_sha256=hashlib.sha256(creator_input_raw).hexdigest(),
        output_sha256=hashlib.sha256(creator_output_bytes).hexdigest(),
    )
    payload = AIReviewPayloadV1(
        environment=AIReviewEnvironment(creator_input["environment"]),
        tenant_id=creator_input["tenant_id"],
        domain_pack_id=creator_input["domain_pack_id"],
        ruleset_snapshot_id=ruleset.snapshot_id,
        ruleset_content_sha256=ruleset.content_sha256,
        evidence_snapshot_id=evidence.snapshot_id,
        evidence_content_sha256=evidence.content_sha256,
        creator=creator,
        sources=source_contexts,
        media_identities=tuple(
            sorted(identity_contexts, key=lambda item: item.media_ref)
        ),
        claims=tuple(sorted(ai_claims, key=lambda item: item.claim_ref)),
    )
    payload.validate_against(
        ruleset,
        evidence,
        tuple(sorted(identity_snapshots, key=lambda item: item.snapshot_id)),
    )
    if payload.eligibility_failures():
        _fail(f"AI review is ineligible: {payload.eligibility_failures()}")
    review = AIReviewSnapshotV1.create(
        _family_id("mai", package_id, "ai-review"), payload
    )
    audit_input = build_claude_audit_input(review)
    return RP001PackArtifactsV1(
        package_input=creator_input,
        creator_output_bytes=creator_output_bytes,
        ruleset=ruleset,
        evidence=evidence,
        media_identity_evidence=tuple(
            sorted(identity_snapshots, key=lambda item: item.snapshot_id)
        ),
        review=review,
        audit_input=audit_input,
        source_file_sha256=source_file_sha256,
    )


def write_draft_artifacts(artifacts: RP001PackArtifactsV1, output: Path) -> None:
    if output.exists():
        _fail("output directory already exists")
    output.mkdir(mode=0o700, parents=True)
    (output / "creator-output.json").write_bytes(artifacts.creator_output_bytes)
    (output / "ruleset-payload.json").write_bytes(artifacts.ruleset.canonical_bytes)
    (output / "material-evidence-payload.json").write_bytes(
        artifacts.evidence.canonical_bytes
    )
    for item in artifacts.media_identity_evidence:
        (output / f"media-identity-{item.payload.target.media_ref}.json").write_bytes(
            item.canonical_bytes
        )
    (output / "ai-review-payload.json").write_bytes(artifacts.review.canonical_bytes)
    (output / "claude-audit-input.json").write_bytes(
        artifacts.audit_input.canonical_bytes
    )
    (output / "snapshot-index.json").write_bytes(
        _canonical_json(artifacts.snapshot_index())
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--creator-input", type=Path, required=True)
    parser.add_argument("--creator-prompt", type=Path, required=True)
    parser.add_argument("--candidate-register", type=Path, required=True)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    artifacts = build_rp001_pack(
        creator_input_raw=args.creator_input.read_bytes(),
        creator_prompt_raw=args.creator_prompt.read_bytes(),
        candidate_register_raw=args.candidate_register.read_bytes(),
        source_directory=args.source_directory,
    )
    write_draft_artifacts(artifacts, args.output)
    print(json.dumps(artifacts.snapshot_index(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
