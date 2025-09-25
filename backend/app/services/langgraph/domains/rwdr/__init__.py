# -*- coding: utf-8 -*-
import os
from typing import Dict, Any
from app.services.langgraph.domains.base import DomainSpec, register_domain
from .calculator import compute as rwdr_compute

def register() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec = DomainSpec(
        id="rwdr",
        name="Radialwellendichtring",
        base_dir=base_dir,
        schema_file="schema.yaml",
        calculator=rwdr_compute,
        ask_order=[
            "falltyp", "bauform", "wellen_mm", "gehause_mm", "breite_mm",
            "medium", "temp_max_c", "druck_bar", "drehzahl_u_min"
        ],
    )
    register_domain(spec)
