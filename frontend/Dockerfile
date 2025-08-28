# Multi-stage build that IGNORES any lockfiles and installs with legacy peer deps
FROM node:20-alpine AS builder
WORKDIR /app

# Only copy package.json to avoid bringing in a broken lockfile
COPY package.json ./

# Always install with legacy peer deps to smooth R3F/Drei/React 18
RUN npm config set legacy-peer-deps true \
 && npm install

# Now bring the rest of the app and build
COPY . .
RUN npm run build

# ── Runtime ──────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Reuse node_modules from builder to avoid reinstall
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.js ./next.config.js
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next

EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
