FROM nginx:1.29.4@sha256:9dd288848f4495869f76676e419ae2d767ca99fece2ec37ec0261f9fdaab5204

# Install Certbot only from a dated Debian snapshot.
RUN set -eux; \
    for file in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources; do \
      [ -f "$file" ] || continue; \
      sed -ri \
        -e 's#https?://deb\.debian\.org/debian#https://snapshot.debian.org/archive/debian/20260714T000000Z#g' \
        -e 's#https?://security\.debian\.org/debian-security#https://snapshot.debian.org/archive/debian-security/20260714T000000Z#g' \
        "$file"; \
    done; \
    grep -Rqs 'snapshot.debian.org/archive/' /etc/apt/sources.list /etc/apt/sources.list.d; \
    printf '%s\n' 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99snapshot; \
    apt-get update; \
    apt-get install -y --no-install-recommends certbot python3-certbot-nginx; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Erstelle das Webroot-Verzeichnis für die Let's Encrypt Challenge
RUN mkdir -p /var/www/certbot

# Stelle sicher, dass Nginx beim Start nicht crasht
CMD ["nginx", "-g", "daemon off;"]
