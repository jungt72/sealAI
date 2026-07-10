"""B — the eval manifest records the eval↔deploy binding (tree_hash + dirty).

`tree_hash` is the served-runtime content hash from ops/tree-hash.sh (the single source of truth the
V2 deploy gate keys on); `dirty` flags uncommitted served content at eval time. Run with
`PYTHONPATH=backend`.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_tree_binding_matches_the_canonical_script():
    from sealai_v2.eval.__main__ import _tree_binding

    tree_hash, dirty = _tree_binding()
    script = subprocess.check_output(
        ["bash", str(REPO / "ops" / "tree-hash.sh")],
        cwd=str(REPO),
        text=True,
    ).strip()
    assert tree_hash == script, "eval must derive tree_hash ONLY from ops/tree-hash.sh"
    assert len(tree_hash) >= 40
    assert isinstance(dirty, bool)


def test_manifest_records_tree_hash_and_dirty(tmp_path):
    # a mini offline run (fake LLM, 1 case, 1 column) must thread tree_hash/dirty into the manifest
    from sealai_v2.config.settings import Settings
    from sealai_v2.eval.harness import COLUMNS, run_eval
    from sealai_v2.tests._fakes import FakeLlmClient

    asyncio.run(
        run_eval(
            Settings(),
            run_dir=tmp_path,
            run_label="binding-probe",
            git_sha="deadbeef",
            tree_hash="PROBE_TREE_HASH",
            dirty=True,
            timestamp="2026-06-19T00:00:00Z",
            columns={"flags_off": COLUMNS["flags_off"]},
            smoke_limit=1,
            client_factory=lambda _provider: FakeLlmClient("ok"),
        )
    )
    manifest = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))[
        "manifest"
    ]
    assert manifest["tree_hash"] == "PROBE_TREE_HASH"  # param → manifest wiring
    assert manifest["dirty"] is True
    assert len(manifest["runtime_profile_hash"]) == 64
    assert manifest["runtime_profile"]["schema_version"] == 1
