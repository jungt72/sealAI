# Deployment-Notes für optimierte SealAI Prompt-Architektur

## Änderungen
- `prompting.py` durch optimierte Version mit Validierung und Normalisierung ersetzt.
- Neue v2-Templates: `global_system_v2.jinja2`, `material_agent_v2.jinja2`, `explain_v2.jinja2`.
- Backup: `prompting_backup_final.py` und `templates_backup/`.

## Schritte für Live-Gang
1. **Backup prüfen**: Stelle sicher, dass Backups vorhanden sind.
2. **Dependencies**: Installiere fehlende Module (z.B. `pip install langchain-core jinja2`).
3. **Konfiguration**: Lade `.env` mit `SEALAI_TEMPLATE_DIRS`.
4. **Tests**: Führe `python -m pytest test_prompts.py` aus.
5. **Restart**: Starte LangGraph-Services neu.
6. **Monitoring**: Aktiviere Logging; überwache Metriken.

## Rollback
Falls Fehler: `cp prompting_backup_final.py prompting.py` und Templates aus `templates_backup/` wiederherstellen.

## Produktivität
- Prompts sind nun sauber und validiert.
- Reduzierte Halluzinationen durch bessere Templates.
- Bereit für Live-Betrieb!