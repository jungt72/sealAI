# RWDR Normative Backbone

Normen werden im MVP nur als interne Referenz-Metadaten geführt. Sie sind keine Compliance-Claims.

Referenzen:

- `ISO_6194_1`: ISO 6194-1, elastomeric radial shaft seals, types, nominal dimensions, tolerances.
- `ISO_6194_3`: ISO 6194-3, storage, handling, installation.
- `ISO_6194_4`: ISO 6194-4, performance / qualification tests.
- `ISO_6194_5`: ISO 6194-5, visible defects.
- `ISO_16589`: thermoplastic / PTFE radial shaft seals.
- `DIN_3760`: German market reference for standard RWDR.

Jedes Objekt trägt:

```json
{
  "mvp_usage": "reference_metadata_only",
  "does_not_claim_compliance": true,
  "does_not_replace_manufacturer_validation": true
}
```

Standard-RWDR werden als Low-Pressure-Kontext behandelt. Druckangaben erzeugen Review-Flags, keine Druckentscheidung.
