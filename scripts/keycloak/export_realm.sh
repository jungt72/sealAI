#!/bin/bash
set -e

# Parse args
if [[ "$1" == "--stdout" ]]; then
  TO_STDOUT=true
else
  TO_STDOUT=false
fi

# Target directories
EXPORT_DIR="/tmp/realm-export"
TARGET_DIR="$HOME/sealai/docs/ops/keycloak/realm-export"
TARGET_FILE="$TARGET_DIR/sealAI-realm.sanitized.json"

echo "Exporting realm sealAI..." >&2
cd ~/sealai
docker compose exec -T keycloak /opt/keycloak/bin/kc.sh export --dir "$EXPORT_DIR" --realm sealAI --users skip >&2

echo "Sanitizing export..." >&2

sanitize() {
  docker compose exec -T keycloak cat "$EXPORT_DIR/sealAI-realm.json" | \
    jq 'del(
      .. | .secret? ,
      .. | .clientSecret? ,
      .. | .privateKey? ,
      .. | .hashedSecret? ,
      .. | .salt?
    )'
}

if [ "$TO_STDOUT" = true ]; then
  sanitize
else
  mkdir -p "$TARGET_DIR"
  sanitize > "$TARGET_FILE"
  echo "Export saved to $TARGET_FILE" >&2
fi
