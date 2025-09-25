# -*- coding: utf-8 -*-
import os
from typing import Dict, Any
from app.services.langgraph.domains.base import DomainSpec, register_domain
from .calculator import compute as hyd_rod_compute

def register() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec = DomainSpec(
        id="hydraulics_rod",
        name="Hydraulik – Stangendichtung",
        base_dir=base_dir,
        schema_file="schema.yaml",
        calculator=hyd_rod_compute,
        ask_order=[
            "falltyp", "stange_mm", "nut_d_mm", "nut_b_mm", "druck_bar",
            "geschwindigkeit_m_s", "medium", "temp_max_c"
        ],
    )
    register_domain(spec)
