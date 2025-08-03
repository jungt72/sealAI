#!/bin/sh
set -e
echo "Warte, bis der Backend-Host erreichbar ist..."
until getent hosts backend; do
  echo "Backend noch nicht bereit – warte 2 Sekunden..."
  sleep 2
done
echo "Backend-Host gefunden, starte nginx!"
exec nginx -g 'daemon off;'
