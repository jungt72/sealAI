from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional

import yaml

from app.models.material_profile import MaterialKnowledgeBase, MaterialPhysicalProfile


class AbstractMaterialRepository(ABC):
    @abstractmethod
    def get_profile(self, material_id: str) -> Optional[MaterialPhysicalProfile]:
        """Returns the material profile for the given material ID."""
        raise NotImplementedError


class YamlMaterialRepository(AbstractMaterialRepository):
    def __init__(self, yaml_path: str):
        self.yaml_path = Path(yaml_path)
        self._profiles: Dict[str, MaterialPhysicalProfile] = {}
        self._load_and_validate()

    def _load_and_validate(self) -> None:
        """
        Loads the YAML file and validates it strictly against the Pydantic schema
        to prevent schema drift.
        """
        if not self.yaml_path.exists():
            raise FileNotFoundError(f"Material profiles YAML baseline not found at {self.yaml_path}")

        with open(self.yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {"profiles": []}

        kb = MaterialKnowledgeBase(**data)

        for profile in kb.profiles:
            self._profiles[profile.material_id.upper()] = profile

    def get_profile(self, material_id: str) -> Optional[MaterialPhysicalProfile]:
        key = material_id.upper()
        return self._profiles.get(key)


_BASE_DIR = Path(__file__).parent.parent.parent
_YAML_PATH = _BASE_DIR / "data" / "knowledge" / "material_profiles.yaml"

_repository_instance: Optional[YamlMaterialRepository] = None


def get_material_repository() -> YamlMaterialRepository:
    """Provides a global singleton instance of the material repository."""
    global _repository_instance
    if _repository_instance is None:
        _repository_instance = YamlMaterialRepository(str(_YAML_PATH))
    return _repository_instance
