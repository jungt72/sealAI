# RWDR DB Persistence and PDF Export Report

Datum: 2026-05-27

## Ausgangsbefehle

- `pwd` -> `/home/thorsten/sealai`
- `git branch --show-current` -> `redesign/sealai-cockpit-overview`
- `git status --short` -> umfangreicher vorbestehender Dirty Worktree; dieser Patch beschränkt sich auf RWDR DB-backed Case-State, Export/API/BFF, fokussierte Tests und diesen Report.

## Discovery

- DB-Session: `backend/app/database.py` mit `AsyncSession`, `get_db`, SQLAlchemy `Base`.
- Bestehende Case-Persistenz: `backend/app/models/case_record.py` mit generischem `cases.payload` JSON/JSONB.
- Bestehende Snapshot-Persistenz: `backend/app/models/case_state_snapshot.py`.
- Migration-Konvention: Alembic in `backend/alembic/versions`.
- RFQ-Preview-Persistenz: `backend/app/services/rfq_preview_service.py` nutzt bestehende Case/Snapshot/Inquiry-Extract-Konventionen.
- PDF-Renderer: `backend/app/api/v1/renderers/rfq_pdf.py`, dependency-free, allowlisted Export-Payload.
- RWDR Case-State vorher: process-local Repository in `backend/app/services/rwdr_mvp_brief.py`.

## Dateien geändert

- `backend/app/services/rwdr_mvp_brief.py`
- `backend/app/api/v1/endpoints/rfq.py`
- `backend/app/api/v1/renderers/rfq_pdf.py`
- `backend/app/api/tests/test_rfq_endpoint.py`
- `frontend/src/lib/bff/workspace.ts`
- `frontend/src/app/api/bff/rfq/rwdr/cases/[caseId]/export.pdf/route.ts`
- `frontend/src/components/dashboard/RfqPane.tsx`
- `frontend/src/components/dashboard/RfqPane.test.tsx`
- `docs/audits/sealingai-engine/15_rwdr_db_persistence_pdf_export_report.md`

## DB Schema / Persistence Approach

Es wurde keine neue Migration erstellt. Der kleinste repo-konforme Ansatz ist Option B: bestehende generische `cases`-Tabelle mit `request_type = rwdr_rfq`, `engineering_path = rwdr` und strukturiertem `payload` JSON/JSONB.

Persistiert werden im `CaseRecord.payload`:

- `artifact_type = rwdr_case_state`
- `schema_version`
- `raw_inquiry_text`
- `extraction_version`
- `rule_version`
- `created_at`, `updated_at` als Audit-Metadaten
- `evidence_fields` inklusive Confirmation Decisions, `previous_value`, `user_action_timestamp`
- `evaluation_status`
- `missing_critical_fields`
- `missing_helpful_fields`
- `computed_values`
- `review_flags`
- `manufacturer_questions`
- `measurement_recommendations`
- `source_evidence_summary`
- `technical_rwdr_rfq_brief`
- `markdown_export_content`
- `pdf_export_reference`
- `export_metadata`

Audit-Felder werden gespeichert, aber nicht in die deterministische Evaluation eingespeist.

## Repository Approach

Ergänzt wurde:

- `RWDRCaseStateRepositoryProtocol`
- bestehendes `RWDRCaseStateRepository` bleibt als In-Memory-Testboundary erhalten
- `DbRWDRCaseStateRepository` nutzt `AsyncSession` und `CaseRecord.payload`

Die produktiven RWDR API-Endpunkte verwenden jetzt den DB-backed Repository-Pfad über `get_db`.

## API Changes

DB-backed:

- `POST /api/v1/rfq/rwdr/analyze`
- `GET /api/v1/rfq/rwdr/cases/{case_id}`
- `POST /api/v1/rfq/rwdr/cases/{case_id}/confirmations`
- `POST /api/v1/rfq/rwdr/cases/{case_id}/evaluate`
- `POST /api/v1/rfq/rwdr/cases/{case_id}/brief`
- `GET /api/v1/rfq/rwdr/cases/{case_id}/export.md`
- `GET /api/v1/rfq/rwdr/cases/{case_id}/export.pdf`

Das alte direkte `/rwdr/brief` bleibt als Legacy-/Testboundary bestehen, ist aber nicht der RWDR Confirmation Flow.

## PDF / Export Integration

- Markdown exportiert aus DB-persisted `Technical RWDR RFQ Brief`.
- PDF exportiert aus DB-persisted Brief ueber den vorhandenen dependency-free RFQ PDF Renderer.
- PDF enthaelt die RWDR Brief Sections, Status, bestaetigte Angaben, Berechnungen, offene Punkte und den verpflichtenden No-Release-/No-Recommendation-Hinweis.
- Kein Frontend-State wird als Exportquelle verwendet.
- Kein Hersteller-Routing, keine Herstellerliste, kein Partner-Fit.

Frontend:

- `RfqPane` zeigt den PDF-Link nur mit vorhandenem `case_id`.
- Copy nutzt weiterhin backend-generierten Markdown.
- Neuer BFF-Pfad: `/api/bff/rfq/rwdr/cases/{case_id}/export.pdf`.

## Tests

Backend:

- DB-backed Analyze erzeugt Case-ID.
- Get Case liest denselben persisted Case-State.
- Confirm/Edit/Unknown/Reject persistieren ueber den DB-backed Pfad.
- Evaluate/Brief/Markdown/PDF Export nutzen persisted EvidenceFields.
- Confirm ohne Source Span fuer extrahierte liability-bearing Felder wird blockiert.
- Umfangsgeschwindigkeit erscheint nach persisted Confirmation.
- OUT_OF_SCOPE und Missing-Field-Regeln bleiben durch bestehende RWDR-Tests abgedeckt.

Frontend:

- Case-ID Flow bleibt aktiv.
- Backend Brief/Markdown Export werden genutzt.
- PDF-Link zeigt auf den backend/BFF PDF-Endpunkt.
- RWDR Flow zeigt kein ManufacturerFitPanel und keine Partner-Fit-UI.

## Befehle und Ergebnisse

- `PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/services/rwdr_mvp_brief.py backend/app/api/v1/endpoints/rfq.py backend/app/api/v1/renderers/rfq_pdf.py`
  - erfolgreich

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py`
  - `72 passed`
  - eine DeprecationWarning fuer `HTTP_422_UNPROCESSABLE_ENTITY`

- `npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts`
  - `3 passed`, `15 tests passed`

- `git diff --check`
  - erfolgreich

- `rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer" backend frontend docs`
  - 405 Treffer. Klassifikation: Guard-/Forbidden-Language-Tests, historische Architektur-/Implementierungsdocs, KB-Daten, Legacy non-RWDR surfaces und Suchstrings in Audit-Reports. Keine neue RWDR-MVP Manufacturer-Matching- oder Recommendation-Fläche wurde eingeführt.

## Bekannte Restlücken

- RWDR Case-State liegt dauerhaft in `cases.payload`, aber ohne eigene relationale Child-Tabelle fuer EvidenceField-History. Fuer Audit-Analytics kann spaeter eine Child-Tabelle sinnvoll sein.
- `case_state_snapshots` werden fuer RWDR noch nicht versioniert mitgeschrieben.
- PDF ist bewusst einfacher Text-PDF-Renderer, kein typografisch ausgearbeiteter Bericht.
- Broad Forbidden-Language-Search bleibt wegen historischer Docs/Tests laut.

## Nächster sinnvoller Patch

RWDR Case-State zusaetzlich revisioniert in `case_state_snapshots` speichern und eine Recovery-Route im Frontend ueber persistierte `case_id`/URL-State sauber ausbauen.
