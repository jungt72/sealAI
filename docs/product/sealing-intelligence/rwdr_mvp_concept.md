# RWDR MVP Concept

`sealing | Intelligence` erstellt im RWDR-MVP ausschließlich einen `Technical RWDR RFQ Brief`.

Doktrin:

```text
AI extracts.
User confirms.
sealing | Intelligence structures.
Manufacturer / distributor / responsible engineer evaluates.
```

## Scope

In scope sind Radialwellendichtringe, RWDR, rotary shaft lip seals und typische MRO-/Ersatzteil-/Leckage-Anfragen.

Out of scope sind Hersteller-Routing, Marketplace, Produkt- oder Materialempfehlung, finale technische Entscheidung, Sicherheitszertifizierung, ATEX, Wasserstoff, Nuklear, Luftfahrt, toxische Prozessmedien, medizinkritische Fälle, Gleitringdichtungen, Hydraulik-Stangen-/Kolbendichtungen, O-Ring-Nutberechnung und statische Flachdichtungen als Primärfall.

## Status Model

Es gibt nur drei customer-facing Status:

- `COMPLETE`: ausreichend strukturiert für Herstellerbewertung, keine technische Entscheidung.
- `NEEDS_CLARIFICATION`: kritische Angaben fehlen, sind widersprüchlich oder unbestätigt.
- `OUT_OF_SCOPE`: harter Ausschluss des RWDR-MVP.

## Minimal RFQ Kernel

Der Kernel kennt Abmessungen `d1 x D x b`, Abdichtfunktion, Medium, Drehzahl, Druck, Temperatur, Anwendung, Wellenzustand, alte Teileangaben, Bauformhinweise, Montage, Umgebung, regulatorische Anforderungen und kommerzielle RFQ-Metadaten.

`D` und `b` sind kritisch. Ohne Gehäusebohrung und Breite darf kein Fall `COMPLETE` werden.

## Non-Goals

Keine Herstellerliste, kein Partner-Matching, kein Checkout, kein automatischer Versand, keine Materialfreigabe, keine Produktempfehlung, keine finale technische Eignungsfreigabe.
