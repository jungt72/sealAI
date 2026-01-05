FROM nginx:latest

# Installiere Certbot
RUN apt-get update && \
    apt-get install -y certbot python3-certbot-nginx && \
    apt-get clean

# Erstelle das Webroot-Verzeichnis für die Let's Encrypt Challenge
RUN mkdir -p /var/www/certbot

# Stelle sicher, dass Nginx beim Start nicht crasht
CMD ["nginx", "-g", "daemon off;"]
