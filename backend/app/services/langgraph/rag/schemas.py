from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class VendorMeta:
    vendor_id: str
    paid_tier: str
    contract_valid_until: date
    active: bool

    def is_partner(self, today: Optional[date] = None) -> bool:
        t = today or date.today()
        return self.paid_tier != "none" and self.active and self.contract_valid_until >= t
