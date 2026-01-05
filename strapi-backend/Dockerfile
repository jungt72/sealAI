FROM node:20-alpine

# Build dependencies needed for native modules (e.g. sharp)
RUN apk add --no-cache python3 make g++ vips-dev

WORKDIR /app

COPY package.json package-lock.json* ./

# Install all deps for the build, then prune dev deps afterwards
RUN npm ci

COPY . .

RUN npm run build && npm prune --omit=dev

ENV NODE_ENV=production

# Non-root execution
RUN addgroup -S strapi && adduser -S strapi -G strapi \
  && chown -R strapi:strapi /app
USER strapi

EXPOSE 1337

CMD ["npm","run","start"]
