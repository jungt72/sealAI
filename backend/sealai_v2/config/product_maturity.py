"""Runtime projection of the ratified product-maturity contract."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from sealai_v2.config.settings import Settings

_MANIFEST = Path(__file__).with_name("product_maturity.json")


@lru_cache(maxsize=1)
def load_product_maturity() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def runtime_product_maturity(settings: Settings) -> dict:
    manifest = deepcopy(load_product_maturity())
    activation = {
        "knowledge": settings.knowledge_mode_enabled,
        "comparison": settings.knowledge_mode_enabled,
        "engineering": settings.compute_enabled,
        "case": settings.case_decision_records_enabled,
        "failure": False,
        "substitution": False,
        "manufacturer_fit": settings.manufacturer_fit_enabled,
        "lifecycle": False,
    }
    for mode, mode_contract in manifest["modes"].items():
        mode_contract["active"] = activation[mode]
    return manifest
