from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Tuple, List, Optional
import yaml

from app.models.chemical_matrix import ChemicalCompatibility, ChemicalKnowledgeBase, RatingEnum

class AbstractChemicalRepository(ABC):
    @abstractmethod
    def get_compatibility(self, material_id: str, medium_id: str) -> ChemicalCompatibility:
        """
        Returns compatibility information for a given material and medium.
        Returns a RatingEnum.U object if no match is found.
        """
        pass

class YamlChemicalRepository(AbstractChemicalRepository):
    def __init__(self, yaml_path: str):
        self.yaml_path = Path(yaml_path)
        self._matrix: Dict[Tuple[str, str], ChemicalCompatibility] = {}
        self._load_and_validate()

    def _load_and_validate(self) -> None:
        """
        Loads the YAML file and validates it strictly against the Pydantic schema
        to prevent schema drift.
        """
        if not self.yaml_path.exists():
            # In a real enterprise scenario, we might want to log this or use a default.
            # For now, we raise to ensure the baseline is present.
            raise FileNotFoundError(f"Chemical matrix YAML baseline not found at {self.yaml_path}")
        
        with open(self.yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {"entries": []}
            
        # Pydantic validation (Schema-Drift-Schutz)
        kb = ChemicalKnowledgeBase(**data)
        
        for entry in kb.entries:
            # We store keys in uppercase for case-insensitive lookup
            key = (entry.material_id.upper(), entry.medium_id.upper())
            self._matrix[key] = entry

    def get_compatibility(self, material_id: str, medium_id: str) -> ChemicalCompatibility:
        """
        Returns the compatibility object for the requested combination.
        If not found, returns a ChemicalCompatibility object with rating 'U'.
        """
        key = (material_id.upper(), medium_id.upper())
        if key in self._matrix:
            return self._matrix[key]
        
        # Fallback for unknown combinations
        return ChemicalCompatibility(
            material_id=material_id,
            medium_id=medium_id,
            rating=RatingEnum.U,
            conditions=["Keine Baseline-Daten verfügbar"],
            failure_modes=[],
            evidence_source="SealAI Fallback"
        )

# Global Singleton for the application
import os

_BASE_DIR = Path(__file__).parent.parent.parent
_YAML_PATH = _BASE_DIR / "data" / "knowledge" / "chemical_matrix.yaml"

_repository_instance: Optional[YamlChemicalRepository] = None

def get_chemical_repository() -> YamlChemicalRepository:
    """Provides a global singleton instance of the chemical repository."""
    global _repository_instance
    if _repository_instance is None:
        _repository_instance = YamlChemicalRepository(str(_YAML_PATH))
    return _repository_instance
