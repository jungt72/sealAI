.PHONY: test init-db sync-dry-run daily weekly backup restore-smoke

PYTHONPATH ?= src
PYTHON ?= python

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests -q

init-db:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sealai_seo.cli init-db

sync-dry-run:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sealai_seo.cli sync-gsc --dry-run

daily:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sealai_seo.cli report-daily

weekly:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sealai_seo.cli report-weekly

backup:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sealai_seo.cli backup

restore-smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sealai_seo.cli restore-smoke-test
