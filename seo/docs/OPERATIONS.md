# SEO Operations

Runtime directories:

- `/var/seo/data`
- `/var/seo/reports/daily`
- `/var/seo/reports/weekly`
- `/var/seo/logs`
- `/var/seo/backups`
- `/etc/seo/secrets`

If the SSH user does not have sudo rights, use the fallback runtime paths:

- `/home/thorsten/var/seo/data`
- `/home/thorsten/var/seo/reports`
- `/home/thorsten/var/seo/logs`
- `/home/thorsten/var/seo/backups`
- `/home/thorsten/.sealai/seo.env`

Initialize:

```bash
seo/scripts/init_runtime_dirs.sh
PYTHONPATH=seo/src python -m sealai_seo.cli init-db
```

Manual sync:

```bash
PYTHONPATH=seo/src python -m sealai_seo.cli sync-gsc --date-from 2026-05-02 --date-to 2026-05-02
```

D-1 and D-2 are provisional. D-3 and older are treated as final. Deterministic reports default to final dates.

Backups:

```bash
seo/scripts/backup_sqlite.sh
seo/scripts/restore_smoke_test.sh
```
