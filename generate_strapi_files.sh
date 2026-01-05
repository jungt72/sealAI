#!/bin/bash

# Base directory
BASE_DIR="/root/sealai/strapi-backend/src/api"

# List of content types
CONTENT_TYPES=("hero" "section" "feature" "next-step" "community-conference")

for type in "${CONTENT_TYPES[@]}"; do
  echo "Generating files for $type..."

  # Create directories
  mkdir -p "$BASE_DIR/$type/controllers"
  mkdir -p "$BASE_DIR/$type/routes"
  mkdir -p "$BASE_DIR/$type/services"

  # Create Controller
  cat <<EOF > "$BASE_DIR/$type/controllers/$type.ts"
/**
 * $type controller
 */

import { factories } from '@strapi/strapi'

// @ts-ignore
export default factories.createCoreController('api::$type.$type');
EOF

  # Create Router
  cat <<EOF > "$BASE_DIR/$type/routes/$type.ts"
/**
 * $type router
 */

import { factories } from '@strapi/strapi';

// @ts-ignore
export default factories.createCoreRouter('api::$type.$type');
EOF

  # Create Service
  cat <<EOF > "$BASE_DIR/$type/services/$type.ts"
/**
 * $type service
 */

import { factories } from '@strapi/strapi';

// @ts-ignore
export default factories.createCoreService('api::$type.$type');
EOF

done

echo "All files generated successfully."
