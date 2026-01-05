import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUB_PATH = ROOT.parent / "langchain_core_stub"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if STUB_PATH.exists() and str(STUB_PATH) not in sys.path:
    sys.path.insert(0, str(STUB_PATH))
