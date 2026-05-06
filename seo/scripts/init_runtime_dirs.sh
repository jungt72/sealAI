#!/usr/bin/env bash
set -euo pipefail

sudo install -d -m 755 /var/seo/data /var/seo/reports/daily /var/seo/reports/weekly /var/seo/backups /var/seo/logs
sudo install -d -m 700 /etc/seo/secrets
