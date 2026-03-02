from __future__ import annotations

import json
from pathlib import Path

from app.langgraph_v2.nodes.worm_evidence_node import worm_evidence_node
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.state.audit import SourceRefPayload, ToolCallRecord
from app.services.rag.state import WorkingProfile


def test_worm_evidence_node_writes_bundle_and_sets_profile_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SEALAI_WORM_SIMULATED_DIR", str(tmp_path))
    state = SealAIState(
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
        tenant_id="tenant-1",
        working_profile=WorkingProfile(material="FKM", pressure_max_bar=42.0),
        tool_call_records=[
            ToolCallRecord(
                tool_name="search_technical_docs",
                tool_input={"query": "FKM"},
                tool_output={"hits": []},
            )
        ],
        source_ref_payloads=[
            SourceRefPayload(
                source_id="src-1",
                chunk_text="FKM pressure table",
                version="2026.02",
            )
        ],
    )

    patch = worm_evidence_node(state)

    bundle_key = patch["working_profile"].evidence_bundle_key
    assert isinstance(bundle_key, str) and bundle_key.startswith("worm://sealai/")
    assert patch["evidence_bundle_hash"] == patch["evidence_bundle"].bundle_hash_sha256

    relative = bundle_key.replace("worm://sealai/", "")
    stored = tmp_path / relative
    assert stored.exists()
    payload = json.loads(stored.read_text(encoding="utf-8"))
    assert payload["bundle_hash_sha256"] == patch["evidence_bundle_hash"]
    assert payload["working_profile_snapshot"]["material"] == "FKM"

