"""Technical manufacturer pool derived only from verified capabilities."""

from __future__ import annotations

from sealai_v2.knowledge.hersteller_partner import HerstellerPartner


class VerifiedCapabilityPartnerRegistry:
    def __init__(self, capability_store) -> None:
        self._capabilities = capability_store

    def _partner(self, profile) -> HerstellerPartner | None:
        if not profile.is_verified():
            return None
        return HerstellerPartner(
            hersteller=profile.manufacturer_id,
            firmenname=profile.company_name,
            # In this registry, aktiv means technically eligible. Billing is not
            # consulted and therefore cannot affect fit or ordering.
            aktiv=True,
            # Commercial contact, visibility, and plan fields are intentionally
            # absent from the technical projection. Handoff resolves them via
            # the separately gated commercial registry.
            lead_email="",
            website="",
            beschreibung="",
            standort="",
            kontakt_oeffentlich="",
            partner_seit="",
            plan="",
            werkstoffe=profile.materials,
            bauformen=profile.seal_types,
            groessen=", ".join(profile.size_ranges),
            zertifikate=profile.certificates,
        )

    def get(self, manufacturer_id: str) -> HerstellerPartner | None:
        profile = self._capabilities.get(manufacturer_id)
        return self._partner(profile) if profile is not None else None

    def list_active(self) -> tuple[HerstellerPartner, ...]:
        partners = (self._partner(profile) for profile in self._capabilities.list_all())
        return tuple(partner for partner in partners if partner is not None)
