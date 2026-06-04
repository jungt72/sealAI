"""C5 (P2-1 TEIL A) — backfill accounting for the pack_affinity marker.

Exercises the pure `plan_backfill` core (no Qdrant I/O): correct classification,
exact conservation of every point, and idempotency on a second run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "backfill_pack_affinity_qdrant.py"
)
_spec = importlib.util.spec_from_file_location("backfill_pack_affinity_qdrant", _SCRIPT)
assert _spec and _spec.loader
backfill = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = backfill  # dataclass annotation resolution needs this
_spec.loader.exec_module(backfill)


def _point(
    point_id: str, metadata: dict | None = None, text: str = ""
) -> SimpleNamespace:
    return SimpleNamespace(
        id=point_id, payload={"metadata": metadata or {}, "text": text}
    )


def test_plan_backfill_classifies_and_conserves() -> None:
    points = [
        _point("p1", {"entity": "Radialwellendichtring"}),
        _point("p2", {"entity": "FKM"}, text="chemische Beständigkeit gegen Öl"),
        _point("p3", {"route_key": "rwdr_dimension"}),
        _point("p4", {"category": "material"}, text="NBR Shore-Härte"),
    ]
    plan = backfill.plan_backfill(points)
    assert plan.total == 4
    assert plan.to_set_rwdr == 2
    assert plan.to_set_cross_cutting == 2
    assert plan.already_correct == 0
    assert plan.write_count == 4
    assert plan.conserved is True


def test_plan_backfill_is_idempotent() -> None:
    pre = [
        _point("p1", {"entity": "Radialwellendichtring", "pack_affinity": "rwdr"}),
        _point("p2", {"entity": "FKM", "pack_affinity": None}),
    ]
    plan = backfill.plan_backfill(pre)
    assert plan.already_correct == 2
    assert plan.write_count == 0
    assert plan.conserved is True


def test_plan_backfill_writes_marker_into_metadata() -> None:
    plan = backfill.plan_backfill([_point("p1", {"entity": "Simmerring"})])
    point_id, payload = plan.writes[0]
    assert point_id == "p1"
    assert payload["metadata"]["pack_affinity"] == "rwdr"
