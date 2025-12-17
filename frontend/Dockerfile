# =========================================
# SealAI Frontend – Production Dockerfile
# Next.js (Standalone-Output)
# =========================================

# ---- Builder ----
FROM node:20-alpine AS builder

ARG BUILD_ID=dev
ARG NEXT_PUBLIC_STRAPI_URL=http://strapi:1337
ARG NEXT_PUBLIC_IMAGE_BASE_URL

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_STRAPI_URL=$NEXT_PUBLIC_STRAPI_URL \
    NEXT_PUBLIC_IMAGE_BASE_URL=${NEXT_PUBLIC_IMAGE_BASE_URL:-$NEXT_PUBLIC_STRAPI_URL}

WORKDIR /app

# 1) Dependencies
COPY package.json package-lock.json ./
RUN node -e "const p=require('./package.json'); if(p?.name!=='sealai-frontend'){console.error('ERROR: frontend/Dockerfile must be built with context ./frontend (got package.json name='+String(p?.name)+')'); process.exit(1)}"
RUN npm ci --include=dev --no-audit --no-fund --legacy-peer-deps
RUN printf "%s" "${BUILD_ID}" > /app/BUILD_ID \
  && node -p "require('next/package.json').version" | tee /app/NEXT_VERSION

# 2) App-Code
COPY . .

# 3) Build (erzeugt .next/standalone dank output:'standalone')
RUN npm run build

# ---- Runner ----
FROM node:20-alpine AS runner

ARG BUILD_ID=dev
ARG NEXT_PUBLIC_STRAPI_URL=http://strapi:1337
ARG NEXT_PUBLIC_IMAGE_BASE_URL

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    BUILD_ID=${BUILD_ID} \
    NEXT_PUBLIC_STRAPI_URL=$NEXT_PUBLIC_STRAPI_URL \
    NEXT_PUBLIC_IMAGE_BASE_URL=${NEXT_PUBLIC_IMAGE_BASE_URL:-$NEXT_PUBLIC_STRAPI_URL}

LABEL org.opencontainers.image.revision=${BUILD_ID}

WORKDIR /app

# Minimaler Runtime-Footprint aus dem Standalone-Build
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/NEXT_VERSION ./NEXT_VERSION
COPY --from=builder /app/BUILD_ID ./BUILD_ID

# Nicht-root User
RUN addgroup -g 10001 -S app && adduser -S app -u 10001 -G app
USER app

EXPOSE 3000

# Der Standalone-Build bringt server.js mit
CMD ["node", "server.js"]
