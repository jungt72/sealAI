from pathlib import Path

from app.langgraph.config.loader import AgentsConfig


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "agents.yaml"


def test_agents_yaml_schema_loads():
    cfg = AgentsConfig.load(_config_path())
    supervisor = cfg.supervisor_cfg()

    assert supervisor.handoff_tool_prefix == "handoff_to_"
    assert supervisor.output_mode == "final"
    assert len(supervisor.workers) >= 3

    domains = {name: cfg.domain_cfg(name) for name in cfg.domain_names()}
    assert "profil" in domains
    assert "validierung" in domains
    assert domains["validierung"].tools == []
    assert domains["profil"].prompt.system.startswith("Du bist der Profil-Agent.")
