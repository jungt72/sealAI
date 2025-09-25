# =========================================
# SealAI Frontend – Production Dockerfile
# Next.js 15, Standalone-Output
# =========================================

# ---- Builder ----
FROM node:20-alpine AS builder

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# 1) Dependencies
COPY package.json package-lock.json* ./
# robust gegen veraltete Locks
RUN if [ -f package-lock.json ]; then \
      npm ci --include=dev || (echo "Lockfile out of sync – regenerating" && rm -f package-lock.json && npm install --include=dev); \
    else \
      npm install --include=dev; \
    fi

# 2) App-Code
COPY . .

# 3) Build (erzeugt .next/standalone dank output:'standalone')
RUN npm run build

# ---- Runner ----
FROM node:20-alpine AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# Minimaler Runtime-Footprint aus dem Standalone-Build
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Nicht-root User
RUN addgroup -g 10001 -S app && adduser -S app -u 10001 -G app
USER app

EXPOSE 3000

# Der Standalone-Build bringt server.js mit
CMD ["node", "server.js"]
