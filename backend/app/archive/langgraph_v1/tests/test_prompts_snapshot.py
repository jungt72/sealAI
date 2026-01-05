from pathlib import Path

from app.langgraph.config.loader import AgentsConfig
from app.langgraph.nodes import supervisor_factory


def test_supervisor_prompt_snapshot():
    cfg = AgentsConfig.load(Path(__file__).resolve().parent.parent / "config" / "agents.yaml")
    sup_cfg = cfg.supervisor_cfg()
    rendered = supervisor_factory._render_prompt(
        sup_cfg.prompt,
        prefix=sup_cfg.handoff_tool_prefix,
        output_mode=sup_cfg.output_mode,
    )

    snapshot_path = Path(__file__).resolve().parent / "__snapshots__" / "supervisor_prompt.md"
    expected = snapshot_path.read_text(encoding="utf-8")
    assert rendered.strip() == expected.strip()
