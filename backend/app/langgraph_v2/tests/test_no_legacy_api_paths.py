from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]


def test_no_legacy_langgraph_api_paths_referenced() -> None:
    offenders: list[str] = []
    for path in _ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "test_no_legacy_api_paths.py":
            continue
        if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/api/langgraph/" in text or '"/api/langgraph' in text or "'/api/langgraph" in text:
            offenders.append(str(path.relative_to(_ROOT)))
    assert offenders == []
