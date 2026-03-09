from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

UnitType = Literal["bar", "psi", "C", "F"]

class PhysicalParameter(BaseModel):
    """
    Repräsentiert einen physikalischen Parameter mit Einheitenkonvertierung (Phase G2).
    Unterstützt Druck (bar, psi) und Temperatur (C, F).
    """
    value: float = Field(..., description="Der numerische Wert des Parameters.")
    unit: UnitType = Field(..., description="Die Einheit des Parameters (bar, psi, C, F).")

    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_base_unit(self) -> float:
        """
        Konvertiert den Wert in die Basis-Einheit des Systems:
        - Druck: bar
        - Temperatur: C
        """
        if self.unit == "bar":
            return self.value
        elif self.unit == "psi":
            # 1 psi = 0.0689476 bar
            return self.value * 0.0689476
        elif self.unit == "C":
            return self.value
        elif self.unit == "F":
            # C = (F - 32) * 5 / 9
            return (self.value - 32) * 5 / 9
        return self.value

    @property
    def base_unit(self) -> str:
        """Gibt die Basis-Einheit für den aktuellen Typ zurück."""
        if self.unit in ["bar", "psi"]:
            return "bar"
        if self.unit in ["C", "F"]:
            return "C"
        return self.unit
