# Evidence handling for REM-2026-07-14

This directory is intentionally ignored except for this policy marker. Raw host
inventories, command output, and scan reports remain local until they have been
reviewed and sanitized. Versioned evidence belongs in the structured manifests
one directory above and must never contain credentials, private-key data,
authorization material, production environment values, Redis values, or
personal data.

The versioned `../evidence-manifest.json` records only artifact names, record
counts, modes, checksums, and unresolved classification counts. It does not
make the ignored raw metadata suitable for publication or commit.
