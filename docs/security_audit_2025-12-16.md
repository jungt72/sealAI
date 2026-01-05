# Security Audit (Forensik) – 2025-12-16

## Ziel
Schneller IOC-/Pattern-Scan im Repo mit harten Excludes (kein Vollscan großer Verzeichnisse).

## Excludes (global)
Verwendete Variable:
`EX="--glob '!.git/**' --glob '!**/node_modules/**' --glob '!**/.next/**' --glob '!**/dist/**' --glob '!**/build/**' --glob '!**/.cache/**' --glob '!**/coverage/**' --glob '!**/tmp/**' --glob '!**/logs/**' --glob '!**/frontend_backup_*/**' --glob '!**/backup*/**' --glob '!**/strapi/**/uploads/**' --glob '!**/.npm-cache/**'"`

Damit ausgeschlossen u.a.: `node_modules/`, `.next/`, `dist/`, `build/`, `.cache/`, `coverage/`, `tmp/`, `logs/`, `frontend_backup_*`, `backup*`, `strapi/**/uploads/`, `.npm-cache/`.

## Treffer (IOC)
IOC-Regex:
`147\.182\.224\.216|94\.154\.35\.154|193\.142\.147\.209|repositorylinux\.publicvm\.com|weball\.sh|linux\.sh|/cox\b|mkfifo\b|nc\s+\S+\s+12323`

- Repo-Scan (`rg ... . | head -n 200`): keine Treffer
- Fokus-Scan (`rg ... backend frontend nginx ops keycloak docs . | head -n 200`): keine Treffer

## Treffer (Suspicious Patterns)
Pattern-Regex:
`curl\s+[^|]*\|\s*sh|wget\s+[^|]*\|\s*sh|\|\s*bash\b|bash\s+-c|sh\s+-c|mkfifo\b|nc\s+|perl\b|python\s+-c|eval\(|new Function\(`

- Repo-Scan (`rg ... . | head -n 200`): keine Treffer
- Fokus-Scan (`rg ... backend frontend nginx ops keycloak docs . | head -n 200`): keine Treffer

## Frontend Install-Scripts (ohne Vollscan)
- `frontend/package.json`: keine `preinstall/install/postinstall/prepare` Scripts (nur `dev/build/start/lint`)
- `frontend/package-lock.json` vorhanden, aber kein Match auf `"preinstall"|"install"|"postinstall"|"prepare"` (per `rg ... | head`)
- `frontend/pnpm-lock.yaml` vorhanden, aber kein Match auf `preinstall|install|postinstall|prepare` (per `rg ... | head`)

## Nächste fokussierte Schritte
- Falls weiterhin Verdacht: nur dann den separaten, hart begrenzten Scan in `frontend/node_modules` ausführen (Step 6 aus dem Runbook).
- Optional: zusätzliche IOCs/Hashes ergänzen (falls aus Incident-Quelle vorhanden) und denselben Exclude-Ansatz wiederverwenden.
