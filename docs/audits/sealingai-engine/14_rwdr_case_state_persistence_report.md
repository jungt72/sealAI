# RWDR Case-State Persistence Repair Report

Datum: 2026-05-27

## Ausgangsbefehle

- `pwd` -> `/home/thorsten/sealai`
- `git branch --show-current` -> `redesign/sealai-cockpit-overview`
- `git status --short` -> umfangreicher vorbestehender Dirty Worktree; dieser Patch beschränkt sich auf RWDR Case-State, API/BFF, RfqPane-Integration, Tests und diesen Report.

## Relevante Discovery

- Backend RWDR Domain Kernel: `backend/app/services/rwdr_mvp_brief.py`
- RFQ API: `backend/app/api/v1/endpoints/rfq.py`
- RFQ Preview Service / Export-Bestand: `backend/app/services/rfq_preview_service.py`, `backend/app/api/v1/renderers/rfq_pdf.py`
- Frontend RWDR Flow: `frontend/src/components/dashboard/RfqPane.tsx`
- BFF Pfadhelfer: `frontend/src/lib/bff/workspace.ts`
- BFF RWDR Routes: `frontend/src/app/api/bff/rfq/rwdr/**`
- Fokussierte Tests: `backend/tests/unit/services/test_rwdr_mvp_brief.py`, `backend/app/api/tests/test_rfq_endpoint.py`, `frontend/src/components/dashboard/RfqPane.test.tsx`

## Dateien geändert

- `backend/app/services/rwdr_mvp_brief.py`
- `backend/app/api/v1/endpoints/rfq.py`
- `backend/tests/unit/services/test_rwdr_mvp_brief.py`
- `backend/app/api/tests/test_rfq_endpoint.py`
- `frontend/src/lib/bff/workspace.ts`
- `frontend/src/app/api/bff/rfq/rwdr/cases/[caseId]/route.ts`
- `frontend/src/app/api/bff/rfq/rwdr/cases/[caseId]/confirmations/route.ts`
- `frontend/src/app/api/bff/rfq/rwdr/cases/[caseId]/brief/route.ts`
- `frontend/src/app/api/bff/rfq/rwdr/cases/[caseId]/export/route.ts`
- `frontend/src/components/dashboard/RfqPane.tsx`
- `frontend/src/components/dashboard/RfqPane.test.tsx`
- `docs/audits/sealingai-engine/14_rwdr_case_state_persistence_report.md`

## Persistence Approach

Implementiert wurde ein backend-owned `RWDRCaseStateRepository` als prozesslokales Repository ohne Datenbankmigration. Das war bewusst gewählt, weil keine Produktionsmigration ausgeführt werden darf und die bestehende Persistenzkonvention zuerst geprüft werden muss, bevor ein dauerhaftes Tabellenmodell eingeführt wird.

Gespeichert werden:

- `case_id`
- `schema_version`
- `raw_inquiry_text`
- `extraction_version`
- `rule_version`
- `created_at` / `updated_at` als Audit-Metadaten
- EvidenceFields inklusive `origin`, `source_span`, `confirmation_status`, `previous_value`, `user_action_timestamp`
- Evaluation-Status, Missing Fields, Computed Values, Review Flags, Fragen, Messhinweise
- generierter `Technical RWDR RFQ Brief`
- Export-Metadaten und Markdown-Exportinhalt

Audit-Zeitstempel werden nicht in die deterministische Bewertung eingespeist.

## API Contracts

- `POST /api/v1/rfq/rwdr/analyze`
  - Erstellt `case_id`, speichert Raw Inquiry und extrahierte EvidenceFields.
  - Liability-bearing Felder bleiben initial unbestätigt.

- `GET /api/v1/rfq/rwdr/cases/{case_id}`
  - Liefert den gespeicherten Case-State für Frontend-Recovery.

- `POST /api/v1/rfq/rwdr/cases/{case_id}/confirmations`
  - Speichert `confirm`, `edit`, `explicitly_unknown`, `reject`.
  - `confirm` für extrahierte liability-bearing Felder verlangt persistierte oder mitgesendete `source_span`.
  - `edit` speichert `previous_value` und setzt den Wert als nutzerbearbeitet.

- `POST /api/v1/rfq/rwdr/cases/{case_id}/evaluate`
  - Bewertet aus persisted EvidenceFields.

- `POST /api/v1/rfq/rwdr/cases/{case_id}/brief`
  - Generiert den Brief aus persisted EvidenceFields.

- `GET /api/v1/rfq/rwdr/cases/{case_id}/export.md`
  - Liefert backend-generierten Markdown/Text-Export aus persisted Brief.

## Export Integration

RWDR Copy/Export ist jetzt an den backend-generierten Case-State gebunden. Für RWDR wurde kein PDF-Support vorgetäuscht; umgesetzt ist ein persistierter Markdown/Text-Export. Die bestehende RFQ-Preview-PDF-Strecke bleibt separat.

## Frontend Flow

- Analyze speichert `case_id` aus der Backend-Antwort.
- Confirm/Edit/Unknown/Reject senden Decisions an `/cases/{case_id}/confirmations`.
- Die UI rendert anschließend den vom Backend zurückgegebenen Case-State.
- Brief-Erzeugung ruft `/cases/{case_id}/brief` auf.
- Copy/Export nutzt den vom Backend gelieferten Markdown-Export, wenn vorhanden.
- RWDR Flow rendert weiterhin kein ManufacturerFitPanel, keine Partner-Fit-Oberfläche und kein Routing.

## Tests hinzugefügt/aktualisiert

Backend:

- Persistierter RWDR Case wird mit `case_id`, Raw Inquiry und unbestätigten EvidenceFields erstellt.
- Confirmation Decisions werden persisted.
- Confirm ohne Source Span für extrahierte liability-bearing Felder wird blockiert.
- Edit speichert `previous_value`.
- `explicitly_unknown` wird nicht bestätigter Fakt.
- Reject entfernt den Wert aus bestätigten Fakten.
- Get/Evaluate/Brief/Export nutzen persisted EvidenceFields.
- Umfangsgeschwindigkeit erscheint aus persisted bestätigten d1/rpm.
- OUT_OF_SCOPE bleibt deterministisch und timestamp-unabhängig.

Frontend:

- Analyze speichert `case_id`.
- Confirm/Edit/Unknown/Reject posten an den Case-State-Endpunkt.
- Backend-Antwort re-rendert die EvidenceFields.
- Brief-Erzeugung nutzt `/cases/{case_id}/brief`.
- Export nutzt `/cases/{case_id}/export`.
- RWDR Flow zeigt keine Partner-Fit-/Matching-Oberfläche.

## Befehle und Testergebnisse

- `PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/services/rwdr_mvp_brief.py backend/app/api/v1/endpoints/rfq.py`
  - erfolgreich

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py`
  - `23 passed`

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rfq_endpoint.py`
  - `13 passed`, eine DeprecationWarning für `HTTP_422_UNPROCESSABLE_ENTITY`

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py`
  - `49 passed`, eine DeprecationWarning für `HTTP_422_UNPROCESSABLE_ENTITY`

- `npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts`
  - `3 passed`, `15 tests passed`

- `git diff --check`
  - erfolgreich

- `rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer" backend frontend docs`
  - liefert weiterhin viele Treffer in Legacy-Tests, Guard-Tests, historischen Konzeptdokumenten, KB-Daten und Such-/Report-Strings. Keine neuen RWDR-MVP Customer-Facing Matching-/Routing-Flächen wurden eingeführt.

## Bekannte Restlücken

- Case-State ist prozesslokal und nach Service-Neustart nicht dauerhaft. Nächster Patch sollte eine DB-/Repository-Implementierung nach bestehenden Projektkonventionen ergänzen.
- RWDR Export ist Markdown/Text. PDF aus persisted RWDR Case-State ist nicht umgesetzt.
- Frontend-Recovery per URL/gespeicherter `case_id` ist vorbereitet über GET-Endpunkt/BFF, aber noch nicht als eigene Nutzer-Navigation ausgebaut.
- Broad Forbidden-Language-Suche bleibt wegen historischer Docs, Tests und Guards laut.

## Nächster sinnvoller Patch

Persistente DB-backed RWDR Case-State-Tabelle oder vorhandene Case-Snapshot-Integration einführen, danach RWDR-PDF-Export direkt aus persisted `Technical RWDR RFQ Brief` anbinden.
