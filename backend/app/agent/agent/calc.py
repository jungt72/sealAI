# Re-export shim — canonical location: app.agent.domain.physics
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.domain.physics import (  # noqa: F401
    calc_kinematics,
    calc_mechanics,
    calc_thermodynamics,
    calc_tribology,
    calculate_physics,
)
