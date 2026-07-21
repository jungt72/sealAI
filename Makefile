# Makefile – E2E-/Pytest-Runner für den Backend-Consult-Flow

# Wichtig: SHELL muss ein ausführbares Binary sein (kein 'env bash').
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# ------------------------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------------------------
BASE ?= http://localhost:8000
BACKEND_CONTAINER ?= backend
NETWORK_BACKEND ?=
PYTHON ?= python3

# ------------------------------------------------------------------------------
# Hilfe
# ------------------------------------------------------------------------------
.PHONY: help
help: ## Diese Hilfe anzeigen
	@printf 'Verfügbare Targets:\n\n'; \
	awk 'BEGIN{FS=":.*?## "}; /^[a-zA-Z0-9_\-]+:.*?## /{printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ------------------------------------------------------------------------------
# E2E: Host-seitig (curl gegen ${BASE})
# ------------------------------------------------------------------------------
.PHONY: e2e e2e-host rwdr missing
e2e: e2e-host ## Führt die E2E-Checks gegen $(BASE) aus

e2e-host: ## Rod-Case (mit Back-up-Ring) prüft Formatregeln
	@echo "Health:"; curl -fsS "$(BASE)/health" | jq .
	@chat="rev_fix_$$(date +%s)"; \
	  R1=$$(curl -fsS -X POST "$(BASE)/api/v1/ai/beratung" \
	    -H "Content-Type: application/json" \
	    -d "{\"chat_id\":\"$$chat\",\"input_text\":\"Hydraulik-Stangendichtung Ersatz: Stange 40 mm, Bohrung 45 mm, Nutbreite 6 mm, Medium HLP46, Druck 200 bar, Temp 80 °C, Geschwindigkeit 0,8 m/s.\"}" \
	    | jq -r .response); \
	  R2=$$(curl -fsS -X POST "$(BASE)/api/v1/ai/beratung" \
	    -H "Content-Type: application/json" \
	    -d "{\"chat_id\":\"$$chat\",\"input_text\":\"Ja, Back-up-Ring ist zulässig. Bitte mit Stützring prüfen.\"}" \
	    | jq -r .response); \
	  R3=$$(curl -fsS -X POST "$(BASE)/api/v1/ai/beratung" \
	    -H "Content-Type: application/json" \
	    -d "{\"chat_id\":\"$$chat\",\"input_text\":\"Bitte konkrete Empfehlung nennen.\"}" \
	    | jq -r .response); \
	  echo "— Prüfe R3 —"; \
	  hdr=$$(echo "$$R3" | grep -c -E '^🔎 \*\*Meine Empfehlung'); \
	  cta=$$(echo "$$R3" | grep -ci -E '^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}'); \
	  after=$$(awk 'BEGIN{IGNORECASE=1} found{print} /^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}/{found=1; next}' <<< "$$R3" | wc -l); \
	  last_nonempty=$$(printf "%s\n" "$$R3" | awk 'NF{last=$$0} END{print last}'); \
	  [[ "$$hdr" -eq 1 ]] || { echo "FAIL: Header=$$hdr != 1"; exit 1; }; \
	  [[ "$$cta" -eq 1 ]] || { echo "FAIL: CTA=$$cta != 1"; exit 1; }; \
	  [[ "$$after" -eq 0 ]] || { echo "FAIL: $$after Zeilen nach CTA"; exit 1; }; \
	  echo "$$last_nonempty" | grep -qiE '^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}' \
	    || { echo "FAIL: endet nicht an CTA"; exit 1; }; \
	  echo "OK ✅"

rwdr: ## RWDR-Case: Druckstufen-Rückfrage + Format der Empfehlung
	@BASE="$(BASE)" bash -c 'set -euo pipefail; curl -fsS "$$BASE/health" >/dev/null; chat="rwdr_fix_$$(date +%s)"; \
	   R1=$$(curl -fsS -X POST "$$BASE/api/v1/ai/beratung" \
	     -H "Content-Type: application/json" \
	     -d "{\"chat_id\":\"$$chat\",\"input_text\":\"RWDR Ersatz: Welle 25 mm, Gehäuse 47 mm, Breite 7 mm, Medium Luft mit Überdruck 3 bar, Temp 60 °C, Drehzahl 1500 U/min.\"}" \
	     | jq -r .response); \
	   echo "$$R1" | grep -qi "Druckstufen" || { echo "FAIL: Keine Druckstufen-Rückfrage"; exit 1; }; \
	   R2=$$(curl -fsS -X POST "$$BASE/api/v1/ai/beratung" \
	     -H "Content-Type: application/json" \
	     -d "{\"chat_id\":\"$$chat\",\"input_text\":\"Druckstufenlösung ist zulässig.\"}" \
	     | jq -r .response); \
	   hdr=$$(echo "$$R2" | grep -c -E "^🔎 \*\*Meine Empfehlung"); \
	   cta=$$(echo "$$R2" | grep -ci -E "^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}"); \
	   after=$$(awk '\''BEGIN{IGNORECASE=1} found{print} /^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}/{found=1; next}'\'' <<< "$$R2" | wc -l); \
	   [[ "$$hdr" -eq 1 && "$$cta" -eq 1 && "$$after" -eq 0 ]] || { echo "FAIL: Formatfehler in R2"; exit 1; }; \
	   echo "OK ✅"'

missing: ## Pflichtfelder-Gate: bei fehlenden Angaben nur Rückfragen, keine Empfehlung
	@BASE="$(BASE)" bash -c 'set -euo pipefail; curl -fsS "$$BASE/health" >/dev/null; chat="missing_$$(date +%s)"; \
	   R1=$$(curl -fsS -X POST "$$BASE/api/v1/ai/beratung" \
	     -H "Content-Type: application/json" \
	     -d "{\"chat_id\":\"$$chat\",\"input_text\":\"Bitte Empfehlung für RWDR.\"}" \
	     | jq -r .response); \
	   echo "$$R1" | grep -qiE "Welche|Bitte|Fehlen|Angaben|Drehzahl|Druck|Temperatur" || { echo "FAIL: keine Rückfrage erkannt"; exit 1; }; \
	   ! echo "$$R1" | grep -q "^🔎 \*\*Meine Empfehlung" || { echo "FAIL: Empfehlung trotz fehlender Pflichtfelder"; exit 1; }; \
	   echo "OK ✅"'

# ------------------------------------------------------------------------------
# Pytest in Docker
# ------------------------------------------------------------------------------
.PHONY: docker-pytest docker-pytest-backend
docker-pytest: ## Pytest in Ephemeral-Container (network=host), BASE=$(BASE)
	@echo "Running pytest in docker (network=host), BASE=$(BASE)"
	@docker run --rm --network host -v $$PWD/tests:/tests python:3.12-slim \
		sh -lc 'pip install -q pytest requests && BASE="$(BASE)" pytest -q /tests/test_consult_e2e.py'

docker-pytest-backend: ## Pytest im Compose-Netz (BASE=http://$(BACKEND_CONTAINER):8000)
	@: $${NETWORK_BACKEND:?"NETWORK_BACKEND nicht gesetzt. Beispiel: make docker-pytest-backend NETWORK_BACKEND=sealai_sealai_network BACKEND_CONTAINER=backend"}
	@echo "Running pytest in docker (network=$(NETWORK_BACKEND)), BASE=http://$(BACKEND_CONTAINER):8000"
	@docker run --rm --network $(NETWORK_BACKEND) -v $$PWD/tests:/tests python:3.12-slim \
		sh -lc 'pip install -q pytest requests && BASE="http://$(BACKEND_CONTAINER):8000" pytest -q /tests/test_consult_e2e.py'
# ------------------------------------------------------------------------------
# Current V2 monorepo quality gates
# ------------------------------------------------------------------------------
.PHONY: test test-v2 lint-v2 architecture-v2 frontend-v2 verify-v2 tree-hash test-v1-container bench-v1
test: test-v2 ## Aktuelle V2-Backendtests ausführen

test-v2: ## Vollständige hermetische V2-Python-Suite
	PYTHONPATH=backend $(PYTHON) -m pytest backend/sealai_v2 --noconftest -q

lint-v2: ## V2-Python formatieren prüfen und linten
	$(PYTHON) -m ruff format --check backend/sealai_v2 backend/tests
	$(PYTHON) -m ruff check backend/sealai_v2 backend/tests

architecture-v2: ## Import- und Modulgrenzen prüfen
	PYTHONPATH=backend $(PYTHON) -m pytest backend/tests/architecture --noconftest -q

frontend-v2: ## Dashboard: Grenzen, Typen, Tests und Produktionsbuild
	npm --prefix frontend-v2 run verify

verify-v2: lint-v2 architecture-v2 test-v2 frontend-v2 ## Gesamter lokale V2-Freigabenachweis

tree-hash: ## Kanonischen Backend-V2 Release-Hash ausgeben
	/bin/bash -p ops/tree-hash.sh

.PHONY: gate-challenge
gate-challenge: ## OpenAI-Challenger-Bericht zu GATE-10 erzeugen (Cent-Betrag pro Lauf, siehe Ausgabe)
	@OPENAI_API_KEY=$$(grep '^OPENAI_API_KEY=' .env.prod | cut -d= -f2-) python3 ops/gate_challenger.py

test-v1-container: ## Legacy-V1-Pytest im laufenden Container
	docker exec -t -w /app backend python -m pytest -q

bench-v1: ## Legacy-V1-Benchmarks im laufenden Container
	docker exec -t -w /app backend python scripts/run_benchmarks.py
