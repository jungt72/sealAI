"""STS — SeaLAI Technical Standard (internes Canonical Model).

Stellt Zugriff auf die STS-Seed-Daten bereit:
  - Materialcodes     (STS-MAT-*)
  - Dichtungstypen    (STS-TYPE-*)
  - Requirement Classes (STS-RS-*)
  - Mediumcodes       (STS-MED-*)
  - Offene Pruefpunkte (STS-OPEN-*)
"""

from app.agent.sts.loader import load_all, validate_all  # noqa: F401
from app.agent.sts.codes import (  # noqa: F401
    get_material,
    get_sealing_type,
    get_requirement_class,
    get_medium,
    get_open_point,
    is_valid_code,
    list_codes,
)
