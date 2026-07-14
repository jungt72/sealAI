"""CLI for the M1 eval-REPLAY:  python -m sealai_v2.eval [--smoke N] [--label L] [--columns ...]

Runs the seed cases through the pipeline in-process (no HTTP) and writes
``eval/runs/<label>/{results.json,report.md,human_review_worksheet.md}``. Needs OPENAI_API_KEY
in the environment for the live run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sealai_v2.config.settings import Settings
from sealai_v2.eval.harness import COLUMNS, run_eval
from sealai_v2.pipeline.timing import configure_timing_logging

_RUNS_DIR = Path(__file__).resolve().parent / "runs"

_ROLES = ("l1", "verifier", "helper", "judge")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RC_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "evidence_type",
        "evidence_sha256",
        "payload_sha256",
        "candidate_image_config_digest",
        "candidate_image_digest",
        "candidate_image_digest_source",
        "served_tree_sha256",
        "database_migration_sha256",
        "authority_epoch",
        "runtime_profile_sha256",
        "retriever_backend",
        "retriever_fallback_allowed",
        "postgres_database",
        "postgres_snapshot_sha256",
        "qdrant_collection",
        "qdrant_authentication",
        "qdrant_snapshot_sha256",
        "source_git_sha",
    }
)
_RC_ENV_BINDINGS = {
    "evidence_sha256": "SEALAI_EVAL_RC_DESCRIPTOR_SHA256",
    "candidate_image_digest": "SEALAI_EVAL_IMAGE_DIGEST",
    "candidate_image_config_digest": "SEALAI_EVAL_IMAGE_CONFIG_DIGEST",
    "served_tree_sha256": "SEALAI_EVAL_SERVED_TREE_SHA256",
    "database_migration_sha256": "SEALAI_EVAL_DATABASE_MIGRATION_SHA256",
    "postgres_snapshot_sha256": "SEALAI_RC_POSTGRES_SNAPSHOT_SHA256",
    "qdrant_snapshot_sha256": "SEALAI_RC_QDRANT_SNAPSHOT_SHA256",
    "source_git_sha": "SEALAI_EVAL_GIT_SHA",
}


def _parse_role_overrides(model_args, provider_args) -> dict:
    """Turn repeated ``--model role=value`` / ``--provider role=value`` into Settings kwargs
    (``{role}_model`` / ``{role}_provider``). Unknown role → SystemExit (fail-closed, no silent
    drop). These kwargs take highest precedence over env when constructing ``Settings``."""
    overrides: dict[str, str] = {}
    for kind, items in (("model", model_args or []), ("provider", provider_args or [])):
        for item in items:
            if "=" not in item:
                raise SystemExit(f"--{kind} expects role=value, got {item!r}")
            role, value = item.split("=", 1)
            role = role.strip().lower()
            if role not in _ROLES:
                raise SystemExit(
                    f"--{kind}: unknown role {role!r}; choose from {list(_ROLES)}"
                )
            overrides[f"{role}_{kind}"] = value.strip()
    return overrides


def _git_sha() -> str:
    if value := os.getenv("SEALAI_EVAL_GIT_SHA"):
        return value.strip()
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[3]),
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _tree_binding() -> tuple[str, bool]:
    """The eval↔deploy binding: the served-runtime CONTENT hash + a dirty flag.

    ``tree_hash`` comes ONLY from ``ops/tree-hash.sh`` (the single source of truth the V2 deploy
    gate also calls — byte-identical by construction). ``dirty`` = the served scope (same eval/+tests/
    exclusion as the hash) has uncommitted changes at eval time — the signal that ``git_sha`` alone
    cannot give (under validate-then-commit, HEAD is the pre-fix commit but the eval'd content is the
    fix). Best-effort: ``("unknown", False)`` if git or the script is unavailable.
    """
    if tree_hash := os.getenv("SEALAI_EVAL_TREE_HASH"):
        dirty = os.getenv("SEALAI_EVAL_DIRTY", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return tree_hash.strip(), dirty

    repo = Path(__file__).resolve().parents[3]
    try:
        tree_hash = subprocess.check_output(
            ["/bin/bash", "-p", str(repo / "ops" / "tree-hash.sh")],
            cwd=str(repo),
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        tree_hash = "unknown"
    try:
        # dirty = uncommitted changes in the FULL image-input set (same scope as ops/tree-hash.sh)
        porcelain = subprocess.check_output(
            [
                "git",
                "status",
                "--porcelain",
                "--",
                "backend/sealai_v2",
                ":(exclude)backend/sealai_v2/eval",
                ":(exclude)backend/sealai_v2/tests",
                "backend/requirements-v2.txt",
                "backend/.dockerignore",
                "backend/Dockerfile.v2",
                "backend/docker-entrypoint-v2.sh",
            ],
            cwd=str(repo),
            text=True,
        )
        dirty = bool(porcelain.strip())
    except Exception:  # noqa: BLE001
        dirty = False
    return tree_hash, dirty


def _no_duplicate_json_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _read_rc_binding(path: Path) -> dict:
    """Read the small canonical descriptor emitted by ``v2_rc_evidence.py verify``.

    Full evidence validation and Gate-10 hash approval remain in the ops-side
    gate.  The eval process independently checks this descriptor against its
    actual Settings and runner-supplied immutable inputs before recording it.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SystemExit("RC evidence binding is unavailable") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 16384:
            raise SystemExit("RC evidence binding must be a bounded regular file")
        chunks = []
        remaining = 16385
        while remaining:
            chunk = os.read(fd, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != metadata.st_size or len(raw) > 16384:
            raise SystemExit("RC evidence binding size changed while reading")
    except OSError as exc:
        raise SystemExit("RC evidence binding cannot be read") from exc
    finally:
        os.close(fd)
    try:
        binding = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicate_json_keys
        )
        canonical = (
            json.dumps(
                binding,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SystemExit("RC evidence binding is not canonical JSON") from exc
    if raw != canonical or not isinstance(binding, dict):
        raise SystemExit("RC evidence binding is not in canonical byte form")
    if set(binding) != _RC_BINDING_KEYS:
        raise SystemExit("RC evidence binding schema is invalid")
    if (
        type(binding.get("schema_version")) is not int
        or binding.get("schema_version") != 1
        or binding.get("evidence_type") != "sealai_v2_production_rc"
    ):
        raise SystemExit("RC evidence binding type is invalid")
    if (
        binding.get("candidate_image_digest_source")
        != "gate10_backend_registry_manifest"
    ):
        raise SystemExit("RC evidence candidate digest is not sourced from Gate 10")
    for key in (
        "evidence_sha256",
        "payload_sha256",
        "served_tree_sha256",
        "database_migration_sha256",
        "runtime_profile_sha256",
        "postgres_snapshot_sha256",
        "qdrant_snapshot_sha256",
    ):
        if (
            not isinstance(binding.get(key), str)
            or _SHA256.fullmatch(binding[key]) is None
        ):
            raise SystemExit(f"RC evidence binding {key} is invalid")
    for key in (
        "candidate_image_digest",
        "candidate_image_config_digest",
        "authority_epoch",
    ):
        if (
            not isinstance(binding.get(key), str)
            or _DIGEST.fullmatch(binding[key]) is None
        ):
            raise SystemExit(f"RC evidence binding {key} is invalid")
    if (
        binding.get("retriever_backend") != "qdrant"
        or binding.get("retriever_fallback_allowed") is not False
    ):
        raise SystemExit(
            "RC evidence binding does not prove fail-closed Qdrant retrieval"
        )
    if binding.get("qdrant_authentication") != "api_key":
        raise SystemExit("RC evidence binding does not require Qdrant authentication")
    for key in ("postgres_database", "qdrant_collection"):
        if not isinstance(binding.get(key), str) or not binding[key]:
            raise SystemExit(f"RC evidence binding {key} is invalid")
    if (
        not isinstance(binding.get("source_git_sha"), str)
        or re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", binding["source_git_sha"])
        is None
    ):
        raise SystemExit("RC evidence binding source_git_sha is invalid")
    return binding


def _release_candidate_binding(
    path: str | None,
    settings: Settings,
    *,
    git_sha: str,
    dirty: bool,
) -> dict | None:
    """Bind eligible eval evidence to the exact runtime that is executing it."""
    if path is None:
        return None
    if os.getenv("SEALAI_EVAL_EVIDENCE_CLASS") != "PRODUCTION_RC_ELIGIBLE":
        raise SystemExit(
            "RC evidence binding is forbidden outside the production-eligible lane"
        )
    binding = _read_rc_binding(Path(path))

    for field, env_name in _RC_ENV_BINDINGS.items():
        if os.getenv(env_name) != binding[field]:
            raise SystemExit(f"RC evidence binding does not match {env_name}")
    if git_sha != binding["source_git_sha"] or dirty is not False:
        raise SystemExit(
            "production-eligible RC evaluation requires the clean approved source"
        )

    from sealai_v2.config.runtime_profile import runtime_profile_hash

    if runtime_profile_hash(settings) != binding["runtime_profile_sha256"]:
        raise SystemExit(
            "RC evidence binding does not match the executing runtime profile"
        )
    if (
        settings.retriever_backend != "qdrant"
        or settings.ground_enabled is not True
        or settings.qdrant_collection != binding["qdrant_collection"]
        or settings.qdrant_url != "http://rc-qdrant:6333"
        or not isinstance(settings.qdrant_api_key, str)
        or not 24 <= len(settings.qdrant_api_key) <= 256
        or any(not 0x21 <= ord(char) <= 0x7E for char in settings.qdrant_api_key)
    ):
        raise SystemExit(
            "RC evidence binding does not match the executing Qdrant retriever"
        )
    if settings.knowledge_authority_epoch != binding["authority_epoch"]:
        raise SystemExit(
            "RC evidence binding does not match the executing Authority Epoch"
        )
    if not settings.database_url:
        raise SystemExit("RC evidence binding requires an isolated Postgres database")
    database_url = urlsplit(settings.database_url)
    if (
        database_url.scheme != "postgresql+psycopg2"
        or database_url.hostname != "rc-postgres"
        or database_url.port != 5432
        or unquote(database_url.username or "") != "sealai_rc_eval"
        or not database_url.password
        or database_url.query
        or database_url.fragment
    ):
        raise SystemExit(
            "RC evidence binding requires the fixed isolated Postgres endpoint"
        )
    database_name = unquote(database_url.path.lstrip("/"))
    if not database_name or "/" in database_name:
        raise SystemExit("RC Postgres database identity is ambiguous")
    if database_name != binding["postgres_database"]:
        raise SystemExit(
            "RC evidence binding does not match the executing Postgres database"
        )
    return binding


def main() -> None:
    ap = argparse.ArgumentParser(description="sealai_v2 M1 eval-REPLAY (L1-alone)")
    ap.add_argument("--label", default="m1-baseline", help="run label / output subdir")
    ap.add_argument(
        "--smoke", type=int, default=None, help="run only the first N cases (dry-run)"
    )
    ap.add_argument(
        "--columns",
        default="flags_off,flags_on",
        help="comma list of flag columns to run (subset of: flags_off, flags_on)",
    )
    ap.add_argument(
        "--case-ids",
        default=None,
        help=(
            "comma-separated case ids across primary and auxiliary suites; only these cases "
            "are executed (targeted remediation mode)"
        ),
    )
    ap.add_argument(
        "--run-dir", default=None, help="output dir (default eval/runs/<label>)"
    )
    ap.add_argument(
        "--adjudicate",
        action="store_true",
        help="recompute final numbers from human_review_worksheet.md (no LLM call) and "
        "re-render report.md; does not run the eval",
    )
    ap.add_argument(
        "--rejudge-failed",
        action="store_true",
        help=(
            "retry only failed/missing judge cells from results.json; reuses stored subject "
            "answers and never calls L1/helper/verifier"
        ),
    )
    ap.add_argument(
        "--model",
        action="append",
        metavar="ROLE=MODEL",
        help="per-role model override (role: l1|verifier|helper|judge), repeatable; "
        "e.g. --model l1=mistral-small-4",
    )
    ap.add_argument(
        "--provider",
        action="append",
        metavar="ROLE=PROVIDER",
        help="per-role provider override (role: l1|verifier|helper|judge), repeatable; "
        "e.g. --provider l1=mistral",
    )
    ap.add_argument(
        "--rc-evidence-binding-file",
        default=os.getenv("SEALAI_EVAL_RC_BINDING_FILE"),
        help=(
            "canonical descriptor emitted by ops/v2_rc_evidence.py verify; when present, "
            "the eval fails closed unless it matches the exact candidate/runtime/snapshots"
        ),
    )
    args = ap.parse_args()
    configure_timing_logging()  # per-turn timing lines → stdout during the live REPLAY

    run_dir = Path(args.run_dir) if args.run_dir else (_RUNS_DIR / args.label)

    if args.adjudicate:
        from sealai_v2.eval.adjudicate import adjudicate_run

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        adj = adjudicate_run(run_dir, run_label=args.label, timestamp=timestamp)
        print(f"\n=== M1 adjudication (recompute): {args.label} ===")
        print(f"label: {adj['label']}  ·  verdicts parsed: {adj['n_verdicts_parsed']}")
        for col, fs in adj["columns"].items():
            q = fs["schranken_quota_final"]
            print(
                f"[{col}] final credibility(2-7)={fs['overall_credibility']:.3f}  "
                f"Schranken-quota(final)={'n/a' if q is None else f'{q:.3f}'}  "
                f"adjudicated {fs['n_units_adjudicated']}/{fs['n_units_human_relevant']}  "
                f"pending {fs['n_units_pending']}"
            )
        mq = adj.get("memory_schranken_quota")
        if mq is not None:
            print(
                f"[memory] memory_fabrication-Schranken(agent-final, not adjudicated)={mq:.3f}"
            )
        print(f"\nArtifacts: {run_dir}")
        return

    overrides = _parse_role_overrides(args.model, args.provider)
    settings = Settings(**overrides)
    case_ids = (
        frozenset(item.strip() for item in args.case_ids.split(",") if item.strip())
        if args.case_ids
        else None
    )
    if args.rejudge_failed:
        from sealai_v2.eval.rejudge import rejudge_failed

        out = asyncio.run(rejudge_failed(run_dir, settings, case_ids=case_ids))
        print(f"\n=== targeted judge retry: {out['run_label']} ===")
        print(f"rejudged: {', '.join(out['rejudged_cells'])}")
        print(f"remaining errors: {out['remaining_errors'] or 'none'}")
        print(f"Artifacts: {run_dir}")
        return
    columns = {k: COLUMNS[k] for k in args.columns.split(",") if k in COLUMNS}
    if not columns:
        raise SystemExit(
            f"no valid columns in {args.columns!r}; choose from {list(COLUMNS)}"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tree_hash, dirty = _tree_binding()
    git_sha = _git_sha()
    release_candidate_evidence = _release_candidate_binding(
        args.rc_evidence_binding_file,
        settings,
        git_sha=git_sha,
        dirty=dirty,
    )
    out = asyncio.run(
        run_eval(
            settings,
            run_dir=run_dir,
            run_label=args.label,
            git_sha=git_sha,
            tree_hash=tree_hash,
            dirty=dirty,
            timestamp=timestamp,
            columns=columns,
            smoke_limit=args.smoke,
            include_auxiliary=args.smoke is None,
            case_ids=case_ids,
            release_candidate_evidence=release_candidate_evidence,
        )
    )
    print(f"\n=== M1 eval-REPLAY: {args.label} ===")
    print(
        f"L1 model: {out['manifest']['l1_model_resolved']}  ·  cases: {out['manifest']['n_cases']}"
    )
    for col, s in out["summaries"].items():
        quota = s["schranken_quota_provisional"]
        print(
            f"[{col}] credibility(2-7)={s['overall_credibility']:.3f}  "
            f"Schranken-quota(prov)={'n/a' if quota is None else f'{quota:.3f}'}  "
            f"status={s['provisional_status_counts']}"
        )
    mt = out.get("multiturn")
    if mt:
        ms = mt["summary"]
        drop = ms.get("drop")
        rate = (
            (drop["dropped"] / drop["proposed"] if drop["proposed"] else 0.0)
            if drop
            else None
        )
        mq = ms["memory_schranken_quota"]
        print(
            f"[memory] memory_fabrication-Schranken(agent-final)="
            f"{'n/a' if mq is None else f'{mq:.3f}'} over {ms['n_turns']} turns  "
            f"drop-rate={'n/a' if rate is None else f'{rate:.3f}'}  "
            f"re-ask: carry_miss={ms['n_carry_misses']} reask_viol={ms['n_reask_violations']}"
        )
    edge = out.get("edge")
    if edge:
        es = edge["summary"]
        eq = es["schranken_quota_provisional"]
        print(
            f"[edge] cases={edge['n_cases']}  credibility(2-7)={es['overall_credibility']:.3f}  "
            f"edge_overreach-Schranken(prov)={'n/a' if eq is None else f'{eq:.3f}'}  "
            f"(non-edge no-regression vs baseline 1.000/0.991 — see report.md)"
        )
    inj = out.get("injection")
    if inj:
        xq = (inj.get("exfiltration") or {}).get("schranken_quota")
        iq = inj["summary"]["schranken_quota_provisional"]
        print(
            f"[injection] cases={inj['n_cases']}  "
            f"exfiltration-Schranken(agent-final)={'n/a' if xq is None else f'{xq:.3f}'}  "
            f"injection_override-Schranken(prov)={'n/a' if iq is None else f'{iq:.3f}'}"
        )
    arch = out.get("archetype")
    if arch:
        asum = arch["summary"]
        print(
            f"[archetype] cases={arch['n_cases']}  credibility(2-7)={asum['overall_credibility']:.3f}  "
            f"(archetype_fit — credibility/axes class, NO hard gate; non-archetype no-regression preserved)"
        )
    calib = out.get("calibration")
    if calib:
        csum = calib["summary"]
        print(
            f"[calibration] cases={calib['n_cases']}  credibility(2-7)={csum['overall_credibility']:.3f}  "
            f"(confident_correct_vs_hedge — credibility/axes class, NO hard gate; assertive-where-grounded vs honest hedge)"
        )
    bux = out.get("beratungs_ux")
    if bux:
        bsum = bux["summary"]
        print(
            f"[beratungs_ux] cases={bux['n_cases']}  credibility(2-7)={bsum['overall_credibility']:.3f}  "
            f"(Beratungs-UX — Klären-vor-Empfehlen / Tiefe-auf-Abruf; 3 Fälle mit bestehendem Hard-Gate: walked_into_trap / confident_wrong)"
        )
    loes = out.get("loesungserarbeitung")
    if loes:
        lsum = loes["summary"]
        print(
            f"[loesungserarbeitung] cases={loes['n_cases']}  credibility(2-7)={lsum['overall_credibility']:.3f}  "
            f"(Lösungserarbeitung — erarbeiten statt abschieben, ohne erfinden; 5 Fälle mit Hard-Gate: invented_precision / confident_wrong)"
        )
    print(f"\nArtifacts: {run_dir}")
    print("→ Adjudicate factual correctness + hard gates in human_review_worksheet.md")


if __name__ == "__main__":
    main()
