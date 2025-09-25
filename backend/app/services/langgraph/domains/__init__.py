# -*- coding: utf-8 -*-
# Stellt sicher, dass Domains beim Import registriert werden.
from .rwdr import register as register_rwdr
from .hydraulics_rod import register as register_hydraulics_rod

def register_all_domains() -> None:
    register_rwdr()
    register_hydraulics_rod()
