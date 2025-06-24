# frontend/Dockerfile
# ─────────────────────────────────────────────────────────────
FROM node:18-alpine AS builder
WORKDIR /app

# Basisdateien
COPY package.json tsconfig.json next.config.js postcss.config.js tailwind.config.js ./

# Dependencies (Tailwind v3)
RUN npm install --legacy-peer-deps

# Quellcode
COPY src ./src
COPY public ./public
COPY .env.local .env.local

# Build
RUN npm run build

# ─────────────────────────────────────────────────────────────
FROM node:18-alpine
WORKDIR /app

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npx", "next", "start"]
