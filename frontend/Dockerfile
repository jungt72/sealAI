# =========================================
# SealAI Frontend – Multi-stage Dockerfile
# Next.js (Standalone-Output) + Test-Target
# =========================================

# ---- deps (install once, reused by build/test) ----
FROM node:20-alpine AS deps

WORKDIR /app

# Dependencies only
COPY package.json package-lock.json ./
RUN node -e "const p=require('./package.json'); if(p?.name!=='sealai-frontend'){console.error('ERROR: frontend/Dockerfile must be built with context ./frontend (got package.json name='+String(p?.name)+')'); process.exit(1)}"
# keep dev deps here so test target works
RUN npm ci --include=dev --no-audit --no-fund --legacy-peer-deps


# ---- builder (Next build -> .next/standalone) ----
FROM node:20-alpine AS builder

# IMPORTANT: declare ALL build args that docker-compose passes,
# otherwise they are ignored by Docker and won't reach Next build.
ARG BUILD_ID=dev

ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ARG NEXTAUTH_URL=http://localhost:3000

ARG KEYCLOAK_ISSUER=http://keycloak:8080/realms/sealAI
ARG KEYCLOAK_CLIENT_ID=nextauth

ARG NEXT_PUBLIC_STRAPI_URL=https://sealai.net/strapi
ARG NEXT_PUBLIC_IMAGE_BASE_URL=https://sealai.net/strapi

ARG NEXT_PUBLIC_PARAM_SYNC_DEBUG=0
ARG NEXT_PUBLIC_AUTO_PATCH_PARAMS=0

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    \
    # Build-time public env (baked by Next into client bundles)
    NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_STRAPI_URL=$NEXT_PUBLIC_STRAPI_URL \
    NEXT_PUBLIC_IMAGE_BASE_URL=$NEXT_PUBLIC_IMAGE_BASE_URL \
    NEXT_PUBLIC_PARAM_SYNC_DEBUG=$NEXT_PUBLIC_PARAM_SYNC_DEBUG \
    NEXT_PUBLIC_AUTO_PATCH_PARAMS=$NEXT_PUBLIC_AUTO_PATCH_PARAMS \
    \
    # Server-side env used by Next/Auth routes during build/runtime
    NEXTAUTH_URL=$NEXTAUTH_URL \
    KEYCLOAK_ISSUER=$KEYCLOAK_ISSUER \
    KEYCLOAK_CLIENT_ID=$KEYCLOAK_CLIENT_ID \
    \
    BUILD_ID=$BUILD_ID

WORKDIR /app

# bring deps
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json ./package.json
COPY --from=deps /app/package-lock.json ./package-lock.json

# app code
COPY . .

# stamp build info
RUN printf "%s" "${BUILD_ID}" > /app/BUILD_ID \
  && node -p "require('next/package.json').version" | tee /app/NEXT_VERSION

# Build (expects next.config output: 'standalone')
RUN npm run build


# ---- test (run vitest in a reproducible build target) ----
FROM node:20-alpine AS test

WORKDIR /app
ENV NODE_ENV=development \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY . .

# default command; override in compose if needed
CMD ["npm","run","test:fast"]


# ---- runner (minimal runtime from standalone build) ----
FROM node:20-alpine AS runner

ARG BUILD_ID=dev

ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ARG NEXTAUTH_URL=http://localhost:3000

ARG KEYCLOAK_ISSUER=http://keycloak:8080/realms/sealAI
ARG KEYCLOAK_CLIENT_ID=nextauth

ARG NEXT_PUBLIC_STRAPI_URL=https://sealai.net/strapi
ARG NEXT_PUBLIC_IMAGE_BASE_URL=https://sealai.net/strapi

ARG NEXT_PUBLIC_PARAM_SYNC_DEBUG=0
ARG NEXT_PUBLIC_AUTO_PATCH_PARAMS=0

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    \
    # keep runtime env consistent (server code reads process.env)
    NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_STRAPI_URL=$NEXT_PUBLIC_STRAPI_URL \
    NEXT_PUBLIC_IMAGE_BASE_URL=$NEXT_PUBLIC_IMAGE_BASE_URL \
    NEXT_PUBLIC_PARAM_SYNC_DEBUG=$NEXT_PUBLIC_PARAM_SYNC_DEBUG \
    NEXT_PUBLIC_AUTO_PATCH_PARAMS=$NEXT_PUBLIC_AUTO_PATCH_PARAMS \
    NEXTAUTH_URL=$NEXTAUTH_URL \
    KEYCLOAK_ISSUER=$KEYCLOAK_ISSUER \
    KEYCLOAK_CLIENT_ID=$KEYCLOAK_CLIENT_ID \
    BUILD_ID=$BUILD_ID

LABEL org.opencontainers.image.revision=${BUILD_ID}

WORKDIR /app

# Minimal runtime footprint from Next standalone output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/NEXT_VERSION ./NEXT_VERSION
COPY --from=builder /app/BUILD_ID ./BUILD_ID
COPY --from=builder /app/src ./src
COPY --from=builder /app/next.config.js ./next.config.js
COPY --from=builder /app/middleware.ts ./middleware.ts
COPY --from=builder /app/tsconfig.json ./tsconfig.json
COPY --from=builder /app/postcss.config.js ./postcss.config.js
COPY --from=builder /app/tailwind.config.js ./tailwind.config.js
COPY --from=deps /app/package.json ./package.json
COPY --from=deps /app/package-lock.json ./package-lock.json
COPY --from=deps /app/node_modules ./node_modules

# Non-root user
RUN addgroup -g 10001 -S app && adduser -S app -u 10001 -G app && chown -R app:app /app
USER app

EXPOSE 3000
CMD ["node", "server.js"]
