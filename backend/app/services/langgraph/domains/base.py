# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import yaml
from dataclasses import dataclass
from typing import Dict, Any, Tuple, List, Optional, Callable


@dataclass
class DomainSpec:
    id: str
    name: str
    base_dir: str            # Ordner der Domain (für Prompts/Schema)
    schema_file: str         # relativer Pfad
    calculator: Callable[[dict], Dict[str, Any]]  # compute(params) -> {'calculated': ..., 'flags': ...}
    ask_order: List[str]     # Reihenfolge der Nachfragen (falls fehlt)

    def template_dir(self) -> str:
        return os.path.join(self.base_dir, "prompts")

    def schema_path(self) -> str:
        return os.path.join(self.base_dir, self.schema_file)

_REGISTRY: Dict[str, DomainSpec] = {}

def register_domain(spec: DomainSpec) -> None:
    _REGISTRY[spec.id] = spec
    # Domain-Prompts dem Jinja-Loader bekannt machen

def get_domain(domain_id: str) -> Optional[DomainSpec]:
    return _REGISTRY.get(domain_id)

def list_domains() -> List[str]:
    return list(_REGISTRY.keys())

# -------- YAML Schema Laden & Validieren (leichtgewichtig) ----------
def load_schema(spec: DomainSpec) -> Dict[str, Any]:
    with open(spec.schema_path(), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def validate_params(spec: DomainSpec, params: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Gibt (errors, warnings) zurück.
    YAML-Schema Felder:
      fields:
        <name>:
          required: bool
          type: str ('int'|'float'|'str'|'enum')
          min: float
          max: float
          enum: [..]
          ask_if: optional (Dependency-Hinweis, nur Info)
    """
    schema = load_schema(spec)
    fields = schema.get("fields", {})
    errors: List[str] = []
    warnings: List[str] = []

    def _typename(x):
        if isinstance(x, bool):   # bool ist auch int in Python
            return "bool"
        if isinstance(x, int):
            return "int"
        if isinstance(x, float):
            return "float"
        if isinstance(x, str):
            return "str"
        return type(x).__name__

    for key, rule in fields.items():
        req = bool(rule.get("required", False))
        if req and (key not in params or params.get(key) in (None, "")):
            errors.append(f"Pflichtfeld fehlt: {key}")
            continue
        if key not in params or params.get(key) in (None, ""):
            continue

        val = params.get(key)
        typ = rule.get("type")
        if typ == "enum":
            allowed = rule.get("enum", [])
            if val not in allowed:
                errors.append(f"{key}: ungültiger Wert '{val}', erlaubt: {allowed}")
        elif typ == "int":
            if not isinstance(val, int):
                # ints können als float ankommen (LLM) – tolerant casten
                try:
                    params[key] = int(float(val))
                except Exception:
                    errors.append(f"{key}: erwartet int, erhalten {_typename(val)}")
            else:
                # ok
                pass
        elif typ == "float":
            if isinstance(val, (int, float)):
                params[key] = float(val)
            else:
                try:
                    params[key] = float(str(val).replace(",", "."))
                except Exception:
                    errors.append(f"{key}: erwartet float, erhalten {_typename(val)}")
        elif typ == "str":
            if not isinstance(val, str):
                params[key] = str(val)

        # Ranges
        if isinstance(params.get(key), (int, float)):
            v = float(params[key])
            if "min" in rule and v < float(rule["min"]):
                errors.append(f"{key}: {v} < min {rule['min']}")
            if "max" in rule and v > float(rule["max"]):
                warnings.append(f"{key}: {v} > empfohlene Obergrenze {rule['max']}")

    return errors, warnings
