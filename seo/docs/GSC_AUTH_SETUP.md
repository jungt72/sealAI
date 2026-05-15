# GSC Auth Setup

1. Create or select a Google Cloud project.
2. Enable the Google Search Console API.
3. Preferred future setup: create a service account, download JSON, store it at `/etc/seo/secrets/gsc-service-account.json`, and add the service account email to the GSC property users.
4. Current production setup uses an OAuth desktop client because GSC did not accept the service account email as a property user.
5. Store secrets in `/etc/seo/secrets/seo.env` with `chmod 600`.

Example:

```bash
SEO_DB_PATH=/var/seo/data/seo.db
SEO_REPORT_DIR=/var/seo/reports
SEO_LOG_DIR=/var/seo/logs
GSC_SITE_URL=sc-domain:sealingai.com
GSC_CLIENT_ID=...
GSC_CLIENT_SECRET=...
GSC_REFRESH_TOKEN=...
```

Verify:

```bash
cd /home/thorsten/sealai
PYTHONPATH=seo/src python -m sealai_seo.cli sync-gsc --dry-run
```
