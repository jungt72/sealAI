"""
Physical plausibility checks for engine outputs.

Called after every L2 calculation to catch garbage-in / garbage-out scenarios.
Thresholds are conservative defaults for elastomer rotary seals.

.. note::
   DOMAIN: thresholds verified against industry standard ranges for rotary
   lip seals and radial shaft seals.  Adjust if supporting other seal families.
"""
from .engine_result import EngineResult
from .enums import EngineStatus


def check_circumferential_speed(value_ms: float) -> EngineResult[float]:
    """
    Post-calculation plausibility check for circumferential speed (v in m/s).

    Args:
        value_ms: Circumferential speed in metres per second.

    Returns:
        :class:`EngineResult` with status ``COMPUTED``, ``OUT_OF_RANGE``, or
        ``CONTRADICTION_DETECTED``.
    """
    if value_ms < 0:
        return EngineResult(
            status=EngineStatus.CONTRADICTION_DETECTED,
            value=value_ms,
            reason=(
                f"Negative circumferential speed ({value_ms:.2f} m/s) indicates "
                "contradictory inputs."
            ),
        )
    if value_ms > 150.0:
        return EngineResult(
            status=EngineStatus.OUT_OF_RANGE,
            value=value_ms,
            reason=(
                f"Circumferential speed {value_ms:.1f} m/s exceeds physical "
                "plausibility for rotary seals (> 150 m/s)."
            ),
        )
    return EngineResult(status=EngineStatus.COMPUTED, value=round(value_ms, 3))


def check_pv_value(value: float) -> EngineResult[float]:
    """
    Post-calculation plausibility check for PV value (pressure × velocity).

    Args:
        value: PV value in MPa·m/s (or bar·m/s, depending on caller convention).

    Returns:
        :class:`EngineResult` with status ``COMPUTED``, ``OUT_OF_RANGE``, or
        ``CONTRADICTION_DETECTED``.
    """
    if value < 0:
        return EngineResult(
            status=EngineStatus.CONTRADICTION_DETECTED,
            value=value,
            reason=(
                f"Negative PV value ({value:.2f}) indicates contradictory inputs."
            ),
        )
    if value > 500.0:
        return EngineResult(
            status=EngineStatus.OUT_OF_RANGE,
            value=value,
            reason=(
                f"PV value {value:.1f} exceeds known material limits for "
                "elastomer seals (> 500)."
            ),
        )
    return EngineResult(status=EngineStatus.COMPUTED, value=round(value, 3))


def check_temperature_range(
    min_c: float | None,
    max_c: float | None,
) -> EngineResult[bool]:
    """
    Check a temperature range for physical plausibility.

    Args:
        min_c: Minimum temperature in °C, or ``None`` if not provided.
        max_c: Maximum temperature in °C, or ``None`` if not provided.

    Returns:
        :class:`EngineResult` with status ``COMPUTED``, ``OUT_OF_RANGE``, or
        ``CONTRADICTION_DETECTED``.
    """
    if min_c is not None and max_c is not None and min_c > max_c:
        return EngineResult(
            status=EngineStatus.CONTRADICTION_DETECTED,
            value=False,
            reason=(
                f"Temperature min ({min_c} °C) exceeds max ({max_c} °C)."
            ),
        )
    if max_c is not None and max_c > 400.0:
        return EngineResult(
            status=EngineStatus.OUT_OF_RANGE,
            value=False,
            reason=(
                f"Max temperature {max_c} °C exceeds elastomer seal operating "
                "range (> 400 °C)."
            ),
        )
    return EngineResult(status=EngineStatus.COMPUTED, value=True)
